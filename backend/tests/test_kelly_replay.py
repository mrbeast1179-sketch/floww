"""backend/tests/test_kelly_replay.py — Hand-verified unit tests for
backend/domain/kelly_replay.py.

Hand-pinned reference values:
  Linear-scaling anchors (baseline = 2%):
    * quarter-Kelly @ p=0.55, b=1.65 → 0.0693 fraction, scale = 3.4646
    * half-Kelly    @ p=0.55, b=1.65 → 0.1386 fraction, scale = 6.9300
    * naive 1%      scale = 0.5000
  Anchor test: $100 under 2% × 6.93 = $693 under half-Kelly.
  Filter test: GS DVT_Pullback_Cloud (wr=11.1%, b=1.65) → empirical
    Kelly = 0 → empirical scaled P&L = $0.
  Breakeven test: p < 1/(b+1) ⇒ empirical_full = 0 ⇒ no-trade.

Reference: Vince (1992) Optimal f; Tharp (1998) Ch. 7.
"""

from __future__ import annotations

import statistics

import pytest

from domain.kelly_replay import (
    ANCHOR_PAYOFF,
    ANCHOR_WIN_PROB,
    DEFAULT_EQUITY,
    NAIVE_BASELINE_PCT,
    POLICY_COLUMNS,
    percentile,
    replay_all,
    replay_record,
    scale_pnl_linear,
    theoretical_policies,
)
from domain.position_sizing import half_kelly, kelly_breakeven_probability

# ----------------------------------------------------------------------- #
# scale_pnl_linear                                                         #
# ----------------------------------------------------------------------- #


class TestScalePnlLinear:
    """Linear-scaling primitives — the workhorse under all replay math."""

    def test_identity_at_baseline(self):
        assert scale_pnl_linear(100.0, 0.02, 0.02) == 100.0

    def test_doubles_at_double_pct(self):
        assert scale_pnl_linear(100.0, 0.04, 0.02) == 200.0

    def test_hand_pin_half_kelly_calibration_anchor(self):
        """$100 under baseline 2% scaled by half-Kelly 0.1386 → $693."""
        scaled = scale_pnl_linear(100.0, half_kelly(0.55, 1.65), 0.02)
        assert scaled == pytest.approx(693.00, abs=1e-2)

    def test_hand_pin_quarter_kelly_calibration_anchor(self):
        """$100 under baseline 2% × quarter-Kelly (0.0693/0.02=3.4646) → $346.46."""
        from domain.position_sizing import quarter_kelly

        scaled = scale_pnl_linear(100.0, quarter_kelly(0.55, 1.65), 0.02)
        assert scaled == pytest.approx(346.46, abs=1e-2)

    def test_hand_pin_naive_1pct(self):
        """$100 under baseline 2% × (0.01/0.02=0.5) → $50."""
        scaled = scale_pnl_linear(100.0, 0.01, 0.02)
        assert scaled == pytest.approx(50.0, abs=1e-9)

    def test_zero_baseline_returns_unmodified(self):
        """Degenerate case: can't scale against a zero baseline."""
        assert scale_pnl_linear(100.0, 0.05, 0.0) == 100.0

    def test_negative_baseline_unmodified(self):
        """Negative baseline is degenerate and bypassed."""
        assert scale_pnl_linear(100.0, 0.05, -0.02) == 100.0

    def test_negative_pnl_scales_correctly(self):
        """$-100 under 2% × 6.93 = $-693 under half-Kelly (sign preserved).
        This is the case for losing strategies — Kelly scales losses too."""
        scaled = scale_pnl_linear(-100.0, half_kelly(0.55, 1.65), 0.02)
        assert scaled == pytest.approx(-693.00, abs=1e-2)


# ----------------------------------------------------------------------- #
# theoretical_policies                                                     #
# ----------------------------------------------------------------------- #


class TestTheoreticalPolicies:
    def test_contains_naive_baseline(self):
        policies = theoretical_policies()
        assert "naive_2pct" in policies
        assert policies["naive_2pct"] == NAIVE_BASELINE_PCT

    def test_calibration_anchor_quantities(self):
        """Quarter-Kelly 0.0693, half-Kelly 0.1386, full-Kelly 0.2773."""
        policies = theoretical_policies()
        from domain.position_sizing import kelly_fraction

        assert policies["theoretical_quarter_kelly_p055_b165"] == pytest.approx(
            0.0693, abs=1e-3
        )
        assert policies["theoretical_half_kelly_p055_b165"] == pytest.approx(
            0.1386, abs=1e-3
        )
        # Verify against canonical Kelly fraction directly.
        assert 2.0 * policies["theoretical_half_kelly_p055_b165"] == pytest.approx(
            kelly_fraction(0.55, 1.65), abs=1e-3
        )


# ----------------------------------------------------------------------- #
# percentile                                                               #
# ----------------------------------------------------------------------- #


class TestPercentile:
    def test_empty_returns_zero(self):
        assert percentile([], 0.5) == 0.0

    def test_single_value(self):
        assert percentile([42.0], 0.5) == 42.0

    def test_minimum(self):
        assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.0) == 1.0

    def test_maximum(self):
        assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 1.0) == 5.0

    def test_median_odd(self):
        assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == 3.0

    def test_median_even_linear_interp(self):
        # Two-point linear interp between 2nd and 3rd values.
        result = percentile([1.0, 2.0, 3.0, 4.0], 0.5)
        assert result == 2.5


# ----------------------------------------------------------------------- #
# replay_record                                                            #
# ----------------------------------------------------------------------- #


class TestReplayRecordFilter:
    """No-trade filter when win-rate < breakeven."""

    def test_sub_breakeven_record_filtered(self):
        """GS DVT_Pullback_Cloud: win_rate=11.1% (0.111), avg_rr=1.65.
        Breakeven at b=1.65 is 1/(1.65+1) = 0.3774. 0.111 < 0.3774
        → empirical Kelly = 0 → empirical half/quarter P&L = $0."""
        record = {
            "symbol": "GS",
            "name": "DVT_Pullback_Cloud",
            "win_rate": 11.1,
            "avg_rr": 1.65,
            "total_pnl": -1154.81,
            "trades": 9,
        }
        out = replay_record(record)
        assert out["empirical_filtered"] is True
        assert out["empirical_full_kelly"] == 0.0
        assert out["pnl_empirical_half_kelly"] == 0.0
        assert out["pnl_empirical_quarter_kelly"] == 0.0
        # Sanity: naive 2% baseline must NOT be filtered (records the real loss).
        assert out["pnl_naive_2pct"] == pytest.approx(-1154.81, abs=1e-2)

    def test_above_breakeven_record_scaled(self):
        """AMAT DVT_Momentum: wr=66.67%, b=1.76. Above breakeven 36.22%
        → empirical Kelly > 0 → empirical half-Kelly scales linearly."""
        record = {
            "symbol": "AMAT",
            "name": "DVT_Momentum",
            "win_rate": 66.67,
            "avg_rr": 1.76,
            "total_pnl": 1464.49,
            "trades": 9,
        }
        out = replay_record(record)
        assert out["empirical_filtered"] is False
        assert out["empirical_full_kelly"] > 0.0
        # Empirical half P&L > naive 2% P&L (Kelly up-weights winners).
        assert out["pnl_empirical_half_kelly"] > out["pnl_naive_2pct"]


class TestReplayRecordScaling:
    def test_baseline_naive_identity(self):
        """Verify naive 2% scaling is identity (pnl_naive_2pct == total_pnl)."""
        record = {
            "symbol": "X",
            "name": "STRAT",
            "win_rate": 55.0,
            "avg_rr": 1.65,
            "total_pnl": 100.0,
            "trades": 5,
        }
        out = replay_record(record)
        assert out["pnl_naive_2pct"] == pytest.approx(100.0)

    def test_naive_1pct_halves(self):
        """naive 1% should produce half of baseline P&L."""
        record = {
            "symbol": "X",
            "name": "STRAT",
            "win_rate": 55.0,
            "avg_rr": 1.65,
            "total_pnl": 100.0,
        }
        out = replay_record(record)
        assert out["pnl_naive_1pct"] == pytest.approx(50.0, abs=1e-9)

    def test_theoretical_half_kelly_scales_by_anchor(self):
        """Anchor policy 0.1386 over baseline 0.02 = 6.93× multiplier."""
        record = {
            "symbol": "X",
            "name": "STRAT",
            "win_rate": 55.0,
            "avg_rr": 1.65,
            "total_pnl": 100.0,
        }
        out = replay_record(record)
        assert out["pnl_theoretical_half_kelly"] == pytest.approx(693.0, abs=1e-1)


# ----------------------------------------------------------------------- #
# replay_all                                                               #
# ----------------------------------------------------------------------- #


class TestReplayAllStructure:
    def test_returns_well_typed_dict(self):
        records = [
            {
                "symbol": "X",
                "name": "STRAT",
                "win_rate": 50.0,
                "avg_rr": 2.0,
                "total_pnl": 200.0,
                "trades": 3,
            }
        ]
        payload = replay_all(records)
        assert "per_record" in payload
        assert "aggregates" in payload
        assert "avoided_loss_count" in payload
        assert "theoretical_policies" in payload
        # Aggregates cover all 6 columns.
        assert set(payload["aggregates"].keys()) == set(POLICY_COLUMNS)
        # Per-record: same length as input.
        assert len(payload["per_record"]) == 1

    def test_empty_records_list_does_not_crash(self):
        payload = replay_all([])
        assert payload["per_record"] == []
        assert payload["avoided_loss_count"] == 0
        # Aggregate counts are zero.
        for _col, agg in payload["aggregates"].items():
            assert agg["n_records"] == 0
            assert agg["total_pnl"] == 0.0

    def test_real_dvt_backtest_v2_loads_cleanly(self):
        """End-to-end: load the actual dvt_backtest_v2.json and verify
        it produces reasonable replay output without errors."""
        import json
        from pathlib import Path

        path = Path("/Users/nav/dvt_backtest_v2.json")
        if not path.exists():
            pytest.skip("dvt_backtest_v2.json not present")
        with path.open() as fh:
            raw = json.load(fh)
        records = raw if isinstance(raw, list) else raw.get("results", [])

        payload = replay_all(records)
        assert len(payload["per_record"]) == 21
        # All aggregates should have n_records == 21.
        for agg in payload["aggregates"].values():
            assert agg["n_records"] == 21


class TestReplayAllConsistency:
    """Cross-policy invariants that must hold on the actual backtest data."""

    def test_full_kelly_filter_count_matches_per_record_filter(self):
        import json
        from pathlib import Path

        path = Path("/Users/nav/dvt_backtest_v2.json")
        if not path.exists():
            pytest.skip("dvt_backtest_v2.json not present")
        with path.open() as fh:
            raw = json.load(fh)
        records = raw if isinstance(raw, list) else raw.get("results", [])

        payload = replay_all(records)
        per_record_filtered = sum(
            1 for r in payload["per_record"] if r["empirical_filtered"]
        )
        assert payload["avoided_loss_count"] == per_record_filtered

    def test_avoided_loss_pnl_sums_correctly(self):
        """Avoided-loss P&L should equal the negative-sum of filtered records'
        raw P&L (the losses the Kelly discipline would have prevented)."""
        import json
        from pathlib import Path

        path = Path("/Users/nav/dvt_backtest_v2.json")
        if not path.exists():
            pytest.skip("dvt_backtest_v2.json not present")
        with path.open() as fh:
            raw = json.load(fh)
        records = raw if isinstance(raw, list) else raw.get("results", [])

        payload = replay_all(records)
        expected = round(
            sum(
                r["pnl_naive_2pct"]
                for r in payload["per_record"]
                if r["empirical_filtered"] and r["pnl_naive_2pct"] < 0
            ),
            2,
        )
        assert payload["avoided_loss_pnl"] == expected

    def test_naive_2pct_aggregate_equals_sum_of_records(self):
        import json
        from pathlib import Path

        path = Path("/Users/nav/dvt_backtest_v2.json")
        if not path.exists():
            pytest.skip("dvt_backtest_v2.json not present")
        with path.open() as fh:
            raw = json.load(fh)
        records = raw if isinstance(raw, list) else raw.get("results", [])

        payload = replay_all(records)
        actual_sum = round(
            sum(r["pnl_naive_2pct"] for r in payload["per_record"]), 2
        )
        assert (
            payload["aggregates"]["pnl_naive_2pct"]["total_pnl"] == actual_sum
        )

    def test_scaling_factor_matches_baseline(self):
        """Aggregate's policy_pct should match the scaling ratio when derived
        from theoretical anchor (sanity check on policy registry)."""
        import json
        from pathlib import Path

        path = Path("/Users/nav/dvt_backtest_v2.json")
        if not path.exists():
            pytest.skip("dvt_backtest_v2.json not present")
        with path.open() as fh:
            raw = json.load(fh)
        records = raw if isinstance(raw, list) else raw.get("results", [])

        payload = replay_all(records)

        # Quarterly theoretical Kelly
        qkt = payload["aggregates"]["pnl_theoretical_quarter_kelly"]
        # Theoretical quarter Kelly pct is constant across records (anchor).
        assert qkt["policy_pct"] == pytest.approx(
            theoretical_policies()[
                "theoretical_quarter_kelly_p055_b165"
            ],
            abs=1e-3,
        )
        # Empirical halfKelly is per-record; median across records matches agg.
        ehl = payload["aggregates"]["pnl_empirical_half_kelly"]
        assert 0.0 <= ehl["policy_pct"] <= 1.0


# ----------------------------------------------------------------------- #
# Cross-property sanity tests                                              #
# ----------------------------------------------------------------------- #


class TestReplayMonotonicity:
    def test_total_pnl_under_higher_pct_proportionally_larger(self):
        """Sums scale linearly with policy pct at fixed baseline."""
        record_template = {
            "symbol": "X",
            "name": "STRAT",
            "win_rate": 60.0,
            "avg_rr": 1.5,
            "total_pnl": 100.0,
        }
        records_a = [dict(record_template) for _ in range(5)]
        records_b = [dict(record_template) for _ in range(5)]

        payload_2pct = replay_all(records_a, baseline_pct=0.02)
        payload_4pct = replay_all(records_b, baseline_pct=0.04)

        # Since baseline_pct changed, naive_2pct column in payload_a maps to 0.02,
        # but in payload_b maps to 0.04. Comparing totals:
        naive_a = payload_2pct["aggregates"]["pnl_naive_2pct"]["total_pnl"]
        naive_b = payload_4pct["aggregates"]["pnl_naive_2pct"]["total_pnl"]
        assert naive_b == pytest.approx(2.0 * naive_a, abs=1e-6)
