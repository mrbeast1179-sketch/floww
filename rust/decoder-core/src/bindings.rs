//! PyO3 0.22 bindings — expose decoder-core to the FastAPI backend.
//!
//! Uses Bound<'_, T> API throughout (PyO3 ≥ 0.21 style).

use crate::gex::{self, RawContract, StrikeRow};
use crate::greeks;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use rayon::prelude::*;

/// bs_gamma(S, K, T, sigma, r=0.05, q=0.0) — parity with backend/bs_greeks.py
#[pyfunction]
#[pyo3(signature = (s, k, t, sigma, r=0.05, q=0.0))]
fn bs_gamma(s: f64, k: f64, t: f64, sigma: f64, r: f64, q: f64) -> f64 {
    greeks::gamma_scalar(s, k, t, sigma, r, q)
}

/// Batch gamma over parallel slices at one spot. Parallel via rayon.
#[pyfunction]
#[pyo3(signature = (spot, strikes, ts, sigmas, r=0.05, q=0.0))]
fn gamma_batch(
    spot: f64,
    strikes: Vec<f64>,
    ts: Vec<f64>,
    sigmas: Vec<f64>,
    r: f64,
    q: f64,
) -> PyResult<Vec<f64>> {
    if strikes.len() != ts.len() || strikes.len() != sigmas.len() {
        return Err(PyValueError::new_err("strikes/ts/sigmas length mismatch"));
    }
    let n = strikes.len();
    // Rayon spawn overhead dominates small batches (~65µs at n=300 vs ~15µs
    // sequential). Dispatch: sequential under 64, parallel above.
    if n < 64 {
        return Ok((0..n)
            .map(|i| greeks::gamma_scalar(spot, strikes[i], ts[i], sigmas[i], r, q))
            .collect());
    }
    Ok((0..n)
        .into_par_iter()
        .map(|i| greeks::gamma_scalar(spot, strikes[i], ts[i], sigmas[i], r, q))
        .collect())
}

/// Normalize raw chain rows (list of dicts from yfinance/cvforge) into clean
/// contract dicts. Drops invalid strikes/kinds; coerces NaN→0.
#[pyfunction]
fn normalize_chain(
    py: Python<'_>,
    rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
) -> PyResult<PyObject> {
    use pyo3::types::{PyAny, PyDict, PyDictMethods, PyList, PyListMethods};

    fn get_f64(map: &std::collections::HashMap<String, Bound<'_, PyAny>>, name: &str) -> Option<f64> {
        map.get(name).and_then(|v| v.extract::<f64>().ok())
    }
    fn get_str<'a>(map: &'a std::collections::HashMap<String, Bound<'a, PyAny>>, name: &str) -> Option<String> {
        map.get(name).and_then(|v| v.extract::<String>().ok())
    }

    let mut out = Vec::with_capacity(rows.len());
    for map in &rows {
        let strike = get_f64(map, "strike").unwrap_or(0.0);
        if !(strike > 0.0) {
            continue;
        }
        let kind = match get_str(map, "type").unwrap_or_default().to_uppercase().as_str() {
            "C" | "CALL" => "C",
            "P" | "PUT" => "P",
            _ => continue,
        };
        let coerce = |v: Option<f64>| match v {
            Some(x) if x.is_finite() && x > 0.0 => x,
            _ => 0.0,
        };
        let oi = get_f64(map, "oi")
            .or_else(|| get_f64(map, "openInterest"))
            .or_else(|| get_f64(map, "open_interest"));
        let iv = coerce(get_f64(map, "iv").or_else(|| get_f64(map, "impliedVolatility")));

        let d = PyDict::new_bound(py);
        d.set_item("strike", strike)?;
        d.set_item("type", kind)?;
        d.set_item("oi", coerce(oi))?;
        d.set_item("volume", coerce(get_f64(map, "volume")))?;
        d.set_item("iv", iv)?;
        // delta may legitimately be negative — keep sign, drop NaN only
        d.set_item(
            "delta",
            get_f64(map, "delta").filter(|x| x.is_finite()).unwrap_or(0.0),
        )?;
        d.set_item(
            "gamma",
            get_f64(map, "gamma").filter(|x| x.is_finite()).unwrap_or(0.0),
        )?;
        out.push(d);
    }
    Ok(PyList::new_bound(py, &out).into_any().unbind())
}

fn parse_contracts(
    rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
) -> Vec<RawContract> {
    rows.into_iter()
        .map(|m| {
            let gf = |name: &str| -> f64 {
                m.get(name).and_then(|v| v.extract::<f64>().ok()).unwrap_or(f64::NAN)
            };
            let kind = m
                .get("type")
                .and_then(|v| v.extract::<String>().ok())
                .map(|s| s.to_ascii_lowercase())
                .unwrap_or_default();
            RawContract {
                strike: gf("strike"),
                kind: if kind.starts_with('c') { 'c' } else { 'p' },
                oi: gf("oi"),
                iv: gf("iv"),
                t: gf("T"),
            }
        })
        .collect()
}

fn row_to_dict<'py>(py: Python<'py>, r: &StrikeRow) -> PyResult<pyo3::Bound<'py, pyo3::types::PyDict>> {
    use pyo3::types::PyDict;
    use pyo3::types::PyDictMethods;
    let d = PyDict::new_bound(py);
    d.set_item("strike", r.strike)?;
    d.set_item("gex", r.gex)?;
    d.set_item("call_gex", r.call_gex)?;
    d.set_item("put_gex", r.put_gex)?;
    d.set_item("call_oi", r.call_oi)?;
    d.set_item("put_oi", r.put_oi)?;
    d.set_item("total_oi", r.total_oi)?;
    d.set_item("vex", r.vex)?;
    d.set_item("vega", r.vega)?;
    d.set_item("charm", r.charm)?;
    d.set_item("vomma", r.vomma)?;
    d.set_item("zomma", r.zomma)?;
    Ok(d)
}

/// Per-strike GEX — parity with services/gex_core.compute_gex_by_strike.
/// contracts: list of dicts with keys strike/type/oi/iv/T. div_yield: e.g. 0.013 for SPY.
#[pyfunction]
#[pyo3(signature = (spot, contracts, div_yield=0.0))]
fn compute_gex_by_strike(
    py: Python<'_>,
    spot: f64,
    contracts: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>,
    div_yield: f64,
) -> PyResult<PyObject> {
    use pyo3::types::PyList;
    let raw = parse_contracts(contracts);
    let rows = gex::compute_gex_by_strike(spot, &raw, div_yield);
    let dicts: Vec<_> = rows.iter().map(|r| row_to_dict(py, r)).collect::<PyResult<_>>()?;
    Ok(PyList::new_bound(py, &dicts).into_any().unbind())
}

/// Zero-gamma flip levels from per-strike GEX rows.
#[pyfunction]
fn zero_gamma_levels(py: Python<'_>, rows: Vec<std::collections::HashMap<String, pyo3::Bound<'_, PyAny>>>) -> PyResult<PyObject> {
    use pyo3::types::{PyDict, PyList};
    use pyo3::types::PyDictMethods;
    let parsed: Vec<StrikeRow> = rows
        .iter()
        .map(|m| StrikeRow {
            strike: m.get("strike").and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0),
            gex: m.get("gex").and_then(|v| v.extract::<f64>().ok()).unwrap_or(0.0),
            ..Default::default()
        })
        .collect();
    let levels = gex::zero_gamma_levels(&parsed);
    Ok(PyList::new_bound(py, &levels).into_any().unbind())
}

#[pymodule]
fn decoder_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(bs_gamma, m)?)?;
    m.add_function(wrap_pyfunction!(gamma_batch, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_chain, m)?)?;
    m.add_function(wrap_pyfunction!(compute_gex_by_strike, m)?)?;
    m.add_function(wrap_pyfunction!(zero_gamma_levels, m)?)?;
    Ok(())
}
