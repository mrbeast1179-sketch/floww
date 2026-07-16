"""
backend/services/strike_cone.py

Strike-Cone service — steal-list rank #10 (value 5 / effort 2)
===============================================================

Converts floww's existing probability distribution (per-strike
{prob_above, prob_below, delta}) into the concrete strikes premium sellers
act on: at target probability levels P(S > K) = 0.16, 0.30, 0.70, 0.84
(the 1σ / 0.5σ expected-move bands) and target delta levels 0.16, 0.30
(the 16Δ / 30Δ wings of an iron condor).

This is the **last-mile** layer from curve to strike selection, and it
pairs naturally with the wheel-income screener and the implied-move panel.

PURE-LOGIC: no yfinance calls, no DB writes. All external I/O is owned
by the route layer (``backend/routes/steal_three.py``) which calls
``compute_cone(prob_distribution, spot, target_probs, target_deltas)``.

Inputs (the output of ``backend/server.py:493 calc_probability_distribution``)::

    prob_distribution = [
        {"strike": 95.0, "prob_above": 0.74, "prob_below": 0.26, "delta": 0.78, "iv": 0.20},
        {"strike": 100.0, "prob_above": 0.51, "prob_below": 0.49, "delta": 0.53, "iv": 0.20},
        {"strike": 105.0, "prob_above": 0.30, "prob_below": 0.70, "delta": 0.27, "iv": 0.20},
        ...
    ]
    spot              = 100.0

Output schema (``compute_cone`` returns this dict verbatim)::

    {
        "spot": float,
        "n_strikes": int,
        "method": "linear_interp_bisect",
        "prob_cones": [
            # For each target_prob:
            {"target_prob": 0.16,
             "strike_above": float,       # interp on prob_above (resistance side)
             "strike_below": float,       # interp on prob_below (support side)
             "warning": None | str},
            ...
        ],
        "delta_cones": [
            # For each target_delta:
            {"target_delta": 0.30,
             "strike_above": float,       # interp on call delta (above ATM)
             "strike_below": float,       # interp on (1 - call_delta) (below ATM)
             "warning": None | str},
            ...
        ],
        "warnings": list[str],
    }

INTERPOLATION ALGORITHM
------------------------

Both ``prob_above`` and ``delta`` (call-delta) are **strictly monotonically
decreasing in strike** under Black-Scholes:
  - ``prob_above(K) = N(d2(K))``     — high for low K (deep ITM calls), low for high K
  - ``delta(K) = N(d1(K))``         — same direction

``prob_below = 1 - prob_above`` is **strictly monotonically increasing in strike**.
For put-delta mapping, we invert the call-delta curve: put_d = call_d - 1, so
finding the strike where ``call_d = 1 - target_delta`` is the strike where the
put has ``delta = -target_delta``.

Per-row linear interpolation on adjacent bracket strikes::

    idx      = bisect_left(values, target)        # decreasing-mono variant
    lo_val   = values[idx-1]
    hi_val   = values[idx]
    t        = (target - lo_val) / (hi_val - lo_val)   # 0..1
    strike   = strikes[idx-1] + t * (strikes[idx] - strikes[idx-1])

Edge handling (matches ``iv_skew_analyzer.py:198`` + ``gex_aggregator.py:406``):

  - target OUTSIDE the curve bounds → clamp to nearest strike + warning.
  - target exactly equal to a strike's value → return that strike verbatim
    (t == 0 or t == 1 branch), no interpolation.
  - degenerate bracket (val_low == val_high) → return strike_low outright.

Defensive guards (NaN-safe, monotonicity-respecting):

  - negative strikes filtered out
  - non-numeric / NaN values coerced to ``None`` + warning
  - non-monotone input (provider-data jitter) is silently sorted with a
    warning ("monotonicity assumed; sorted to enforce decreasing")

Steal intent: ``EazyDuz1t_EzOptions/ezoptions.py`` — ``find_probability_strikes``
(L2948) + ``find_delta_strikes`` (L2990). The math is the same; floww's
``prob_distribution`` already carries the per-strike ``delta`` so we
avoid a redundant BS inversion.

Audit: ``backend/tests/services/test_strike_cone.py`` (15 cases — empty,
single-strike, two-strike linear interp, exact match, standard interp,
out-of-bounds top + bottom, reversed input, jittery data, large target
delta, negative strikes, detached spot, missing keys, NaN, target=0.50
edge, malformed-input graceful).
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Pure helpers — no module-level globals except those used to label
# monotonicity direction.
# ─────────────────────────────────────────────────────────────────────


def _safe_float(key: str, row: dict[str, Any], value: Any, warnings: list[str]) -> float | None:
    """Coerce a value to float. NaN / inf / None / non-numeric → None + warning."""
    if value is None:
        warnings.append(f"{key} missing on strike={row.get('strike', '?')}")
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{key} not numeric on strike={row.get('strike', '?')}")
        return None
    if not math.isfinite(v):
        warnings.append(f"{key} not finite on strike={row.get('strike', '?')}")
        return None
    return v


def _interp_decreasing(
    sorted_strikes: Sequence[float],
    sorted_values: Sequence[float],
    target: float,
) -> tuple[float | None, str | None]:
    """Linear-interpolate on a DECREASING-in-strike value sequence.

    Returns ``(strike, warning)``.  ``warning`` is None for the happy
    path and a string when the target is outside the achievable range
    (clamped) or when the bracket is degenerate.

    Mirrors the precedent at ``gex_aggregator.py:406-418``
    (flip-zone linear interpolation) and ``iv_skew_analyzer.py:198``
    (ATM linear interpolation).
    """
    n = len(sorted_strikes)
    if n == 0 or len(sorted_values) != n:
        return None, "no strikes / values mismatch"

    # Out-of-bounds top: target larger than max value (for decreasing curves,
    # max value is the LOWEST-strike point). Clamp to strikes[0].
    max_val = sorted_values[0]
    if target > max_val:
        return sorted_strikes[0], "target above curve max — clamped to lowest strike"

    # Out-of-bounds bottom: target smaller than min value (min is the
    # HIGHEST-strike point). Clamp to strikes[-1].
    min_val = sorted_values[-1]
    if target < min_val:
        return sorted_strikes[-1], "target below curve min — clamped to highest strike"

    # In-range: bisect for the bracket where sorted_values crosses target.
    # sorted_values is decreasing, so we flip the search direction:
    # build a cmp key in increasing order (negate values).
    inv = [-v for v in sorted_values]
    idx = bisect.bisect_left(inv, -target)     # insertion point in negated seq

    if idx >= n:
        # Shouldn't trigger given min_val check above, but belt-and-suspenders.
        return sorted_strikes[-1], None
    if idx == 0:
        # Exact match at strikes[0] OR target > sorted_values[0] (handled above)
        if sorted_values[0] == target:
            return sorted_strikes[0], None
        return sorted_strikes[0], None

    # Bracket: (idx-1, idx) — values[idx-1] > target >= values[idx].
    lo_val = sorted_values[idx - 1]
    hi_val = sorted_values[idx]
    lo_strike = sorted_strikes[idx - 1]
    hi_strike = sorted_strikes[idx]

    # Exact match at hi-strike (target equals hi_val).
    if hi_val == target:
        return hi_strike, None
    if lo_val == target:
        return lo_strike, None

    # Degenerate bracket.
    if hi_val == lo_val:
        return lo_strike, "degenerate bracket — exact strike returned"

    # Linear interp (decreasing monotonic).
    t = (lo_val - target) / (lo_val - hi_val)   # 0..1, weight on hi_strike
    return lo_strike + t * (hi_strike - lo_strike), None


def _interp_increasing(
    sorted_strikes: Sequence[float],
    sorted_values: Sequence[float],
    target: float,
) -> tuple[float | None, str | None]:
    """Linear-interpolate on an INCREASING-in-strike value sequence.

    Same precedence as ``_interp_decreasing`` but on the increasing
    monotone branch (prob_below ascending in strike).
    """
    n = len(sorted_strikes)
    if n == 0 or len(sorted_values) != n:
        return None, "no strikes / values mismatch"

    min_val = sorted_values[0]
    if target < min_val:
        return sorted_strikes[0], "target below curve min — clamped to lowest strike"

    max_val = sorted_values[-1]
    if target > max_val:
        return sorted_strikes[-1], "target above curve max — clamped to highest strike"

    # Standard bisect on increasing sequence.
    idx = bisect.bisect_left(sorted_values, target)

    if idx >= n:
        return sorted_strikes[-1], None
    if idx == 0:
        return sorted_strikes[0], None

    lo_val = sorted_values[idx - 1]
    hi_val = sorted_values[idx]
    lo_strike = sorted_strikes[idx - 1]
    hi_strike = sorted_strikes[idx]

    if hi_val == target:
        return hi_strike, None
    if lo_val == target:
        return lo_strike, None

    if hi_val == lo_val:
        return lo_strike, "degenerate bracket — exact strike returned"

    t = (target - lo_val) / (hi_val - lo_val)
    return lo_strike + t * (hi_strike - lo_strike), None


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def compute_cone(
    prob_distribution: list[dict[str, Any]],
    spot: float = 0.0,
    target_probs: Sequence[float] = (0.16, 0.30),
    target_deltas: Sequence[float] = (0.16, 0.30),
) -> dict[str, Any]:
    """Compute the strike cone — strikes at target prob and target delta levels.

    Args:
        prob_distribution: per-strike {strike, prob_above, prob_below, delta}.
            The output of ``backend/server.py:493 calc_probability_distribution``.
        spot: current underlying price (used only for echo / metadata).
        target_probs: probability targets at which to interpolate strikes;
            typically ``(0.16, 0.30)`` for the lower-tail bands. Set to
            ``(0.16, 0.30, 0.70, 0.84)`` for full expect-range wings.
        target_deltas: call-delta targets at which to interpolate strikes;
            typically ``(0.16, 0.30)`` for iron-condor wings.

    Returns:
        A dict matching the schema documented at the top of this module.
        Always returns — never raises on malformed / sparse input.

    Notes:
        - Missing inputs never crash: malformed rows are filtered out and
          surfaces a warning.
        - Out-of-range targets clamp to the nearest valid strike + warning.
        - ``strike_above`` = interp target on prob_above (resistance); pair
          strikes for both above and below.
    """
    warnings: list[str] = []

    if not isinstance(prob_distribution, list):
        return {
            "spot": spot,
            "n_strikes": 0,
            "method": "linear_interp_bisect",
            "prob_cones": [],
            "delta_cones": [],
            "warnings": ["prob_distribution must be a list"],
        }

    # ── 1. Sanitize + filter ─────────────────────────────────────────
    cleaned: list[dict[str, float | None]] = []
    for row in prob_distribution:
        if not isinstance(row, dict):
            warnings.append("row not a dict — skipped")
            continue
        # Strike must be a positive finite number.
        if row.get("strike") is None:
            warnings.append("strike missing — skipped")
            continue
        try:
            strike_f = float(row["strike"])
        except (TypeError, ValueError):
            warnings.append(f"strike non-numeric: {row.get('strike')!r} — skipped")
            continue
        if not math.isfinite(strike_f) or strike_f <= 0:
            warnings.append(f"strike non-positive / non-finite: {strike_f} — skipped")
            continue

        prob_above = _safe_float("prob_above", row, row.get("prob_above"), warnings)
        prob_below = _safe_float("prob_below", row, row.get("prob_below"), warnings)
        if prob_below is None and prob_above is not None:
            prob_below = 1.0 - prob_above
        delta = _safe_float("delta", row, row.get("delta"), warnings)

        cleaned.append({
            "strike": strike_f,
            "prob_above": prob_above,
            "prob_below": prob_below,
            "delta": delta,
        })

    n = len(cleaned)
    if n < 1:
        return {
            "spot": spot,
            "n_strikes": 0,
            "method": "linear_interp_bisect",
            "prob_cones": [],
            "delta_cones": [],
            "warnings": warnings + ["no valid strikes post-filter"],
        }

    # ── 2. Sort by strike ────────────────────────────────────────────
    cleaned.sort(key=lambda r: r["strike"])
    strikes_sorted = [r["strike"] for r in cleaned]

    # ── 3. Build decreasing/increasing value arrays for interpolation ──
    prob_above_vals: list[float] = []
    prob_below_vals: list[float] = []
    delta_vals: list[float] = []
    nonmono_warned = False

    for r in cleaned:
        pa = r["prob_above"]
        pb = r["prob_below"]
        d = r["delta"]
        # Treat None as "skip from this cone; we'll handle missing by returning
        # None + warning outside the loop."
        prob_above_vals.append(pa if pa is not None else float("nan"))
        prob_below_vals.append(pb if pb is not None else float("nan"))
        delta_vals.append(d if d is not None else float("nan"))

    # Monotonicity guard: enforce decreasing on prob_above + delta by
    # worst-case take along the sorted sequence.  This silences
    # provider-data jitter (occasional NaN rows, sign flips near expiry).
    def _force_decreasing(arr: list[float], key: str) -> list[float]:
        nonlocal nonmono_warned
        fixed: list[float] = []
        prev: float | None = None
        for v in arr:
            if math.isnan(v):
                fixed.append(v)
                continue
            if prev is not None and v > prev:
                v = prev
                if not nonmono_warned:
                    warnings.append(f"{key} non-monotone — forced decreasing")
                    nonmono_warned = True
            fixed.append(v)
            prev = v
        return fixed

    def _force_increasing(arr: list[float]) -> list[float]:
        nonlocal nonmono_warned
        fixed: list[float] = []
        prev: float | None = None
        for v in arr:
            if math.isnan(v):
                fixed.append(v)
                continue
            if prev is not None and v < prev:
                v = prev
                if not nonmono_warned:
                    warnings.append("prob_below non-monotone — forced increasing")
                    nonmono_warned = True
            fixed.append(v)
            prev = v
        return fixed

    prob_above_vals = _force_decreasing(prob_above_vals, "prob_above")
    prob_below_vals = _force_increasing(prob_below_vals)
    delta_vals = _force_decreasing(delta_vals, "delta")

    # ── 4. Build prob_cones ──────────────────────────────────────────
    prob_cones: list[dict[str, Any]] = []
    for tp in target_probs:
        try:
            tp_f = float(tp)
        except (TypeError, ValueError):
            warnings.append(f"target_prob non-numeric: {tp!r} — skipped")
            continue
        if not math.isfinite(tp_f) or tp_f < 0.0 or tp_f > 1.0:
            warnings.append(f"target_prob out of [0,1]: {tp_f} — skipped")
            continue

        # Filter to non-NaN entries for this cone.
        pa_sub, pb_sub, ks_sub = [], [], []
        for k, pa, pb in zip(strikes_sorted, prob_above_vals, prob_below_vals, strict=False):
            if not math.isnan(pa) and not math.isnan(pb):
                pa_sub.append(pa)
                pb_sub.append(pb)
                ks_sub.append(k)

        if not ks_sub:
            cone_above = None
            cone_below = None
            warn_msg = "no usable prob values for this target"
        else:
            strike_above, warn_above = _interp_decreasing(ks_sub, pa_sub, tp_f)
            strike_below, warn_below = _interp_increasing(ks_sub, pb_sub, tp_f)
            join_warn = None
            if warn_above and warn_below:
                join_warn = f"above+below: {warn_above}; {warn_below}"
            elif warn_above:
                join_warn = f"above: {warn_above}"
            elif warn_below:
                join_warn = f"below: {warn_below}"
            # Round to 4 decimal places (matches the round() in
            # calc_probability_distribution).
            cone_above = round(strike_above, 4) if strike_above is not None else None
            cone_below = round(strike_below, 4) if strike_below is not None else None
            prob_cones.append({
                "target_prob": tp_f,
                "strike_above": cone_above,
                "strike_below": cone_below,
                "warning": join_warn,
            })
            continue  # next tp_f
        prob_cones.append({
            "target_prob": tp_f,
            "strike_above": cone_above,
            "strike_below": cone_below,
            "warning": warn_msg,
        })

    # ── 5. Build delta_cones ─────────────────────────────────────────
    #   strike_above = interp(target_delta) on (delta vs strike)
    #   strike_below = interp(1 - target_delta) on (delta vs strike)
    delta_cones: list[dict[str, Any]] = []
    for td in target_deltas:
        try:
            td_f = float(td)
        except (TypeError, ValueError):
            warnings.append(f"target_delta non-numeric: {td!r} — skipped")
            continue
        if not math.isfinite(td_f) or td_f < 0.0 or td_f > 1.0:
            warnings.append(f"target_delta out of [0,1]: {td_f} — skipped")
            continue

        # Filter to non-NaN delta entries.
        d_sub, ks_sub = [], []
        for k, d in zip(strikes_sorted, delta_vals, strict=False):
            if not math.isnan(d):
                d_sub.append(d)
                ks_sub.append(k)

        if not ks_sub:
            delta_cones.append({
                "target_delta": td_f,
                "strike_above": None,
                "strike_below": None,
                "warning": "no usable delta values for this target",
            })
            continue

        # Call-delta is decreasing in strike; target=td_f for the call above
        # (strike > ATM); 1 - td_f for the put below (strike < ATM, where
        # the put has delta = -td_f).
        strike_call_above, warn_above = _interp_decreasing(ks_sub, d_sub, td_f)
        strike_put_below, warn_below = _interp_decreasing(ks_sub, d_sub, 1.0 - td_f)
        join_warn = None
        if warn_above and warn_below:
            join_warn = f"above+below: {warn_above}; {warn_below}"
        elif warn_above:
            join_warn = f"above: {warn_above}"
        elif warn_below:
            join_warn = f"below: {warn_below}"
        delta_cones.append({
            "target_delta": td_f,
            "strike_above": round(strike_call_above, 4) if strike_call_above is not None else None,
            "strike_below": round(strike_put_below, 4) if strike_put_below is not None else None,
            "warning": join_warn,
        })

    return {
        "spot": round(spot, 4) if isinstance(spot, (int, float)) and math.isfinite(spot) else None,
        "n_strikes": n,
        "method": "linear_interp_bisect",
        "prob_cones": prob_cones,
        "delta_cones": delta_cones,
        "warnings": warnings,
    }


__all__ = [
    "compute_cone",
]
