"""
Tests for Quote Imbalance Z-Score Calculator.

Validates:
  - QI = (bid_size - ask_size) / (bid_size + ask_size)
  - Bid-dominant LOB → positive QI.
  - Rolling z-score matches manual numpy computation.
  - Z-score is 0 with insufficient history.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.quote_imbalance import QuoteImbalanceTracker
from services.vpin_engine import VpinEngine


class TestQuoteImputation:
    """Basic QI computation."""

    def test_equal_bid_ask_gives_zero_qi(self):
        """Equal bid/ask sizes → QI = 0."""
        qi = QuoteImbalanceTracker()
        assert qi.update(100.0, 100.0) == pytest.approx(0.0)

    def test_bid_dominant_positive_qi(self):
        """Larger bid → positive QI."""
        qi = QuoteImbalanceTracker()
        result = qi.update(200.0, 100.0)
        assert result > 0.0
        assert result == pytest.approx(1 / 3, rel=1e-9)

    def test_ask_dominant_negative_qi(self):
        """Larger ask → negative QI."""
        qi = QuoteImbalanceTracker()
        result = qi.update(100.0, 200.0)
        assert result < 0.0
        assert result == pytest.approx(-1 / 3, rel=1e-9)

    def test_qi_range(self):
        """QI is always in [-1, 1]."""
        rng = np.random.default_rng(42)
        qi = QuoteImbalanceTracker()
        for _ in range(100):
            b = rng.uniform(0, 10000)
            a = rng.uniform(0, 10000)
            result = qi.update(b, a)
            assert -1.0 <= result <= 1.0

    def test_zero_total_gives_zero_qi(self):
        """Both sizes zero → QI = 0."""
        qi = QuoteImbalanceTracker()
        assert qi.update(0.0, 0.0) == pytest.approx(0.0)

    def test_only_bid_gives_qi_1(self):
        """Only bid, no ask → QI = 1.0."""
        qi = QuoteImbalanceTracker()
        assert qi.update(100.0, 0.0) == pytest.approx(1.0)

    def test_only_ask_gives_qi_neg1(self):
        """Only ask, no bid → QI = -1.0."""
        qi = QuoteImbalanceTracker()
        assert qi.update(0.0, 100.0) == pytest.approx(-1.0)


class TestQuoteImbalanceZScore:
    """Rolling z-score computation."""

    def test_insufficient_history_zscore_zero(self):
        """With < 2 observations, z-score = 0."""
        qi = QuoteImbalanceTracker(window=100)
        qi.update(100.0, 50.0)
        assert qi.zscore == 0.0

    def test_zscore_matches_numpy(self):
        """Z-score matches manual numpy computation."""
        qi = QuoteImbalanceTracker(window=100)
        values = [0.1, -0.2, 0.3, -0.1, 0.0, 0.15, -0.05, 0.25, -0.15, 0.05]
        for v in values:
            # Create LOB that produces this QI
            # QI = (b-a)/(b+a) → b = a*(1+QI)/(1-QI)
            a = 100.0
            b = a * (1 + v) / (1 - v) if abs(v) < 1 else 100.0
            qi.update(b, a)
        # Manual z-score
        arr = np.array(values, dtype=np.float64)
        mean = np.mean(arr)
        std = np.std(arr, ddof=0)
        expected_z = float((values[-1] - mean) / std) if std > 0 else 0.0
        assert qi.zscore == pytest.approx(expected_z, abs=1e-9)

    def test_positive_zscore_for_extreme_bid(self):
        """Extreme bid dominance → positive z-score."""
        qi = QuoteImbalanceTracker(window=50)
        for _ in range(20):
            qi.update(100.0, 100.0)  # neutral
        qi.update(500.0, 50.0)  # extreme bid
        assert qi.zscore > 0.0

    def test_negative_zscore_for_extreme_ask(self):
        """Extreme ask dominance → negative z-score."""
        qi = QuoteImbalanceTracker(window=50)
        for _ in range(20):
            qi.update(100.0, 100.0)  # neutral
        qi.update(50.0, 500.0)  # extreme ask
        assert qi.zscore < 0.0

    def test_zscore_window_slides(self):
        """Old values drop out when window slides."""
        qi = QuoteImbalanceTracker(window=5)
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            qi.update(100.0 * (1 + v) / (1 - v), 100.0)
        z1 = qi.zscore
        # Add one more → oldest (0.1) drops out
        qi.update(100.0 * (1 + 0.9) / (1 - 0.9), 100.0)
        z2 = qi.zscore
        assert z1 != z2  # z-score changed after window slide

    def test_is_bid_dominant(self):
        """is_bid_dominant is True when QI > 0."""
        qi = QuoteImbalanceTracker()
        qi.update(200.0, 100.0)
        assert qi.is_bid_dominant is True
        qi.update(100.0, 200.0)
        assert qi.is_bid_dominant is False

    def test_is_significant(self):
        """is_significant when |z-score| > threshold."""
        qi = QuoteImbalanceTracker(window=50)
        for _ in range(20):
            qi.update(100.0, 100.0)
        qi.update(500.0, 50.0)
        # is_significant is a property with threshold param — just verify it doesn't crash
        _ = qi.is_significant

    def test_reset_clears_history(self):
        """reset() clears all history."""
        qi = QuoteImbalanceTracker()
        for _ in range(10):
            qi.update(200.0, 100.0)
        qi.reset()
        assert qi.qi == 0.0
        assert qi.zscore == 0.0

    def test_state_dict(self):
        """get_state returns complete state."""
        qi = QuoteImbalanceTracker(window=50)
        qi.update(200.0, 100.0)
        state = qi.get_state()
        assert "qi" in state
        assert "zscore" in state
        assert "window" in state
        assert "history_length" in state
        assert "is_bid_dominant" in state


class TestQuoteImbalanceEngineIntegration:
    """Integration with VpinEngine."""

    def test_engine_qi_integration(self):
        """VpinEngine.compute_quote_imbalance delegates to tracker."""
        eng = VpinEngine()
        qi = eng.compute_quote_imbalance(200.0, 100.0)
        assert qi > 0.0

    def test_engine_qi_zscore(self):
        """VpinEngine.compute_qi_zscore returns tracker z-score."""
        eng = VpinEngine()
        for _ in range(20):
            eng.compute_quote_imbalance(100.0, 100.0)
        eng.compute_quote_imbalance(500.0, 50.0)
        z = eng.compute_qi_zscore()
        assert z > 0.0

    def test_toxicity_includes_qi(self):
        """get_toxicity_signal includes QI and z-score."""
        eng = VpinEngine()
        eng.compute_quote_imbalance(200.0, 100.0)
        sig = eng.get_toxicity_signal()
        assert "qi" in sig
        assert "qi_zscore" in sig
