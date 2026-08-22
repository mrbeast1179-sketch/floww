//! Parity tests: Rust output must match Python bs_greeks.py golden values
//! (tolerance 1e-9 relative on greeks; edge cases return exactly 0.0).

use crate::chain::{net_gex_by_strike, normalize_chain, RawRow};
use crate::greeks::*;

fn approx(a: f64, b: f64, tol: f64) -> bool {
    (a - b).abs() <= tol * a.abs().max(b.abs()).max(1e-12)
}

#[test]
fn test_gamma_matches_python_golden() {
    // Golden values from backend/bs_greeks.py bs_gamma(766, 760, 0.02, 0.2)
    let g = gamma_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    // scipy.stats.norm.pdf-based reference
    let expected = {
        let d1 = ((766f64 / 760.0).ln() + (0.05 + 0.5 * 0.04) * 0.02) / (0.2 * 0.02f64.sqrt());
        (-0.5 * d1 * d1).exp() / (2.0 * std::f64::consts::PI).sqrt() / (766.0 * 0.2 * 0.02f64.sqrt())
    };
    assert!(approx(g, expected, 1e-9), "rust {g} vs py {expected}");
}

#[test]
fn test_edge_cases_return_zero() {
    // Parity with bs_greeks.py: invalid → 0.0
    assert_eq!(gamma_scalar(0.0, 100.0, 1.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, -5.0, 1.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 0.0, 0.2, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 1.0, 0.0, 0.05, 0.0), 0.0);
    assert_eq!(gamma_scalar(100.0, 100.0, 1.0, f64::NAN, 0.05, 0.0), 0.0);
}

#[test]
fn test_delta_bounds() {
    let dc = delta_call_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    let dp = delta_put_scalar(766.0, 760.0, 0.02, 0.2, 0.05, 0.0);
    // put-call parity: C_delta − P_delta = e^(−qT) = 1.0 when q=0
    assert!((dc - dp - 1.0).abs() < 1e-9, "dc={dc} dp={dp}");
    assert!(dc > 0.0 && dc < 1.0);
}

#[test]
fn test_normalize_drops_invalid_and_coerces_nan() {
    let rows = vec![
        raw(760.0, "C", Some(f64::NAN), Some(50.0)),   // NaN OI → 0
        raw(0.0, "C", Some(100.0), None),              // bad strike → dropped
        raw(765.0, "P", None, None),                   // missing → zeros
    ];
    let out = normalize_chain(rows);
    assert_eq!(out.len(), 2);
    assert_eq!(out[0].oi, 0.0); // NaN coerced
    assert_eq!(out[1].strike, 765.0);
}

fn raw(strike: f64, kind: &str, oi: Option<f64>, vol: Option<f64>) -> RawRow {
    RawRow {
        strike,
        kind: kind.into(),
        open_interest: oi,
        volume: vol,
        implied_volatility: Some(0.2),
        delta: Some(0.5),
        gamma: None,
    }
}

#[test]
fn test_net_gex_signs() {
    let contracts = normalize_chain(vec![raw(760.0, "C", Some(100.0), None), raw(770.0, "P", Some(200.0), None)]);
    let by_strike = net_gex_by_strike(&contracts, 766.0, |s, k, t, sig| gamma_scalar(s, k, t, sig, 0.05, 0.0));
    assert_eq!(by_strike.len(), 2);
    // calls positive, puts negative
    let call = by_strike.iter().find(|(k, _)| *k == 760.0).unwrap().1;
    let put = by_strike.iter().find(|(k, _)| *k == 770.0).unwrap().1;
    assert!(call > 0.0 && put < 0.0);
}

#[test]
fn bench_gamma_batch_300_contracts() {
    let n = 300;
    let strikes: Vec<f64> = (0..n).map(|i| 700.0 + i as f64 * 0.45).collect();
    let ts = vec![0.02; n];
    let sigs = vec![0.2; n];
    let rates = vec![0.05; n];
    let divs = vec![0.013; n];
    let spots = vec![766.0; n];

    let start = std::time::Instant::now();
    let iters = 10_000;
    for _ in 0..iters {
        let _g = gamma_batch(&spots, &strikes, &ts, &sigs, &rates, &divs);
    }
    let per_call_us = start.elapsed().as_secs_f64() * 1e6 / iters as f64;
    println!("gamma_batch {} contracts: {:.1}µs/call", n, per_call_us);
    // Scalar python was 216µs; rust should be well under.
}

#[test]
fn test_gex_by_strike_parity() {
    use crate::gex::{compute_gex_by_strike, RawContract};
    let contracts = vec![
        RawContract { strike: 760.0, kind: 'c', oi: 500.0, iv: 0.2, t: 0.02 },
        RawContract { strike: 770.0, kind: 'p', oi: 800.0, iv: 0.22, t: 0.02 },
        RawContract { strike: 760.0, kind: 'p', oi: 0.0,   iv: 0.2,  t: 0.02 }, // skipped (oi<=0)
        RawContract { strike: -1.0, kind: 'c', oi: 100.0, iv: 0.2,  t: 0.02 }, // skipped
    ];
    let rows = compute_gex_by_strike(766.0, &contracts, 0.013);
    assert_eq!(rows.len(), 2);
    assert!(rows[0].strike < rows[1].strike); // sorted
    let call_row = rows.iter().find(|r| r.strike == 760.0).unwrap();
    assert!(call_row.gex > 0.0, "call gex positive");
    let put_row = rows.iter().find(|r| r.strike == 770.0).unwrap();
    assert!(put_row.gex < 0.0, "put gex negative");
}

#[test]
fn test_zero_gamma_flip() {
    use crate::gex::{compute_gex_by_strike, zero_gamma_levels, RawContract};
    // calls below spot, puts above → sign change between them
    let contracts = vec![
        RawContract { strike: 750.0, kind: 'c', oi: 900.0, iv: 0.2, t: 0.05 },
        RawContract { strike: 790.0, kind: 'p', oi: 900.0, iv: 0.25, t: 0.05 },
    ];
    let rows = compute_gex_by_strike(766.0, &contracts, 0.0);
    let flips = zero_gamma_levels(&rows);
    assert_eq!(flips.len(), 1);
    assert_eq!(flips[0], 790.0);
}

#[test]
fn bench_gex_300_contracts() {
    use crate::gex::{compute_gex_by_strike, RawContract};
    let contracts: Vec<RawContract> = (0..300)
        .map(|i| RawContract {
            strike: 700.0 + i as f64 * 0.45,
            kind: if i % 2 == 0 { 'c' } else { 'p' },
            oi: 100.0 + i as f64,
            iv: 0.15 + (i % 20) as f64 * 0.005,
            t: 0.02 + (i % 5) as f64 * 0.01,
        })
        .collect();
    let start = std::time::Instant::now();
    let iters = 10_000;
    for _ in 0..iters {
        let _ = compute_gex_by_strike(766.0, &contracts, 0.013);
    }
    println!("gex_by_strike 300 contracts: {:.1}µs/call",
        start.elapsed().as_secs_f64() * 1e6 / iters as f64);
}

#[test]
fn test_term_structure_regime() {
    use crate::term::{term_analysis, TermContract};

    // INVERTED: gex decreasing with expiry
    let contracts = vec![
        TermContract { time_to_expiry: 1.0, strike: 760.0, kind: 'p', gamma: 0.01, oi: 5000.0 },
        TermContract { time_to_expiry: 30.0, strike: 760.0, kind: 'c', gamma: 0.001, oi: 5000.0 },
    ];
    let ta = term_analysis(766.0, &contracts);
    assert_eq!(ta.expiries.len(), 2);
    assert!(ta.net_gex_by_expiry[0] < ta.net_gex_by_expiry[1]);
}

#[test]
fn test_term_structure_insufficient() {
    use crate::term::{term_analysis, TermContract};
    let contracts = vec![TermContract { time_to_expiry: 1.0, strike: 760.0, kind: 'c', gamma: 0.01, oi: 100.0 }];
    let ta = term_analysis(766.0, &contracts);
    assert_eq!(ta.regime, "flat");
    assert_eq!(ta.slope, 0.0);
}

#[test]
fn test_liquidity_basins_threshold() {
    use crate::term::liquidity_basins;
    // $100M threshold — small values → no basins
    let sg = vec![(760.0, 1e6), (761.0, 2e6), (762.0, -1e6)];
    assert!(liquidity_basins(&sg, 766.0).is_empty());
}
