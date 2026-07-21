"""
Pins the 3-class decode in MlBriefingIntegrator._combine_signals.

The InferenceEngine emits a THREE-class label (DOWN=0, HOLD=1, UP=2 —
services/ml/inference.py; ml_api.py maps 0->bearish, 1->neutral, 2->bullish).
The combine step previously used `(2*pred - 1)*conf`, a BINARY {0,1} formula,
which scored HOLD(1) as +conf (bullish) and UP(2) as +3*conf. This suite
locks the correct per-class contribution so a neutral ML read never tips the
live briefing bullish.
"""

import pytest

from services.ml.inference import DOWN, HOLD, UP
from services.ml_briefing import MlBriefingIntegrator


def _combine(regime, rconf, pred, pconf):
    return MlBriefingIntegrator()._combine_signals(regime, rconf, pred, pconf)


def test_hold_prediction_is_neutral_not_bullish():
    # HOLD with a NEUTRAL regime must stay NEUTRAL (the old binary formula
    # turned HOLD into +conf and tipped this bullish).
    signal, _ = _combine("NEUTRAL", 0.5, HOLD, 0.7)
    assert signal == "NEUTRAL"


def test_hold_dilutes_but_never_amplifies():
    # A HOLD is an active neutral vote (like a NEUTRAL regime): it adds zero
    # DIRECTION, so against a bullish regime it can only weaken or hold the
    # combined confidence — never push it MORE bullish (the old binary bug
    # made HOLD add +conf and amplify).
    hold_sig, hold_conf = _combine("BULLISH", 0.8, HOLD, 0.7)
    _, no_ml_conf = _combine("BULLISH", 0.8, None, None)
    assert hold_conf <= no_ml_conf + 1e-9
    assert "BEARISH" not in hold_sig  # a HOLD never flips a bullish regime bearish


def test_up_prediction_is_bullish():
    signal, conf = _combine("BULLISH", 0.8, UP, 0.7)
    assert "BULLISH" in signal and conf > 0.5


def test_down_prediction_is_bearish():
    signal, conf = _combine("BEARISH", 0.8, DOWN, 0.7)
    assert "BEARISH" in signal and conf > 0.5


def test_up_does_not_overweight_beyond_unit_scale():
    # UP must not blow past a bullish regime's own magnitude (the old +3*conf
    # made the ML term dominate and could push combined confidence absurdly).
    _, conf = _combine("BULLISH", 0.7, UP, 0.7)
    assert conf <= 1.0


def test_up_regime_bearish_ml_cancels_toward_neutral():
    # Opposing regime (bearish) and ML (UP) should weaken, not compound.
    signal, conf = _combine("BEARISH", 0.6, UP, 0.6)
    assert signal in ("NEUTRAL", "BULLISH", "BEARISH")
    assert conf < 0.6
