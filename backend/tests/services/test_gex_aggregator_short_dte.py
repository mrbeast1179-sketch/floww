"""
Tests for steal-list rank #2 — short-DTE volume substitution in GexAggregator.compute().

Activates via env flag ``FLOWW_USE_VOL_FOR_SHORT_DTE``. Default **OFF** so
existing callers (including the S^2 oracle test ``test_gex_aggregator_oracle``)
see byte-identical results — the regression assertions below pin that.

Threshold semantics: T <= 1/252 (inclusive — matches aaguiar10/gflows'
``is_short_dte`` convention so 0DTE AND 1DTE contracts both qualify).
Fillna policy: missing or zero ``volume`` key → fall back to OI per contract
(matches ``services/gex_dual.DualGexCalculator._resolve_volume``).
"""

import pytest

from services.gex_aggregator import GexAggregator

SPOT = 100.0
GAMMA = 0.04
SCALE_FACTOR = SPOT * SPOT * 0.01 * 100.0  # dollar-GEX per-contract scale (S^2)


def _c(K, type_, oi, volume=0, T=2 / 365):
    """Compact contract factory — matches the GexAggregator._OI_KEYS/TYPE/EXPIRY aliases.

    Note: we DON'T include a date-string ``"expiry"`` key. The resolver pulls the
    FIRST matching alias in ``_EXPIRY_KEYS = ("expiry", "T", ...)``; if ``"expiry"``
    is a date string like ``"2026-08-15"``, ``float(...)`` crashes before it can
    fall through to the numeric ``"T"``. To exercise the short-DTE branch we
    pass ``"T"`` directly as a year-float, the same convention as
    ``tests/services/test_gex_aggregator_oracle.py``.
    """
    return {
        "strike": K,
        "gamma": GAMMA,
        "type": type_,
        "oi": oi,
        "volume": volume,
        "T": T,
        "vomma": 0.0,
    }


def _expected_call_gex(weight: float) -> float:
    """Pre-compute the expected per-contract gex for a CALL (sign +1)."""
    return 1.0 * GAMMA * weight * SCALE_FACTOR


# ----------------------------------------------------------------------
# Default-OFF behavior — regression guards.
# ----------------------------------------------------------------------

def test_default_flag_off_uses_oi_for_all(monkeypatch):
    """With FLOWW_USE_VOL_FOR_SHORT_DTE unset/empty, compute() behaves as
    before this steal-list item landed — OI everywhere."""
    monkeypatch.delenv("FLOWW_USE_VOL_FOR_SHORT_DTE", raising=False)
    contracts = [
        _c(100, "call", oi=500, volume=200, T=0.5 / 252),  # short DTE, vol present
        _c(105, "put", oi=400, volume=150, T=2 / 365),    # long DTE
    ]
    out = GexAggregator().compute(SPOT, contracts)
    assert out["net_gex"] == pytest.approx(
        _expected_call_gex(500) - 1.0 * GAMMA * 400 * SCALE_FACTOR
    )


# ----------------------------------------------------------------------
# Flag-ON, short-DTE vs long-DTE behaviour.
# ----------------------------------------------------------------------

def test_flag_on_short_dte_uses_volume(monkeypatch):
    """T < 1/252 → contract uses volume, not OI."""
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    contracts = [_c(100, "call", oi=500, volume=200, T=0.5 / 252)]
    out = GexAggregator().compute(SPOT, contracts)
    s = sum(out["gex_1d"])
    assert s == pytest.approx(_expected_call_gex(200))


def test_flag_on_long_dte_uses_oi(monkeypatch):
    """T > 1/252 → contract still uses OI even when volume is present."""
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    contracts = [_c(100, "call", oi=500, volume=200, T=2 / 365)]
    out = GexAggregator().compute(SPOT, contracts)
    s = sum(out["gex_1d"])
    assert s == pytest.approx(_expected_call_gex(500))


def test_flag_on_boundary_t_equals_thresh_uses_volume(monkeypatch):
    """T == 1/252 EXACTLY → inclusive <= semantics → short DTE → volume."""
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    contracts = [_c(100, "call", oi=500, volume=200, T=1 / 252)]
    out = GexAggregator().compute(SPOT, contracts)
    s = sum(out["gex_1d"])
    assert s == pytest.approx(_expected_call_gex(200))


def test_flag_on_volume_zero_falls_back_to_oi(monkeypatch):
    """Short DTE but volume=0 has no signal — fillna to OI (matches gex_dual)."""
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    contracts = [_c(100, "call", oi=500, volume=0, T=0.5 / 252)]
    out = GexAggregator().compute(SPOT, contracts)
    s = sum(out["gex_1d"])
    assert s == pytest.approx(_expected_call_gex(500))


def test_flag_on_volume_missing_key_falls_back_to_oi(monkeypatch):
    """No 'volume' / 'vol' / 'today_volume' / 'total_volume' / 'day_volume' in
    the contract dict — fillna to OI per gex_dual alias resolution order."""
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    raw = {
        # Numeric ``T`` only — no date-string ``"expiry"`` so the resolver
        # doesn't try `float("2026-08-15")` and crash before falling through.
        # See _EXPIRY_KEYS ordering caveat documented in _c().
        "strike": 100, "gamma": GAMMA, "type": "call",
        "oi": 500, "T": 0.5 / 252, "vomma": 0.0,
    }
    out = GexAggregator().compute(SPOT, [raw])
    s = sum(out["gex_1d"])
    assert s == pytest.approx(_expected_call_gex(500))


# ----------------------------------------------------------------------
# Flag-ON mix + net_gex sanity vs OFF — confirms the flag has bite.
# ----------------------------------------------------------------------

def test_flag_on_off_differs_on_short_dte_only_when_vol_set(monkeypatch):
    """Two-contract mix (short + long DTE): flipping the flag ONLY changes
    the short-DTE leg, so net_gex must differ between OFF and ON when the
    short-DTE contract has a meaningful volume signal."""
    contracts = [
        _c(100, "call", oi=2000, volume=9999, T=0.5 / 252),  # short DTE, vol>>OI
        _c(105, "put",  oi=3000, volume=9999, T=2 / 365),    # long DTE — no change
    ]

    monkeypatch.delenv("FLOWW_USE_VOL_FOR_SHORT_DTE", raising=False)
    out_off = GexAggregator().compute(SPOT, contracts)
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    out_on = GexAggregator().compute(SPOT, contracts)

    # spot_sq scale: SPOT=100, gamma=0.04, multiplier=100, dovmove=0.01
    # OI-only net:   +1*0.04*2000*100^2*0.01*100  +  (-1)*0.04*3000*100^2*0.01*100
    expected_off = 800_000.0 - 1_200_000.0          # = -400_000
    # ON uses vol=9999 for the short-DTE leg → +1*0.04*9999*1000 = +3_999_600
    expected_on = 3_999_600.0 - 1_200_000.0        # = +2_799_600
    assert out_off["net_gex"] == pytest.approx(expected_off)
    assert out_on["net_gex"] == pytest.approx(expected_on)
    assert out_on["net_gex"] != out_off["net_gex"]


# ----------------------------------------------------------------------
# Env-flag value parsing.
# ----------------------------------------------------------------------

@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "TRUE", "YeS", "On"])
def test_flag_accepts_case_insensitive_truthy_values(monkeypatch, truthy):
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", truthy)
    contracts = [_c(100, "call", oi=500, volume=200, T=0.5 / 252)]
    s = sum(GexAggregator().compute(SPOT, contracts)["gex_1d"])
    # All truthy values → volume weight (200).
    assert s == pytest.approx(_expected_call_gex(200))


@pytest.mark.parametrize("falsy", ["0", "false", "no", "", "off", "nope"])
def test_flag_accepts_case_insensitive_falsy_values(monkeypatch, falsy):
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", falsy)
    contracts = [_c(100, "call", oi=500, volume=200, T=0.5 / 252)]
    s = sum(GexAggregator().compute(SPOT, contracts)["gex_1d"])
    # All falsy values → OI weight (500).
    assert s == pytest.approx(_expected_call_gex(500))


# ----------------------------------------------------------------------
# Output-shape preservation — flag ON/OFF must return identical keys.
# ----------------------------------------------------------------------

def test_flag_on_output_shape_identical_to_off(monkeypatch):
    """Defensive: the dict surface from compute() must be IDENTICAL whether
    the flag is on or off (no keys added/removed/lost in either path)."""
    contracts = [
        _c(100, "call", oi=2000, volume=500, T=0.5 / 252),
        _c(105, "put",  oi=3000, volume=500, T=2 / 365),
    ]
    monkeypatch.delenv("FLOWW_USE_VOL_FOR_SHORT_DTE", raising=False)
    off = GexAggregator().compute(SPOT, contracts)
    monkeypatch.setenv("FLOWW_USE_VOL_FOR_SHORT_DTE", "1")
    on = GexAggregator().compute(SPOT, contracts)
    assert set(off.keys()) == set(on.keys())
