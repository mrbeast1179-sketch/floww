//! PyO3 0.22 bindings — expose decoder-core to the FastAPI backend.
//!
//! Uses Bound<'_, T> API throughout (PyO3 ≥ 0.21 style).

use crate::greeks;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDictMethods, PyListMethods};
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
    use pyo3::types::{PyAny, PyDict, PyList};
    use pyo3::types::{PyDictMethods, PyListMethods};

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

#[pymodule]
fn decoder_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(bs_gamma, m)?)?;
    m.add_function(wrap_pyfunction!(gamma_batch, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_chain, m)?)?;
    Ok(())
}
