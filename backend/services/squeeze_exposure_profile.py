"""
backend/services/squeeze_exposure_profile.py

SqueezeMetrics Spot-Shifted Exposure Profile (steal-list #6 — value 8 / effort 3)
==================================================================================

Re-prices the option chain against hypothetical spot movements to build a
forward-looking "what happens to GEX if spot moves X%?" curve — the
SqueezeMetrics 2020 white-paper framing of gamma/delta exposure across a
grid of candidate future spot values rather than a single scalar at the
current spot.

Core logic:
  1. Derive implied volatility (σ) per contract from the live mid via
     bs_greeks.implied_vol_from_price (with raw-IV fallback when the IV
     solver brackets fail).
  2. For each hypothetical shift_pct in ``shifts_pct`` (default
     [-5, -2, 0, +2, +5]), build the per-shift chain via the
     ``_build_shifted_chain_for_shift`` helper — every strike's gamma
     is recomputed at the shifted spot via ``bs_gamma``.
  3. Hand-roll the per-shift dollar-GEX math inline against the shifted
     chain using the SAME ``spot² · OI · γ · 100 · 0.01`` scaling the
     canonical ``GexAggregator`` enforces. We previously routed through
     ``GexAggregator.compute()`` for "math consistency," but its return
     shape only exposes ``total_gex`` / ``net_gex`` / ``gex_1d`` (NOT
     per-side totals like ``total_call_gex`` / ``total_put_gex``), so
     the deferred path contributed zero net-new signal while doubling
     the per-shift compute. Hand-roll keeps the math identical while
     killing the dead-code read of ``agg_res`` keys.

NOTE: any consumer of ``shifted_chain`` MUST keep the ``_EXPIRY_KEYS``
invariant — the chain dict carries a numeric ``T: float`` evaluation
key and explicitly NO ``expiry: str`` label. The Stage-2 helper
documents this invariant in its docstring. Original silent regression
(``float("30DTE")``) was the source of the original #6 steal-list
blocker.

Audit:      docs/reports/2026-07-11-steal-list-integration-roadmap.md
            (rank #6 SqueezeMetrics spot-shifted Exposure Profile)
Test suite: backend/tests/services/test_squeeze_exposure_profile.py (17 cases incl. shifted_chain invariant + IV ratio pin).
Upstream:   aaguiar10/gflows compute_exposures + zerodelta / zerogamma
            routines (steal intent) — see ``Steal from`` line in the .md.
"""

from __future__ import annotations

import logging
import math
from datetime import date
from typing import Any

from bs_greeks import bs_gamma, implied_vol_from_price

logger = logging.getLogger(__name__)

__all__ = [
    "compute_spot_shifted_exposure_profile",
    "init_exposure_profile_table",
    "persist_daily",
]


# ─────────────────────────────────────────────────────────────────────
# Internal helpers (private to keep service boundary pure-logic)
# ─────────────────────────────────────────────────────────────────────


def _premium(row: dict) -> float:
    """Resolve a contract's primary fair-price via mid → lastPrice priority."""
    bid = row.get("bid")
    ask = row.get("ask")
    try:
        b_f = float(bid) if bid is not None else 0.0
        a_f = float(ask) if ask is not None else 0.0
        if b_f > 0.0 and a_f > 0.0:
            return 0.5 * (b_f + a_f)
        last = row.get("lastPrice")
        return float(last) if last is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _kind(row: dict) -> str:
    """Normalize contract type to ``"call"`` or ``"put"`` from any of the
    upstream conventions (yfinance flag, OCC type, broker row char)."""
    candidates = ("type", "optionType", "right", "kind", "side")
    for k in candidates:
        if k in row and row[k] is not None:
            v = str(row[k]).strip().lower()
            if v in ("c", "call", "calls", "0"):
                return "call"
            if v in ("p", "put", "puts", "1"):
                return "put"
    # Default to call (matches GexAggregator convention).
    return "call"


def _resolve_iv(row: dict, spot: float, T: float, r: float) -> float:
    """Invert the live mid to σ via bs_greeks.implied_vol_from_price; fall
    back to the chain-supplied `impliedVolatility`/iv field if the solver
    brackets fail. Returns 0.0 when no σ isractable."""
    mid = _premium(row)
    try:
        K = float(row.get("strike", 0.0) or 0.0)
    except (TypeError, ValueError):
        K = 0.0
    if K <= 0.0 or mid <= 0.0 or spot <= 0.0 or T <= 0.0:
        return _raw_iv_fallback(row)
    try:
        sigma = float(implied_vol_from_price(
            mid, spot, K, T, kind=_kind(row), q=0.0, r=r,
        ))
        return sigma if sigma > 0.0 else _raw_iv_fallback(row)
    except Exception:
        return _raw_iv_fallback(row)


def _raw_iv_fallback(row: dict) -> float:
    """Read σ from chain-supplied impliedVolatility / iv field. Returns 0.0
    if the field is missing/unparseable. Caller treats 0.0 σ as
    "skip this contract" downstream."""
    val = row.get("impliedVolatility", row.get("iv", None))
    if val is None:
        return 0.0
    try:
        v = float(val)
        return v if v > 0.0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _open_interest(row: dict) -> float:
    for k in ("oi", "openInterest", "open_interest", "OI"):
        if k in row and row[k] is not None:
            try:
                v = float(row[k])
                return v if v > 0.0 else 0.0
            except (TypeError, ValueError):
                pass
    return 0.0


# ─────────────────────────────────────────────────────────────────────
# Stage-2 helper — invariant-safe shifted chain construction.
# Spy-target for the regression invariant test.
# ─────────────────────────────────────────────────────────────────────


def _build_shifted_chain_for_shift(
    valid_contracts: list[dict[str, Any]],
    shifted_spot: float,
    T: float,
    r: float,
) -> list[dict[str, Any]]:
    """Re-price ``valid_contracts`` at ``shifted_spot`` and return a chain
    dict list whose every element has a NUMERIC ``T`` and NO ``expiry``
    string label.

    CRITICAL invariant: any downstream consumer that walks an
    *_EXPIRY_KEYS-style tuple via ``float(...)`` coercion (the original
    regression pre-fix routed this through GexAggregator.compute() which
    does exactly that) will silently crash on ``float("30DTE")`` and
    collapse every shift row to zero GEX. Stage-1 ``valid_contracts``
    carry ``expiry="30DTE"`` etc. as a LABEL — this helper re-stamps the
    *evaluation* numeric T onto every shifted contract dict so the
    invariant is preserved regardless of where the chain is consumed next
    (gauge-bot dashboard, future route layer, downstream backtester).

    ``vomma`` defaults to 0.0 so consumers that read
    ``_VOMMA_KEYS = ("vomma", ...)`` via ``float(...)`` see a clean
    zero rather than a missing-key warning.

    Returns a list of dicts each carrying the documented shifted-chain
    schema: ``{"strike": float, "oi": float, "type": str, "T": float,
    "gamma": float, "vomma": float}``.
    """
    out: list[dict[str, Any]] = []
    for c in valid_contracts:
        sigma = c["sigma"]
        try:
            gamma_val = float(bs_gamma(
                shifted_spot, c["strike"], T, sigma, q=0.0, r=r,
            )) if sigma > 0.0 else 0.0
        except Exception:
            gamma_val = 0.0
        out.append({
            "strike": c["strike"],
            "oi": c["oi"],
            "type": c["type"],
            "T": float(T),
            "gamma": float(gamma_val),
            "vomma": 0.0,
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def compute_spot_shifted_exposure_profile(
    chain: list[dict],
    spot: float,
    T: float,
    r: float = 0.05,
    shifts_pct: tuple[float, ...] = (-5.0, -2.0, 0.0, 2.0, 5.0),
    ) -> dict[str, Any]:
    """    Compute the multi-shift dollar-GEX exposure profile.

    For each shift value in ``shifts_pct`` (sorted ascending), every
    chain contract's gamma is recomputed at the hypothetical shifted
    spot via ``bs_gamma`` (via the Stage-2
    ``_build_shifted_chain_for_shift`` helper), then the per-shift
    dollar-GEX math is hand-rolled inline to produce per-strike
    contributions plus the net/total/dominant-sign summary.

    NOTE: the contract ``expiry`` field on each row is treated as a
    LABEL only (e.g. ``"30DTE"``). The evaluation time-to-expiry is
    the function's ``T`` parameter (numeric years), which the Stage-2
    helper re-stamps as the numeric key ``T: float`` onto every
    shifted contract dict and explicitly omits the ``expiry`` string
    label so any downstream consumer walking ``_EXPIRY_KEYS`` via
    ``float(...)`` does not crash on the label.

    Returns the schema documented in the test contract:

        {
            "ticker": None,                         # filled by route layer
            "spot": float,
            "shifts_pct": [float, ...],             # sorted asc
            "current_total_exposure": float,        # net_gex at shift=0
            "profile": [
                {
                    "shift_pct": float,
                    "shifted_spot": float,
                    "total_gex_dollars": float,
                    "call_gex_dollars": float,
                    "put_gex_dollars": float,
                    "net_gex_dollars": float,
                    "dominant_sign": "positive" | "negative" | "neutral",
                    "per_strike": [(strike, gex_dollars), ...],
                    "warnings": list[str],
                },
                ...
            ],
            "warnings": list[str],
            "method": "bs_reprice_then_dollar_gex",
        }
    """
    warnings: list[str] = []

    if not chain or spot <= 0.0 or T <= 0.0:
        warnings.append("empty chain or non-positive spot/T")
        return {
            "ticker": None,
            "spot": float(spot) if spot else 0.0,
            "shifts_pct": sorted([float(s) for s in shifts_pct]),
            "current_total_exposure": 0.0,
            "profile": [],
            "warnings": warnings,
            "method": "bs_reprice_then_dollar_gex",
        }

    # ── Stage 1: Pre-resolve σ per valid contract (one pass) ────────
    valid_contracts: list[dict[str, Any]] = []
    for row in chain:
        try:
            K = float(row.get("strike", 0.0) or 0.0)
        except (TypeError, ValueError):
            warnings.append(f"non-numeric strike on row skipped")
            continue
        oi = _open_interest(row)
        if K <= 0.0 or oi <= 0.0:
            warnings.append(f"zero OI or non-positive strike={K} skipped")
            continue
        valid_contracts.append({
            "strike": K,
            "oi": oi,
            "type": _kind(row),
            "sigma": _resolve_iv(row, spot, T, r),
            "expiry": row.get("expiry") or row.get("expirationDate") or "0DTE",
        })

    if not valid_contracts:
        warnings.append("no valid contracts after explicit filter pass")
        return {
            "ticker": None,
            "spot": round(float(spot), 4),
            "shifts_pct": sorted([float(s) for s in shifts_pct]),
            "current_total_exposure": 0.0,
            "profile": [],
            "warnings": warnings,
            "method": "bs_reprice_then_dollar_gex",
        }

    # ── Stage 2: Spot-shifted dollar-GEX hand-roll (no aggregator call) ──
    # NOTE: this loop previously routed each shifted_chain through
    # ``GexAggregator.compute()`` to apply the model-locked S²·OI·100·0.01
    # scaling. We discovered the aggregator's return shape only exposes
    # ``total_gex`` / ``net_gex`` / ``gex_1d`` — NOT the per-side totals
    # (``total_call_gex`` / ``total_put_gex``). Routing through it for
    # "math consistency" doubled the per-shift compute work against the
    # SAME shifted_chain while contributing zero net-new signal. The
    # hand-roll below applies the IDENTICAL S² · OI · γ · 100 · 0.01
    # scaling inline. ``_build_shifted_chain_for_shift`` is the spy-target
    # location the invariant regression test monkey-patches to verify the
    # numeric-T / string-expiry schema invariant.
    sorted_shifts = sorted([float(s) for s in shifts_pct])
    current_total_exposure = 0.0
    profile: list[dict[str, Any]] = []

    for shift in sorted_shifts:
        shifted_spot = float(spot) * (1.0 + (shift / 100.0))
        try:
            shifted_chain = _build_shifted_chain_for_shift(
                valid_contracts, shifted_spot, T, r,
            )
        except Exception as exc:
            warnings.append(
                f"_build_shifted_chain_for_shift failed at shift={shift}: "
                f"{type(exc).__name__}: {exc}"
            )
            profile.append({
                "shift_pct": float(shift),
                "shifted_spot": round(shifted_spot, 4),
                "total_gex_dollars": 0.0,
                "call_gex_dollars": 0.0,
                "put_gex_dollars": 0.0,
                "net_gex_dollars": 0.0,
                "dominant_sign": "neutral",
                "per_strike": [],
                "warnings": [str(exc)],
            })
            continue

        # Per-shift dollar-GEX hand-roll against shifted_chain directly.
        # spot_sq_scale = shifted_spot² · 0.01 · 100 (matches GexAggregator's
        # model-locked S² · OI · γ · 100 · 0.01 scaling). Calls accumulate
        # positively, puts contribute their absolute magnitude into put_gex
        # (which gets subtracted from call_gex to form net_gex — same
        # sign convention as the aggregator's net_gex).
        spot_sq_scale = shifted_spot * shifted_spot * 0.01 * 100.0
        call_gex = 0.0
        put_gex = 0.0
        per_strike_dict: dict[float, float] = {}
        for c in shifted_chain:
            contribution = float(c["gamma"]) * float(c["oi"]) * spot_sq_scale
            K_key = float(c["strike"])
            is_put = str(c.get("type", "call")).strip().lower() in (
                "p", "put", "puts", "1"
            )
            if is_put:
                put_gex += contribution
                per_strike_dict[K_key] = per_strike_dict.get(K_key, 0.0) - contribution
            else:
                call_gex += contribution
                per_strike_dict[K_key] = per_strike_dict.get(K_key, 0.0) + contribution
        net_gex = call_gex - put_gex
        total_dollars = abs(call_gex) + abs(put_gex)

        if abs(net_gex) < 1e-6:
            dominant = "neutral"
        elif net_gex > 0.0:
            dominant = "positive"
        else:
            dominant = "negative"

        per_strike = sorted(per_strike_dict.items())

        if shift == 0.0:
            current_total_exposure = net_gex

        profile.append({
            "shift_pct": float(shift),
            "shifted_spot": round(shifted_spot, 4),
            "total_gex_dollars": round(total_dollars, 4),
            "call_gex_dollars": round(call_gex, 4),
            "put_gex_dollars": round(put_gex, 4),
            "net_gex_dollars": round(net_gex, 4),
            "dominant_sign": dominant,
            "per_strike": per_strike,
            "warnings": [],
        })

    return {
        "ticker": None,
        "spot": round(float(spot), 4),
        "shifts_pct": sorted_shifts,
        "current_total_exposure": round(current_total_exposure, 4),
        "profile": profile,
        "warnings": warnings,
        "method": "bs_reprice_then_dollar_gex",
    }


# ─────────────────────────────────────────────────────────────────────
# DuckDB persistence (mirrors insider_scraper.py UPSERT pattern)
# ─────────────────────────────────────────────────────────────────────


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS floww_squeeze_exposure_daily (
    snapshot_date  DATE    NOT NULL,
    ticker         VARCHAR NOT NULL,
    shift_pct      DOUBLE  NOT NULL,
    shifted_spot   DOUBLE  NOT NULL,
    net_gex        DOUBLE  NOT NULL,
    dominant_sign  VARCHAR NOT NULL,
    method         VARCHAR NOT NULL DEFAULT 'bs_reprice_then_dollar_gex',
    computed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_date, ticker, shift_pct)
);
"""


def init_exposure_profile_table(engine: Any) -> None:
    """Create the persistence table idempotently."""
    engine.execute_write(CREATE_TABLE_SQL)


UPSERT_SQL = """
INSERT INTO floww_squeeze_exposure_daily
    (snapshot_date, ticker, shift_pct, shifted_spot, net_gex, dominant_sign, method)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, ticker, shift_pct) DO UPDATE SET
    shifted_spot  = excluded.shifted_spot,
    net_gex       = excluded.net_gex,
    dominant_sign = excluded.dominant_sign,
    method        = excluded.method,
    computed_at   = CURRENT_TIMESTAMP
"""


def persist_daily(
    engine: Any,
    ticker: str,
    profile_out: dict[str, Any],
    snapshot_date: "date | None" = None,
) -> int:
    """UPSERT each shift row into floww_squeeze_exposure_daily. Returns
    the count of rows actually written. NEVER raises on malformed input
    — the route defensive-degrade path relies on this."""
    profile = profile_out.get("profile") or []
    if not profile:
        return 0
    if snapshot_date is None:
        snapshot_date = date.today()

    tuples: list[tuple] = []
    for p in profile:
        try:
            tuples.append((
                snapshot_date,
                str(ticker).upper(),
                float(p["shift_pct"]),
                float(p["shifted_spot"]),
                float(p["net_gex_dollars"]),
                str(p["dominant_sign"]),
                str(profile_out.get("method", "bs_reprice_then_dollar_gex")),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "squeeze_exposure_profile.persist_daily skipping malformed row: %s",
                exc,
            )
            continue

    if not tuples:
        return 0
    engine.execute_write(UPSERT_SQL, tuples)
    return len(tuples)
