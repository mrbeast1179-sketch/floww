"""
backend/tests/services/test_regime_opportunity.py

Opportunity Engine test profile (steal-list #8 — value 4 / effort 2)
====================================================================

This file pins the Opportunity Engine contract documented in
``backend/services/regime_opportunity.py``. Sixteen hand-verified cases:

    1.  test_full_inputs_bull_quiet → HIGH tier, debit_spread, BULL
    2.  test_full_inputs_bear_stressed → defensive_hedge, Panic, BEAR
    3.  test_classify_6_cell_grid_all_paths
    4.  test_regime_unknown_hmm_returns_none_and_warning
    5.  test_regime_unknown_band_returns_none_and_warning
    6.  test_opportunity_score_clamping_zero_floor
    7.  test_opportunity_score_clamping_ten_ceiling
    8.  test_opportunity_score_components_alignment_bonus_bull_positive_gamma
    9.  test_mean_rev_bonus_only_in_range_with_positive_gamma_iv_above_half
    10. test_vol_penalty_band_table_hand_verified
    11. test_arbitrate_range_bound_high_iv_yields_iron_condor_short_premium
    12. test_arbitrate_range_bound_low_iv_no_premium_selling_yields_wheel
    13. test_arbitrate_choppy_low_iv_yields_no_trade
    14. test_arbitrate_panic_yields_defensive_hedge_any_gamma
    15. test_malformed_inputs_do_not_crash_and_surface_warnings
    16. test_compute_top_level_orchestrator_assembles_dict
    17. test_inputs_not_a_dict_returns_no_trade_zero_score
    18. test_opportunity_tier_thresholds_hand_verified
"""

from __future__ import annotations

import math

import pytest

from services.regime_opportunity import (
    ALL_REGIMES,
    BIAS_DEFENSIVE,
    BIAS_LONG_PREMIUM,
    BIAS_SHORT_PREMIUM,
    GAMMA_NEG,
    GAMMA_POS,
    HMM_BEAR,
    HMM_BULL,
    HMM_RANGING,
    REGIME_CHOPPY,
    REGIME_DOWNTREND,
    REGIME_PANIC,
    REGIME_RANGE_BOUND,
    REGIME_TRENDING_HIGH_VOL,
    REGIME_TRENDING_LOW_VOL,
    RV_ACTIVE,
    RV_MILD,
    RV_QUIET,
    RV_STRESSED,
    TIER_HIGH,
    TIER_LOW,
    TIER_MED,
    TIER_WATCH,
    TT_BEAR_PUT_DEBIT,
    TT_CREDIT_SPREAD,
    TT_DEBIT_SPREAD,
    TT_DEFENSIVE_HEDGE,
    TT_IRON_CONDOR,
    TT_IRON_FLY,
    TT_NO_TRADE,
    TT_WHEEL_CSP,
    arbitrate_trade_idea,
    classify_regime,
    compute,
    compute_opportunity_score,
)

# ─────────────────────────────────────────────────────────────────────
# 1. End-to-end happy paths (top-level ``compute``)
# ─────────────────────────────────────────────────────────────────────


def test_full_inputs_bull_quiet_high_confidence_yields_high_tier_debit():
    """A clean bull trend in quiet vol should be a HIGH-opportunity BUY-play."""
    out = compute({
        "hmm_state": HMM_BULL,
        "hmm_confidence": 0.92,
        "rv_band": RV_QUIET,
        "iv_rank": 0.30,            # cheap
        "gamma_sign": GAMMA_POS,    # dealers absorbing (aligns with trend)
        "roc_5d": 0.015,            # +1.5% over 5 days
    })
    assert out["regime"] == REGIME_TRENDING_LOW_VOL
    assert out["direction"] == "BULL"
    assert out["trade_type"] == TT_DEBIT_SPREAD
    assert out["trade_bias"] == BIAS_LONG_PREMIUM
    assert out["opportunity_tier"] in (TIER_HIGH, TIER_MED)
    # live formula: 10*0.92 + 1.5*0.15 + 0.5*1 - 2*0.25 + 0
    # ≈ 9.2 + 0.225 + 0.5 - 0.5 = 9.425 → clamps to 9.43 → HIGH
    assert out["opportunity_score"] >= 7.5
    assert "Close if HMM flips" in out["invalidation"]
    # Components visible
    assert out["components"]["trend_component"] == 0.92
    assert out["components"]["vol_penalty"] == 0.25
    assert out["components"]["alignment_component"] == 1.0


def test_full_inputs_bear_stressed_high_iv_yields_panic_defensive_hedge():
    """Stress volatility on a bear regime = Panic → defensive only."""
    out = compute({
        "hmm_state": HMM_BEAR,
        "hmm_confidence": 0.85,
        "rv_band": RV_STRESSED,
        "iv_rank": 0.85,
        "gamma_sign": GAMMA_NEG,
        "roc_5d": -0.04,            # -4% over 5 days
    })
    assert out["regime"] == REGIME_PANIC
    assert out["direction"] == "BEAR"
    assert out["trade_type"] == TT_DEFENSIVE_HEDGE
    assert out["trade_bias"] == BIAS_DEFENSIVE
    # Trend-dominance invariant: a confident BEAR trend's 10·|trend|
    # contribution (8.5) + alignment (0.5) + momentum (0.6) only loses
    # -2.0 to maxed-out STRESSED vol_penalty, leaving a net ~7.6 → MED-or-
    # better tier. Pin the SCORE FLOOR (not the tier label, which can
    # change names with future palette refactors).
    assert out["opportunity_score"] >= 7.0, (
        f"BEAR+STRESSED+near-perfect alignment should clear MED (got "
        f"{out['opportunity_score']}, expected >= 7.0 — formula bug?)"
    )
    assert out["opportunity_tier"] in {TIER_HIGH, TIER_MED}


# ─────────────────────────────────────────────────────────────────────
# 2. 6-cell grid full-table walk
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hmm", "band", "expected_regime"),
    [
        # BULL row
        (HMM_BULL,    RV_QUIET,     REGIME_TRENDING_LOW_VOL),
        (HMM_BULL,    RV_MILD,      REGIME_TRENDING_HIGH_VOL),
        (HMM_BULL,    RV_ACTIVE,    REGIME_TRENDING_HIGH_VOL),
        (HMM_BULL,    RV_STRESSED,  REGIME_TRENDING_HIGH_VOL),
        # RANGING row
        (HMM_RANGING, RV_QUIET,     REGIME_RANGE_BOUND),
        (HMM_RANGING, RV_MILD,      REGIME_RANGE_BOUND),
        (HMM_RANGING, RV_ACTIVE,    REGIME_CHOPPY),
        (HMM_RANGING, RV_STRESSED,  REGIME_CHOPPY),
        # BEAR row
        (HMM_BEAR,    RV_QUIET,     REGIME_DOWNTREND),
        (HMM_BEAR,    RV_MILD,      REGIME_DOWNTREND),
        (HMM_BEAR,    RV_ACTIVE,    REGIME_DOWNTREND),
        (HMM_BEAR,    RV_STRESSED,  REGIME_PANIC),
    ],
)
def test_classify_6_cell_grid_all_paths(hmm, band, expected_regime):
    out = classify_regime(hmm, band)
    assert out["regime"] == expected_regime
    assert out["warnings"] == []


def test_classify_all_regimes_covered_by_grid_table():
    """The 6 regimes listed in ``ALL_REGIMES`` MUST all appear in the cartesian
    table — if a new regime is added via a roadmap patch without updating
    the grid, this asserts loudly.
    """
    hmm_states = (HMM_BULL, HMM_RANGING, HMM_BEAR)
    bands = (RV_QUIET, RV_MILD, RV_ACTIVE, RV_STRESSED)
    produced = {classify_regime(h, b)["regime"] for h in hmm_states for b in bands}
    missing = set(ALL_REGIMES) - produced
    assert not missing, (
        f"Regime(s) {missing} never produced by the 3×4 grid. "
        "Either expand the grid or update ALL_REGIMES."
    )


# ─────────────────────────────────────────────────────────────────────
# 3. Missing / unrecognised inputs → safe degradation
# ─────────────────────────────────────────────────────────────────────


def test_regime_unknown_hmm_returns_none_and_warning():
    out = classify_regime("SOMETHING_ELSE", RV_QUIET)
    assert out["regime"] is None
    assert any("hmm_state" in w for w in out["warnings"])


def test_regime_unknown_band_returns_none_and_warning():
    out = classify_regime(HMM_BULL, "VERY_VOLATILE")
    assert out["regime"] is None
    assert any("rv_band" in w for w in out["warnings"])


def test_regime_missing_both_returns_two_warnings():
    out = classify_regime(None, None)
    assert out["regime"] is None
    assert len(out["warnings"]) >= 2


def test_regime_band_missing_but_rv_value_resolves_band_by_threshold():
    """When the band string is missing but rv_value is supplied, classify
    uses the numeric-band mapping (mirrors realised_volatility.classify).
    """
    out = classify_regime(HMM_BEAR, None, rv_value=0.55)
    assert out["regime"] == REGIME_PANIC


def test_regime_unknown_rv_value_falls_back_to_none():
    out = classify_regime(HMM_BULL, None, rv_value="not-a-number")
    assert out["regime"] is None
    assert any("rv_value" in w for w in out["warnings"])


# ─────────────────────────────────────────────────────────────────────
# 4. Score formula boundaries
# ─────────────────────────────────────────────────────────────────────


def test_opportunity_score_clamping_zero_floor():
    """Max adverse combination: RANGING + STRESSED + wrong-way move +
    negative gamma (no alignment) → score falls to 0 (clamped)."""
    out = compute_opportunity_score(
        hmm_state=HMM_RANGING,
        hmm_confidence=0.10,    # any confidence in RANGING → trend_comp=0
        rv_band=RV_STRESSED,    # vol_penalty = 1.0 → -2.0
        iv_rank=0.10,           # below the 0.5 threshold for mean_rev
        gamma_sign=GAMMA_POS,   # RANGING+positive doesn't earn alignment
        roc_5d=-0.05,
    )
    # 10*0 + 1.5*0 + 0.5*0 - 2*1.0 + 0 = -2.0 → clamped to 0.0
    assert out["opportunity_score"] == 0.0
    assert out["opportunity_tier"] == TIER_LOW


def test_opportunity_score_clamping_ten_ceiling():
    """A perfect storm: bull + high conf + tailwind ROC + aligned gamma +
    quiet vol → beyond 10, clamped."""
    out = compute_opportunity_score(
        hmm_state=HMM_BULL,
        hmm_confidence=1.0,
        rv_band=RV_QUIET,
        iv_rank=0.20,
        gamma_sign=GAMMA_POS,
        roc_5d=0.20,            # momentum = clip(0.20*10, 0, 1) = 1.0
    )
    # 10*1 + 1.5*1 + 0.5*1 - 2*0.25 + 0 = 10 + 1.5 + 0.5 - 0.5 = 11.5 → 10
    assert out["opportunity_score"] == 10.0
    assert out["opportunity_tier"] == TIER_HIGH


def test_opportunity_score_components_alignment_bonus_only_bull_positive():
    """Alignment bonus = 1 only for BULL+positive_gamma OR BEAR+negative_gamma."""
    out_bull_pos = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.6, rv_band=RV_QUIET,
        iv_rank=0.3, gamma_sign=GAMMA_POS, roc_5d=0.0,
    )
    assert out_bull_pos["components"]["alignment_component"] == 1.0
    out_bull_neg = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.6, rv_band=RV_QUIET,
        iv_rank=0.3, gamma_sign=GAMMA_NEG, roc_5d=0.0,
    )
    assert out_bull_neg["components"]["alignment_component"] == 0.0
    out_bear_neg = compute_opportunity_score(
        hmm_state=HMM_BEAR, hmm_confidence=0.6, rv_band=RV_QUIET,
        iv_rank=0.3, gamma_sign=GAMMA_NEG, roc_5d=0.0,
    )
    assert out_bear_neg["components"]["alignment_component"] == 1.0


def test_mean_rev_bonus_only_in_range_with_positive_gamma_iv_above_half():
    """The sweet-spot: RANGING + positive_gamma + iv_rank >= 0.5 → mean_rev=1.0."""
    out = compute_opportunity_score(
        hmm_state=HMM_RANGING, hmm_confidence=0.5, rv_band=RV_QUIET,
        iv_rank=0.7, gamma_sign=GAMMA_POS, roc_5d=0.0,
    )
    assert out["components"]["mean_rev_component"] == 1.0
    # Below threshold
    out_mid = compute_opportunity_score(
        hmm_state=HMM_RANGING, hmm_confidence=0.5, rv_band=RV_QUIET,
        iv_rank=0.4, gamma_sign=GAMMA_POS, roc_5d=0.0,
    )
    assert out_mid["components"]["mean_rev_component"] == 0.5
    # Wrong gamma
    out_neg = compute_opportunity_score(
        hmm_state=HMM_RANGING, hmm_confidence=0.5, rv_band=RV_QUIET,
        iv_rank=0.7, gamma_sign=GAMMA_NEG, roc_5d=0.0,
    )
    assert out_neg["components"]["mean_rev_component"] == 0.0
    # Trending → no mean-reversion bonus regardless of iv
    out_trend = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.5, rv_band=RV_QUIET,
        iv_rank=0.9, gamma_sign=GAMMA_POS, roc_5d=0.0,
    )
    assert out_trend["components"]["mean_rev_component"] == 0.0


@pytest.mark.parametrize(
    ("band", "expected_penalty"),
    [
        (RV_QUIET,    0.25),
        (RV_MILD,     0.50),
        (RV_ACTIVE,   0.75),
        (RV_STRESSED, 1.00),
    ],
)
def test_vol_penalty_band_table_hand_verified(band, expected_penalty):
    out = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.0,  # zero out everything else
        rv_band=band, iv_rank=0.0, gamma_sign=None, roc_5d=0.0,
    )
    assert out["components"]["vol_penalty"] == expected_penalty


def test_opportunity_tier_thresholds_hand_verified():
    """Score tiers: ≥ 7.5 HIGH, ≥ 5.0 MED, ≥ 2.5 WATCH, else LOW."""
    # Construct a case that scores exactly within MED band (5.0..7.5)
    # raw_score = 10*0.5 + 1.5*0 + 0.5*0 - 2*0.25 + 0 = 4.5 → too low
    # raw_score = 10*0.6 + 1.5*0 + 0.5*0 - 2*0.25 + 0 = 5.5 → MED
    out_med = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.6, rv_band=RV_QUIET,
        iv_rank=0.2, gamma_sign=None, roc_5d=0.0,
    )
    assert 5.0 <= out_med["opportunity_score"] < 7.5
    assert out_med["opportunity_tier"] == TIER_MED
    # WATCH (raw=10*0.4 - 2*0.5 = 3.0 → tier WATCH)
    out_watch = compute_opportunity_score(
        hmm_state=HMM_BULL, hmm_confidence=0.4, rv_band=RV_MILD,
        iv_rank=0.2, gamma_sign=None, roc_5d=0.0,
    )
    # raw = 4.0 - 1.0 = 3.0 → WATCH
    assert 2.5 <= out_watch["opportunity_score"] < 5.0
    assert out_watch["opportunity_tier"] == TIER_WATCH


# ─────────────────────────────────────────────────────────────────────
# 5. Arbitration paths
# ─────────────────────────────────────────────────────────────────────


def test_arbitrate_range_bound_high_iv_yields_iron_condor_short_premium():
    idea = arbitrate_trade_idea(
        REGIME_RANGE_BOUND, GAMMA_POS, iv_rank=0.7, hmm_state=HMM_RANGING,
    )
    assert idea["direction"] == "NEUTRAL"
    assert idea["trade_type"] == TT_IRON_CONDOR
    assert idea["trade_bias"] == BIAS_SHORT_PREMIUM


def test_arbitrate_range_bound_low_iv_falls_back_to_wheel_csp():
    idea = arbitrate_trade_idea(
        REGIME_RANGE_BOUND, GAMMA_POS, iv_rank=0.2, hmm_state=HMM_RANGING,
    )
    assert idea["trade_type"] == TT_WHEEL_CSP
    assert idea["trade_bias"] == BIAS_SHORT_PREMIUM


def test_arbitrate_choppy_low_iv_yields_no_trade():
    idea = arbitrate_trade_idea(
        REGIME_CHOPPY, GAMMA_POS, iv_rank=0.20, hmm_state=HMM_RANGING,
    )
    assert idea["trade_type"] == TT_NO_TRADE
    assert idea["direction"] == "NEUTRAL"
    assert idea["trade_bias"] == BIAS_DEFENSIVE


def test_arbitrate_choppy_high_iv_yields_iron_fly():
    idea = arbitrate_trade_idea(
        REGIME_CHOPPY, GAMMA_POS, iv_rank=0.65, hmm_state=HMM_RANGING,
    )
    assert idea["trade_type"] == TT_IRON_FLY


def test_arbitrate_panic_yields_defensive_hedge_any_gamma():
    for g in (GAMMA_POS, GAMMA_NEG, None):
        idea = arbitrate_trade_idea(
            REGIME_PANIC, g, iv_rank=0.8, hmm_state=HMM_BEAR,
        )
        assert idea["trade_type"] == TT_DEFENSIVE_HEDGE
        assert idea["trade_bias"] == BIAS_DEFENSIVE
        assert "Re-evaluate" in idea["invalidation"]


def test_arbitrate_downtrend_pos_gamma_high_iv_credit_or_low_iv_debit():
    idea_high = arbitrate_trade_idea(
        REGIME_DOWNTREND, GAMMA_POS, iv_rank=0.7, hmm_state=HMM_BEAR,
    )
    assert idea_high["trade_type"] == TT_CREDIT_SPREAD
    assert idea_high["direction"] == "BEAR"
    assert idea_high["trade_bias"] == BIAS_SHORT_PREMIUM
    idea_low = arbitrate_trade_idea(
        REGIME_DOWNTREND, GAMMA_POS, iv_rank=0.3, hmm_state=HMM_BEAR,
    )
    assert idea_low["trade_type"] == TT_BEAR_PUT_DEBIT
    assert idea_low["trade_bias"] == BIAS_LONG_PREMIUM


def test_arbitrate_downtrend_neg_gamma_yields_bear_put_debit():
    idea = arbitrate_trade_idea(
        REGIME_DOWNTREND, GAMMA_NEG, iv_rank=0.5, hmm_state=HMM_BEAR,
    )
    assert idea["trade_type"] == TT_BEAR_PUT_DEBIT
    assert idea["trade_bias"] == BIAS_LONG_PREMIUM


def test_arbitrate_unknown_regime_yields_no_trade_with_warning():
    idea = arbitrate_trade_idea(None, GAMMA_POS, iv_rank=0.5, hmm_state=HMM_BULL)
    assert idea["trade_type"] == TT_NO_TRADE
    assert idea["direction"] == "NEUTRAL"
    assert any("regime" in w for w in idea["warnings"])


def test_invalidation_string_for_credit_spread_mentions_rv_bandshift():
    idea = arbitrate_trade_idea(
        REGIME_DOWNTREND, GAMMA_POS, iv_rank=0.6, hmm_state=HMM_BEAR,
    )
    assert idea["trade_type"] == TT_CREDIT_SPREAD
    assert "RV exceeds next band" in idea["invalidation"] or "band-shift" in idea["invalidation"]


def test_invalidation_string_for_long_premium_mentions_hmm_flip():
    idea = arbitrate_trade_idea(
        REGIME_TRENDING_LOW_VOL, GAMMA_POS, iv_rank=0.3, hmm_state=HMM_BULL,
    )
    assert idea["trade_type"] == TT_DEBIT_SPREAD
    assert "HMM flips" in idea["invalidation"]


# ─────────────────────────────────────────────────────────────────────
# 6. Malformed / missing input graceful paths
# ─────────────────────────────────────────────────────────────────────


def test_malformed_inputs_do_not_crash_and_surface_warnings():
    out = compute({
        "hmm_state": 12345,            # wrong type
        "hmm_confidence": "high",      # wrong type
        "rv_band": "totally_wrong",    # unknown band
        "iv_rank": [-1.5, 2.0],        # negative + overshoot
        "gamma_sign": 999,             # wrong type
        "roc_5d": "pump",
    })
    assert isinstance(out, dict)
    assert out["regime"] is None
    assert out["trade_type"] == TT_NO_TRADE
    assert out["opportunity_tier"] == TIER_LOW
    # At least 4 distinct input-shape warnings surfaced
    assert len(out["warnings"]) >= 4


def test_compute_top_level_orchestrator_assembles_dict():
    """A clean bull-quiet case must produce ALL documented keys."""
    out = compute({
        "hmm_state": HMM_BULL,
        "hmm_confidence": 0.80,
        "rv_band": RV_QUIET,
        "iv_rank": 0.25,
        "gamma_sign": GAMMA_POS,
        "roc_5d": 0.01,
    })
    expected_keys = {
        "regime", "opportunity_score", "opportunity_tier",
        "direction", "trade_type", "trade_bias", "invalidation",
        "components", "warnings",
    }
    assert set(out.keys()) == expected_keys
    assert set(out["components"].keys()) == {
        "trend_component", "momentum_component", "alignment_component",
        "vol_penalty", "mean_rev_component",
    }
    assert out["regime"] == REGIME_TRENDING_LOW_VOL


def test_compute_with_only_minimal_inputs_does_not_crash():
    out = compute({"hmm_state": HMM_BULL})
    assert isinstance(out, dict)
    assert out["regime"] is None, "Missing rv must give None regime"
    assert out["opportunity_tier"] == TIER_LOW
    assert out["trade_type"] == TT_NO_TRADE
    assert any("rv" in w for w in out["warnings"])


def test_inputs_not_a_dict_returns_no_trade_zero_score():
    out = compute("not a dict")    # type: ignore[arg-type]
    assert out["regime"] is None
    assert out["opportunity_score"] == 0.0
    assert out["opportunity_tier"] == TIER_LOW
    assert out["trade_type"] == TT_NO_TRADE
    assert "Inputs must be a dict" in out["invalidation"]
    assert out["warnings"] == ["inputs not a dict"]


def test_score_is_always_finite_and_nonnegative():
    """Belt-and-suspenders: no NaN/inf in the score for any null-feasible combo."""
    none_combos = [
        {"hmm_state": None, "hmm_confidence": None, "rv_band": None,
         "iv_rank": None, "gamma_sign": None, "roc_5d": None},
        {"hmm_state": HMM_BULL, "hmm_confidence": float("nan"),
         "rv_band": RV_QUIET, "iv_rank": 0.5, "gamma_sign": GAMMA_POS,
         "roc_5d": float("nan")},
    ]
    for inp in none_combos:
        out = compute(inp)
        assert math.isfinite(out["opportunity_score"])
        assert 0.0 <= out["opportunity_score"] <= 10.0
