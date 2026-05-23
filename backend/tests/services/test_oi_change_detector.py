"""
Tests for Open Interest Change Detector.

Validates:
  - Correct % change calculation.
  - "New Positioning" flag for >10% changes.
  - Edge cases (zero previous OI, missing strikes).
  - Array-based API.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.oi_change_detector import OiChangeDetector, OiChangeSnapshot


class TestOiChangeBasic:
    """Core % change computation."""

    def setup_method(self):
        self.det = OiChangeDetector()

    def test_no_change(self):
        result = self.det.detect(
            current_oi={450.0: 1000.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].pct_change == 0.0
        assert result.changes[450.0].flag == ""

    def test_10pct_increase(self):
        result = self.det.detect(
            current_oi={450.0: 1100.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert abs(result.changes[450.0].pct_change - 0.10) < 1e-9

    def test_50pct_increase(self):
        result = self.det.detect(
            current_oi={450.0: 1500.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert abs(result.changes[450.0].pct_change - 0.50) < 1e-9

    def test_20pct_decrease(self):
        result = self.det.detect(
            current_oi={450.0: 800.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert abs(result.changes[450.0].pct_change - (-0.20)) < 1e-9


class TestOiChangeFlagging:
    """New Positioning flag."""

    def setup_method(self):
        self.det = OiChangeDetector(threshold=0.10)

    def test_15pct_increase_flagged(self):
        result = self.det.detect(
            current_oi={450.0: 1150.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].flag == "New Positioning"
        assert 450.0 in result.significant

    def test_5pct_increase_not_flagged(self):
        result = self.det.detect(
            current_oi={450.0: 1050.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].flag == ""
        assert 450.0 not in result.significant

    def test_15pct_decrease_flagged(self):
        result = self.det.detect(
            current_oi={450.0: 850.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].flag == "New Positioning"

    def test_new_positioning_from_zero(self):
        result = self.det.detect(
            current_oi={450.0: 500.0},
            previous_oi={450.0: 0.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].pct_change == float("inf")
        assert result.changes[450.0].flag == "New Positioning"


class TestOiChangeMaxValues:
    """Max increase/decrease tracking."""

    def setup_method(self):
        self.det = OiChangeDetector()

    def test_max_increase(self):
        result = self.det.detect(
            current_oi={440.0: 1100.0, 450.0: 1300.0, 460.0: 1000.0},
            previous_oi={440.0: 1000.0, 450.0: 1000.0, 460.0: 1000.0},
            expiry="2026-07-06",
        )
        assert abs(result.max_increase - 0.30) < 1e-9

    def test_max_decrease(self):
        result = self.det.detect(
            current_oi={440.0: 900.0, 450.0: 700.0, 460.0: 1000.0},
            previous_oi={440.0: 1000.0, 450.0: 1000.0, 460.0: 1000.0},
            expiry="2026-07-06",
        )
        assert abs(result.max_decrease - (-0.30)) < 1e-9


class TestOiChangeEdgeCases:
    """Edge cases."""

    def setup_method(self):
        self.det = OiChangeDetector()

    def test_both_zero(self):
        result = self.det.detect(
            current_oi={450.0: 0.0},
            previous_oi={450.0: 0.0},
            expiry="2026-07-06",
        )
        assert result.changes[450.0].pct_change == 0.0

    def test_missing_strike_in_previous(self):
        result = self.det.detect(
            current_oi={450.0: 500.0, 460.0: 300.0},
            previous_oi={450.0: 1000.0},
            expiry="2026-07-06",
        )
        assert 460.0 in result.changes
        assert result.changes[460.0].pct_change == float("inf")

    def test_missing_strike_in_current(self):
        result = self.det.detect(
            current_oi={450.0: 500.0},
            previous_oi={450.0: 1000.0, 460.0: 300.0},
            expiry="2026-07-06",
        )
        assert 460.0 in result.changes
        assert result.changes[460.0].current_oi == 0.0


class TestOiChangeFromArrays:
    """NumPy array convenience wrapper."""

    def setup_method(self):
        self.det = OiChangeDetector()

    def test_array_input(self):
        result = self.det.detect_from_arrays(
            current_oi=np.array([1100.0, 800.0]),
            previous_oi=np.array([1000.0, 1000.0]),
            strikes=np.array([440.0, 450.0]),
            expiry="2026-07-06",
        )
        assert abs(result.changes[440.0].pct_change - 0.10) < 1e-9
        assert abs(result.changes[450.0].pct_change - (-0.20)) < 1e-9
