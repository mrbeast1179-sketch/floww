"""
backend/services/regime_opportunity.py

Opportunity Engine — steal-list rank #8 (value 4 / effort 2)
==============================================================

A per-ticker DIRECTIONAL trade-idea layer that floww previously lacked.
Flowseeker's ``composite_flow_score`` ranks the *flow* environment but never
emits a ranked, risk-defined trade recommendation with a regime label +
invalidation. This engine maps (trend × realised-volatility) into a 6-cell
regime grid, computes an ``opportunity_score`` in [0, 10], and arbitrates
that regime + IV-rank + dealer-gamma-sign into a risk-defined trade-idea.

PURE-LOGIC: no yfinance calls, no DB writes, no logging side-effects. All
external I/O is owned by the route layer (``backend/routes/steal_three.py``)
which calls ``compute(inputs) → dict``.

Inputs accepted (all optional with safe defaults — missing inputs never crash
the engine, they just degrade tier/direction confidence)::

    {
        "hmm_state":         "TRENDING_BULL" | "RANGING" | "TRENDING_BEAR" | None,
        "hmm_confidence":    float in [0, 1],
        "rv_band":           "QUIET" | "MILD" | "ACTIVE" | "STRESSED" | None,
        "rv_value":          float (annualised, used when band absent),
        "iv_rank":           float in [0, 1]            (0 = cheap, 1 = rich),
        "skew_percentile":   float in [0, 1],
        "gamma_sign":        "positive_gamma" | "negative_gamma" | None,
        "roc_5d":            float (5-day rate-of-change, decimal),
    }

Output schema (``compute`` returns this dict verbatim)::

    {
        "regime":            str,   # one of the 6 cells (see below)
        "opportunity_score": float, # clamped [0, 10]
        "opportunity_tier":  "HIGH" | "MED" | "WATCH" | "LOW",
        "direction":         "BULL" | "BEAR" | "NEUTRAL",
        "trade_type":        one of "debit_spread" | "credit_spread" |
                             "iron_condor" | "iron_fly" | "wheel_csp" |
                             "wheel_cc"  | "long_call" | "long_put" |
                             "bear_put_debit" | "defensive_hedge" |
                             "no_trade",
        "trade_bias":        "long_premium" | "short_premium" | "defensive",
        "invalidation":      str,   # human-readable invalidation rule
        "components": {                # sub-scores, each clamped [0, 1]
            "trend_component":       float,
            "momentum_component":    float,
            "alignment_component":   float,
            "vol_penalty":           float,
            "mean_rev_component":    float,
        },
        "warnings":          list[str],   # any degradation messages
    }

6-CELL REGIME GRID (rows = HMM state, cols = RV band)::

                  QUIET      MILD       ACTIVE     STRESSED
    BULL      │ Trending    │ Trending  │ Trending │ ranges →  │
              │ Low-Vol     │ High-Vol  │ High-Vol │ overshoot │
              │ (the bull  │ (the bull │ (the bull │ DOWN as   │
              │ drift)     │ accelerates)│ pushes) │ RANGING+ACTIVE│
              ───────────────────────────────────────────────────────
    RANGING   │ Range       │ Range     │ Choppy   │ Choppy    │
              │ Bound       │ Bound     │          │           │
              ───────────────────────────────────────────────────────
    BEAR      │ Downtrend   │ Downtrend │ Downtrend│ Panic     │
              │             │ (heavy)   │ (rising  │           │
              │             │           │ vol)     │           │

  Final mapping (deterministic, see ``_classify_regime``):

      BULL × QUIET/MILD/ACTIVE         → "Trending Low-Vol"
                                          if QUIET else "Trending High-Vol"
      BULL × STRESSED                  → "Trending High-Vol"
                                          (treat as extreme acceleration)
      RANGING × QUIET/MILD             → "Range Bound"
      RANGING × ACTIVE/STRESSED        → "Choppy"
      BEAR × QUIET/MILD                → "Downtrend"
      BEAR × ACTIVE                    → "Downtrend"
      BEAR × STRESSED                  → "Panic"

opportunity_score formula (each sub-score clamped [0, 1], final score
clamped [0, 10])::

       score_raw
         = 10·|trend|
         + 1.5·momentum_bonus
         + 0.5·alignment_bonus
         − 2.0·vol_penalty
         + 1.0·mean_rev_bonus

    Where:
       |trend|           = hmm_confidence if state != RANGING, else 0
       momentum_bonus    = clip(sign(trend)·ROC_5d · 10, 0, 1)
       alignment_bonus   = 1 if gamma sign agrees with trend direction, else 0
       vol_penalty       = 0.25·QUIET + 0.50·MILD + 0.75·ACTIVE + 1.0·STRESSED
       mean_rev_bonus    = 1 if RANGING + positive_gamma + iv_rank >= 0.5
                              (premium selling sweet spot)
                           0.5 if RANGING + iv_rank in [0.3, 0.7)
                           0   otherwise

    opportunity_tier:
       score >= 7.5  → HIGH
       score >= 5.0  → MED
       score >= 2.5  → WATCH
       score <  2.5  → LOW

trade-idea arbitration (see ``_arbitrate_trade_idea``)::

    regime   |  gamma_sign     |  iv_rank  |  direction | trade_type
    ---------+-----------------+----------+------------+-----------
    Trending |  any gamma_sign  |  any     |  BULL      | debit_spread
    High-Vol |  positive_gamma |  >= 0.4  |  BULL      | debit_spread
    Trending |  negative_gamma |  any     |  BULL      | long_call
    High-Vol |  negative_gamma |  any     |  BULL      | debit_spread
    Low-Vol  |  positive_gamma |  any     |  BULL      | debit_spread
    Downtrend|  positive_gamma |  >= 0.5  |  BEAR      | credit_spread
    Downtrend|  positive_gamma |  <  0.5  |  BEAR      | bear_put_debit
    Downtrend|  negative_gamma |  any     |  BEAR      | put_debit_spread
    Panic    |  any            |  any     |  BEAR      | defensive_hedge
    Range    |  positive_gamma |  >= 0.5  |  NEUTRAL   | iron_condor
    Bound    |  positive_gamma |  <  0.5  |  NEUTRAL   | wheel_csp
    Range    |  positive_gamma |  <  0.5  |  NEUTRAL   | wheel_cc
    Choppy   |  positive_gamma |  >= 0.5  |  NEUTRAL   | iron_fly
    Choppy   |  any             |  <  0.5  |  NEUTRAL   | no_trade
    Choppy   |  negative_gamma  |  >= 0.5  |  NEUTRAL   | no_trade
    Range    |  negative_gamma  |  any     |  NEUTRAL   | defensive_hedge
    Bound    |  negative_gamma  |  any     |  NEUTRAL   | defensive_hedge
    Downtrend|  gamma unknown   |  any     |  NEUTRAL   | defensive_hedge
    Trending |  gamma unknown   |  any     |  NEUTRAL   | no_trade
    High-Vol |  gamma unknown   |  any     |  NEUTRAL   | no_trade
    Low-Vol  |  gamma unknown   |  any     |  NEUTRAL   | no_trade

    trade_bias:
       long_premium   → trade_type ∈ {long_call,long_put,debit_spread,
                                       bear_put_debit}
       short_premium  → trade_type ∈ {credit_spread,iron_condor,iron_fly,
                                       wheel_csp,wheel_cc}
       defensive      → trade_type = defensive_hedge || regime = "Panic"

    invalidation (human-readable rule string):
       debit_spread / bear_put_debit / long_call / long_put:
           "Close if HMM flips to opposite state with confidence ≥ 0.6"
       credit_spread / iron_condor / iron_fly / wheel_*:
           "Close if RV exceeds next band or HMM flips to opposite state"
       defensive_hedge:
           "Re-evaluate when RV drops below ACTIVE (dealer hedging abates)"

Steal intent: ``jwolberg_options-scanner`` — the jwolberg design intent
matches this 6-cell grid + opportunity_tier arbitration; the spec is
black-box (paid upstream UI), so we own the implementation verbatim off
of our published roadmap at ``docs/reports/2026-07-11-steal-list-integration-roadmap.md``.

Audit: ``backend/tests/services/test_regime_opportunity.py`` (16 cases —
the boundaries of the 6-cell grid, the formula hand-verified, arbitration
gamma+IV-rank, and the malformed-input / missing-signal graceful paths).
"""

from __future__ import annotations

import math
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Regime labels + enums (strings baked to engine contract)
# ─────────────────────────────────────────────────────────────────────

REGIME_TRENDING_LOW_VOL = "Trending Low-Vol"
REGIME_TRENDING_HIGH_VOL = "Trending High-Vol"
REGIME_RANGE_BOUND = "Range Bound"
REGIME_CHOPPY = "Choppy"
REGIME_DOWNTREND = "Downtrend"
REGIME_PANIC = "Panic"

ALL_REGIMES: tuple[str, ...] = (
    REGIME_TRENDING_LOW_VOL,
    REGIME_TRENDING_HIGH_VOL,
    REGIME_RANGE_BOUND,
    REGIME_CHOPPY,
    REGIME_DOWNTREND,
    REGIME_PANIC,
)

# HMM states hmm_regime.GaussianHMMRegime.classify() emits
HMM_BULL = "TRENDING_BULL"
HMM_RANGING = "RANGING"
HMM_BEAR = "TRENDING_BEAR"

# RV bands services/realised_volatility.classify() emits
RV_QUIET = "QUIET"
RV_MILD = "MILD"
RV_ACTIVE = "ACTIVE"
RV_STRESSED = "STRESSED"

# Dealer gamma-sign advanced_analytics.calc_gamma_flip_levels emits
GAMMA_POS = "positive_gamma"
GAMMA_NEG = "negative_gamma"

# Tier labels (mirrors the composite_flow_score palette anchors)
TIER_HIGH = "HIGH"
TIER_MED = "MED"
TIER_WATCH = "WATCH"
TIER_LOW = "LOW"
TIER_SCORE_HIGH = 7.5
TIER_SCORE_MED = 5.0
TIER_SCORE_WATCH = 2.5

# trade_types & trade_bias
TT_DEBIT_SPREAD = "debit_spread"
TT_CREDIT_SPREAD = "credit_spread"
TT_IRON_CONDOR = "iron_condor"
TT_IRON_FLY = "iron_fly"
TT_WHEEL_CSP = "wheel_csp"
TT_WHEEL_CC = "wheel_cc"
TT_LONG_CALL = "long_call"
TT_LONG_PUT = "long_put"
TT_BEAR_PUT_DEBIT = "bear_put_debit"
TT_DEFENSIVE_HEDGE = "defensive_hedge"
TT_NO_TRADE = "no_trade"

BIAS_LONG_PREMIUM = "long_premium"
BIAS_SHORT_PREMIUM = "short_premium"
BIAS_DEFENSIVE = "defensive"

# trade_types that are long-premium
_LONG_PREMIUM_TYPES: frozenset[str] = frozenset({
    TT_DEBIT_SPREAD,
    TT_LONG_CALL,
    TT_LONG_PUT,
    TT_BEAR_PUT_DEBIT,
})
# trade_types that are short-premium
_SHORT_PREMIUM_TYPES: frozenset[str] = frozenset({
    TT_CREDIT_SPREAD,
    TT_IRON_CONDOR,
    TT_IRON_FLY,
    TT_WHEEL_CSP,
    TT_WHEEL_CC,
})


# ─────────────────────────────────────────────────────────────────────
# Defensive extractors — coerce malformed inputs to safe defaults
# ─────────────────────────────────────────────────────────────────────


def _norm_hmm(state: Any) -> str | None:
    """Coerce an HMM state string to one of our three constants, else None."""
    if state is None:
        return None
    s = str(state).upper().strip()
    if s == HMM_BULL:
        return HMM_BULL
    if s == HMM_RANGING:
        return HMM_RANGING
    if s == HMM_BEAR:
        return HMM_BEAR
    return None


def _norm_rv_band(band: Any, rv_value: Any) -> tuple[str | None, list[str]]:
    """Coerce RV band — fall back to numeric mapping if band missing.

    Mirrors the band boundaries used in ``backend/services/realised_volatility.py``:
      QUIET    < 0.10
      MILD     0.10..0.20
      ACTIVE   0.20..0.40
      STRESSED ≥ 0.40
    Returns ``(band, warnings)``.
    """
    warnings: list[str] = []
    if band is not None and str(band).upper().strip() in {
        RV_QUIET, RV_MILD, RV_ACTIVE, RV_STRESSED,
    }:
        return str(band).upper().strip(), warnings
    if rv_value is None:
        warnings.append("rv_band and rv_value both missing")
        return None, warnings
    try:
        v = float(rv_value)
    except (TypeError, ValueError):
        warnings.append("rv_value not numeric")
        return None, warnings
    if v < 0.10:
        return RV_QUIET, warnings
    if v < 0.20:
        return RV_MILD, warnings
    if v < 0.40:
        return RV_ACTIVE, warnings
    return RV_STRESSED, warnings


def _norm_unit(value: Any, name: str, warnings: list[str]) -> float:
    """Coerce a [0, 1] unit-valued float — clamp negatives + overshoots.

    NaN and +inf/-inf inputs are coerced to 0.0 with a warning so they
    never propagate into the score formula (where Python's ``min``/``max``
    pass-through NaN under IEEE-754 semantics).
    """
    if value is None:
        warnings.append(f"{name} missing")
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{name} not numeric")
        return 0.0
    if not math.isfinite(v):
        warnings.append(f"{name} not finite (NaN/inf) — coerced to 0")
        return 0.0
    if v < 0.0:
        warnings.append(f"{name} clamped from {v} to 0")
        return 0.0
    if v > 1.0:
        warnings.append(f"{name} clamped from {v} to 1")
        return 1.0
    return v


def _norm_gamma(sign: Any, warnings: list[str] | None = None) -> str | None:
    """Coerce gamma-sign to GAMMA_POS / GAMMA_NEG / None.

    Symmetric with ``_norm_unit`` / ``_norm_roc``: type-mismatch and
    unrecognised-token cases append warnings so callers (esp. ``compute``)
    can surface them in the response. The optional ``warnings`` param
    keeps backward-compat for direct unit-test callers.
    """
    if sign is None:
        if warnings is not None:
            warnings.append("gamma_sign missing")
        return None
    if not isinstance(sign, (str, bytes)):
        if warnings is not None:
            warnings.append(f"gamma_sign not a string (got {type(sign).__name__})")
        return None
    s = str(sign).lower().strip()
    if s == GAMMA_POS:
        return GAMMA_POS
    if s == GAMMA_NEG:
        return GAMMA_NEG
    if warnings is not None:
        warnings.append(f"gamma_sign unrecognised token: {s!r}")
    return None


def _norm_roc(roc: Any, warnings: list[str]) -> float:
    """ROC-5d as decimal (e.g. 0.02 = +2%). No clamp — momentum can be very
    negative. NaN/inf are coerced to 0.0 with a warning so they do not
    propagate into ``momentum_component`` (which gates on ``roc > 0.0`` —
    NaN-false-pass would otherwise dead-arm the bonus).
    """
    if roc is None:
        warnings.append("roc_5d missing")
        return 0.0
    try:
        v = float(roc)
    except (TypeError, ValueError):
        warnings.append("roc_5d not numeric")
        return 0.0
    if not math.isfinite(v):
        warnings.append("roc_5d not finite (NaN/inf) — coerced to 0")
        return 0.0
    return v


# ─────────────────────────────────────────────────────────────────────
# Regime classification (the 6-cell grid)
# ─────────────────────────────────────────────────────────────────────


def classify_regime(hmm_state: Any, rv_band: Any, rv_value: Any = None) -> dict[str, Any]:
    """Map ``(hmm_state, rv_band [, rv_value])`` into one of the 6 cells.

    Returns ``{"regime": str|None, "warnings": list[str]}``.
    Conservative: if either input is missing the regime is ``None`` and
    the route layer must surface a ``"warming"``-style fallback.
    """
    warnings: list[str] = []
    state = _norm_hmm(hmm_state)
    if state is None:
        warnings.append("hmm_state missing or unrecognised")
    band, more_warnings = _norm_rv_band(rv_band, rv_value)
    warnings.extend(more_warnings)
    if state is None or band is None:
        return {"regime": None, "warnings": warnings}

    if state == HMM_BULL:
        if band == RV_QUIET:
            return {"regime": REGIME_TRENDING_LOW_VOL, "warnings": warnings}
        # BULL + MILD / ACTIVE / STRESSED → High-Vol bucket
        return {"regime": REGIME_TRENDING_HIGH_VOL, "warnings": warnings}

    if state == HMM_RANGING:
        if band in (RV_QUIET, RV_MILD):
            return {"regime": REGIME_RANGE_BOUND, "warnings": warnings}
        return {"regime": REGIME_CHOPPY, "warnings": warnings}

    # BEAR
    if band == RV_STRESSED:
        return {"regime": REGIME_PANIC, "warnings": warnings}
    return {"regime": REGIME_DOWNTREND, "warnings": warnings}


# ─────────────────────────────────────────────────────────────────────
# Opportunity score formula
# ─────────────────────────────────────────────────────────────────────


def _clip01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return float(v)


_V_PENALTY_BY_BAND: dict[str, float] = {
    RV_QUIET: 0.25,
    RV_MILD: 0.50,
    RV_ACTIVE: 0.75,
    RV_STRESSED: 1.0,
}


def compute_opportunity_score(
    hmm_state: Any,
    hmm_confidence: Any,
    rv_band: Any,
    iv_rank: Any,
    gamma_sign: Any,
    roc_5d: Any,
    rv_value: Any = None,
) -> dict[str, Any]:
    """Compute ``opportunity_score`` (clamped [0, 10]) and its 5 components.

    Each component is in [0, 1] and surfaces in ``"components"`` for the
    route layer / Heatseeker badges. The tier label is the human-friendly
    collapse of the [0, 10] score into TRAFFIC-LIGHT bands.
    """
    warnings: list[str] = []
    state = _norm_hmm(hmm_state)
    band, more_warnings = _norm_rv_band(rv_band, rv_value)
    warnings.extend(more_warnings)
    confidence = _norm_unit(hmm_confidence, "hmm_confidence", warnings)
    iv = _norm_unit(iv_rank, "iv_rank", warnings)
    gamma = _norm_gamma(gamma_sign, warnings)
    roc = _norm_roc(roc_5d, warnings)

    # |trend|: trend confidence *if* state is not RANGING, else 0
    trend_component = 0.0
    if state is not None and state != HMM_RANGING:
        trend_component = confidence

    # momentum_bonus: direction-aware, scaled by ROC magnitude
    #   if state == RANGING OR no state → 0
    #   sign(trend) == +1 for BULL, -1 for BEAR
    #   momentum = clip(sign·ROC·10, 0, 1)  — a 10% up move on a bull
    #   trend scores 1.0; a -10% move scores 0.0.
    momentum_component = 0.0
    if state == HMM_BULL and roc > 0.0:
        momentum_component = _clip01(roc * 10.0)
    elif state == HMM_BEAR and roc < 0.0:
        momentum_component = _clip01((-roc) * 10.0)

    # alignment_bonus: gamma sign agrees with trend direction
    alignment_component = 0.0
    if state == HMM_BULL and gamma == GAMMA_POS or state == HMM_BEAR and gamma == GAMMA_NEG:
        alignment_component = 1.0
    elif state == HMM_RANGING and gamma is not None:
        # In a range, alignment is always neutral — premium selling benefits
        # from either polarity, but we don't reward it as alignment here.
        alignment_component = 0.0

    # vol_penalty
    vol_penalty = _V_PENALTY_BY_BAND.get(band or "", 0.5)
    # If band unknown, use the median penalty to avoid over- or under-credit
    # missing inputs.

    # mean_rev_bonus: sweet-spot for premium selling in ranges
    mean_rev_component = 0.0
    if state == HMM_RANGING and gamma == GAMMA_POS:
        if iv >= 0.5:
            mean_rev_component = 1.0
        elif iv >= 0.3:
            mean_rev_component = 0.5

    raw_score = (
        10.0 * trend_component
        + 1.5 * momentum_component
        + 0.5 * alignment_component
        - 2.0 * vol_penalty
        + 1.0 * mean_rev_component
    )
    score = max(0.0, min(10.0, float(round(raw_score, 2))))

    if score >= TIER_SCORE_HIGH:
        tier = TIER_HIGH
    elif score >= TIER_SCORE_MED:
        tier = TIER_MED
    elif score >= TIER_SCORE_WATCH:
        tier = TIER_WATCH
    else:
        tier = TIER_LOW

    return {
        "opportunity_score": score,
        "opportunity_tier": tier,
        "components": {
            "trend_component": float(round(trend_component, 3)),
            "momentum_component": float(round(momentum_component, 3)),
            "alignment_component": float(round(alignment_component, 3)),
            "vol_penalty": float(round(vol_penalty, 3)),
            "mean_rev_component": float(round(mean_rev_component, 3)),
        },
        "warnings": warnings,
    }


# ─────────────────────────────────────────────────────────────────────
# Trade-idea arbitration
# ─────────────────────────────────────────────────────────────────────


def _direction_from_state(state: str | None) -> str:
    if state is None:
        return "NEUTRAL"
    if state == HMM_BULL:
        return "BULL"
    if state == HMM_BEAR:
        return "BEAR"
    return "NEUTRAL"


def _invalidation_for(trade_type: str, state: str | None) -> str:
    if state is None:
        return "Insufficient signal — re-check inputs"
    if trade_type in (TT_DEBIT_SPREAD, TT_BEAR_PUT_DEBIT,
                      TT_LONG_CALL, TT_LONG_PUT):
        return (
            f"Close if HMM flips to opposite state with confidence ≥ 0.60 "
            f"(currently {state})"
        )
    if trade_type in (TT_CREDIT_SPREAD, TT_IRON_CONDOR, TT_IRON_FLY,
                      TT_WHEEL_CSP, TT_WHEEL_CC):
        return (
            "Close if RV exceeds next band (band-shift would invalidate "
            "premium-selling edge) or HMM flips to opposite state"
        )
    if trade_type == TT_DEFENSIVE_HEDGE:
        return (
            "Re-evaluate when RV drops below ACTIVE (dealer hedging "
            "pressure abates)"
        )
    return "Re-evaluate when regime changepoint confidence > 0.60"


def arbitrate_trade_idea(
    regime: str | None,
    gamma_sign: Any,
    iv_rank: Any,
    hmm_state: Any = None,
) -> dict[str, Any]:
    """Map ``(regime, gamma_sign, iv_rank[, hmm_state])`` → trade-idea.

    Returns ``{direction, trade_type, trade_bias, invalidation}``.
    When the regime is missing/unrecognised, falls back to ``no_trade``
    with ``NEUTRAL`` direction so the route layer doesn't fabricate a
    recommendation off of insufficient signal.
    """
    warnings: list[str] = []
    gamma = _norm_gamma(gamma_sign, warnings)
    if gamma is None:
        warnings.append("gamma_sign missing — arbitration degraded")
    iv = _norm_unit(iv_rank, "iv_rank", warnings)
    state = _norm_hmm(hmm_state)
    direction = _direction_from_state(state)

    trade_type = TT_NO_TRADE
    if regime == REGIME_TRENDING_LOW_VOL:
        # Quiet bull drift — debit spread fits best
        trade_type = TT_DEBIT_SPREAD
    elif regime == REGIME_TRENDING_HIGH_VOL:
        # High-vol bull — both gamma polarities resolve to debit-spread
        # (gamma-pos: trend may snap, gamma-neg: breakout extension).
        # See docstring arbitration table for full rationale.
        trade_type = TT_DEBIT_SPREAD
    elif regime == REGIME_DOWNTREND:
        if gamma == GAMMA_POS:
            trade_type = TT_CREDIT_SPREAD if iv >= 0.5 else TT_BEAR_PUT_DEBIT
        elif gamma == GAMMA_NEG:
            trade_type = TT_BEAR_PUT_DEBIT
        else:
            # gamma unknown → conservative credit on downtrend for premium capture
            trade_type = TT_CREDIT_SPREAD if iv >= 0.5 else TT_BEAR_PUT_DEBIT
    elif regime == REGIME_PANIC:
        trade_type = TT_DEFENSIVE_HEDGE
    elif regime == REGIME_RANGE_BOUND:
        # direction defaulted to NEUTRAL by _direction_from_state(RANGING)
        if gamma == GAMMA_POS and iv >= 0.5:
            trade_type = TT_IRON_CONDOR
        elif gamma == GAMMA_POS:
            trade_type = TT_WHEEL_CSP
        else:
            # gamma unknown/negative in range → tight iron condor / no_trade
            trade_type = TT_IRON_CONDOR if iv >= 0.5 else TT_NO_TRADE
    elif regime == REGIME_CHOPPY:
        # direction defaulted to NEUTRAL by _direction_from_state(RANGING)
        if gamma == GAMMA_POS and iv >= 0.5:
            trade_type = TT_IRON_FLY
        else:
            # Choppy + cheap IV → no clean premium-selling edge
            trade_type = TT_NO_TRADE
    else:
        # regime missing or unrecognised
        warnings.append("regime unknown — defaulting to no_trade")
        direction = "NEUTRAL"
        trade_type = TT_NO_TRADE

    if trade_type in _LONG_PREMIUM_TYPES:
        bias = BIAS_LONG_PREMIUM
    elif trade_type in _SHORT_PREMIUM_TYPES:
        bias = BIAS_SHORT_PREMIUM
    else:
        # Everything else is defensive (DEFENSIVE_HEDGE or NO_TRADE).
        bias = BIAS_DEFENSIVE

    invalidation = _invalidation_for(trade_type, state)

    return {
        "direction": direction,
        "trade_type": trade_type,
        "trade_bias": bias,
        "invalidation": invalidation,
        "warnings": warnings,
    }


# ─────────────────────────────────────────────────────────────────────
# Top-level orchestrator
# ─────────────────────────────────────────────────────────────────────


def compute(inputs: dict[str, Any]) -> dict[str, Any]:
    """End-to-end opportunity computation — single entry point for the route.

    Accepts a dict shaped like::

        {"hmm_state": ..., "hmm_confidence": ..., "rv_band": ...,
         "rv_value": ..., "iv_rank": ..., "skew_percentile": ...,
         "gamma_sign": ..., "roc_5d": ...}

    Missing keys are tolerated (degraded tier, no crash).
    Returns the assembled dict documented at the top of this module.
    """
    if not isinstance(inputs, dict):
        return {
            "regime": None,
            "opportunity_score": 0.0,
            "opportunity_tier": TIER_LOW,
            "direction": "NEUTRAL",
            "trade_type": TT_NO_TRADE,
            "trade_bias": BIAS_DEFENSIVE,
            "invalidation": "Inputs must be a dict",
            "components": {
                "trend_component": 0.0,
                "momentum_component": 0.0,
                "alignment_component": 0.0,
                "vol_penalty": 0.5,
                "mean_rev_component": 0.0,
            },
            "warnings": ["inputs not a dict"],
        }

    regime_out = classify_regime(
        inputs.get("hmm_state"),
        inputs.get("rv_band"),
        inputs.get("rv_value"),
    )
    score_out = compute_opportunity_score(
        hmm_state=inputs.get("hmm_state"),
        hmm_confidence=inputs.get("hmm_confidence"),
        rv_band=inputs.get("rv_band"),
        iv_rank=inputs.get("iv_rank"),
        gamma_sign=inputs.get("gamma_sign"),
        roc_5d=inputs.get("roc_5d"),
        rv_value=inputs.get("rv_value"),
    )
    idea_out = arbitrate_trade_idea(
        regime_out["regime"],
        inputs.get("gamma_sign"),
        inputs.get("iv_rank"),
        hmm_state=inputs.get("hmm_state"),
    )

    warnings: list[str] = []
    warnings.extend(regime_out.get("warnings", []))
    warnings.extend(score_out.get("warnings", []))
    warnings.extend(idea_out.get("warnings", []))

    return {
        "regime": regime_out["regime"],
        "opportunity_score": score_out["opportunity_score"],
        "opportunity_tier": score_out["opportunity_tier"],
        "direction": idea_out["direction"],
        "trade_type": idea_out["trade_type"],
        "trade_bias": idea_out["trade_bias"],
        "invalidation": idea_out["invalidation"],
        "components": score_out["components"],
        "warnings": warnings,
    }


__all__ = [
    "compute",
    "classify_regime",
    "compute_opportunity_score",
    "arbitrate_trade_idea",
    # regime labels
    "REGIME_TRENDING_LOW_VOL", "REGIME_TRENDING_HIGH_VOL",
    "REGIME_RANGE_BOUND", "REGIME_CHOPPY",
    "REGIME_DOWNTREND", "REGIME_PANIC", "ALL_REGIMES",
    # hmm / rv / gamma enums
    "HMM_BULL", "HMM_RANGING", "HMM_BEAR",
    "RV_QUIET", "RV_MILD", "RV_ACTIVE", "RV_STRESSED",
    "GAMMA_POS", "GAMMA_NEG",
    # tiers
    "TIER_HIGH", "TIER_MED", "TIER_WATCH", "TIER_LOW",
    # trade_types / bias
    "TT_DEBIT_SPREAD", "TT_CREDIT_SPREAD", "TT_IRON_CONDOR", "TT_IRON_FLY",
    "TT_WHEEL_CSP", "TT_WHEEL_CC",
    "TT_LONG_CALL", "TT_LONG_PUT", "TT_BEAR_PUT_DEBIT",
    "TT_DEFENSIVE_HEDGE", "TT_NO_TRADE",
    "BIAS_LONG_PREMIUM", "BIAS_SHORT_PREMIUM", "BIAS_DEFENSIVE",
]
