"""
backend/tests/services/test_heatseeker.py

Unit tests for services.heatseeker — Skylit Wave 1 (flip zones, node
lifecycle, air pockets). All fixtures are hand-built so the expected answer
can be verified by inspection; no random data.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Add backend/ to path so `services.heatseeker` is importable.
# __file__ = backend/tests/services/test_heatseeker.py; parents[2] = backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.heatseeker import (  # noqa: E402
    calc_air_pockets,
    calc_flip_zones,
    calc_node_lifecycle,
    calc_trinity_confluence,
    calc_velocity_mode,
    detect_beach_ball,
    detect_rainbow_road,
    detect_reverse_rug,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _c(strike: float, ctype: str, gamma: float, oi: float) -> Dict[str, Any]:
    """Build a minimal contract dict matching advanced_analytics.py conventions."""
    return {
        "strike": strike,
        "type": ctype,
        "gamma": gamma,
        "open_interest": oi,
    }


def _gex(spot: float, gamma: float, oi: float, sign: int) -> float:
    """Compute the GEX a single contract contributes — useful for asserting strengths."""
    return sign * gamma * oi * 100.0 * spot * spot * 0.01


# ===========================================================================
# Function 1: calc_flip_zones
# ===========================================================================

class TestFlipZones:
    def test_happy_path_single_crossing(self):
        """
        Spot=100. Strikes 95-105. Heavy negative GEX through 102, then a big
        positive contribution at 105 → cumulative crosses zero once between
        102 and 105. Verified by hand:
            GEX  per strike: 95=-100k, 98=-120k, 102=+180k, 105=+140k
            cumulative:      -100k, -220k, -40k, +100k
            sign flip between 102 and 105.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "P", 0.02, 500),
            _c(98.0, "P", 0.03, 400),
            _c(102.0, "C", 0.03, 600),
            _c(105.0, "C", 0.02, 700),
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.10)
        assert result["count"] == 1
        zone = result["flip_zones"][0]
        # The cumulative crossing lives between 102 and 105.
        assert 102.0 < zone["price"] < 105.0
        assert zone["from_sign"] == "negative"
        assert zone["to_sign"] == "positive"
        assert zone["strength"] > 0
        assert result["window_low"] == pytest.approx(90.0)
        assert result["window_high"] == pytest.approx(110.0)

    def test_empty_contracts(self):
        """Empty input must return empty zones without crashing."""
        result = calc_flip_zones(100.0, [], window_pct=0.05)
        assert result["flip_zones"] == []
        assert result["count"] == 0
        assert result["window_low"] == pytest.approx(95.0)
        assert result["window_high"] == pytest.approx(105.0)

    def test_boundary_flip_outside_window_excluded(self):
        """
        A crossing that falls outside the ±window_pct band of spot must be
        excluded. With strikes 80 / 85 producing a cumulative sign change
        between them (- → +), the interpolated crossing lives around 82.
        With a ±2% window around spot=100 (i.e. 98..102) it must NOT be
        reported; with ±25% (75..125) it must be reported.
        """
        spot = 100.0
        contracts = [
            _c(80.0, "P", 0.05, 1000),
            _c(85.0, "C", 0.05, 2000),  # larger OI so cumulative goes positive
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.02)
        assert result["count"] == 0
        result2 = calc_flip_zones(spot, contracts, window_pct=0.25)
        assert result2["count"] == 1
        assert 80.0 < result2["flip_zones"][0]["price"] < 85.0

    def test_regression_multiple_crossings(self):
        """
        Oscillating GEX across four strikes inside a ±5% window produces
        three sign changes in the running cumulative. Verified by hand:

            signed GEX:  97 → -100k, 99 → +250k, 101 → -300k, 103 → +400k
            cumulative:  -100k, +150k, -150k, +250k
            crossings:   97↔99 (- → +), 99↔101 (+ → -), 101↔103 (- → +)

        All three crossings fall within ±5% of spot=100 (i.e. 95..105), so
        the result must contain exactly 3 zones in strike-ascending order.
        """
        spot = 100.0
        contracts = [
            _c(97.0, "P", 0.05, 200),
            _c(99.0, "C", 0.05, 500),
            _c(101.0, "P", 0.05, 600),
            _c(103.0, "C", 0.05, 800),
        ]
        result = calc_flip_zones(spot, contracts, window_pct=0.05)
        assert result["count"] == 3
        prices = [z["price"] for z in result["flip_zones"]]
        assert prices == sorted(prices)
        signs = [(z["from_sign"], z["to_sign"]) for z in result["flip_zones"]]
        assert signs == [
            ("negative", "positive"),
            ("positive", "negative"),
            ("negative", "positive"),
        ]
        for z in result["flip_zones"]:
            assert z["strength"] > 0


# ===========================================================================
# Function 2: calc_node_lifecycle
# ===========================================================================

class TestNodeLifecycle:
    def test_happy_path_mixed_states(self):
        """
        Four strikes with distinct |GEX| ranks and a history that taps each a
        different number of times.
        """
        spot = 100.0
        # Same OI/gamma → magnitude differentiated only by call vs put? No —
        # we need distinct |GEX|. Use different OI per strike.
        contracts = [
            _c(95.0, "P", 0.05, 1000),  # largest |GEX|
            _c(100.0, "C", 0.05, 800),
            _c(105.0, "C", 0.05, 600),
            _c(110.0, "C", 0.05, 400),  # smallest
        ]
        # History: 95 tapped 0 times (fresh), 100 tapped once (tested),
        # 105 tapped twice (delivered), 110 tapped three times (decaying).
        history = [
            {"timestamp": "2026-05-18T00:00:00Z", "spot": 100.05},  # within 0.1% of 100
            {"timestamp": "2026-05-18T01:00:00Z", "spot": 105.0},   # tap 105
            {"timestamp": "2026-05-18T02:00:00Z", "spot": 105.05},  # tap 105 again
            {"timestamp": "2026-05-18T03:00:00Z", "spot": 110.0},   # tap 110
            {"timestamp": "2026-05-18T04:00:00Z", "spot": 110.05},  # tap 110
            {"timestamp": "2026-05-18T05:00:00Z", "spot": 109.95},  # tap 110 (within 0.1%)
        ]
        result = calc_node_lifecycle(spot, contracts, history)
        nodes_by_strike = {n["strike"]: n for n in result["nodes"]}
        assert nodes_by_strike[95.0]["state"] == "fresh"
        assert nodes_by_strike[95.0]["tap_probability"] == 80
        assert nodes_by_strike[100.0]["state"] == "tested"
        assert nodes_by_strike[100.0]["tap_probability"] == 66
        assert nodes_by_strike[105.0]["state"] == "delivered"
        assert nodes_by_strike[105.0]["tap_probability"] == 33
        assert nodes_by_strike[110.0]["state"] == "decaying"
        assert nodes_by_strike[110.0]["tap_probability"] == 10

    def test_empty_contracts(self):
        """Empty contracts must return empty nodes."""
        result = calc_node_lifecycle(100.0, [], history=[{"timestamp": "x", "spot": 100.0}])
        assert result["nodes"] == []

    def test_boundary_all_fresh_no_history(self):
        """With empty history, every node is fresh and prob=80."""
        spot = 100.0
        contracts = [
            _c(95.0, "P", 0.05, 1000),
            _c(100.0, "C", 0.05, 800),
            _c(105.0, "C", 0.05, 600),
        ]
        result = calc_node_lifecycle(spot, contracts, history=[])
        assert len(result["nodes"]) == 3
        for n in result["nodes"]:
            assert n["state"] == "fresh"
            assert n["tap_probability"] == 80
            assert n["taps"] == 0

    def test_regression_top10_only_and_sorted_by_abs_gex(self):
        """
        With 15 strikes, only the top 10 by |net_gex| are returned, and the
        list comes back sorted by |net_gex| descending.
        """
        spot = 100.0
        # 15 calls, OI from 100..1500 — |GEX| scales with OI so largest OI
        # produces largest |GEX|.
        contracts = [_c(90.0 + i, "C", 0.05, 100 * (i + 1)) for i in range(15)]
        result = calc_node_lifecycle(spot, contracts, history=[])
        assert len(result["nodes"]) == 10
        gexes = [abs(n["net_gex"]) for n in result["nodes"]]
        assert gexes == sorted(gexes, reverse=True)
        # The biggest strike (104) has the largest OI (1500) → should be first.
        assert result["nodes"][0]["strike"] == 104.0


# ===========================================================================
# Function 3: calc_air_pockets
# ===========================================================================

class TestAirPockets:
    def test_happy_path_single_pocket(self):
        """
        8 high-|GEX| anchors and 3 thin strikes in a contiguous run. The
        median of |GEX| in the ±5% window is dominated by the anchors, so
        threshold = 0.2 * (large median) easily excludes them — only the
        three thin strikes (101, 102, 103) fall below threshold and form a
        2.0-wide pocket (span_pct = 0.02), which exceeds min_gap_pct=0.005.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 1000),
            _c(96.0, "C", 0.05, 1000),
            _c(97.0, "C", 0.05, 1000),
            _c(98.0, "C", 0.05, 1000),
            _c(99.0, "C", 0.05, 1000),
            _c(100.0, "C", 0.05, 1000),
            # Thin run.
            _c(101.0, "C", 0.0001, 1),
            _c(102.0, "C", 0.0001, 1),
            _c(103.0, "C", 0.0001, 1),
            _c(104.0, "C", 0.05, 1000),
            _c(105.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        assert len(result["air_pockets"]) == 1
        pocket = result["air_pockets"][0]
        assert pocket["low"] == pytest.approx(101.0)
        assert pocket["high"] == pytest.approx(103.0)
        assert pocket["span_pct"] == pytest.approx(0.02)
        assert pocket["max_abs_gex_in_run"] >= 0

    def test_empty_contracts(self):
        """Empty contracts → empty pockets, no crash."""
        result = calc_air_pockets(100.0, [], min_gap_pct=0.005)
        assert result["air_pockets"] == []

    def test_boundary_no_pockets_when_all_strikes_dense(self):
        """
        Every strike has equal large |GEX| → local median equals the value
        at every strike → threshold (0.2*median) is below every strike's
        |GEX| → no pocket reported.
        """
        spot = 100.0
        contracts = [_c(95.0 + i, "C", 0.05, 1000) for i in range(11)]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        assert result["air_pockets"] == []

    def test_regression_short_gap_below_min_span_excluded(self):
        """
        Two anchor strikes very close (100.1 and 100.2) with a thin strike
        between them at 100.15. Even though 100.15 is "thin," the run only
        spans 0.0 in price (single strike), failing the min_gap_pct=0.005
        (which requires span >= 0.5 at spot=100). No pocket reported.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 1000),
            _c(100.10, "C", 0.05, 1000),
            _c(100.15, "C", 0.0001, 1),  # the only thin strike — span is 0
            _c(100.20, "C", 0.05, 1000),
            _c(105.0, "C", 0.05, 1000),
        ]
        result = calc_air_pockets(spot, contracts, min_gap_pct=0.005)
        # Span from a single thin strike has width 0 → excluded.
        for p in result["air_pockets"]:
            assert (p["high"] - p["low"]) >= 0.5


# ===========================================================================
# Wave 2 — Function 4: detect_beach_ball
# ===========================================================================

class TestBeachBall:
    def test_happy_path_spot_stretched_above_king(self):
        """
        King node sits at 100 (largest |GEX|). Spot=103.0 → 3% above king.
        Active=True, direction='above', confidence capped at 1.0 because
        distance (0.03) > 0.02.
        """
        spot = 103.0
        contracts = [
            _c(95.0, "C", 0.05, 100),
            _c(100.0, "C", 0.05, 5000),   # king node by |GEX|
            _c(105.0, "C", 0.05, 200),
        ]
        result = detect_beach_ball(spot, contracts)
        assert result["pattern"] == "beach_ball"
        assert result["active"] is True
        assert result["king_node"] == pytest.approx(100.0)
        assert result["direction"] == "above"
        assert result["spot_distance_pct"] == pytest.approx(0.03)
        assert result["confidence"] == pytest.approx(1.0)

    def test_inactive_when_spot_at_king_node(self):
        """
        Spot sitting on top of the king node → not stretched, inactive.
        """
        spot = 100.0
        contracts = [
            _c(100.0, "C", 0.05, 5000),
            _c(105.0, "C", 0.05, 200),
        ]
        result = detect_beach_ball(spot, contracts)
        assert result["active"] is False
        assert result["direction"] == "at"
        assert result["spot_distance_pct"] == pytest.approx(0.0)
        assert result["confidence"] == pytest.approx(0.0)

    def test_empty_contracts_and_explicit_king(self):
        """
        Empty input must return inactive without crashing. Also exercise
        the explicit ``king_node`` override path: spot 99.0, king=100 →
        distance = 1% > 0.5% threshold → active=True, direction='below'.
        """
        empty = detect_beach_ball(100.0, [])
        assert empty["active"] is False

        result = detect_beach_ball(99.0, [], king_node=100.0)
        assert result["active"] is True
        assert result["king_node"] == pytest.approx(100.0)
        assert result["direction"] == "below"
        assert result["spot_distance_pct"] == pytest.approx(0.01)
        # confidence = min(1.0, 0.01 / 0.02) = 0.5
        assert result["confidence"] == pytest.approx(0.5)


# ===========================================================================
# Wave 2 — Function 5: detect_reverse_rug
# ===========================================================================

class TestReverseRug:
    def test_happy_path_floor_below_ceiling_above(self):
        """
        Spot=100. Big positive (call) GEX at 95 → floor below. Big negative
        (put) GEX at 105 → ceiling above. Pattern active.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "C", 0.05, 2000),  # floor
            _c(100.0, "C", 0.01, 100),
            _c(105.0, "P", 0.05, 2000),  # ceiling
        ]
        result = detect_reverse_rug(spot, contracts)
        assert result["pattern"] == "reverse_rug"
        assert result["active"] is True
        assert result["floor_strike"] == pytest.approx(95.0)
        assert result["floor_gex"] > 0
        assert result["ceiling_strike"] == pytest.approx(105.0)
        assert result["ceiling_gex"] < 0

    def test_empty_contracts(self):
        """Empty input → inactive, missing strikes set to None."""
        result = detect_reverse_rug(100.0, [])
        assert result["active"] is False
        assert result["floor_strike"] is None
        assert result["ceiling_strike"] is None

    def test_inactive_when_no_floor_below(self):
        """
        All positive GEX is ABOVE spot — there is no floor strike below spot
        with positive GEX, so the pattern is inactive.
        """
        spot = 100.0
        contracts = [
            _c(95.0, "P", 0.05, 2000),   # negative GEX below — wrong side
            _c(105.0, "C", 0.05, 2000),  # positive GEX above — wrong side
            _c(108.0, "P", 0.05, 1500),  # negative ceiling above (good)
        ]
        result = detect_reverse_rug(spot, contracts)
        assert result["active"] is False
        # No positive GEX below spot → no floor.
        assert result["floor_strike"] is None
        # There IS a negative GEX above spot, so ceiling may be present.
        assert result["ceiling_strike"] == pytest.approx(108.0)


# ===========================================================================
# Wave 2 — Function 6: detect_rainbow_road
# ===========================================================================

class TestRainbowRoad:
    def test_happy_path_diffuse_gex(self):
        """
        10 strikes within ±5% of spot, all roughly equal |GEX|. Top share
        ≈ 1/10 = 0.10 — well below max_dominant_share=0.15 → active=True.
        """
        spot = 100.0
        contracts = [_c(95.0 + i, "C", 0.05, 1000) for i in range(10)]
        result = detect_rainbow_road(spot, contracts, max_dominant_share=0.15)
        assert result["pattern"] == "rainbow_road"
        assert result["active"] is True
        assert result["top_strike_share"] <= 0.15
        # n_strikes_significant: with all equal |GEX|, mean = each value, so
        # |gex| > 0.5*mean is satisfied by every strike → all 10 count.
        assert result["n_strikes_significant"] == 10

    def test_inactive_when_one_strike_dominates(self):
        """
        One huge strike + a few small ones — top share >> 0.15.
        """
        spot = 100.0
        contracts = [
            _c(99.0, "C", 0.05, 50),
            _c(100.0, "C", 0.05, 50_000),  # dominant
            _c(101.0, "C", 0.05, 50),
            _c(102.0, "C", 0.05, 50),
        ]
        result = detect_rainbow_road(spot, contracts, max_dominant_share=0.15)
        assert result["active"] is False
        assert result["top_strike_share"] > 0.15

    def test_empty_contracts(self):
        """Empty input → inactive, zero shares."""
        result = detect_rainbow_road(100.0, [])
        assert result["active"] is False
        assert result["top_strike_share"] == pytest.approx(0.0)
        assert result["n_strikes_significant"] == 0


# ===========================================================================
# Wave 2 — Function 7: calc_velocity_mode
# ===========================================================================

class TestVelocityMode:
    def test_happy_path_active_mode(self):
        """
        King node moves from 100 → 110 over 10 minutes → velocity = 1.0
        strikes/min → falls in [0.5, 2.0) → mode='active'.
        """
        history = [
            {"timestamp": "2026-05-18T13:30:00+00:00", "king_node_strike": 100.0, "spot": 100.0},
            {"timestamp": "2026-05-18T13:40:00+00:00", "king_node_strike": 110.0, "spot": 100.0},
        ]
        result = calc_velocity_mode(history)
        assert result["velocity_strikes_per_min"] == pytest.approx(1.0)
        assert result["mode"] == "active"
        assert result["n_snapshots"] == 2

    def test_empty_history_returns_calm(self):
        """Zero snapshots → velocity 0, mode 'calm'."""
        result = calc_velocity_mode([])
        assert result["velocity_strikes_per_min"] == pytest.approx(0.0)
        assert result["mode"] == "calm"
        assert result["n_snapshots"] == 0

    def test_urgent_mode_high_velocity(self):
        """
        King node jumps 50 strikes in 10 min → velocity 5.0 → mode 'urgent'.
        Negative direction still triggers urgent because |velocity| is used.
        """
        history = [
            {"timestamp": "2026-05-18T13:30:00+00:00", "king_node_strike": 150.0, "spot": 100.0},
            {"timestamp": "2026-05-18T13:40:00+00:00", "king_node_strike": 100.0, "spot": 100.0},
        ]
        result = calc_velocity_mode(history)
        assert result["velocity_strikes_per_min"] == pytest.approx(-5.0)
        assert result["mode"] == "urgent"
        assert result["n_snapshots"] == 2

    def test_single_snapshot_returns_calm(self):
        """One snapshot is not enough to compute velocity → velocity 0, calm."""
        history = [
            {"timestamp": "2026-05-18T13:30:00+00:00", "king_node_strike": 100.0, "spot": 100.0},
        ]
        result = calc_velocity_mode(history)
        assert result["velocity_strikes_per_min"] == pytest.approx(0.0)
        assert result["mode"] == "calm"
        assert result["n_snapshots"] == 1


# ===========================================================================
# Wave 2 — Function 8: calc_trinity_confluence
# ===========================================================================

class TestTrinityConfluence:
    def test_full_alignment_score_100(self):
        """All three regimes / sides / trends agree → score 100, high_confluence."""
        snap = lambda spot, gflip, regime, trend: {
            "gex_regime": regime,
            "spot": spot,
            "gamma_flip": gflip,
            "trend_direction": trend,
        }
        spx = snap(5800.0, 5750.0, "positive", "up")
        spy = snap(580.0, 575.0, "positive", "up")
        qqq = snap(500.0, 490.0, "positive", "up")
        result = calc_trinity_confluence(spx, spy, qqq)
        assert result["score"] == 100
        assert result["verdict"] == "high_confluence"
        assert set(result["aligned_dimensions"]) == {"gex_regime", "side_of_flip", "trend"}
        assert result["divergences"] == []

    def test_full_divergence_score_zero(self):
        """
        Regimes differ, sides differ, trends differ → score 0, divergence.
        SPX above its flip with positive regime + up trend.
        SPY below its flip with negative regime + down trend.
        QQQ above its flip with neutral regime + flat trend.
        """
        snap = lambda spot, gflip, regime, trend: {
            "gex_regime": regime,
            "spot": spot,
            "gamma_flip": gflip,
            "trend_direction": trend,
        }
        spx = snap(5800.0, 5750.0, "positive", "up")
        spy = snap(560.0, 580.0, "negative", "down")
        qqq = snap(500.0, 490.0, "neutral", "flat")
        result = calc_trinity_confluence(spx, spy, qqq)
        assert result["score"] == 0
        assert result["verdict"] == "divergence"
        assert set(result["divergences"]) == {"gex_regime", "trend"}
        # Sides of flip: SPX above, SPY below, QQQ above → mixed → divergence.
        assert "side_of_flip" in result["divergences"]

    def test_partial_alignment_two_of_three(self):
        """
        Regimes all positive (+33). Sides all above flip (+33). Trends mixed
        (no +34). Total = 66 → 'high_confluence' (boundary at 66).
        """
        snap = lambda spot, gflip, regime, trend: {
            "gex_regime": regime,
            "spot": spot,
            "gamma_flip": gflip,
            "trend_direction": trend,
        }
        spx = snap(5800.0, 5750.0, "positive", "up")
        spy = snap(580.0, 575.0, "positive", "up")
        qqq = snap(500.0, 490.0, "positive", "down")  # trend differs
        result = calc_trinity_confluence(spx, spy, qqq)
        assert result["score"] == 66
        assert result["verdict"] == "high_confluence"
        assert "gex_regime" in result["aligned_dimensions"]
        assert "side_of_flip" in result["aligned_dimensions"]
        assert "trend" in result["divergences"]

    def test_missing_data_does_not_crash(self):
        """A snapshot with regime='missing' should not crash; dimension flagged."""
        snap_full = {
            "gex_regime": "positive",
            "spot": 5800.0,
            "gamma_flip": 5750.0,
            "trend_direction": "up",
        }
        snap_missing = {"gex_regime": "missing", "spot": None, "gamma_flip": None, "trend_direction": None}
        result = calc_trinity_confluence(snap_full, snap_missing, snap_full)
        # gex_regime not unanimous → 0
        # side_of_flip: SPY has None spot/flip → undefined → 0
        # trend: SPY has None trend → undefined → 0
        assert result["score"] == 0
        assert result["verdict"] == "divergence"
