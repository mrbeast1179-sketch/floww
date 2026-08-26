//! 2D GEX grid (strike × expiry heatmap) — Rust port of
//! `backend/services/gex_core.py::compute_gex_grid`.
//!
//! Parity contract: same filters (oi≤0, iv≤0, T≤0, strike≤0, no-expiry,
//! gamma≤0 skipped), same dollar conventions, same sign convention,
//! same output structure (expiries sorted, strikes sorted, strike-key
//! stringification int-if-integral).

use crate::greeks::{gamma_scalar};
use rayon::prelude::*;
use std::collections::BTreeMap;

/// Columnar input; returns (expiries, strikes, grid, charm_grid, vex_grid,
/// strike_totals) as parallel structures. Keys are (expiry, strike).
pub struct GridOut {
    pub expiries: Vec<String>,
    pub strikes: Vec<f64>,
    /// (expiry_idx, strike_idx) → gex cell
    pub cells: Vec<((usize, usize), f64, f64, f64)>, // idx → (gex, charm, vex)
    pub strike_totals: Vec<(f64, f64)>,
}

#[inline]
fn norm_pdf(x: f64) -> f64 {
    (-0.5 * x * x).exp() / (2.0 * std::f64::consts::PI).sqrt()
}

fn bs_charm_scalar(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64, is_call: bool) -> f64 {
    if !(s > 0.0 && k > 0.0 && t > 0.0 && sigma > 0.0) {
        return 0.0;
    }
    let sq = t.sqrt();
    let d1v = ((s / k).ln() + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sq);
    let d2v = d1v - sigma * sq;
    let pdf_d1 = norm_pdf(d1v);
    let cdf_d1 = crate::greeks::norm_cdf(d1v);
    let term = pdf_d1 * (2.0 * (r - q) * t - d2v * sigma * sq) / (2.0 * t * sigma * sq);
    let c = if is_call {
        (-q * t).exp() * (q * cdf_d1 - term)
    } else {
        (-q * t).exp() * (-q * (1.0 - cdf_d1) - term)
    };
    if c.is_finite() { c } else { 0.0 }
}

fn bs_vanna_scalar(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64) -> f64 {
    if !(s > 0.0 && k > 0.0 && t > 0.0 && sigma > 0.0) {
        return 0.0;
    }
    let sq = t.sqrt();
    let d1v = ((s / k).ln() + (r - q + 0.5 * sigma * sigma) * t) / (sigma * sq);
    let d2v = d1v - sigma * sq;
    let v = -(-q * t).exp() * norm_pdf(d1v) * d2v / sigma;
    if v.is_finite() { v } else { 0.0 }
}

struct Cell {
    expiry_idx: usize,
    strike_bits: u64,
    gex: f64,
    charm: f64,
    vex: f64,
}

/// Compute the 2D grid. Returns structured data for Python-side dict assembly.
/// `div_yield` from DIV_YIELD table; r=0.05 hardcoded like the python call site.
pub fn compute_gex_grid(
    spot: f64,
    strikes_in: &[f64],
    ts: &[f64],
    ois: &[f64],
    ivs: &[f64],
    kinds: &[bool], // true = call
    expiries: &[String],
    div_yield: f64,
    weight_volume: bool,
) -> Option<GridOut> {
    if spot <= 0.0 || strikes_in.is_empty() {
        return None;
    }

    // Per-contract compute in parallel (pure math)
    let computed: Vec<Option<Cell>> = (0..strikes_in.len())
        .into_par_iter()
        .map(|i| {
            let oi = ois[i];
            let iv = ivs[i];
            let t = ts[i];
            let strike = strikes_in[i];
            if oi <= 0.0 || iv <= 0.0 || t <= 0.0 || strike <= 0.0 || !strike.is_finite() {
                return None;
            }
            if expiries[i].is_empty() {
                return None;
            }
            let is_call = kinds[i];
            let gamma = gamma_scalar(spot, strike, t, iv, 0.05, div_yield);
            if gamma <= 0.0 {
                return None;
            }
            let charm = bs_charm_scalar(spot, strike, t, iv, 0.05, div_yield, is_call);
            let vanna = bs_vanna_scalar(spot, strike, t, iv, 0.05, div_yield);
            // Two weighting modes (parity with gex_core.compute_gex_grid and
            // gex_core.compute_gex_grid_volume):
            //   OI mode:     gex = gamma*w*100*spot^2*0.01 ; charm/vex signed
            //   volume mode: gex = gamma*w*spot*100      ; charm/vex abs()*sign
            let (gex_unit, charm_unit, vex_unit) = if weight_volume {
                (
                    gamma * oi * spot * 100.0,
                    charm.abs() * oi * spot * 100.0,
                    vanna.abs() * oi * spot * 100.0,
                )
            } else {
                (
                    gamma * oi * 100.0 * spot * spot * 0.01,
                    charm * oi * 100.0 * spot * 0.01,
                    vanna * oi * 100.0 * spot * 0.01,
                )
            };
            let sign = if is_call { 1.0 } else { -1.0 };
            Some(Cell {
                expiry_idx: 0, // filled below by grouping
                strike_bits: strike.to_bits(),
                gex: sign * gex_unit,
                charm: sign * charm_unit,
                vex: sign * vex_unit,
            })
        })
        .collect();

    // Group valid contracts by expiry string → index
    let mut expiry_order: Vec<String> = vec![];
    let mut expiry_idx_map: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    let mut valid: Vec<(usize, u64, f64, f64, f64)> = vec![]; // (expiry_idx, strike_bits, gex, charm, vex)
    let mut strike_totals: BTreeMap<u64, f64> = BTreeMap::new();

    let mut vi = 0usize;
    for (i, cell_opt) in computed.into_iter().enumerate() {
        if let Some(mut c) = cell_opt {
            let key = expiries[i].as_str();
            let idx = match expiry_idx_map.get(key) {
                Some(&ix) => ix,
                None => {
                    expiry_order.push(expiries[i].clone());
                    let ix = expiry_order.len() - 1;
                    expiry_idx_map.insert(key, ix);
                    ix
                }
            };
            c.expiry_idx = idx;
            *strike_totals.entry(c.strike_bits).or_insert(0.0) += c.gex;
            valid.push((idx, c.strike_bits, c.gex, c.charm, c.vex));
        }
        let _ = &mut vi;
        vi += 0;
    }

    // Collect distinct strikes sorted
    let mut strike_set: Vec<u64> = strike_totals.keys().cloned().collect();
    strike_set.sort();
    let strikes_out: Vec<f64> = strike_set.iter().map(|b| f64::from_bits(*b)).collect();
    let mut strike_idx: std::collections::HashMap<u64, usize> = std::collections::HashMap::new();
    for (i, s) in strikes_out.iter().enumerate() {
        strike_idx.insert(s.to_bits(), i);
    }

    let cells = valid
        .into_iter()
        .map(|(e, sb, gex, charm, vex)| {
            (
                (e, *strike_idx.get(&sb).unwrap_or(&0)),
                gex, charm, vex,
            )
        })
        .collect();

    let strike_totals_list: Vec<(f64, f64)> = strike_totals
        .iter()
        .map(|(b, g)| (f64::from_bits(*b), *g))
        .collect();

    Some(GridOut {
        expiries: expiry_order,
        strikes: strikes_out,
        cells,
        strike_totals: strike_totals_list,
    })
}
