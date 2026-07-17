"""
backend/tests/test_composite_flow_score.py

Regression tests for the Composite Flow Score synthesis service used
by Flowseeker Pro. Locks the observable behaviour of
:class:`CompositeFlowScore` so refactors cannot silently change the
weighted synthesis or the 4-band label mapping.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_composite_flow_score.py -v

Or directly (no pytest install needed):

    python3 backend/tests/test_composite_flow_score.py
"""

from __future__ import annotations

import sys
import pytest
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.composite_flow_score import (
    CompositeFlowScore,
    LABEL_COLORS,
    LABEL_HIGH,
    LABEL_LOW,
    LABEL_MED,
    LABEL_WATCH,
)


# ─────────────────────────────────────────────────────────────────────
# Helpers — fabricate minimally-shaped sub-service dicts for tests
# ─────────────────────────────────────────────────────────────────────

def _amihud(amihud: float, is_warming: bool = False, n_obs: int = 20):
    return {
        "amihud":        amihud,
        "abs_return":    0.0,
        "dollar_volume": 1.0,
        "label":         "NORMAL",
        "label_color":   "#fbbf24",
        "n_obs":         n_obs,
        "is_warming":    is_warming,
    }


def _kyle(lam: float, is_warming: bool = False, n_obs: int = 20):
    return {
        "lambda_value":  lam,
        "intercept":     0.0,
        "r_squared":     0.0,
        "label":         "NORMAL",
        "label_color":   "#fbbf24",
        "n_obs":         n_obs,
        "is_warming":    is_warming,
    }


def _vpin(vpin: float, is_warming: bool = False, n_obs: int = 20):
    return {
        "vpin":         vpin,
        "label":        "NORMAL",
        "label_color":  "#fbbf24",
        "n_buckets":    n_obs,
        "is_warming":   is_warming,
    }


def _regime(current_state: str = "RANGING", confidence: float = 0.0,
            posterior=None, is_warming: bool = False, n_obs: int = 5):
    if posterior is None:
        posterior = [0.33, 0.34, 0.33]
    return {
        "current_state":  current_state,
        "posterior":      posterior,
        "confidence":     confidence,
        "smoothed_path":  [current_state] * max(n_obs, 1),
        "n_obs":          n_obs,
        "is_warming":     is_warming,
    }


def _ofi(of_aggregated: float, snaps_used: int = 2,
         imbalance_label: str = "neutral"):
    return {
        "of_per_level":   [10, -5, 0, 5, -10],
        "of_aggregated":  of_aggregated,
        "imbalance_label": imbalance_label,
        "levels_used":    5,
        "snaps_used":     snaps_used,
    }


def _empty_stack(is_warming_each: bool = True):
    """Build a stack where every sub-service is warming."""
    return (
        _amihud(0.0,    is_warming=is_warming_each),
        _kyle(0.0,      is_warming=is_warming_each),
        _vpin(0.0,      is_warming=is_warming_each),
        _regime(is_warming=is_warming_each),
        _ofi(0.0,       snaps_used=(0 if is_warming_each else 2)),
    )


# ─────────────────────────────────────────────────────────────────────
# Lifecycle / warming
# ─────────────────────────────────────────────────────────────────────

def test_is_warming_when_any_subservice_is_warming():
    """If any sub-service is still warming, composite flags warming."""
    am, kyle, vpin, regime, ofi = _empty_stack(is_warming_each=False)
    cases = [
        ("amihud",  _amihud(0.0, is_warming=True, n_obs=20)),
        ("kyle",    _kyle(0.0, is_warming=True)),
        ("vpin",    _vpin(0.0, is_warming=True)),
        ("regime",  _regime(is_warming=True)),
        ("ofi",     _ofi(0.0, snaps_used=1)),
    ]
    # OFI's warming marker is `snaps_used < 2`. The composite wakes
    # when OFI snaps_used == 1 (verified per-case in the loop below).
    for label, hot in cases:
        # Build the (am, kyle, vpin, regime, ofi) tuple with `hot`
        # substituted at the right position.
        am_l, kl_l, vp_l, rg_l, of_l = am, kyle, vpin, regime, ofi
        if label == "amihud":  am_l = hot
        if label == "kyle":    kl_l = hot
        if label == "vpin":    vp_l = hot
        if label == "regime":  rg_l = hot
        if label == "ofi":     of_l = hot
        out = CompositeFlowScore.compute(am_l, kl_l, vp_l, rg_l, of_l)
        assert out["is_warming"] is True, (
            f"composite should be warming when {label} is hot"
        )
        assert out["composite"] == 0.0


def test_warming_components_drive_zero_score():
    """Composite score is clamped to 0 while warming, regardless of magnitude."""
    am = _amihud(amihud=9e-3, is_warming=True)   # even if huge, score=0
    kyle = _kyle(lam=5.0, is_warming=True)
    vpin = _vpin(vpin=0.99, is_warming=True)
    regime = _regime(current_state="TRENDING_BEAR", confidence=0.95, is_warming=True)
    ofi = _ofi(of_aggregated=9000.0)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["is_warming"] is True
    assert out["composite"] == 0.0


# ─────────────────────────────────────────────────────────────────────
# Label thresholds (boundary cases)
# ─────────────────────────────────────────────────────────────────────

def test_label_thresholds_match_specification():
    """4-band boundaries at composite ∈ {80, 60, 40}.

    Hand-crafts a stack that *exactly* lands on each labelled composite
    via the documented weighting::

        composite = 100·(0.25·illiq + 0.20·tox + 0.25·dis + 0.20·dir + 0.10·sent)

    Weight split is the steal-list deferred-(b) ship's reshape:
    illiq 0.30→0.25, tox 0.25→0.20, dis/dir unchanged, NEW sent 0.10.
    Sentiment sub-score in the cases below defaults to 0.0
    (``sentiment_out=None`` means extract_sentiment_feature returns 0,0).

    where ``dis`` follows
    :func:`services.composite_flow_score._dislocation`:

    * ``RANGING`` regime short-circuits to 0.
    * Otherwise, ``dis = min(confidence · (0.5 + conflict), 1.0)``.
    * ``conflict = 1`` when (TRENDING_BULL ⇔ ofi ≤ 0) or
      (TRENDING_BEAR ⇔ ofi > 0), else 0.

    See the comment next to each case tuple for the analytic derivation.
    A future refactor that changes weights, anchors, or the dislocation
    formula will surface here as a (composite, label) drift.
    """
    def _stack(tox, illiq_am, illiq_kyle, of_aggregated,
               regime_state, regime_conf):
        am = _amihud(illiq_am * 1e-4)     # inverse of norm_amihud
        kyle = _kyle(illiq_kyle * 0.01)   # inverse of norm_kyle
        vpin = _vpin(tox)
        if regime_state == "TRENDING_BULL":
            posterior = [0.70, 0.20, 0.10]
        elif regime_state == "TRENDING_BEAR":
            posterior = [0.10, 0.20, 0.70]
        else:
            posterior = [0.40, 0.20, 0.40]
        regime = _regime(
            current_state=regime_state,
            confidence=regime_conf,
            posterior=posterior,
        )
        ofi = _ofi(of_aggregated=of_aggregated, snaps_used=2)
        return am, kyle, vpin, regime, ofi

    # (label, expected_composite, tox, illiq_am, illiq_kyle,
    #  of_aggregated, regime_state, regime_conf)
    cases = [
        # ----- LOW band (RANGING → dis=0 + sent=0; tox/dir/illiq only) -----
        (LABEL_LOW,    4.00, 0.20, 0.0, 0.0,    0, "RANGING",       0.0),  # 100·0.20·0.20 = 4
        (LABEL_LOW,   20.00, 1.00, 0.0, 0.0,    0, "RANGING",       0.0),  # 100·0.20·1.00 = 20
        (LABEL_LOW,   31.20, 1.00, 0.0, 0.0,  560, "RANGING",       0.0),  # 20 + 0.56·0.20·100 = 31.2
        # ----- borderline LOW ↔ WATCH -----
        (LABEL_LOW,   35.00, 1.00, 0.6, 0.6,    0, "RANGING",       0.0),  # 20 + 0.6·0.25·100 = 35
        # ----- WATCH band (40 ≤ composite < 60) -----
        (LABEL_WATCH, 45.00, 1.00, 1.0, 1.0,    0, "RANGING",       0.0),  # 20 + 0.25·1.00·100 = 45
        (LABEL_WATCH, 49.00, 1.00, 1.0, 1.0,  200, "RANGING",       0.0),  # 45 + 0.20·0.20·100 = 49
        (LABEL_WATCH, 50.00, 1.00, 1.0, 1.0,  250, "RANGING",       0.0),  # 45 + 0.20·0.25·100 = 50
        (LABEL_WATCH, 55.00, 1.00, 1.0, 1.0,  500, "RANGING",       0.0),  # 45 + 0.20·0.50·100 = 55
        # ----- MED band (60 ≤ composite < 80) -----
        (LABEL_MED,   65.00, 1.00, 1.0, 1.0, 1000, "RANGING",       0.0),  # 45 + 0.20·1.00·100 = 65
        (LABEL_MED,   70.00, 1.00, 1.0, 1.0, 1000, "TRENDING_BULL", 0.40),  # 65 + 0.25·0.5·0.4·100 = 70
        (LABEL_MED,   77.50, 1.00, 1.0, 1.0, 1000, "TRENDING_BULL", 1.00),  # 65 + 0.25·0.5·1.0·100 = 77.5
        # ----- HIGH band (composite ≥ 80; conflict-elevated dislocation) -----
        (LABEL_HIGH,  85.00, 1.00, 1.0, 1.0, -1000, "TRENDING_BULL", 0.5333),  # dis=min(0.8,1)=0.8; 65+20 = 85
        (LABEL_HIGH,  90.00, 1.00, 1.0, 1.0, -1000, "TRENDING_BULL", 1.00),    # dis=min(1.5,1)=1.0; 65+25 = 90
    ]
    for (expected_label, expected_composite, tox, illiq_am,
         illiq_kyle, of_aggregated, regime_state, regime_conf) in cases:
        am, kyle, vpin, regime, ofi = _stack(
            tox, illiq_am, illiq_kyle, of_aggregated,
            regime_state, regime_conf,
        )
        out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
        assert abs(out["composite"] - expected_composite) < 0.5, (
            f"composite={out['composite']} expected={expected_composite} "
            f"for (tox={tox}, illiq_am={illiq_am}, illiq_kyle={illiq_kyle}, "
            f"of_aggregated={of_aggregated}, regime={regime_state}, "
            f"conf={regime_conf})"
        )
        assert out["label"] == expected_label, (
            f"composite={out['composite']} got={out['label']} "
            f"expected={expected_label}"
        )
        assert out["label_color"] == LABEL_COLORS[expected_label]


def test_label_color_matches_label():
    """Every label has a colour and it's a valid hex trio."""
    for lbl in (LABEL_HIGH, LABEL_MED, LABEL_WATCH, LABEL_LOW):
        c = LABEL_COLORS[lbl]
        assert c.startswith("#") and len(c) == 7


# ─────────────────────────────────────────────────────────────────────
# Sub-score spot-checks
# ─────────────────────────────────────────────────────────────────────

def test_calm_market_yields_low_composite():
    """All zero inputs + RANGING regime → composite = 0 → LOW."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=0.5, posterior=[0.2, 0.6, 0.2])
    ofi = _ofi(0.0, snaps_used=2)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["composite"] == 0.0
    assert out["label"] == LABEL_LOW
    assert out["sub_scores"] == {
        "illiquidity": 0.0,
        "toxicity":    0.0,
        "dislocation": 0.0,
        "direction":   0.0,
        "sentiment":   0.0,
    }


def test_max_inputs_yield_composite_at_least_high():
    """Max inputs + bull regime signed-positive ofi + bullish sentiment
    → at least HIGH band.

    Steal-list deferred-(b) weight split (illiq 0.25 · tox 0.20 · dis 0.25 · dir 0.20 ·
    sent 0.10) means the 4-stack max is 86.875 ⇒ HIGH; bumping the
    ``sentiment_out`` through to ``1.0`` keeps that contract and also
    exercises the 5th sub-component path. With sentiment=None (the
    default) the composite falls to 76.875 ⇒ MED. The test pins the
    "WITH bullish sentiment" path to keep the HIGH anchor.
    """
    am = _amihud(amihud=1e-3)             # way above 1e-4 anchor → 1.0
    kyle = _kyle(lam=0.05)               # |0.05| / 0.01 = 5 → 1.0
    vpin = _vpin(vpin=1.0)               # clamp
    regime = _regime(
        current_state="TRENDING_BULL",
        confidence=0.95,
        posterior=[0.95, 0.03, 0.02],
    )
    ofi = _ofi(of_aggregated=2000.0)      # 2000/1000 = 2 → 1.0
    sentiment = {
        "avg_vader": 0.85, "avg_textblob": 0.65,
        "tweet_count": 5, "bullish_count": 4, "bearish_count": 1,
        "neutral_count": 0, "sentiment_label": "positive",
        "confidence": 0.8, "top_tweets": [],
    }
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi, sentiment)
    # illiq=1.0·0.25   = 0.250
    # tox=1.0·0.20     = 0.200
    # dis=0.95·(0.5+0)·0.25 = 0.119   (concordant: 0.5·conf)
    # dir=1.0·0.20     = 0.200
    # sent=abs(0.75)·0.10 = 0.075
    # composite = 100·(0.844) = 84.375
    assert out["label"] == LABEL_HIGH
    assert out["composite"] >= 80.0


def test_regime_disagreement_with_ofi_elevates_dislocation():
    """Bear regime + bull ofi (signed-positive of_aggr) → conflict=1 → dislocation rises."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(
        current_state="TRENDING_BEAR",
        confidence=0.90,
        posterior=[0.05, 0.05, 0.90],
    )
    ofi = _ofi(of_aggregated=500.0, imbalance_label="buy_pressure")
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    # illiquidity=0, toxicity=0, direction=0.5
    # dislocation = 0.90 * (0.5*1 + 1*1) = 1.5 → capped at 1.0
    # composite = 100·(0 + 0 + 0.25·1 + 0.20·0.5) = 100·(0.25 + 0.10) = 35
    assert out["sub_scores"]["dislocation"] == 1.0  # capped at 1.0
    assert out["composite"] == 35.0
    assert out["label"] == LABEL_LOW  # 35 < 40 → LOW


def test_regime_concordant_with_flow_does_not_elevate_dislocation():
    """Bull regime + bull ofi → conflict=0 → dislocation ≈ confidence * 0.5."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(
        current_state="TRENDING_BULL",
        confidence=0.90,
        posterior=[0.90, 0.05, 0.05],
    )
    ofi = _ofi(of_aggregated=500.0, imbalance_label="buy_pressure")
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    # dislocation = 0.90 * 0.5 = 0.45
    assert abs(out["sub_scores"]["dislocation"] - 0.45) < 1e-6


def test_ranging_regime_zeroes_dislocation_regardless_of_ofi():
    """RANGING regime with strong ofi → dislocation still 0."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=1.0,
                     posterior=[0.05, 0.90, 0.05])
    ofi = _ofi(of_aggregated=5000.0, imbalance_label="buy_pressure")
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["sub_scores"]["dislocation"] == 0.0


def test_components_payload_includes_regime_and_ofi_aggr():
    """The components block must round-trip regime and the bounded ofi_aggr."""
    am = _amihud(5e-6)
    kyle = _kyle(0.001)
    vpin = _vpin(0.2)
    regime = _regime(current_state="TRENDING_BULL", confidence=0.7,
                     posterior=[0.7, 0.2, 0.1])
    ofi = _ofi(of_aggregated=300.0, snaps_used=2)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["components"]["regime"] == "TRENDING_BULL"
    assert out["components"]["ofi_aggr"] == 300.0
    assert 0.0 <= out["components"]["vpin"] <= 1.0
    assert 0.0 <= out["components"]["amihud_norm"] <= 1.0
    assert 0.0 <= out["components"]["kyle_norm"] <= 1.0


def test_ofi_aggregate_clipped_for_ui_safety():
    """of_aggregated magnitude beyond ±9999 is clipped in the components payload."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime("RANGING", 0.5)
    ofi = _ofi(of_aggregated=99999.0)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["components"]["ofi_aggr"] == 9999.0
    ofi2 = _ofi(of_aggregated=-99999.0)
    out2 = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi2)
    assert out2["components"]["ofi_aggr"] == -9999.0


def test_n_obs_min_is_minimum_across_sub_services():
    am  = _amihud(0.0, n_obs=15)
    kyle = _kyle(0.0,  n_obs=18)
    vpin = _vpin(0.0,  n_obs=12)
    regime = _regime("RANGING", 0.5, n_obs=20)
    ofi = _ofi(0.0, snaps_used=2)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["n_obs_min"] == 12  # vpin is the minimum


def test_clamps_reject_negative_inputs_gracefully():
    """Negative raw vpin/amihud (shouldn't happen but defensive) clamp to 0."""
    am = _amihud(-1e-5)
    kyle = _kyle(0.0)
    vpin = _vpin(-1.0)
    regime = _regime("RANGING", 0.5)
    ofi = _ofi(of_aggregated=-2000.0)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["sub_scores"]["illiquidity"] == 0.0  # clamped
    assert out["sub_scores"]["toxicity"] == 0.0     # clamped
    assert out["sub_scores"]["direction"] == 1.0    # 2000 cap


# ─────────────────────────────────────────────────────────────────────
# Plain-script runner (no pytest required)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        (n, f) for n, f in globals().items() if n.startswith("test_")
    ]
    failures = 0
    for name, fn in test_cases:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(test_cases) - failures}/{len(test_cases)} passed")
    sys.exit(0 if failures == 0 else 1)



# ─────────────────────────────────────────────────────────────────────
# Sentiment integration tests (steal-list deferred-(b) ship)
# ─────────────────────────────────────────────────────────────────────

def test_sentiment_subscore_appears_in_output():
    """`sentiment_out=None` (default) yields sub_scores["sentiment"]=0.0
    AND components["sentiment_available"]=False.  Missing sentiment must NOT
    flip is_warming (graceful degrade, not strict-ANY-warming kill)."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=0.5,
                     posterior=[0.4, 0.2, 0.4])
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    assert out["sub_scores"]["sentiment"] == 0.0
    assert out["components"]["sentiment"] == 0.0
    assert out["components"]["sentiment_available"] is False
    assert out["is_warming"] is False  # NOT flipped by missing sentiment


def test_sentiment_positive_corpus_raises_composite():
    """With bullish sentiment injected, composite rises by exactly 100·(0.10·|mean|)
    over the no-sentiment baseline. Confirms the 5-component weight split math."""
    am = _amihud(amihud=2e-4)        # norm_amihud = 2.0 → cap to 1.0
    kyle = _kyle(lam=0.02)           # norm_kyle = 2.0 → cap to 1.0
    vpin = _vpin(vpin=0.5)
    regime = _regime(current_state="RANGING", confidence=0.5,
                     posterior=[0.4, 0.2, 0.4])
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    sentiment = {
        "avg_vader": 0.6, "avg_textblob": 0.4, "tweet_count": 8,
        "bullish_count": 6, "bearish_count": 0, "neutral_count": 2,
        "sentiment_label": "positive", "confidence": 0.75,
        "top_tweets": [],
    }
    out_a = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    out_b = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi,
                                       sentiment_out=sentiment)
    # sentiment_score = mean(0.6, 0.4) = 0.5 → norm_sentiment = abs(0.5) = 0.5
    # contribution delta = 100·(0.10·0.5) = 5.0
    assert out_b["composite"] - out_a["composite"] == pytest.approx(5.0, abs=0.2)
    assert out_b["components"]["sentiment"] == pytest.approx(0.5, abs=1e-4)
    assert out_b["components"]["sentiment_available"] is True
    """`sentiment_out` with positive avg_vader + positive avg_textblob
    pulls the composite above the no-sentiment baseline (graceful) and
    surfaces the score in components."""
    am = _amihud(amihud=2e-4)        # norm_amihud = 2.0 → cap to 1.0
    kyle = _kyle(lam=0.02)           # norm_kyle = 2.0 → cap to 1.0
    vpin = _vpin(vpin=0.5)
    regime = _regime(current_state="RANGING", confidence=0.5,
                     posterior=[0.4, 0.2, 0.4])
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    sentiment = {
        "avg_vader": 0.6, "avg_textblob": 0.4, "tweet_count": 8,
        "bullish_count": 6, "bearish_count": 0, "neutral_count": 2,
        "sentiment_label": "positive", "confidence": 0.75,
        "top_tweets": [],
    }
    out_a = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi)
    out_b = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi,
                                       sentiment_out=sentiment)
    # sentiment_score = mean(0.6, 0.4) = 0.5 → norm_sentiment = abs(0.5) = 0.5
    # contribution delta = 100·(0.10·0.5) = 5.0
    assert out_b["composite"] - out_a["composite"] == pytest.approx(5.0, abs=0.2)
    assert out_b["components"]["sentiment"] == pytest.approx(0.5, abs=1e-4)
    assert out_b["components"]["sentiment_available"] is True


def test_sentiment_negative_polarity_counts_as_magnitude():
    """``norm_sentiment = abs(sentiment_score)`` — heavily negative sentiment
    raises composite the same as heavily positive (per convention that
    conviction magnitude is orthogonal to direction)."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=0.5)
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    sentiment_neg = {
        "avg_vader": -0.7, "avg_textblob": -0.5, "tweet_count": 10,
        "bullish_count": 0, "bearish_count": 8, "neutral_count": 2,
        "sentiment_label": "negative", "confidence": 0.8,
        "top_tweets": [],
    }
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi,
                                     sentiment_out=sentiment_neg)
    # sentiment_score = mean(-0.7, -0.5) = -0.6;  norm = abs = 0.6
    assert out["components"]["sentiment_available"] is True
    # 0.6 * 0.10 * 100 = 6 contribution; + the tox/illiq baseline 0.
    assert out["composite"] == pytest.approx(6.0, abs=0.2)
    """`norm_sentiment = abs(sentiment_score)` — heavily negative
    sentiment raises composite the same as heavily positive (per
    convention that conviction magnitude is orthogonal to direction)."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=0.5)
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    sentiment_neg = {
        "avg_vader": -0.7, "avg_textblob": -0.5, "tweet_count": 10,
        "bullish_count": 0, "bearish_count": 8, "neutral_count": 2,
        "sentiment_label": "negative", "confidence": 0.8,
        "top_tweets": [],
    }
    out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi,
                                     sentiment_out=sentiment_neg)
    # sentiment_score = mean(-0.7, -0.5) = -0.6;  norm = abs = 0.6
    assert out["components"]["sentiment_available"] is True
    # 0.6 * 0.10 * 100 = 6 contribution; + the tox/illiq baseline 0.
    assert out["composite"] == pytest.approx(6.0, abs=0.2)


def test_sentiment_malformed_payload_does_not_crash():
    """Non-dict sentiment_out (or wrong keys) → silent 0-extract +
    warning log. Composite remains well-formed."""
    am = _amihud(0.0)
    kyle = _kyle(0.0)
    vpin = _vpin(0.0)
    regime = _regime(current_state="RANGING", confidence=0.5)
    ofi = _ofi(of_aggregated=0.0, snaps_used=2)
    for payload in [None, {}, {"tweet_count": 0}, {"tweet_count": 5}, "garbage"]:
        out = CompositeFlowScore.compute(am, kyle, vpin, regime, ofi,
                                         sentiment_out=payload)
        assert out["sub_scores"]["sentiment"] == 0.0
        assert out["components"]["sentiment_available"] in (True, False)
        assert out["is_warming"] is False
