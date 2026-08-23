//! Realized-volatility estimators — Rust port of the five estimators in
//! `backend/services/realized_volatility.py` (close-to-close, Parkinson,
//! Garman-Klass, Rogers-Satchell, Yang-Zhang).
//!
//! Parity contract: same constants, same ddof semantics (sample ddof=1 for
//! CC/overnight/intraday variance; population mean for RS/GK/Parkinson),
//! same minimum-bar rules, negative-variance clamp to 0 for YZ.

use rayon::prelude::*;

pub const MIN_BARS_FOR_YZ: usize = 3;
pub const MIN_BARS_FOR_OTHER: usize = 2;
pub const PARKINSON_LN2_FACTOR: f64 = 4.0 * std::f64::consts::LN_2;
pub const GK_INTRADAY_BIAS: f64 = 2.0 * std::f64::consts::LN_2 - 1.0;
pub const YZ_K_NUMERATOR: f64 = 0.34;
pub const YZ_K_DENOMINATOR_BIAS: f64 = 1.34;

/// One OHLC + prev_close bar. NaN fields are treated as invalid (the
/// Python side pre-filters with _safe_positive_float).
#[derive(Debug, Clone, Copy)]
pub struct Bar {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    /// NaN when unavailable.
    pub prev_close: f64,
}

#[inline]
fn valid_bar(b: &Bar) -> bool {
    [b.open, b.high, b.low, b.close]
        .iter()
        .all(|v| v.is_finite() && *v > 0.0)
}

/// Sample variance (ddof=1). Returns None when n < 2.
fn sample_var(xs: &[f64]) -> Option<f64> {
    let n = xs.len();
    if n < 2 {
        return None;
    }
    let mean = xs.iter().sum::<f64>() / n as f64;
    Some(xs.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n - 1) as f64)
}

/// Close-to-close: sample std of log returns × √annual.
pub fn close_to_close(bars: &[Bar], annual_factor: f64) -> Option<f64> {
    let closes: Vec<f64> = bars.iter().filter(|b| valid_bar(b)).map(|b| b.close).collect();
    if closes.len() < 2 {
        return None;
    }
    let rets: Vec<f64> = (1..closes.len())
        .map(|i| (closes[i] / closes[i - 1]).ln())
        .collect();
    let var = sample_var(&rets)?;
    Some(var.sqrt() * annual_factor.sqrt())
}

/// Parkinson: high/low log range.
pub fn parkinson(bars: &[Bar], annual_factor: f64) -> Option<f64> {
    let pairs: Vec<(f64, f64)> = bars
        .iter()
        .filter(|b| valid_bar(b))
        .map(|b| (b.high, b.low))
        .collect();
    if pairs.len() < MIN_BARS_FOR_OTHER {
        return None;
    }
    let sum_sq: f64 = pairs.iter().map(|(h, l)| (h / l).ln().powi(2)).sum();
    let var = sum_sq / (PARKINSON_LN2_FACTOR * pairs.len() as f64);
    Some((var * annual_factor).sqrt())
}

/// Garman-Klass: drift-corrected OHLC.
pub fn garman_klass(bars: &[Bar], annual_factor: f64) -> Option<f64> {
    let valid: Vec<&Bar> = bars.iter().filter(|b| valid_bar(b)).collect();
    if valid.len() < MIN_BARS_FOR_OTHER {
        return None;
    }
    let terms: f64 = valid
        .iter()
        .map(|b| {
            0.5 * (b.high / b.low).ln().powi(2) - GK_INTRADAY_BIAS * (b.close / b.open).ln().powi(2)
        })
        .sum();
    let var = terms / valid.len() as f64;
    Some((var * annual_factor).sqrt())
}

#[inline]
fn rs_term(b: &Bar) -> f64 {
    let log_hc = (b.high / b.close).ln();
    let log_ho = (b.high / b.open).ln();
    let log_lc = (b.low / b.close).ln();
    let log_lo = (b.low / b.open).ln();
    log_hc * log_ho + log_lc * log_lo
}

/// Rogers-Satchell: drift-independent OHLC.
pub fn rogers_satchell(bars: &[Bar], annual_factor: f64) -> Option<f64> {
    let valid: Vec<&Bar> = bars.iter().filter(|b| valid_bar(b)).collect();
    if valid.len() < MIN_BARS_FOR_OTHER {
        return None;
    }
    let terms: f64 = valid.iter().map(|b| rs_term(b)).sum();
    let var = terms / valid.len() as f64;
    Some((var * annual_factor).sqrt())
}

/// Yang-Zhang: overnight + k·intraday + (1−k)·RS. Needs prev_close per bar.
pub fn yang_zhang(bars: &[Bar], annual_factor: f64) -> Option<f64> {
    let valid: Vec<(Bar, f64)> = bars
        .iter()
        .filter(|b| valid_bar(b) && b.prev_close.is_finite() && b.prev_close > 0.0)
        .map(|b| (*b, b.prev_close))
        .collect();
    if valid.len() < MIN_BARS_FOR_YZ {
        return None;
    }

    let log_overnight: Vec<f64> = valid.iter().map(|(b, pc)| (b.open / pc).ln()).collect();
    let sigma_overnight_sq = sample_var(&log_overnight)?;

    let log_intraday: Vec<f64> = valid.iter().map(|(b, _)| (b.close / b.open).ln()).collect();
    let sigma_intraday_sq = sample_var(&log_intraday)?;

    let sigma_rs_sq = valid.iter().map(|(b, _)| rs_term(b)).sum::<f64>() / valid.len() as f64;

    let n = valid.len() as f64;
    let k = YZ_K_NUMERATOR / (YZ_K_DENOMINATOR_BIAS + (n + 1.0) / (n - 1.0));
    let var = sigma_overnight_sq + k * sigma_intraday_sq + (1.0 - k) * sigma_rs_sq;
    if var < 0.0 {
        return Some(0.0); // parity: python clamps to 0
    }
    Some((var * annual_factor).sqrt())
}

/// All five estimators at once — parallel where it matters, single pass
/// over the bars per estimator. `None` = insufficient bars (parity).
#[allow(clippy::too_many_arguments)]
pub fn realized_vol_all(
    bars: &[Bar],
    annual_factor: f64,
) -> [Option<f64>; 5] {
    // Sequential is faster than rayon for typical bar counts (<1k); the five
    // estimators share filtered passes so keep them ordered cheap→expensive.
    [
        close_to_close(bars, annual_factor),
        parkinson(bars, annual_factor),
        garman_klass(bars, annual_factor),
        rogers_satchell(bars, annual_factor),
        yang_zhang(bars, annual_factor),
    ]
}
