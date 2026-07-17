"""
backend/services/stress_test.py

Steal-list #12 — Whole-book scenario stress-test matrix  [high-impact]
========================================================================
value 8 / effort 4 (V/E 2.0). Steal from
George-Dros_Options_Portfolio/functions.py:457-770
(analyze_combined_impact, process_portfolio, compute_portfolio_stats)
+ 3D surface plots L797-884.

Public API
----------
``compute_stress_test_matrix(positions, current_spot, r=0.045, ...)``
    Returns a 9-key dict containing the 3D P&L matrix over
    ``(spot_multipliers × iv_multipliers × days_decay)`` plus
    per-axis marginals and a defensive ``warnings`` list.

    Schema (frozen — pinned by test_stress_test.py's
    ``test_all_documented_keys_present_in_output``):
        base_spot, base_book_value, n_legs, shock_axes,
        pnl_matrix, marginal_pnl_per_spot, marginal_pnl_per_iv,
        marginal_pnl_per_t, warnings.

Algorithm
---------
For each leg ``[K, T_years, iv, qty, kind∈{call,put}, side∈{buy,sell}]``:

    sign  = +1 if side == "buy" else -1
    base  = bs_price(current_spot, K, T, r, iv, kind)
    leg_base_value = base * qty * 100 * sign

For each (spot_mult, iv_mult, days_decay):

    spot_new = current_spot * spot_mult
    iv_new   = iv * iv_mult
    T_new    = max(0, T - days_decay / 365)

    if T_new <= 0 or iv_new <= 0:
        shocked_price = intrinsic(spot_new, K, kind)
    else:
        shocked_price = bs_price(spot_new, K, T_new, r, iv_new, kind)

    leg_pnl = (shocked_price - base) * qty * 100 * sign
    cell.total_book_pnl = sum(leg_pnl for leg in positions)

Marginals isolate one axis at a time (others held at baseline =
closest axis value to spot=1.0×, iv=1.0×, days=0).

Defensive degradation
---------------------
* Malformed position dicts (missing keys, non-numeric values, invalid
  ``kind``/``side``, ``T<=0`` or ``iv<=0`` at baseline) are skipped
  with a string warning — never crash on input.
* Negative ``quantity`` is interpreted as a direction flip
  (``buy, -1`` ≡ ``sell, +1``) and a warning is surfaced.
* Non-numeric shock-axis values are coerced via ``float()``; on
  ``TypeError`` / ``ValueError`` they're dropped and a warning
  emitted so the grid still computes over the valid subset.
* Pure-logic: no yfinance calls, no DB writes. The route layer at
  ``backend/routes/...`` is responsible for fetching positions and
  triggering any cron-write flows.
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["compute_stress_test_matrix", "DEFAULT_SPOT_MULTIPLIERS",
           "DEFAULT_IV_MULTIPLIERS", "DEFAULT_DAYS_DECAY", "DEFAULT_R"]


# Default shock axes — chosen to mirror the roadmap spec verbatim:
#   "spot 0.8-1.2x, IV 0.8-1.2x, +7/30/60d decay"
# We add a denser centre bucket (0.95/0.90 and 1.05/1.10 on spot)
# because the at-the-money region is where retail users most often
# ask "what happens to my book if the name barely moves."
DEFAULT_SPOT_MULTIPLIERS: tuple[float, ...] = (
    0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20,
)
DEFAULT_IV_MULTIPLIERS: tuple[float, ...] = (
    0.80, 0.90, 1.00, 1.10, 1.20,
)
DEFAULT_DAYS_DECAY: tuple[float, ...] = (0.0, 7.0, 30.0, 60.0)
DEFAULT_R: float = 0.045

CONTRACT_MULTIPLIER: int = 100
_VALID_KINDS = {"call", "put"}
_VALID_SIDES = {"buy", "sell"}


# ─────────────────────────────────────────────────────────────────────
# Local Black-Scholes — mirrors the helper in test_stress_test.py so
# the hand-traced anchors agree to floating-point precision (±1e-6).
# Self-contained: does NOT import from strategy_builder.py to keep the
# surface area of this service standalone and testable in isolation.
# ─────────────────────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via math.erf (no scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_price(
    spot: float, K: float, T: float, r: float, sigma: float, kind: str,
) -> float:
    """Black-Scholes price with intrinsic fallback only at T<=0 or σ<=0.

    When ``spot == 0`` we floor it to ``1e-12`` inside ``math.log`` so the
    BS formulation retains full numerical precision at the ``S→0`` limit
    (calls → 0, puts → ``K · exp(-r·T)``) without raising
    ``ValueError`` on ``math.log(0)``. The T<=0 / σ<=0 branch is the
    *mathematical* limit (intrinsic is correct at expiry or zero vol),
    not the numerical guard.
    """
    if T <= 0.0 or sigma <= 0.0:
        return _intrinsic(spot, K, kind)
    spot_safe = max(spot, 1e-12)
    sqrt_t = math.sqrt(T)
    d1 = (math.log(spot_safe / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if kind == "call":
        return spot * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def _intrinsic(spot: float, K: float, kind: str) -> float:
    """Intrinsic value at expiry — used both as fallback when T<=0 and
    as the post-expiry shocked price."""
    if kind == "call":
        return max(spot - K, 0.0)
    return max(K - spot, 0.0)


def _closest_axis_value(axis: list[float], target: float) -> float:
    """Return the axis value closest to ``target`` (used to find the
    baseline multiplier — typically 1.0 for spot/IV and 0.0 for
    days_decay — even when the user's custom axis omitted it)."""
    return min(axis, key=lambda v: abs(v - target))


def _coerce_axis_value(
    raw: Any, label: str, idx: int, warnings: list[str],
) -> float | None:
    """Coerce a shock-axis element to float; on failure, drop + warn."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        warnings.append(
            f"{label}[{idx}]: non-numeric shock value {raw!r} — dropped"
        )
        return None


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def compute_stress_test_matrix(
    positions: list[dict[str, Any]],
    current_spot: float,
    r: float = DEFAULT_R,
    spot_multipliers: tuple[float, ...] = DEFAULT_SPOT_MULTIPLIERS,
    iv_multipliers: tuple[float, ...] = DEFAULT_IV_MULTIPLIERS,
    days_decay: tuple[float, ...] = DEFAULT_DAYS_DECAY,
) -> dict[str, Any]:
    """Compute a 3D P&L matrix for a portfolio under (spot × IV × time) shocks.

    Args:
        positions: list of per-leg dicts each with keys
            ``K`` (float), ``T`` (years, float), ``iv`` (float),
            ``quantity`` (float), ``kind`` (``"call"`` | ``"put"``),
            ``side`` (``"buy"`` | ``"sell"``).
        current_spot: spot at which the book is currently marked.
        r: risk-free rate. Default 0.045 mirrors floww's convention.
        spot_multipliers: tuple of ``S / S_current`` multipliers
            (e.g. ``(0.80, 1.00, 1.20)``).
        iv_multipliers: tuple of ``σ_new / σ_current`` multipliers.
        days_decay: tuple of forward days to advance time by.

    Returns:
        9-key dict per the schema documented in the module docstring.
        Never raises on malformed input — invalid legs are skipped and
        surfaced via ``warnings``.

        The matrix length is ``len(spot_axis) × len(iv_axis) × len(days_axis)``;
        marginals have lengths matching their respective axes.
    """
    warnings: list[str] = []

    # 1. Coerce shock axes (drop non-numeric values).
    spot_axis: list[float] = []
    for idx, sm in enumerate(spot_multipliers):
        v = _coerce_axis_value(sm, "spot_multipliers", idx, warnings)
        if v is not None:
            spot_axis.append(v)
    iv_axis: list[float] = []
    for idx, im in enumerate(iv_multipliers):
        v = _coerce_axis_value(im, "iv_multipliers", idx, warnings)
        if v is not None:
            iv_axis.append(v)
    days_axis: list[float] = []
    for idx, td in enumerate(days_decay):
        v = _coerce_axis_value(td, "days_decay", idx, warnings)
        if v is not None:
            days_axis.append(v)

    # Empty-axis safety: if every value got dropped, pnl_matrix is empty.
    if not spot_axis or not iv_axis or not days_axis:
        return {
            "base_spot": float(current_spot),
            "base_book_value": 0.0,
            "n_legs": 0,
            "shock_axes": {
                "spot_multipliers": spot_axis,
                "iv_multipliers": iv_axis,
                "days_decay": days_axis,
            },
            "pnl_matrix": [],
            "marginal_pnl_per_spot": [],
            "marginal_pnl_per_iv": [],
            "marginal_pnl_per_t": [],
            "warnings": warnings + ["empty shock axes — grid empty"],
        }

    # 2. Sanitize each leg; skip malformed ones with a warning.
    legs: list[dict[str, Any]] = []
    for idx, leg in enumerate(positions):
        if not isinstance(leg, dict):
            warnings.append(f"position[{idx}]: not a dict — skipped")
            continue
        keys_present = {k: leg.get(k) for k in
                        ("K", "T", "iv", "quantity", "kind", "side")}
        missing = [k for k, v in keys_present.items() if v is None]
        if missing:
            warnings.append(
                f"position[{idx}]: missing keys {missing} — skipped"
            )
            continue
        try:
            K = float(keys_present["K"])
            T = float(keys_present["T"])
            iv = float(keys_present["iv"])
            qty = float(keys_present["quantity"])
            kind = str(keys_present["kind"])
            side = str(keys_present["side"])
        except (TypeError, ValueError) as exc:
            warnings.append(
                f"position[{idx}]: non-numeric field "
                f"({type(exc).__name__}: {exc}) — skipped"
            )
            continue
        if kind not in _VALID_KINDS:
            warnings.append(
                f"position[{idx}]: invalid kind={kind!r} — skipped"
            )
            continue
        if side not in _VALID_SIDES:
            warnings.append(
                f"position[{idx}]: invalid side={side!r} — skipped"
            )
            continue

        # Baseline guards: T<=0 or iv<=0 ⇒ leg has no pricing uncertainty.
        if T <= 0.0 or iv <= 0.0:
            warnings.append(
                f"position[{idx}]: T={T}, iv={iv} (≤0) — leg ignored"
            )
            continue

        # Negative qty: direction flip (buy ↔ sell).
        if qty < 0.0:
            warnings.append(
                f"position[{idx}]: negative quantity {qty} — sign flipped"
            )
            if side == "buy":
                side = "sell"
            else:
                side = "buy"
            qty = -qty

        base_price = _bs_price(current_spot, K, T, r, iv, kind)
        legs.append({
            "K": K,
            "T": T,
            "iv": iv,
            "qty": qty,
            "kind": kind,
            "side": side,
            "sign": +1 if side == "buy" else -1,
            "base_price": base_price,
        })

    # 3. Aggregate per-shock cell.
    base_book_value: float = sum(
        leg["base_price"] * leg["qty"] * CONTRACT_MULTIPLIER * leg["sign"]
        for leg in legs
    )
    pnl_matrix: list[dict[str, Any]] = []
    for sm in spot_axis:
        for im in iv_axis:
            for td in days_axis:
                spot_new = current_spot * sm
                leg_pnl_sum = 0.0
                shocked_value_sum = 0.0
                for leg in legs:
                    iv_new = leg["iv"] * im
                    T_new = max(0.0, leg["T"] - td / 365.0)
                    if T_new <= 0.0 or iv_new <= 0.0:
                        shocked_price = _intrinsic(spot_new, leg["K"],
                                                   leg["kind"])
                    else:
                        shocked_price = _bs_price(
                            spot_new, leg["K"], T_new, r, iv_new,
                            leg["kind"],
                        )
                    leg_pnl_sum += (
                        (shocked_price - leg["base_price"])
                        * leg["qty"] * CONTRACT_MULTIPLIER * leg["sign"]
                    )
                    shocked_value_sum += (
                        shocked_price * leg["qty"] * CONTRACT_MULTIPLIER
                        * leg["sign"]
                    )
                pnl_matrix.append({
                    "spot_mult": sm,
                    "iv_mult": im,
                    "days_decay": td,
                    "shocked_book_value": shocked_value_sum,
                    "total_book_pnl": leg_pnl_sum,
                })

    # 4. Marginals — isolate one axis at a time, others at baseline.
    # Baseline = axis value closest to spot=1.0, iv=1.0, days=0.0
    # (so user-supplied axes without 1.0/0.0 still produce sensible
    # marginals via the nearest-neighbour fallback).
    baseline_iv = _closest_axis_value(iv_axis, 1.0)
    baseline_td = _closest_axis_value(days_axis, 0.0)

    def _lookup_cell(sm: float, im: float, td: float) -> float:
        for c in pnl_matrix:
            if (c["spot_mult"] == sm
                    and c["iv_mult"] == im
                    and c["days_decay"] == td):
                return c["total_book_pnl"]
        return 0.0  # unreachable given the nested-loop construction

    marginal_pnl_per_spot = [
        [sm, _lookup_cell(sm, baseline_iv, baseline_td)]
        for sm in spot_axis
    ]
    marginal_pnl_per_iv = [
        [im, _lookup_cell(1.0 if 1.0 in spot_axis else spot_axis[0],
                          im, baseline_td)]
        for im in iv_axis
    ]
    marginal_pnl_per_t = [
        [td, _lookup_cell(1.0 if 1.0 in spot_axis else spot_axis[0],
                          baseline_iv, td)]
        for td in days_axis
    ]

    return {
        "base_spot": float(current_spot),
        "base_book_value": base_book_value,
        "n_legs": len(legs),
        "shock_axes": {
            "spot_multipliers": spot_axis,
            "iv_multipliers": iv_axis,
            "days_decay": days_axis,
        },
        "pnl_matrix": pnl_matrix,
        "marginal_pnl_per_spot": marginal_pnl_per_spot,
        "marginal_pnl_per_iv": marginal_pnl_per_iv,
        "marginal_pnl_per_t": marginal_pnl_per_t,
        "warnings": warnings,
    }
