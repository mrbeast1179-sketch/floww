//! VPIN batch classification + rolling computation — Rust port of
//! `backend/services/vpin_engine.py::classify_volume` and the bucket/VPIN math.
//!
//! Parity contract (vs classify_volume):
//! - sigma = population std of price_changes (ddof=0, like np.std)
//! - sigma <= 0 or NaN → fallback: mean_abs>0 ? mean_abs : 50/50 split
//! - buy = V * Phi(dP / (sigma*sqrt(dt))), sell = V − buy
//!
//! The stateful per-trade engine stays in Python (it owns Mongo/prometheus
//! side effects); this covers the CPU-heavy batch path.

/// Population standard deviation (np.std parity).
fn pop_std(xs: &[f64]) -> f64 {
    let n = xs.len() as f64;
    if xs.is_empty() {
        return 0.0;
    }
    let mean = xs.iter().sum::<f64>() / n;
    (xs.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / n).sqrt()
}

#[inline]
fn norm_cdf(x: f64) -> f64 {
    // A&S 26.2.17 (Zelen-Severo) — ~1e-7 abs accuracy; matches math.erf-based
    // Python within float noise for greek parity at typical |z| < 4.
    const B0: f64 = 0.2316419;
    const B: [f64; 5] = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let ax = x.abs();
    let t = 1.0 / (1.0 + B0 * ax);
    let poly = t * (B[0] + t * (B[1] + t * (B[2] + t * (B[3] + t * B[4]))));
    let cdf_pos = 1.0 - norm_pdf(x) * poly;
    0.5 * (1.0 + sign * (2.0 * cdf_pos - 1.0))
}

#[inline]
fn norm_pdf(x: f64) -> f64 {
    (-0.5 * x * x).exp() / (2.0 * std::f64::consts::PI).sqrt()
}

pub struct ClassifiedVolumes {
    pub buy: Vec<f64>,
    pub sell: Vec<f64>,
}

/// Bulk Volume Classification over a trade sequence — drop-in replacement
/// for `VpinEngine.classify_volume`.
pub fn classify_volume(
    price_changes: &[f64],
    volumes: &[f64],
    dt: f64,
) -> Result<ClassifiedVolumes, String> {
    if price_changes.len() != volumes.len() {
        return Err("price_changes and volumes must have the same shape".into());
    }
    if dt <= 0.0 {
        return Err("dt must be positive".into());
    }

    let sigma = pop_std(price_changes);
    let eff_sigma = if !(sigma > 0.0) || sigma.is_nan() {
        // parity fallback: mean absolute change; if that's also 0 → 50/50
        let mean_abs = price_changes.iter().map(|x| x.abs()).sum::<f64>() / price_changes.len() as f64;
        if !(mean_abs > 0.0) {
            let half_buy: Vec<f64> = volumes.iter().map(|v| v * 0.5).collect();
            let half_sell: Vec<f64> = volumes.iter().map(|v| v * 0.5).collect();
            return Ok(ClassifiedVolumes { buy: half_buy, sell: half_sell });
        }
        mean_abs
    } else {
        sigma
    };

    let sqrt_dt = dt.sqrt();
    let mut buy = Vec::with_capacity(volumes.len());
    let mut sell = Vec::with_capacity(volumes.len());
    for i in 0..volumes.len() {
        let z = price_changes[i] / (eff_sigma * sqrt_dt);
        let b = volumes[i] * norm_cdf(z);
        buy.push(b);
        sell.push(volumes[i] - b);
    }
    Ok(ClassifiedVolumes { buy, sell })
}

/// Rolling VPIN over finalized buckets: sum(|B−S|)/sum(V).
/// Parity with VpinEngine._recompute_vpin.
pub fn vpin_from_buckets(buy: &[f64], sell: &[f64], total: &[f64]) -> f64 {
    if buy.is_empty() {
        return 0.0;
    }
    let total_vol: f64 = total.iter().sum();
    if total_vol <= 0.0 {
        return 0.0;
    }
    let imbalance: f64 = buy
        .iter()
        .zip(sell.iter())
        .map(|(b, s)| (b - s).abs())
        .sum();
    imbalance / total_vol
}

// ── Batch ingestion: whole trade stream → buckets + VPIN series ─────────

pub struct BucketOut {
    pub bucket_id: u64,
    pub start_time: f64,
    pub end_time: f64,
    pub total_volume: f64,
    pub buy_volume: f64,
    pub sell_volume: f64,
}

/// Ingest a full trade stream through the volume clock. Parity with the
/// VpinEngine.update() loop:
/// - volume<=0 trades skipped
/// - sigma<=0/NaN/Inf → buy_frac 0.5
/// - bucket finalizes when accumulated total >= bucket_size
/// - rolling VPIN over last `window` finalized buckets
///
/// Returns (finalized buckets, vpin after each finalization).
pub fn ingest_batch(
    price_changes: &[f64],
    volumes: &[f64],
    timestamps: &[f64],
    sigmas: &[f64],
    dt: f64,
    bucket_size: f64,
    window: usize,
) -> Result<(Vec<BucketOut>, Vec<f64>), String> {
    if volumes.len() != price_changes.len()
        || volumes.len() != timestamps.len()
        || volumes.len() != sigmas.len()
    {
        return Err("input arrays must have equal length".into());
    }
    if bucket_size <= 0.0 {
        return Err("bucket_size must be positive".into());
    }
    if window == 0 {
        return Err("window must be positive".into());
    }

    let sqrt_dt = dt.sqrt();
    let mut buckets_out: Vec<BucketOut> = Vec::new();
    // rolling windows (bounded)
    let mut wb: std::collections::VecDeque<f64> = std::collections::VecDeque::with_capacity(window);
    let mut ws: std::collections::VecDeque<f64> = std::collections::VecDeque::with_capacity(window);
    let mut wt: std::collections::VecDeque<f64> = std::collections::VecDeque::with_capacity(window);
    let mut vpins: Vec<f64> = Vec::new();

    let mut acc_buy = 0.0;
    let mut acc_sell = 0.0;
    let mut acc_total = 0.0;
    let mut start_time: Option<f64> = None;
    let mut end_time = 0.0;

    for i in 0..volumes.len() {
        let vol = volumes[i];
        if vol <= 0.0 {
            continue;
        }
        let pc = price_changes[i];
        let ts = timestamps[i];
        let sigma = sigmas[i];
        let buy_frac = if !(sigma > 0.0) || sigma.is_nan() || sigma.is_infinite() {
            0.5
        } else {
            norm_cdf(pc / (sigma * sqrt_dt))
        };
        let bvol = vol * buy_frac;
        acc_buy += bvol;
        acc_sell += vol - bvol;
        acc_total += vol;
        if start_time.is_none() {
            start_time = Some(ts);
        }
        end_time = ts;

        if acc_total >= bucket_size {
            let (b, s) = (acc_buy, acc_sell);
            wb.push_back(b);
            ws.push_back(s);
            wt.push_back(acc_total);
            if wb.len() > window {
                wb.pop_front();
                ws.pop_front();
                wt.pop_front();
            }
            buckets_out.push(BucketOut {
                bucket_id: buckets_out.len() as u64,
                start_time: start_time.unwrap_or(ts),
                end_time: ts,
                total_volume: acc_total,
                buy_volume: b,
                sell_volume: s,
            });

            // recompute vpin over window
            let total_vol: f64 = wt.iter().sum();
            let vpin = if total_vol > 0.0 {
                wb.iter().zip(ws.iter()).map(|(b2, s2)| (b2 - s2).abs()).sum::<f64>() / total_vol
            } else {
                0.0
            };
            vpins.push(vpin);

            acc_buy = 0.0;
            acc_sell = 0.0;
            acc_total = 0.0;
            start_time = None;
            end_time = 0.0;
        }
    }
    let _ = end_time;
    Ok((buckets_out, vpins))
}
