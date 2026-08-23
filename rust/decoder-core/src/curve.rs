//! Aggregate GEX curve — Rust port of
//! `backend/services/gex_core.py::calc_aggregate_gex_curve`.
//!
//! Parity contract: same price grid (lo = max(min_strike, spot·0.85),
//! hi = min(max_strike, spot·1.15), 100 steps), same relevance filter
//! (strike within [0.5·lo, 1.5·hi]), same skip rules (oi≤0, T≤0, iv≤0,
//! gamma≤0), same sign convention and /1e9 output scaling.

use crate::greeks::{gamma_scalar};
use rayon::prelude::*;

#[derive(Debug, Clone)]
pub struct CurveContract {
    pub strike: f64,
    pub oi: f64,
    pub iv: f64,
    pub t: f64,
    pub is_call: bool,
}

#[inline]
fn gamma_at(spot: f64, strike: f64, t: f64, iv: f64, q: f64) -> f64 {
    // r=0.05 hardcoded — matches gex_core's call site (bs_gamma default).
    crate::greeks::gamma_scalar(spot, strike, t, iv, 0.05, q)
}

/// Compute the aggregate GEX curve (101 points by default).
/// Returns (price, gex_in_billions) pairs.
pub fn aggregate_gex_curve(
    spot: f64,
    contracts: &[CurveContract],
    div_yield: f64,
) -> Vec<(f64, f64)> {
    if spot <= 0.0 || contracts.is_empty() {
        return vec![];
    }
    let mut strikes: Vec<f64> = contracts.iter().map(|c| c.strike).collect();
    strikes.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    strikes.dedup();
    if strikes.is_empty() {
        return vec![];
    }
    let min_s = strikes[0];
    let max_s = strikes[strikes.len() - 1];
    let lo = min_s.max(spot * 0.85);
    let hi = max_s.min(spot * 1.15);
    let step = (hi - lo) / 100.0;
    if step <= 0.0 {
        return vec![];
    }

    let relevant: Vec<&CurveContract> = contracts
        .iter()
        .filter(|c| {
            c.oi > 0.0 && c.strike >= lo * 0.5 && c.strike <= hi * 1.5
        })
        .collect();

    // Price points are independent → rayon-parallel across the grid.
    (0..=100usize)
        .into_par_iter()
        .map(|i| {
            let price = lo + i as f64 * step;
            let total_gex: f64 = relevant
                .iter()
                .filter(|c| c.t > 0.0 && c.iv > 0.0)
                .map(|c| {
                    let gamma = gamma_scalar(price, c.strike, c.t, c.iv, 0.05, div_yield);
                    if gamma <= 0.0 {
                        return 0.0;
                    }
                    let gex = gamma * c.oi * 100.0 * price * price * 0.01;
                    if c.is_call { gex } else { -gex }
                })
                .sum();
            let rounded_price = (price * 100.0).round() / 100.0;
            let out_gex = if total_gex.is_nan() || total_gex.is_infinite() {
                0.0
            } else {
                (total_gex / 1e9 * 10000.0).round() / 10000.0
            };
            (rounded_price, out_gex)
        })
        .collect()
}
