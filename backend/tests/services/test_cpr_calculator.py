"""
Tests for Call/Put Volume Ratio (CPR) Calculator.

Validates:
  - Correct CPR calculation per expiry.
  - Rolling average over 5-day window.
  - Anomaly flagging (Bullish >2.0, Bearish <0.5).
  - Edge cases (zero volume, inf handling).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.cpr_calculator import CprCalculator


class TestCprBasic:
    """Core CPR computation."""

    def setup_method(self):
        self.calc = CprCalculator()

    def test_equal_volume_cpr_is_one(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 1000.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert result.current["2026-07-06"].cpr == 1.0
        assert result.current["2026-07-06"].label == "Neutral"

    def test_double_call_volume_cpr_is_two(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 2000.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert result.current["2026-07-06"].cpr == 2.0
        assert result.current["2026-07-06"].label == "Bullish"

    def test_half_call_volume_cpr_is_half(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 500.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert result.current["2026-07-06"].cpr == 0.5
        assert result.current["2026-07-06"].label == "Bearish"

    def test_zero_both_volumes_cpr_is_zero(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 0.0},
            put_volumes={"2026-07-06": 0.0},
        )
        assert result.current["2026-07-06"].cpr == 0.0

    def test_zero_put_volume_cpr_is_inf(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 1000.0},
            put_volumes={"2026-07-06": 0.0},
        )
        assert result.current["2026-07-06"].cpr == float("inf")
        assert result.current["2026-07-06"].label == "Bullish"


class TestCprMultiExpiry:
    """Multiple expiries in one call."""

    def setup_method(self):
        self.calc = CprCalculator()

    def test_two_expiries(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 2000.0, "2026-07-13": 500.0},
            put_volumes={"2026-07-06": 1000.0, "2026-07-13": 1000.0},
        )
        assert result.current["2026-07-06"].cpr == 2.0
        assert result.current["2026-07-13"].cpr == 0.5

    def test_missing_expiry_in_put_defaults_zero(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 1000.0},
            put_volumes={},
        )
        assert result.current["2026-07-06"].cpr == float("inf")


class TestCprAnomalies:
    """Anomaly flagging."""

    def setup_method(self):
        self.calc = CprCalculator()

    def test_bullish_anomaly_flagged(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 3000.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert len(result.anomalies) == 1
        assert "Bullish" in result.anomalies[0]

    def test_bearish_anomaly_flagged(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 300.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert len(result.anomalies) == 1
        assert "Bearish" in result.anomalies[0]

    def test_neutral_no_anomaly(self):
        result = self.calc.compute(
            call_volumes={"2026-07-06": 1200.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert len(result.anomalies) == 0


class TestCprRollingAverage:
    """Rolling 5-day average."""

    def setup_method(self):
        self.calc = CprCalculator(window_days=5)

    def test_rolling_avg_after_3_days(self):
        for _ in range(3):
            self.calc.compute(
                call_volumes={"2026-07-06": 1500.0},
                put_volumes={"2026-07-06": 1000.0},
            )
        result = self.calc.compute(
            call_volumes={"2026-07-06": 1500.0},
            put_volumes={"2026-07-06": 1000.0},
        )
        assert self.calc.history_depth == 4
        assert abs(result.rolling_avg["2026-07-06"] - 1.5) < 0.01

    def test_rolling_avg_window_caps_at_5(self):
        for i in range(10):
            self.calc.compute(
                call_volumes={"2026-07-06": 1000.0 + i * 100},
                put_volumes={"2026-07-06": 1000.0},
            )
        assert self.calc.history_depth == 5


class TestCprFromArrays:
    """NumPy array convenience wrapper."""

    def setup_method(self):
        self.calc = CprCalculator()

    def test_array_input(self):
        result = self.calc.compute_from_arrays(
            call_vols=np.array([2000.0, 500.0]),
            put_vols=np.array([1000.0, 1000.0]),
            expiries=["2026-07-06", "2026-07-13"],
        )
        assert result.current["2026-07-06"].cpr == 2.0
        assert result.current["2026-07-13"].cpr == 0.5
