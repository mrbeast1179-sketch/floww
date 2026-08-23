//! Risk-neutral probability distribution — Rust port of
//! `backend/services/gex_core.py::calc_probability_distribution`.
//!
//! Parity contract: per-strike, first call (else put) supplies iv/T;
//! prob_above = N(d2), delta = N(d1); rounded to 4dp; invalid skipped.

use crate::greeks::norm_cdf;
use rayon::prelude::*;

#[derive(Debug, Clone)]
pub struct ProbRow {
    pub strike: f64,
    pub prob_above: f64,
    pub prob_below: f64,
    pub delta: f64,
    pub iv: f64,
}

/// Columnar input. `kinds`: true=call, false=put.
/// Contracts with iv≤0 or T≤0 are skipped (parity with python continue).
pub fn probability_distribution(
    spot: f64,
    strikes: &[f64],
    kinds: &[bool],
    ivs: &[f64],
    ts: &[f64],
    risk_free_rate: f64,
) -> Vec<ProbRow> {
    if spot <= 0.0 || strikes.is_empty() {
        return vec![];
    }

    // Group by strike: pick first call's iv/T, else first put's
    let mut by_strike: std::collections::BTreeMap<u64, (Option<f64>, Option<f64>, Option<bool>)> =
        std::collections::BTreeMap::new();
    for i in 0..strikes.len() {
        let k = strikes[i];
        if !k.is_finite() || k <= 0.0 {
            continue;
        }
        let entry = by_strike.entry(k.to_bits()).or_insert((None, None, None));
        if kinds[i] && entry.0.is_none() {
            entry.0 = Some(ivs[i]);
            entry.1 = Some(ts[i]);
        } else if !kinds[i] && entry.0.is_none() {
            entry.0 = Some(ivs[i]);
            entry.1 = Some(ts[i]);
            entry.2 = Some(false);
        }
    }

    by_strike
        .par_iter()
        .filter_map(|(&kb, &(iv, t, _))| {
            let k = f64::from_bits(kb);
            let iv = iv?;
            let t = t?;
            if iv <= 0.0 || t <= 0.0 {
                return None;
            }
            let sq_t = t.sqrt();
            let d1 = ((spot / k).ln() + (risk_free_rate + 0.5 * iv * iv) * t) / (iv * sq_t);
            let d2 = d1 - iv * sq_t;
            let prob_above = norm_cdf(d2);
            let r4 = |x: f64| (x * 10000.0).round() / 10000.0;
            Some(ProbRow {
                strike: k,
                prob_above: r4(prob_above),
                prob_below: r4(1.0 - prob_above),
                delta: r4(norm_cdf(d1)),
                iv: r4(iv),
            })
        })
        .collect()
}
