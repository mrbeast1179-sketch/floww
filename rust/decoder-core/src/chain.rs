//! Options chain normalization — replaces iterrows() loops in
//! server.py:527, flowseeker.py:211-214, ml_realtime_features.py:80/99.

use serde::{Deserialize, Serialize};

/// One normalized contract. Field names match the Python dict contract
/// consumed by gex_core.compute_gex_by_strike and friends.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Contract {
    pub strike: f64,
    #[serde(rename = "type")]
    pub kind: char, // 'C' | 'P'
    pub oi: f64,
    pub volume: f64,
    pub iv: f64,
    pub delta: f64,
    pub gamma: f64,
}

/// Raw row from upstream (yfinance/cvforge) — NaN-prone.
#[derive(Debug, Clone, Deserialize)]
pub struct RawRow {
    #[serde(default)]
    pub strike: f64,
    #[serde(default, rename = "type")]
    pub kind: String,
    #[serde(default)]
    pub open_interest: Option<f64>,
    #[serde(default)]
    pub volume: Option<f64>,
    #[serde(default)]
    pub implied_volatility: Option<f64>,
    #[serde(default)]
    pub delta: Option<f64>,
    #[serde(default)]
    pub gamma: Option<f64>,
}

impl RawRow {
    /// Normalize one raw row — mirrors the Python NaN-coercion semantics
    /// (NaN → 0, missing → 0) that caused the 2026-08-22 briefing 500.
    pub fn normalize(self) -> Option<Contract> {
        if !(self.strike > 0.0) {
            return None; // mirrors `if strike <= 0: continue` in server.py:533
        }
        let kind = match self.kind.to_uppercase().as_str() {
            "C" | "CALL" => 'C',
            "P" | "PUT" => 'P',
            _ => return None,
        };
        let nz = |v: Option<f64>| match v {
            Some(v) if v.is_finite() && v > 0.0 => v,
            _ => 0.0,
        };
        Some(Contract {
            strike: self.strike,
            kind,
            oi: nz(self.open_interest),
            volume: nz(self.volume),
            iv: nz(self.implied_volatility),
            delta: self.delta.unwrap_or(0.0).finite_or(0.0),
            gamma: self.gamma.unwrap_or(0.0).finite_or(0.0),
        })
    }
}

trait FiniteOr {
    fn finite_or(self, fallback: f64) -> f64;
}
impl FiniteOr for f64 {
    fn finite_or(self, fallback: f64) -> f64 {
        if self.is_finite() {
            self
        } else {
            fallback
        }
    }
}

/// Normalize a batch of raw rows, dropping invalid contracts (parity with
/// the Python `continue` filter).
pub fn normalize_chain(rows: Vec<RawRow>) -> Vec<Contract> {
    rows.into_iter().filter_map(|r| r.normalize()).collect()
}

/// Net GEX by strike (calls positive, puts negative) — parity with
/// gex_core.compute_gex_by_strike. Uses Rust gamma when provided (0 → skip).
pub fn net_gex_by_strike(contracts: &[Contract], spot: f64, gamma_fn: impl Fn(f64, f64, f64, f64) -> f64) -> Vec<(f64, f64)> {
    use std::collections::BTreeMap;
    let mut by_strike: BTreeMap<i64, f64> = BTreeMap::new();
    for c in contracts {
        let gamma = if c.gamma != 0.0 {
            c.gamma
        } else {
            gamma_fn(spot, c.strike, 0.02, c.iv)
        };
        let sign = match c.kind {
            'C' => 1.0,
            _ => -1.0,
        };
        *by_strike.entry(c.strike.to_bits() as i64).or_insert(0.0) += dollar_gamma(gamma, spot, c.oi) * sign;
    }
    by_strike
        .into_iter()
        .map(|(bits, gex)| (f64::from_bits(bits as u64), gex))
        .collect()
}

use crate::greeks::dollar_gamma;
