//! GEX term structure + gamma scallop — Rust port of
//! `backend/services/gex_term_structure.py`.
//!
//! Parity contract: same grouping key (`time_to_expiry`), same GEX formula
//! (γ × OI × 100 × S² × 0.01), same sign convention (CALL +1 / else −1),
//! same regime thresholds (slope_ratio > 0.5), same $100M basin threshold.

use rayon::prelude::*;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Regime {
    Pyramidal,
    Inverted,
    Flat,
}

impl Regime {
    pub fn as_str(&self) -> &'static str {
        match self {
            Regime::Pyramidal => "pyramidal",
            Regime::Inverted => "inverted",
            Regime::Flat => "flat",
        }
    }
}

/// One raw contract row (keys mirrored from the Python dicts).
#[derive(Debug, Clone)]
pub struct TermContract {
    /// Python key `time_to_expiry` (days).
    pub time_to_expiry: f64,
    pub strike: f64,
    pub kind: char, // 'c' | 'p'
    pub gamma: f64,
    pub oi: f64,
}

#[derive(Debug, Clone)]
pub struct ExpiryGex {
    pub expiry: f64,
    pub net_gex: f64,
    /// Sorted (strike, signed gex) pairs.
    pub gex_surface: Vec<(f64, f64)>,
    pub call_oi: f64,
    pub put_oi: f64,
}

#[inline]
fn is_call(kind: char) -> bool {
    kind.to_ascii_lowercase() == 'c'
}

#[inline]
fn contract_gex(gamma: f64, oi: f64, spot: f64) -> f64 {
    gamma * oi * 100.0 * spot * spot * 0.01
}

/// Group by expiry, net GEX per expiry — parity with the Python grouping.
/// Parallel across expiries; deterministic BTreeMap ordering.
pub fn expiry_gex_list(spot: f64, contracts: &[TermContract]) -> Vec<ExpiryGex> {
    let mut keys: BTreeMap<u64, ()> = BTreeMap::new();
    for c in contracts {
        if c.time_to_expiry.is_finite() {
            keys.insert(c.time_to_expiry.to_bits(), ());
        }
    }
    let expiry_bits: Vec<u64> = keys.into_keys().collect();

    expiry_bits
        .into_par_iter()
        .map(|eb| {
            let mut strike_gex: BTreeMap<u64, f64> = BTreeMap::new();
            let mut call_oi = 0.0;
            let mut put_oi = 0.0;
            for c in contracts {
                if c.time_to_expiry.to_bits() != eb || !c.strike.is_finite() {
                    continue;
                }
                let sign = if is_call(c.kind) { 1.0 } else { -1.0 };
                *strike_gex.entry(c.strike.to_bits()).or_insert(0.0) +=
                    sign * contract_gex(c.gamma, c.oi, spot);
                if is_call(c.kind) {
                    call_oi += c.oi;
                } else {
                    put_oi += c.oi;
                }
            }
            let surface: Vec<(f64, f64)> = strike_gex
                .iter()
                .map(|(b, g)| (f64::from_bits(*b), *g))
                .collect();
            ExpiryGex {
                expiry: f64::from_bits(eb),
                net_gex: surface.iter().map(|(_, g)| *g).sum(),
                gex_surface: surface,
                call_oi,
                put_oi,
            }
        })
        .collect()
}

fn linreg_slope(xs: &[f64], ys: &[f64]) -> f64 {
    let n = xs.len() as f64;
    if xs.len() < 2 {
        return 0.0;
    }
    let sx: f64 = xs.iter().sum();
    let sy: f64 = ys.iter().sum();
    let sxx: f64 = xs.iter().map(|x| x * x).sum();
    let sxy: f64 = xs.iter().zip(ys).map(|(x, y)| x * y).sum();
    let denom = n * sxx - sx * sx;
    if denom.abs() < 1e-300 {
        return 0.0;
    }
    (n * sxy - sx * sy) / denom
}

fn stdev(v: &[f64]) -> f64 {
    let n = v.len() as f64;
    if v.len() < 2 {
        return 0.0;
    }
    let mean = v.iter().sum::<f64>() / n;
    (v.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n - 1.0)).sqrt()
}

pub struct TermAnalysis {
    pub regime: &'static str,
    pub interpretation: &'static str,
    pub expiries: Vec<f64>,
    pub net_gex_by_expiry: Vec<f64>,
    pub slope: f64,
    pub calendar_spread_impact: f64,
    pub slope_ratio: f64,
}

/// Parity with compute_gex_term_structure's analysis fields.
pub fn term_analysis(spot: f64, contracts: &[TermContract]) -> TermAnalysis {
    let list = expiry_gex_list(spot, contracts);
    let expiries: Vec<f64> = list.iter().map(|e| e.expiry).collect();
    let gex_values: Vec<f64> = list.iter().map(|e| e.net_gex).collect();

    if list.len() < 2 {
        return TermAnalysis {
            regime: "flat",
            interpretation: "Insufficient data for term structure analysis.",
            expiries,
            net_gex_by_expiry: gex_values,
            slope: 0.0,
            calendar_spread_impact: 0.0,
            slope_ratio: 0.0,
        };
    }

    let slope = linreg_slope(&expiries, &gex_values);
    let slope_ratio = slope.abs() / (stdev(&gex_values) + 1e-10);

    let (regime, interpretation) = if slope_ratio > 0.5 {
        if slope > 0.0 {
            (
                "pyramidal",
                "PYRAMIDAL term structure: GEX increases with time to expiry. Dealers are providing liquidity across the curve. This is typically a stabilizing environment.",
            )
        } else {
            (
                "inverted",
                "INVERTED term structure: GEX decreases with time to expiry. Shorter-dated options show more negative gamma. Potential for short-gamma cascade if short-dated positions are sold.",
            )
        }
    } else {
        (
            "flat",
            "FLAT term structure: GEX relatively uniform across expiries. Balanced dealer positioning across time horizons.",
        )
    };

    let calendar_spread_impact = list.last().map(|e| e.net_gex).unwrap_or(0.0)
        - list.first().map(|e| e.net_gex).unwrap_or(0.0);

    TermAnalysis {
        regime,
        interpretation,
        expiries,
        net_gex_by_expiry: gex_values,
        slope,
        calendar_spread_impact,
        slope_ratio,
    }
}

/// Liquidity basins — parity with analyze_liquidity_basins ($100M threshold,
/// adaptive window max(5, n/10), top 5 by |gex|).
pub fn liquidity_basins(
    strike_gex: &[(f64, f64)],
    spot: f64,
) -> Vec<std::collections::HashMap<&'static str, f64>> {
    let mut sorted = strike_gex.to_vec();
    sorted.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(std::cmp::Ordering::Equal));
    if sorted.len() < 3 {
        return vec![];
    }
    let window_size = (sorted.len() / 10).max(5);
    let mut basins: Vec<(f64, std::collections::HashMap<&'static str, f64>)> = Vec::new();

    for i in 0..sorted.len() {
        let lo = i.saturating_sub(window_size);
        let hi = (i + window_size + 1).min(sorted.len());
        let win = &sorted[lo..hi];
        if win.is_empty() {
            continue;
        }
        let total_gex: f64 = win.iter().map(|(_, g)| g).sum();
        let avg_strike = win.iter().map(|(s, _)| s).sum::<f64>() / win.len() as f64;
        if total_gex.abs() > 1e8 {
            let mut b = std::collections::HashMap::new();
            b.insert("strike", avg_strike);
            b.insert("net_gex", total_gex);
            b.insert("distance_from_spot", avg_strike - spot);
            b.insert("width", win.last().unwrap().0 - win.first().unwrap().0);
            basins.push((total_gex, b));
        }
    }
    basins.sort_by(|a, b| b.0.abs().partial_cmp(&a.0.abs()).unwrap_or(std::cmp::Ordering::Equal));
    basins.into_iter().map(|(_, b)| b).take(5).collect()
}
