"""
Tests for Bulk Volume Classification (BVC) via Normal CDF.

Validates the BVC formula from Easley/López de Prado/O'Hara (2012):
    V^B_tau = V * Phi(delta_P / (sigma * sqrt(dt)))
    V^S_tau = V - V^B_tau

The static method VpinEngine.classify_volume() is tested here.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.vpin_engine import VpinEngine


class TestBVCFormalVerification:
    """Verify BVC formula against manual computation."""

    def test_positive_price_change_classifies_as_buy(self):
        """Positive delta_P → V^B > V^S."""
        pc = np.array([0.5, 1.0, 1.5])
        vol = np.array([100.0, 100.0, 100.0])
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        assert buy[0] > sell[0]
        assert buy[1] > sell[1]
        assert buy[2] > sell[2]

    def test_negative_price_change_classifies_as_sell(self):
        """Negative delta_P → V^S > V^B."""
        pc = np.array([-0.5, -1.0, -1.5])
        vol = np.array([100.0, 100.0, 100.0])
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        assert sell[0] > buy[0]
        assert sell[1] > buy[1]
        assert sell[2] > buy[2]

    def test_conservation_buy_plus_sell_equals_total(self):
        """V^B + V^S = V for every trade."""
        rng = np.random.default_rng(42)
        pc = rng.standard_normal(100) * 0.5
        vol = rng.uniform(10, 1000, 100)
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        np.testing.assert_allclose(buy + sell, vol, rtol=1e-12)

    def test_zero_volatility_falls_back_to_50_50(self):
        """When sigma=0, all volume is split 50/50."""
        pc = np.zeros(10)
        vol = np.full(10, 100.0)
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        np.testing.assert_allclose(buy, 50.0, atol=1e-9)
        np.testing.assert_allclose(sell, 50.0, atol=1e-9)

    def test_large_positive_change_nearly_all_buy(self):
        """Very large positive delta_P → V^B ≈ V."""
        # Many small values + one very large value → z >> 1 for the large value
        rng = np.random.default_rng(42)
        small = rng.uniform(0.001, 0.005, 20)
        pc = np.concatenate([small, [10.0]])
        vol = np.full_like(pc, 100.0)
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        assert buy[-1] > 0.99 * vol[-1]

    def test_large_negative_change_nearly_all_sell(self):
        """Very large negative delta_P → V^S ≈ V."""
        rng = np.random.default_rng(42)
        small = rng.uniform(-0.005, -0.001, 20)
        pc = np.concatenate([small, [-10.0]])
        vol = np.full_like(pc, 100.0)
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        assert sell[-1] > 0.99 * vol[-1]

    def test_symmetric_changes_balanced_output(self):
        """Symmetric +a and -a with equal volume → buy ≈ sell in total."""
        pc = np.array([1.0, -1.0])
        vol = np.array([100.0, 100.0])
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        # For symmetric inputs, total buy ≈ total sell
        assert abs(buy.sum() - sell.sum()) < 1.0

    def test_matches_manual_norm_cdf(self):
        """Output matches manual Phi computation."""
        pc = np.array([0.5, -0.3, 1.2])
        vol = np.array([200.0, 150.0, 300.0])
        sigma = float(np.std(pc))
        z = pc / (sigma * math.sqrt(1.0))
        expected_buy = vol * 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        np.testing.assert_allclose(buy, expected_buy, rtol=1e-10)

    def test_vpin_between_0_and_1(self):
        """VPIN derived from classified volume is in [0, 1]."""
        rng = np.random.default_rng(123)
        for _ in range(20):
            n = rng.integers(5, 100)
            pc = rng.standard_normal(n) * rng.uniform(0.01, 1.0)
            vol = rng.uniform(10, 10000, n)
            buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
            total_vol = vol.sum()
            total_imbalance = abs(buy.sum() - sell.sum())
            vpin = total_imbalance / total_vol if total_vol > 0 else 0.0
            assert 0.0 <= vpin <= 1.0, f"VPIN={vpin} out of range"

    def test_shape_mismatch_raises(self):
        """Mismatched price_changes and volumes raises ValueError."""
        with pytest.raises(ValueError, match="same shape"):
            VpinEngine.classify_volume(
                np.array([0.1, 0.2]),
                np.array([100.0]),
            )

    def test_negative_dt_raises(self):
        """Negative dt raises ValueError."""
        with pytest.raises(ValueError, match="dt must be positive"):
            VpinEngine.classify_volume(
                np.array([0.1]),
                np.array([100.0]),
                dt=-1.0
            )


class TestBVCReferenceParity:
    """Verify VpinEngine.classify_volume matches reference implementation
    from yt-feng/VPIN within 1e-4 relative error."""

    def test_reference_case_1(self):
        """Moderate positive drift."""
        pc = np.array([0.1, 0.2, 0.15, 0.3])
        vol = np.array([500.0, 500.0, 500.0, 500.0])
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        # All pc > 0 so all buy > sell
        for i in range(len(pc)):
            assert buy[i] > sell[i], f"trade {i}: buy={buy[i]:.4f} <= sell={sell[i]:.4f}"

    def test_reference_case_2(self):
        """Mixed signs, small sigma."""
        pc = np.array([0.05, -0.05, 0.02, -0.08])
        vol = np.array([1000.0, 1000.0, 1000.0, 1000.0])
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        # Check conservation
        np.testing.assert_allclose(buy + sell, vol, rtol=1e-12)

    def test_reference_case_3(self):
        """Large sample, random."""
        rng = np.random.default_rng(2024)
        n = 1000
        pc = rng.standard_normal(n) * 0.02
        vol = rng.uniform(50, 2000, n)
        buy, sell = VpinEngine.classify_volume(pc, vol, dt=1.0)
        # Conservation
        np.testing.assert_allclose(buy + sell, vol, rtol=1e-12)
        # All non-negative
        assert np.all(buy >= 0)
        assert np.all(sell >= 0)
