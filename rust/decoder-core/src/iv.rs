//! Implied-volatility solver — Rust port of
//! `backend/bs_greeks.py::implied_vol_from_price` + batch IV surface build.
//!
//! Parity contract:
//! - Guard: S/K/T/market_price <= 0 → 0.0
//! - Intrinsic-floor guard (market < intrinsic − 1e-8) → 0.0
//! - Brenner initial guess clamped [0.05, 2.0]
//! - Newton-Raphson with bs_vega derivative, tol 1e-6, max 50 iters,
//!   bisection fallback over [1e-4, 5.0]
//! - result rounded to 6 dp

use rayon::prelude::*;

#[inline]
fn norm_pdf(x: f64) -> f64 {
    (-0.5 * x * x).exp() / (2.0 * std::f64::consts::PI).sqrt()
}

/// A&S 26.2.17 normal CDF (same as greeks.rs).
#[inline]
pub fn norm_cdf(x: f64) -> f64 {
    const B0: f64 = 0.2316419;
    const B: [f64; 5] = [0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429];
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let ax = x.abs();
    let t = 1.0 / (1.0 + B0 * ax);
    let poly = t * (B[0] + t * (B[1] + t * (B[2] + t * (B[3] + t * B[4]))));
    let cdf_pos = 1.0 - norm_pdf(x) * poly;
    0.5 * (1.0 + sign * (2.0 * cdf_pos - 1.0))
}

fn d1(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64) -> f64 {
    ((s / k).ln() + (r - q + 0.5 * sigma * sigma) * t) / (sigma * t.sqrt())
}

fn bs_price(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64, is_call: bool) -> f64 {
    if !(s > 0.0 && k > 0.0 && t > 0.0 && sigma > 0.0 && sigma.is_finite()) {
        return 0.0;
    }
    let sq = t.sqrt();
    let d1v = d1(s, k, t, sigma, r, q);
    let d2v = d1v - sigma * sq;
    let disc_q = (-q * t).exp();
    let disc_r = (-r * t).exp();
    let p = if is_call {
        s * disc_q * norm_cdf(d1v) - k * disc_r * norm_cdf(d2v)
    } else {
        k * disc_r * norm_cdf(-d2v) - s * disc_q * norm_cdf(-d1v)
    };
    if p.is_finite() { p } else { 0.0 }
}

fn bs_vega(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64) -> f64 {
    if !(s > 0.0 && k > 0.0 && t > 0.0 && sigma > 0.0) {
        return 0.0;
    }
    s * (-q * t).exp() * norm_pdf(d1(s, k, t, sigma, r, q)) * t.sqrt()
}

/// Intrinsic value for call/put.
#[inline]
fn intrinsic(s: f64, k: f64, is_call: bool) -> f64 {
    if is_call {
        (s - k).max(0.0)
    } else {
        (k - s).max(0.0)
    }
}

/// Solve BS price == market for sigma. Returns 0.0 on guard failures
/// (parity with the Python silent-mask convention).
pub fn implied_vol(
    market_price: f64,
    s: f64,
    k: f64,
    t: f64,
    is_call: bool,
    q: f64,
    r: f64,
    tol: f64,
    max_iter: u32,
) -> f64 {
    if s <= 0.0 || k <= 0.0 || t <= 0.0 || market_price <= 0.0 {
        return 0.0;
    }
    let intr = intrinsic(s, k, is_call);
    if market_price < intr - 1e-8 {
        return 0.0; // below intrinsic — bad input, masked like python _mask_zero
    }

    // Brenner initial guess
    let time_value = (market_price - intr).max(0.01);
    let mut sigma = (time_value / (s * t.sqrt()).max(1e-6) * (2.0 * std::f64::consts::PI).sqrt())
        .clamp(0.05, 2.0);

    // Newton phase with vega derivative; fall back to bisection.
    let mut newton_ok = true;
    for _ in 0..max_iter {
        let price = bs_price(s, k, t, sigma, r, q, is_call);
        let diff = price - market_price;
        if diff.abs() < tol {
            return (sigma * 1e6).round() / 1e6;
        }
        let vega = bs_vega(s, k, t, sigma, r, q);
        if vega <= 0.0 {
            newton_ok = false;
            break;
        }
        sigma -= diff / vega;
        if !(sigma > 0.0) || !sigma.is_finite() {
            newton_ok = false;
            break;
        }
        sigma = sigma.clamp(1e-4, 5.0);
    }
    let _ = newton_ok;

    // Bisection over [1e-4, 5.0] — monotone, guaranteed.
    let mut lo = 1e-4_f64;
    let mut hi = 5.0_f64;
    for _ in 0..100 {
        let mid = (lo + hi) / 2.0;
        let p = bs_price(s, k, t, mid, r, q, is_call);
        if (p - market_price).abs() < tol {
            return (mid * 1e6).round() / 1e6;
        }
        if p < market_price {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    ((lo + hi) / 2.0 * 1e6).round() / 1e6
}

/// Batch IV surface: solve implied vol for N contracts in parallel.
/// Columnar inputs; invalid rows → iv 0.0.
#[allow(clippy::too_many_arguments)]
pub fn implied_vol_surface(
    market_prices: &[f64],
    spots: &[f64],
    strikes: &[f64],
    ts: &[f64],
    kinds: &[bool], // true=call false=put
    qs: &[f64],
    rs: &[f64],
    tol: f64,
    max_iter: u32,
) -> Vec<f64> {
    let n = market_prices.len();
    assert_eq!(n, strikes.len(), "length mismatch");
    assert_eq!(n, ts.len(), "length mismatch");
    assert_eq!(n, kinds.len(), "length mismatch");
    assert_eq!(n, qs.len(), "length mismatch");
    assert_eq!(n, rs.len(), "length mismatch");

    // Small batches: sequential avoids rayon spawn overhead.
    if n < 64 {
        return (0..n)
            .map(|i| {
                implied_vol(market_prices[i], spots[i], strikes[i], ts[i], kinds[i], qs[i], rs[i], tol, max_iter)
            })
            .collect();
    }
    (0..n)
        .into_par_iter()
        .map(|i| {
            implied_vol(market_prices[i], spots[i], strikes[i], ts[i], kinds[i], qs[i], rs[i], tol, max_iter)
        })
        .collect()
}
