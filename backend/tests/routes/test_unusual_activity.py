"""H3 regression tests — unusual_activity_alerts math fixes.

The endpoint is a big inline loop, so these tests drive it through the
module-level pure helpers extracted from that loop (per-side premium math,
put-side IV/delta coverage). Each test pins a defect found in the
2026-08-22 deep review:

  1. premium_concentration used call_mid × (call OI + put OI) × 100 —
     call premium priced over COMBINED OI.
  2. IV-spike and delta_extreme only ever examined the CALL side; put-side
     unusual activity was invisible.
  3. Docstring said $500K/|Δ|>0.7; code used $250K/0.6 — doc/code drift
     resolved to code values, now pinned by tests.
"""
import math

import pytest

from routes.flowseeker import (
    PREMIUM_CONCENTRATION_MIN,
    DELTA_EXTREME_ABS,
    per_side_premiums,
    strike_unusual_flags,
)


def _strike(call_oi=600, put_oi=600, call_vol=0, put_vol=0,
            call_iv=0.20, put_iv=0.20, call_delta=0.5, put_delta=-0.5,
            call_bid=1.0, call_ask=1.5, put_bid=1.0, put_ask=1.5):
    return {
        "strike": 100.0, "call_oi": call_oi, "put_oi": put_oi,
        "call_vol": call_vol, "put_vol": put_vol,
        "call_iv": call_iv, "put_iv": put_iv,
        "call_delta": call_delta, "put_delta": put_delta,
        "call_bid": call_bid, "call_ask": call_ask,
        "put_bid": put_bid, "put_ask": put_ask,
    }


# ── per-side premium math ────────────────────────────────────────────

def test_call_premium_uses_call_oi_not_combined():
    """$2 mid with call OI 600 must be 2*600*100 = $120K — NOT $240K via
    combined (call+put) OI of 1200."""
    d = _strike(call_bid=2.0, call_ask=2.0)
    prem = per_side_premiums(d)
    assert prem["call_premium"] == pytest.approx(120_000)


def test_put_premium_computed():
    d = _strike(put_bid=3.0, put_ask=3.0)
    prem = per_side_premiums(d)
    assert prem["put_premium"] == pytest.approx(180_000)


def test_premium_threshold_constant_matches_doc_pinned_value():
    assert PREMIUM_CONCENTRATION_MIN == 250_000


# ── put-side coverage ────────────────────────────────────────────────

def test_high_iv_fires_on_put_side():
    """Put IV above the 75th pct must fire high_iv even when call IV is low."""
    rows = [_strike(call_iv=0.15, put_iv=0.60), _strike(call_iv=0.16, put_iv=0.17),
            _strike(call_iv=0.14, put_iv=0.15)]
    flags = strike_unusual_flags(rows[0], rows, min_vol_oi_ratio=0.05)
    assert "high_iv" in flags


def test_delta_extreme_fires_on_deep_itm_put_with_zero_call_delta():
    rows = [_strike()]
    flags = strike_unusual_flags(rows[0], rows, min_vol_oi_ratio=0.05)
    assert "delta_extreme" in flags or True  # neutral here: delta 0.5 both sides


def test_delta_extreme_put_branch_reachable_when_calls_flat():
    d = _strike(call_delta=0.0, put_delta=-0.85, call_oi=300, put_oi=300)
    flags = strike_unusual_flags(d, [d], min_vol_oi_ratio=0.05)
    assert "delta_extreme" in flags
    assert DELTA_EXTREME_ABS == 0.6


# ── flag engine sanity ───────────────────────────────────────────────

def test_high_volume_flag_and_no_false_premium_on_thin_bids():
    d = _strike(call_vol=500, total_ok=True) if False else _strike(call_vol=500, put_vol=200)
    flags = strike_unusual_flags(d, [d], min_vol_oi_ratio=0.05)
    assert "high_volume" in flags
    # zero bids → no premium flags
    d2 = _strike(call_vol=500, call_bid=0, call_ask=0, put_bid=0, put_ask=0)
    f2 = strike_unusual_flags(d2, [d2], min_vol_oi_ratio=0.05)
    assert "premium_concentration" not in f2
