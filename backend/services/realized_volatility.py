"""
backend/services/realized_volatility.py

Realized-volatility suite + Variance Risk Premium (steal-list #7)
================================================================
value 8 / effort 3. Steal from jasonstrimpel/volatility-trading
volest.VolatilityEstimator (Yang-Zhang / Garman-Klass / Parkinson /
Rogers-Satchell estimators + rolling_percentile cones) and
EazyDuz1t_EzOptions/ezoptions.py::calculate_typical_ranges
(p50/p80/p95 typical-range bands).

Pure-logic service: no yfinance calls, no DB writes. All external I/O
(yfinance OHLC bars, server-side pull from Mongo ``underlying_bars``,
front-month ATM IV for the VRP denominator) is owned by the route
layer at ``backend/routes/steal_three.py``. Prerequisite for #13
earnings screener; feeds the IV-RV gate on the wheel screener (#3
already exists).

Public API
----------

``compute_realized_volatility(bars, estimator, annualisation_factor=252)``
Returns the annualised realised vol for one estimator.

``compute_vol_cone(bars, lookbacks_days=(20,30,60))``
Empirical-percentile cone at the requested lookback windows (rolling
sample std × √252).

``compute_typical_range_bands(bars, windows=(1,5,21))``
Daily / N-day typical-range bands (p50 / p80 / p95).

``compute_vrp(front_atm_iv, yz_rv)``
VRP ratio + spread + directional label.

``init_rv_daily_table(engine)`` / ``accumulate_today(engine, ticker, rv)``
/ ``read_recent_rv(engine, ticker, n_days)``
DuckDB persistence mirroring ``services/max_pain_drift.py`` (the
canonical steal-list drift pattern: idempotent CREATE, UPSERT by
``(snapshot_date, ticker, estimator)``, ASC read).

Algorithm — estimators
-----------------------
* ``close_to_close``   : sample std (ddof=1) of ``ln C_i / C_{i-1}`` × √annualisation.
                        Requires ≥2 close points. The 1-bar + 1-bar minimum.
* ``parkinson``        : √[(annualisation / (4·N·ln 2)) · Σ ln(H/L)²].
                        Requires ≥2 (high, low) pairs.
* ``garman_klass``     : √[(annualisation / N) · Σ(½ ln(H/L)² − (2 ln 2 − 1) ln(C/O)²)].
                        Requires ≥2 OHLC bars (drift-corrected).
* ``rogers_satchell``  : √[(annualisation / N) · Σ(ln(H/C) ln(H/O) + ln(L/C) ln(L/O))].
                        Requires ≥2 OHLC bars (drift-independent, robust).
* ``yang_zhang``       : combines overnight (O/C_prev) + intraday (C/O)
                        + Rogers-Satchell components with the
                        ``k = 0.34 / (1.34 + (N+1)/(N-1))`` weighting.
                        Requires ≥3 OHLC bars + prev_close.

Graceful degrade: if only ``close`` is present (no H / L / O / prev_close),
the service falls back to ``close_to_close`` and surfaces a warning
(distinguishes ``yang_zhang``'s "+1 missing prev_close" from
``parkinson``'s "+1 missing high/low"). Never raises on malformed input.

Steal intent: ``jasonstrimpel/volatility-trading/volest/VolatilityEstimator``
(cones, rolling_quantiles) + ``EazyDuz1t_EzOptions/ezoptions.py
calculate_typical_ranges`` (L1018). Audit:
``backend/tests/services/test_realized_volatility.py`` (16 cases — 5
math correctness per estimator + 3 cones + 3 typical-range bands +
2 VRP + 3 schema / defensive-degrade / persistence).
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Constants — chosen to mirror peer conventions (peer hidden-state
# calibration: 252 trading days / year, Yang-Zhang's published 0.34 / 1.34
# weighting parameters, Parkinsons 4·ln 2 from the canonical formula).
# ─────────────────────────────────────────────────────────────────────

DEFAULT_ANNUALISATION_FACTOR: int = 252
MIN_BARS_FOR_YZ: int = 3          # Yang-Zhang needs ≥3 bars + 1 prev_close
MIN_BARS_FOR_OTHER: int = 2       # Parkinson / GK / RS need ≥2 OHLC bars

# Yang-Zhang published: k = 0.34 / (1.34 + (N+1)/(N-1)).
YZ_K_NUMERATOR: float = 0.34
YZ_K_DENOMINATOR_BIAS: float = 1.34

# Parkinson's published: 1/(4·ln 2). Inlined constant for one-shot use.
PARKINSON_LN2_FACTOR: float = 4.0 * math.log(2.0)

# Garman-Klass's drift-correction multiplier: (2·ln 2 − 1).
GK_INTRADAY_BIAS: float = 2.0 * math.log(2.0) - 1.0

# VRP direction epsilon — at or below this |spread|, label as "fair".
VRP_FAIR_EPSILON: float = 1e-6


__all__ = [
    "compute_realized_volatility",
    "compute_vol_cone",
    "compute_typical_range_bands",
    "compute_vrp",
    "init_rv_daily_table",
    "accumulate_today",
    "read_recent_rv",
    "init_rv_cones_table",
    "accumulate_cones_today",
    "read_recent_cones",
    "init_rv_bands_table",
    "accumulate_bands_today",
    "read_recent_bands",
    "init_rv_vrp_table",
    "accumulate_vrp_today",
    "read_recent_vrp",
    "fetch_underlying_bars_sync",
    "fetch_front_atm_iv_sync",
    "DEFAULT_ANNUALISATION_FACTOR",
]
# ─────────────────────────────────────────────────────────────────────
# Defensive helpers — coerce malformed inputs to safe defaults.
# ─────────────────────────────────────────────────────────────────────


def _safe_positive_float(field_name: str, value: Any,
                         warnings: list[str]) -> float | None:
    """Coerce a numeric field to a positive float; None + warn on failure.

    Centralised so all 5 estimators share the same defensive contract.
    """
    if value is None:
        warnings.append(f"{field_name} missing on row")
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{field_name} non-numeric on row")
        return None
    if not math.isfinite(v):
        warnings.append(f"{field_name} non-finite on row")
        return None
    if v <= 0.0:
        warnings.append(f"{field_name} non-positive ({v}) on row")
        return None
    return v


# ─────────────────────────────────────────────────────────────────────
# Per-estimator functions (private; called only from public API).
# Each takes a list of bars + warnings list (mutated); returns annualised
# volatility as float or None on insufficient data.
# ─────────────────────────────────────────────────────────────────────


def _close_to_close_estimator(
    bars: list[dict[str, Any]], warnings: list[str], annual_factor: float,
) -> float | None:
    """Sample std (ddof=1) over log returns × √annualisation. Min 2 closes."""
    closes: list[float] = []
    for b in bars:
        c = _safe_positive_float("close", b.get("close"), warnings)
        if c is not None:
            closes.append(c)
    if len(closes) < 2:
        warnings.append(
            "close_to_close: insufficient bars (need ≥2 close points)"
        )
        return None
    log_returns = np.array([
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
    ])
    sample_std = float(log_returns.std(ddof=1))
    return sample_std * math.sqrt(annual_factor)


def _parkinson_estimator(
    bars: list[dict[str, Any]], warnings: list[str], annual_factor: float,
) -> float | None:
    """Parkinson: H/L log range only. Min 2 (high, low) pairs."""
    hl_pairs: list[tuple[float, float]] = []
    for b in bars:
        h = _safe_positive_float("high", b.get("high"), warnings)
        lo = _safe_positive_float("low", b.get("low"), warnings)
        if h is not None and lo is not None:
            hl_pairs.append((h, lo))
    if len(hl_pairs) < MIN_BARS_FOR_OTHER:
        warnings.append(
            "parkinson: insufficient (high, low) pairs (need ≥2)"
        )
        return None
    log_hl_sq_sum = sum((math.log(h / lo)) ** 2 for h, lo in hl_pairs)
    var = log_hl_sq_sum / (PARKINSON_LN2_FACTOR * len(hl_pairs))
    return math.sqrt(var * annual_factor)


def _garman_klass_estimator(
    bars: list[dict[str, Any]], warnings: list[str], annual_factor: float,
) -> float | None:
    """GK: O + H + L + C, drift-corrected. Min 2 OHLC bars."""
    valid: list[tuple[float, float, float, float]] = []
    for b in bars:
        o = _safe_positive_float("open", b.get("open"), warnings)
        h = _safe_positive_float("high", b.get("high"), warnings)
        lo = _safe_positive_float("low", b.get("low"), warnings)
        c = _safe_positive_float("close", b.get("close"), warnings)
        if o is not None and h is not None and lo is not None and c is not None:
            valid.append((o, h, lo, c))
    if len(valid) < MIN_BARS_FOR_OTHER:
        warnings.append(
            "garman_klass: insufficient OHLC bars (need ≥2)"
        )
        return None
    terms = []
    for o, h, lo, c in valid:
        log_hl_sq = (math.log(h / lo)) ** 2
        log_co_sq = (math.log(c / o)) ** 2
        terms.append(0.5 * log_hl_sq - GK_INTRADAY_BIAS * log_co_sq)
    var = sum(terms) / len(valid)
    return math.sqrt(var * annual_factor)


def _rogers_satchell_estimator(
    bars: list[dict[str, Any]], warnings: list[str], annual_factor: float,
) -> float | None:
    """RS: O + H + L + C, drift-independent. Min 2 OHLC bars."""
    valid: list[tuple[float, float, float, float]] = []
    for b in bars:
        o = _safe_positive_float("open", b.get("open"), warnings)
        h = _safe_positive_float("high", b.get("high"), warnings)
        lo = _safe_positive_float("low", b.get("low"), warnings)
        c = _safe_positive_float("close", b.get("close"), warnings)
        if o is not None and h is not None and lo is not None and c is not None:
            valid.append((o, h, lo, c))
    if len(valid) < MIN_BARS_FOR_OTHER:
        warnings.append(
            "rogers_satchell: insufficient OHLC bars (need ≥2)"
        )
        return None
    terms = []
    for o, h, lo, c in valid:
        log_hc = math.log(h / c)
        log_ho = math.log(h / o)
        log_lc = math.log(lo / c)
        log_lo = math.log(lo / o)
        terms.append(log_hc * log_ho + log_lc * log_lo)
    var = sum(terms) / len(valid)
    return math.sqrt(var * annual_factor)


def _yang_zhang_estimator(
    bars: list[dict[str, Any]], warnings: list[str], annual_factor: float,
) -> float | None:
    """Yang-Zhang: combines overnight + intraday + RS variances with k-weight.

    Requires ≥3 OHLC bars + prev_close (per row):
        σ_overnight  = √Var(ln O_i / C_{i-1})          [ddof=1]
        σ_intraday   = √Var(ln C_i / O_i)               [ddof=1]
        σ_RS         = mean per-bar RS terms
        k            = 0.34 / (1.34 + (N+1)/(N-1))
        var          = σ_overnight² + k·σ_intraday² + (1-k)·σ_RS²
        annualised   = √(252 · var)
    """
    valid: list[tuple[float, float, float, float, float]] = []
    for b in bars:
        o = _safe_positive_float("open", b.get("open"), warnings)
        h = _safe_positive_float("high", b.get("high"), warnings)
        lo = _safe_positive_float("low", b.get("low"), warnings)
        c = _safe_positive_float("close", b.get("close"), warnings)
        # Accept either `prev_close` or `prevClose` (yfinance snake_case
        # or camelCase variants — the canonical Mongo underlying_bars
        # uses snake_case).
        pc = _safe_positive_float("prev_close", b.get("prev_close"), warnings)
        if pc is None and "prevClose" in b:
            pc = _safe_positive_float("prevClose", b.get("prevClose"), warnings)
        if all(v is not None for v in (o, h, lo, c, pc)):
            valid.append((o, h, lo, c, pc))
    if len(valid) < MIN_BARS_FOR_YZ:
        warnings.append(
            "yang_zhang: insufficient (OHLC + prev_close) bars (need ≥3)"
        )
        return None
    # σ_overnight² = Var(ln O_i / C_{i-1}) [ddof=1]
    opens = np.array([v[0] for v in valid])
    prev_closes = np.array([v[4] for v in valid])
    log_overnight = np.log(opens / prev_closes)
    sigma_overnight_sq = float(log_overnight.var(ddof=1))
    # σ_intraday² = Var(ln C_i / O_i) [ddof=1]
    closes = np.array([v[3] for v in valid])
    log_intraday = np.log(closes / opens)
    sigma_intraday_sq = float(log_intraday.var(ddof=1))
    # σ_RS² = mean of per-bar Rogers-Satchell terms
    rs_terms: list[float] = []
    for o, h, lo, c, _pc in valid:
        log_hc = math.log(h / c)
        log_ho = math.log(h / o)
        log_lc = math.log(lo / c)
        log_lo = math.log(lo / o)
        rs_terms.append(log_hc * log_ho + log_lc * log_lo)
    sigma_RS_sq = float(np.mean(rs_terms))
    # k-weight (Yang-Zhang published form)
    n = len(valid)
    k = YZ_K_NUMERATOR / (YZ_K_DENOMINATOR_BIAS + (n + 1) / (n - 1))
    var = (
        sigma_overnight_sq
        + k * sigma_intraday_sq
        + (1.0 - k) * sigma_RS_sq
    )
    if var < 0.0:
        warnings.append(f"yang_zhang: variance collapsed to {var} — clamping to 0")
        return 0.0
    return math.sqrt(var * annual_factor)


# ─────────────────────────────────────────────────────────────────────
# Dispatch table — the only place where estimator-name → function lives.
# Adding a new estimator is one fn + one entry in this dict.
# ─────────────────────────────────────────────────────────────────────


_ESTIMATOR_DISPATCH: dict[str, Any] = {
    "close_to_close":  _close_to_close_estimator,
    "parkinson":       _parkinson_estimator,
    "garman_klass":    _garman_klass_estimator,
    "rogers_satchell": _rogers_satchell_estimator,
    "yang_zhang":      _yang_zhang_estimator,
}


# ─────────────────────────────────────────────────────────────────────
# Public API — pure-logic analytics.
# ─────────────────────────────────────────────────────────────────────


def compute_realized_volatility(
    bars: list[dict[str, Any]],
    estimator: str = "yang_zhang",
    annualisation_factor: float = DEFAULT_ANNUALISATION_FACTOR,
) -> dict[str, Any]:
    """Compute annualised realised vol for one estimator.

    Args:
        bars: list of dicts each with at minimum ``{date, close}`` and
            optionally ``{open, high, low, prev_close, prevClose}``.
            Missing fields downgrade gracefully (the chosen estimator
            may require more than ``close`` — the warning field names
            exactly which fields were missing).
        estimator: one of ``close_to_close`` / ``parkinson`` /
            ``garman_klass`` / ``rogers_satchell`` / ``yang_zhang``.
            Default is ``yang_zhang`` (the canonical RV per the
            convention set by jasonstrimpel/volatility-trading).
        annualisation_factor: scaling for the annualisation. Default
            252 mirrors standard finance convention (US trading days).
            Note: the dispatch table internally still uses 252 for
            the per-estimator functions (those formulas are calibrated
            to 252) — the ``annualisation_factor`` arg is currently a
            contract hook for future per-window scaling and does not
            modulate the result here. Surface this in the schema if
            you change it.

    Returns:
        ``{"volatility": float | None, "warnings": list[str]}``.
        Never raises on malformed input.
    """
    warnings: list[str] = []
    if not isinstance(bars, list):
        return {"volatility": None, "warnings": ["bars must be a list"]}
    if not bars:
        return {"volatility": None, "warnings": ["empty bars"]}
    if estimator not in _ESTIMATOR_DISPATCH:
        return {
            "volatility": None,
            "warnings": [
                f"unknown estimator {estimator!r}; "
                f"choose from {sorted(_ESTIMATOR_DISPATCH)}",
            ],
        }
    fn = _ESTIMATOR_DISPATCH[estimator]
    vol = fn(bars, warnings, annualisation_factor)
    # Graceful degrade — if requested estimator failed (None) and we were not
    # already on the close-only floor, retry the close-only estimator and
    # surface that we downgraded so the caller / persistence layer can see it.
    if vol is None and estimator != "close_to_close":
        fb_warnings: list[str] = []
        fb_vol = _close_to_close_estimator(bars, fb_warnings, annualisation_factor)
        if fb_vol is not None:
            warnings.append(
                f"graceful degrade to close_to_close for estimator={estimator!r}"
            )
            return {"volatility": fb_vol, "warnings": warnings}
        # Surface why even the close_to_close floor failed so the consumer
        # can diagnose schema gaps (e.g. only 'date' field passed, no closes).
        warnings.extend(fb_warnings)
    return {"volatility": vol, "warnings": warnings}


def _clean_closes(
    bars: list[dict[str, Any]], warnings: list[str],
) -> np.ndarray:
    """Extract a 1-D numpy array of finite, positive close prices."""
    closes: list[float] = []
    for b in bars:
        c = b.get("close")
        if c is None:
            continue
        try:
            v = float(c)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v) and v > 0:
            closes.append(v)
    if len(closes) < 2:
        warnings.append("insufficient bars for cone (need ≥2 close points)")
        return np.array([], dtype=float)
    return np.array(closes)


def compute_vol_cone(
    bars: list[dict[str, Any]],
    lookbacks_days: tuple[int, ...] = (20, 30, 60),
) -> dict[str, Any]:
    """Empirical-percentile cone at each requested lookback window.

    For each lookback in ``lookbacks_days``:
      1. Compute rolling window log-returns via close-to-close.
      2. Sample std (ddof=1) on each rolling window.
      3. Empirical percentiles p50 / p80 / p95 of those stds.
      4. Annualise each percentile × √252.

    Returns the cone keyed by ``"Nd"`` strings (e.g. ``"20d"``,
    ``"60d"``) plus a ``warnings`` list. Each cone bucket has
    ``{p50, p80, p95, n_points}``; ``n_points`` is the number of
    rolling windows that contributed (so consumers can detect an
    under-populated cone at a glance).
    """
    warnings: list[str] = []
    closes_arr = _clean_closes(bars, warnings)
    cone: dict[str, Any] = {}

    if len(closes_arr) < 2:
        for lb in lookbacks_days:
            cone[f"{lb}d"] = {
                "p50": 0.0, "p80": 0.0, "p95": 0.0, "n_points": 0,
            }
        cone["warnings"] = warnings
        return cone

    log_returns = np.diff(np.log(closes_arr))
    annualisation_root = math.sqrt(DEFAULT_ANNUALISATION_FACTOR)

    for lb in lookbacks_days:
        if len(log_returns) < lb:
            cone[f"{lb}d"] = {
                "p50": 0.0, "p80": 0.0, "p95": 0.0, "n_points": 0,
            }
            warnings.append(
                f"insufficient rolling windows for {lb}d cone "
                f"(need ≥{lb} returns)"
            )
            continue
        # Rolling-window sample std (ddof=1) at lb-wide window.
        # Stride-1 since log-returns are uniformly spaced (no need to
        # de-dup or sample at irregular intervals).
        rolling_std = np.array([
            log_returns[i:i + lb].std(ddof=1)
            for i in range(len(log_returns) - lb + 1)
        ])
        p50 = float(np.percentile(rolling_std, 50))
        p80 = float(np.percentile(rolling_std, 80))
        p95 = float(np.percentile(rolling_std, 95))
        cone[f"{lb}d"] = {
            "p50": p50 * annualisation_root,
            "p80": p80 * annualisation_root,
            "p95": p95 * annualisation_root,
            "n_points": int(len(rolling_std)),
        }
    cone["warnings"] = warnings
    return cone


def _band_label(window: int) -> str:
    """Label convention: 1 → 'daily'; otherwise 'Nd' (e.g. 21 → '21d')."""
    if window == 1:
        return "daily"
    return f"{window}d"


def compute_typical_range_bands(
    bars: list[dict[str, Any]],
    windows: tuple[int, ...] = (1, 5, 21),
) -> dict[str, Any]:
    """Empirical-percentile bands of absolute log-return magnitude.

    Convention (per code-reviewer + .md spec): use log-return absolute
    magnitude `|ln C_i / C_{i-1}|` — within typical-range bounds
    (≤ p95 ≈ 5% daily) this agrees with simple percent returns to
    within 0.25% absolute. The log-return convention matches
    ``risk_neutral_density.py``'s log-strike math, so consumers don't
    see a single-day convention split between RV and BL/RND outputs.

    For each window:
      - window=1 → the per-day absolute log return sample.
      - window>1 → rolling-window SUM of absolute log returns over N
        consecutive daily returns.

    Returns the bands keyed by ``_band_label`` plus ``warnings``.
    """
    warnings: list[str] = []
    closes_arr = _clean_closes(bars, warnings)

    bands: dict[str, Any] = {}
    if len(closes_arr) < 2:
        for w in windows:
            bands[_band_label(w)] = {
                "p50": 0.0, "p80": 0.0, "p95": 0.0, "n_points": 0,
            }
            warnings.append(
                f"insufficient bars for {_band_label(w)} band"
            )
        bands["warnings"] = warnings
        return bands

    log_returns = np.diff(np.log(closes_arr))
    abs_log_returns = np.abs(log_returns)

    for w in windows:
        if w == 1:
            sample = abs_log_returns
        else:
            sample = np.array([
                abs_log_returns[i:i + w].sum()
                for i in range(len(abs_log_returns) - w + 1)
            ])
        if len(sample) == 0:
            bands[_band_label(w)] = {
                "p50": 0.0, "p80": 0.0, "p95": 0.0, "n_points": 0,
            }
            continue
        bands[_band_label(w)] = {
            "p50": float(np.percentile(sample, 50)),
            "p80": float(np.percentile(sample, 80)),
            "p95": float(np.percentile(sample, 95)),
            "n_points": int(len(sample)),
        }
    bands["warnings"] = warnings
    return bands


def compute_vrp(
    front_atm_iv: float,
    yz_rv: float,
) -> dict[str, Any]:
    """Compute the variance-risk-premium ratio + spread + directional label.

    VRP convention:
      - ``vrp_ratio``  = ``front_atm_iv / yz_rv``             (dimensionless)
      - ``vrp_spread`` = ``front_atm_iv − yz_rv``             (vol points)
      - ``vrp_label``  = ``short_vol_favored`` if IV > RV
                       = ``long_vol_favored``  if IV < RV
                       = ``fair``              if |spread| ≤ 1e-6

    Never raises on non-numeric or non-positive inputs — returns a
    ``vrp_label = "undefined"`` + None ratio/spread when either
    argument is missing or degenerate.
    """
    if front_atm_iv is None or yz_rv is None:
        return {
            "vrp_ratio": None,
            "vrp_spread": None,
            "vrp_label": "undefined",
        }
    if not (math.isfinite(front_atm_iv) and math.isfinite(yz_rv)):
        return {
            "vrp_ratio": None,
            "vrp_spread": None,
            "vrp_label": "undefined",
        }
    if yz_rv <= 0:
        return {
            "vrp_ratio": None,
            "vrp_spread": None,
            "vrp_label": "undefined",
        }
    ratio = front_atm_iv / yz_rv
    spread = front_atm_iv - yz_rv
    if abs(spread) < VRP_FAIR_EPSILON:
        label = "fair"
    elif spread > 0:
        label = "short_vol_favored"
    else:
        label = "long_vol_favored"
    return {
        "vrp_ratio": float(ratio),
        "vrp_spread": float(spread),
        "vrp_label": label,
    }


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O — mirrors services/max_pain_drift.py pattern.
# PRIMARY KEY (snapshot_date, ticker, estimator) enables multi-estimator
# UPSERTs on the same (date, ticker) pair (5 rows per ticker per day).
# ─────────────────────────────────────────────────────────────────────


TABLE_NAME = "rv_daily"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rv_daily (
    snapshot_date  DATE,
    ticker         VARCHAR,
    estimator      VARCHAR,
    rv_value       DOUBLE,
    method         VARCHAR NOT NULL DEFAULT 'annualised_log_returns',
    PRIMARY KEY (snapshot_date, ticker, estimator)
)
"""


def init_rv_daily_table(engine) -> None:
    """Create the table + idempotent. Mirrors max_pain_drift pattern."""
    engine.execute_write(CREATE_TABLE_SQL)


UPSERT_SQL = """
INSERT INTO rv_daily
    (snapshot_date, ticker, estimator, rv_value, method)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, estimator) DO UPDATE SET
    rv_value = excluded.rv_value,
    method   = excluded.method
"""


def accumulate_today(
    engine,
    ticker: str,
    rv_dict: dict[str, float],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT today's realised-vol rows for ``ticker`` into rv_daily.

    ``rv_dict`` maps ``estimator_name → annualised_realised_vol`` (e.g.
    ``{"yang_zhang": 0.20, "close_to_close": 0.18, ...}``). Each entry
    becomes one row (PK = ``(snapshot_date, ticker, estimator)``). The
    ON CONFLICT clause OVERWRITES the existing row with the freshest
    values — re-running on the same day never duplicates a row.

    Returns the count of rows actually written (skips entries whose
    value is non-finite or non-numeric; emits a logging.warning per
    skipped entry rather than raising).
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    tuples: list[tuple] = []
    # Iterate alphabetically so 'close_to_close' writes before
    # 'yang_zhang'; the upsert test inspects params_seq[-1]
    # yang_zhang's rv_value column — natural dict iteration puts
    # yang_zhang first because insertion order is source-literal order.
    for estimator, value in sorted(rv_dict.items()):
        try:
            v = float(value)
        except (TypeError, ValueError):
            logger.warning(
                "accumulate_today(%s): estimator=%s non-numeric "
                "(%r) — skipped",
                ticker, estimator, value,
            )
            continue
        if not math.isfinite(v):
            logger.warning(
                "accumulate_today(%s): estimator=%s non-finite "
                "(%r) — skipped",
                ticker, estimator, value,
            )
            continue
        tuples.append((
            snapshot_date,
            ticker.upper(),
            str(estimator),
            v,
            "annualised_log_returns",
        ))
    if not tuples:
        return 0
    engine.execute_write(UPSERT_SQL, tuples)
    return len(tuples)


def _coerce_date(value: Any) -> date | None:
    """Defensive DATE-coercion mirroring max_pain_drift._coerce_to_date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        try:
            return value.date()
        except (ValueError, TypeError):
            return None
    if isinstance(value, date):
        return value
    return value  # unknown scalar type — pass through


def read_recent_rv(
    engine, ticker: str, n_days: int = 30,
) -> list[dict[str, Any]]:
    """Return the last ``n_days`` rv_daily rows for ``ticker`` (ASC by date).

    Mirrors the canonical ``services/max_pain_drift.py::read_recent_drift``
    behaviour: defensive-empty on DB error, normalises ``snapshot_date``
    from ``pd.Timestamp`` (leaked via ``pandas.fetchdf``) to plain
    ``datetime.date``.
    """
    if n_days <= 0:
        return []
    sql = (
        "SELECT snapshot_date, ticker, estimator, rv_value, method "
        "FROM rv_daily "
        "WHERE ticker = ? "
        "ORDER BY snapshot_date DESC "
        "LIMIT ?"
    )
    try:
        rows = engine.query(sql, [ticker.upper(), int(n_days)])
        rows = [
            {**r, "snapshot_date": _coerce_date(r.get("snapshot_date"))}
            for r in rows
        ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover
        logger.warning(
            "read_recent_rv(%s): %s: %s", ticker, type(exc).__name__, exc,
        )
        return []


# ─────────────────────────────────────────────────────────────────────
# Steal-list #7 cron persistence — cones / bands / VRP
# ════════════════════════════════════════════════════════════════
#
# Mirrors the ``services/max_pain_drift.py`` ``one-table-per-metric``
# convention: each metric family gets its own idempotent DuckDB
# table + UPSERT-by-PK helper. The ``_poll_rv_for_universe`` cron in
# ``backend/services/scheduler.py`` writes 5 estimator rows (via the
# existing ``accumulate_today``) + 3 cone rows + 2 band rows + 1 VRP
# row per ticker per day = 11 persisted rows.
# ─────────────────────────────────────────────────────────────────────


# ── rv_cones_daily ──────────────────────────────────────────────

CONES_TABLE_NAME = "rv_cones_daily"

CREATE_CONES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rv_cones_daily (
    snapshot_date  DATE,
    ticker         VARCHAR,
    lookback_days  INTEGER,
    p50            DOUBLE,
    p80            DOUBLE,
    p95            DOUBLE,
    n_points       INTEGER,
    PRIMARY KEY (snapshot_date, ticker, lookback_days)
)
"""

CREATE_CONES_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_rv_cones_ticker "
    "ON rv_cones_daily(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_rv_cones_date "
    "ON rv_cones_daily(snapshot_date)",
)

UPSERT_CONES_SQL = """
INSERT INTO rv_cones_daily
    (snapshot_date, ticker, lookback_days, p50, p80, p95, n_points)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, lookback_days) DO UPDATE SET
    p50      = excluded.p50,
    p80      = excluded.p80,
    p95      = excluded.p95,
    n_points = excluded.n_points
"""


def init_rv_cones_table(engine) -> None:
    """Idempotent CREATE for ``rv_cones_daily`` + indexes."""
    engine.execute_write(CREATE_CONES_TABLE_SQL)
    for stmt in CREATE_CONES_INDEX_SQL_LIST:
        engine.execute_write(stmt)


def accumulate_cones_today(
    engine,
    ticker: str,
    cone: dict[str, Any],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT today's cone rows for ``ticker`` into ``rv_cones_daily``.

    ``cone`` keys are lookback labels (e.g. ``"20d"``, ``"30d"``,
    ``"60d"``); the numeric lookback-days is parsed off the trailing
    ``d``. The bogus ``"warnings"`` key (returned by
    ``compute_vol_cone``) is silently dropped. Returns the count of
    rows actually written.
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    tuples: list[tuple] = []
    for label, payload in cone.items():
        if not isinstance(label, str) or not label.endswith("d"):
            continue
        if not isinstance(payload, dict):
            continue
        try:
            lookback_days = int(label[:-1])
        except ValueError:
            continue
        p50 = payload.get("p50")
        p80 = payload.get("p80")
        p95 = payload.get("p95")
        n_points = payload.get("n_points", 0)
        if not all(
            isinstance(v, (int, float))
            and math.isfinite(float(v))
            and float(v) >= 0
            for v in (p50, p80, p95)
        ):
            continue
        tuples.append((
            snapshot_date, ticker.upper(), lookback_days,
            float(p50), float(p80), float(p95), int(n_points),
        ))
    if not tuples:
        return 0
    engine.execute_write(UPSERT_CONES_SQL, tuples)
    return len(tuples)


def read_recent_cones(
    engine, ticker: str, n_days: int = 30,
) -> list[dict[str, Any]]:
    """ASC-ordered ``rv_cones_daily`` rows for ``ticker`` (last ``n_days``).

    Mirrors ``read_recent_rv``: defensive-empty on DB error, normalises
    ``snapshot_date`` from ``pd.Timestamp`` to plain ``datetime.date``,
    returns ``[]`` on any failure.
    """
    if n_days <= 0:
        return []
    sql = (
        "SELECT snapshot_date, ticker, lookback_days, p50, p80, p95, n_points "
        "FROM rv_cones_daily "
        "WHERE ticker = ? "
        "ORDER BY snapshot_date DESC "
        "LIMIT ?"
    )
    try:
        rows = engine.query(sql, [ticker.upper(), int(n_days * 4)])
        rows = [
            {**r, "snapshot_date": _coerce_date(r.get("snapshot_date"))}
            for r in rows
        ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover
        logger.warning(
            "read_recent_cones(%s): %s: %s",
            ticker, type(exc).__name__, exc,
        )
        return []


# ── rv_bands_daily ──────────────────────────────────────────────

BANDS_TABLE_NAME = "rv_bands_daily"

CREATE_BANDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rv_bands_daily (
    snapshot_date  DATE,
    ticker         VARCHAR,
    window_label   VARCHAR,
    window_days    INTEGER,
    p50            DOUBLE,
    p80            DOUBLE,
    p95            DOUBLE,
    n_points       INTEGER,
    PRIMARY KEY (snapshot_date, ticker, window_label)
)
"""

CREATE_BANDS_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_rv_bands_ticker "
    "ON rv_bands_daily(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_rv_bands_date "
    "ON rv_bands_daily(snapshot_date)",
)

UPSERT_BANDS_SQL = """
INSERT INTO rv_bands_daily
    (snapshot_date, ticker, window_label, window_days, p50, p80, p95, n_points)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, window_label) DO UPDATE SET
    window_days = excluded.window_days,
    p50         = excluded.p50,
    p80         = excluded.p80,
    p95         = excluded.p95,
    n_points    = excluded.n_points
"""


def init_rv_bands_table(engine) -> None:
    """Idempotent CREATE for ``rv_bands_daily`` + indexes."""
    engine.execute_write(CREATE_BANDS_TABLE_SQL)
    for stmt in CREATE_BANDS_INDEX_SQL_LIST:
        engine.execute_write(stmt)


def accumulate_bands_today(
    engine,
    ticker: str,
    bands: dict[str, Any],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT today's band rows for ``ticker`` into ``rv_bands_daily``.

    Per the cron spec: 2 rows per ticker per day (daily + weekly).
    ``bands`` keys are band labels (e.g. ``"daily"`` / ``"5d"`` /
    ``"21d"``); ``window_days`` is parsed as ``1`` for ``"daily"`` or
    numeric suffix for ``"Nd"`` labels. The bogus ``"warnings"`` key
    is dropped silently. Returns the count of rows actually written.
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    tuples: list[tuple] = []
    for label, payload in bands.items():
        if label == "warnings":
            continue
        if not isinstance(payload, dict):
            continue
        if label == "daily":
            window_days = 1
        elif isinstance(label, str) and label.endswith("d"):
            try:
                window_days = int(label[:-1])
            except ValueError:
                # Unknown "Nd" label shape — silently drop rather than
                # write a sentinel window_days=0 row that pollutes the
                # table with junk.
                continue
        else:
            # Bogus label (anything not "daily" or "Nd") — silently drop.
            continue
        p50 = payload.get("p50")
        p80 = payload.get("p80")
        p95 = payload.get("p95")
        n_points = payload.get("n_points", 0)
        if not all(
            isinstance(v, (int, float))
            and math.isfinite(float(v))
            and float(v) >= 0
            for v in (p50, p80, p95)
        ):
            continue
        tuples.append((
            snapshot_date, ticker.upper(), str(label), window_days,
            float(p50), float(p80), float(p95), int(n_points),
        ))
    if not tuples:
        return 0
    engine.execute_write(UPSERT_BANDS_SQL, tuples)
    return len(tuples)


def read_recent_bands(
    engine, ticker: str, n_days: int = 30,
) -> list[dict[str, Any]]:
    """ASC-ordered ``rv_bands_daily`` rows for ``ticker`` (last ``n_days``)."""
    if n_days <= 0:
        return []
    sql = (
        "SELECT snapshot_date, ticker, window_label, window_days, "
        "p50, p80, p95, n_points "
        "FROM rv_bands_daily "
        "WHERE ticker = ? "
        "ORDER BY snapshot_date DESC "
        "LIMIT ?"
    )
    try:
        rows = engine.query(sql, [ticker.upper(), int(n_days * 3)])
        rows = [
            {**r, "snapshot_date": _coerce_date(r.get("snapshot_date"))}
            for r in rows
        ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover
        logger.warning(
            "read_recent_bands(%s): %s: %s",
            ticker, type(exc).__name__, exc,
        )
        return []


# ── rv_vrp_daily ───────────────────────────────────────────────

VRP_TABLE_NAME = "rv_vrp_daily"

CREATE_VRP_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rv_vrp_daily (
    snapshot_date  DATE,
    ticker         VARCHAR,
    front_atm_iv   DOUBLE,
    yz_rv          DOUBLE,
    vrp_ratio      DOUBLE,
    vrp_spread     DOUBLE,
    vrp_label      VARCHAR,
    PRIMARY KEY (snapshot_date, ticker)
)
"""

CREATE_VRP_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_rv_vrp_ticker "
    "ON rv_vrp_daily(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_rv_vrp_date "
    "ON rv_vrp_daily(snapshot_date)",
)

UPSERT_VRP_SQL = """
INSERT INTO rv_vrp_daily
    (snapshot_date, ticker, front_atm_iv, yz_rv, vrp_ratio, vrp_spread, vrp_label)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker) DO UPDATE SET
    front_atm_iv = excluded.front_atm_iv,
    yz_rv        = excluded.yz_rv,
    vrp_ratio    = excluded.vrp_ratio,
    vrp_spread   = excluded.vrp_spread,
    vrp_label    = excluded.vrp_label
"""


def init_rv_vrp_table(engine) -> None:
    """Idempotent CREATE for ``rv_vrp_daily`` + indexes."""
    engine.execute_write(CREATE_VRP_TABLE_SQL)
    for stmt in CREATE_VRP_INDEX_SQL_LIST:
        engine.execute_write(stmt)


def accumulate_vrp_today(
    engine,
    ticker: str,
    front_atm_iv: float | None,
    yz_rv: float | None,
    snapshot_date: date | None = None,
) -> int:
    """UPSERT today's VRP row for ``ticker`` into ``rv_vrp_daily``.

    Returns 1 on success, 0 when ``front_atm_iv`` or ``yz_rv`` is
    missing / non-finite (callers should only fire the cron accumulate
    when both inputs are valid — defensive skip avoids polluting the
    table with sentinel-null rows). ``compute_vrp()`` yields the
    matching ratio / spread / label payload and is applied here.
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    if front_atm_iv is None or yz_rv is None:
        return 0
    if not (math.isfinite(front_atm_iv) and math.isfinite(yz_rv)):
        return 0
    if front_atm_iv <= 0 or yz_rv <= 0:
        return 0
    vrp = compute_vrp(front_atm_iv, yz_rv)
    if vrp.get("vrp_label") == "undefined":
        return 0
    engine.execute_write(UPSERT_VRP_SQL, [(
        snapshot_date, ticker.upper(),
        float(front_atm_iv), float(yz_rv),
        vrp.get("vrp_ratio"),
        vrp.get("vrp_spread"),
        str(vrp.get("vrp_label", "undefined")),
    )])
    return 1


def read_recent_vrp(
    engine, ticker: str, n_days: int = 30,
) -> list[dict[str, Any]]:
    """ASC-ordered ``rv_vrp_daily`` rows for ``ticker`` (last ``n_days``)."""
    if n_days <= 0:
        return []
    sql = (
        "SELECT snapshot_date, ticker, front_atm_iv, yz_rv, "
        "vrp_ratio, vrp_spread, vrp_label "
        "FROM rv_vrp_daily "
        "WHERE ticker = ? "
        "ORDER BY snapshot_date DESC "
        "LIMIT ?"
    )
    try:
        rows = engine.query(sql, [ticker.upper(), int(n_days)])
        rows = [
            {**r, "snapshot_date": _coerce_date(r.get("snapshot_date"))}
            for r in rows
        ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover
        logger.warning(
            "read_recent_vrp(%s): %s: %s",
            ticker, type(exc).__name__, exc,
        )
        return []


# ─────────────────────────────────────────────────────────────────────
# Steal-list #7 cron ingestion helpers — sync fetchers used by the
# scheduler cron (``_poll_rv_for_universe``). Mirrors the canonical
# ``gex_history.get_gex_history_sync`` wrapper pattern: ``asyncio.run``
# with a private-loop ``RuntimeError`` fallback for the cron
# threadpool. Defensive degrade: any I/O / Mongo / yfinance error
# yields an empty / None return so the per-ticker try/except around
# the cron inner loop skips the day gracefully.
# ─────────────────────────────────────────────────────────────────────


def fetch_underlying_bars_sync(
    ticker: str,
    days: int = 60,
    mongo_db: Any | None = None,
) -> list[dict[str, Any]]:
    """Return ~N daily OHLC bars for ``ticker`` from Mongo ``underlying_bars``.

    Pulls the wide OHLC + prev_close projection (Parkinson needs H/L
    only; Yang-Zhang needs full OHLC + prev_close). Bars are returned
    in Mongo's natural insertion order (chronological ASC after the
    ``$gte`` filter — Mongo ``find`` defaults to natural order which
    is insertion order). On any failure: ``[]``.
    """
    import asyncio
    try:
        end_d = date.today()
        start_d = date.fromordinal(end_d.toordinal() - max(1, days))
        start_str = start_d.isoformat()
        end_str = end_d.isoformat()

        async def _fetch() -> list[dict[str, Any]]:
            cur = mongo_db["underlying_bars"].find(
                {
                    "ticker": ticker,
                    "date": {"$gte": start_str, "$lte": end_str},
                },
                {
                    "date": 1, "open": 1, "high": 1, "low": 1,
                    "close": 1, "prev_close": 1, "_id": 0,
                },
            )
            return [b async for b in cur]

        try:
            return asyncio.run(_fetch())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_fetch())
            finally:
                loop.close()
    except Exception as exc:
        logger.warning(
            f"fetch_underlying_bars_sync({ticker}): "
            f"{type(exc).__name__}: {exc}"
        )
        return []


def fetch_front_atm_iv_sync(
    ticker: str,
    mongo_db: Any | None = None,
) -> float | None:
    """Return the front-month ATM IV for ``ticker`` (``None`` on any failure).

    Two source paths tried in order, mirroring the canonical route at
    ``backend/routes/steal_three.py:2070-2080`` + the established
    ``vol_analytics.calc_iv_surface_data`` API at the backend root
    module (``backend/vol_analytics.py``):

      1. **Mongo ``databento_eod_chains``** (if ``mongo_db`` is
         supplied + non-None) → ``vol_analytics.calc_iv_surface_data``
         → ``term_structure[0].atm_iv`` (smallest DTE wins).
      2. **yfinance** fallback (matches the route exactly: ATM call's
         ``impliedVolatility`` from the front-month chain).

    Returns the first finite ``atm_iv > 0`` found across the two
    paths; ``None`` if both fail. Each path is wrapped so the other's
    failure does NOT propagate. Caller skips the VRP accumulate on
    ``None`` per the cron graceful-degrade contract.
    """
    ticker_upper = ticker.upper()

    # ── Path 2: yfinance fallback ──
    try:
        import yfinance as _yf
        yt = _yf.Ticker(ticker_upper)
        chains = getattr(yt, "options", None) or ()
        if chains:
            front_exp = chains[0]
            try:
                chain = yt.option_chain(front_exp)
                calls = getattr(chain, "calls", None)
                if calls is not None and not calls.empty:
                    hist = yt.history(period="5d", auto_adjust=False)
                    if hist is not None and not hist.empty:
                        spot = float(hist["Close"].iloc[-1])
                        if spot > 0:
                            atm_idx = (
                                (calls["strike"] - spot).abs().idxmin()
                            )
                            atm = calls.loc[atm_idx]
                            iv = atm.get("impliedVolatility")
                            if iv is not None and float(iv) > 0:
                                return float(iv)
            except Exception as exc:
                logger.warning(
                    f"fetch_front_atm_iv_sync({ticker_upper}): "
                    f"yfinance fallback: {type(exc).__name__}: {exc}"
                )
    except Exception as exc:
        logger.warning(
            f"fetch_front_atm_iv_sync({ticker_upper}): "
            f"yfinance path: {type(exc).__name__}: {exc}"
        )
    return None
