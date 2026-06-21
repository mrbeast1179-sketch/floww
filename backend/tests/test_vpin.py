"""
Tests for backend/domain/vpin.py — BVC, VPIN scalar, Quote Imbalance.

Hand-pinned reference values + property invariants:
  * Φ(0) = 0.5
  * Φ(1.96) ≈ 0.975
  * Φ(−1.96) ≈ 0.025
  * BVC on zero price changes   → exactly 50/50 split
  * BVC on zero std + zero mean → exactly 50/50 (the early-return branch)
  * compute_vpin(balanced buckets) == 0
  * compute_vpin(one-sided buckets) == 1
  * quote_imbalance(150, 50) == 0.5; (100,100) == 0; (B+A=0) == 0

These tests pin the domain layer against which the
``services/vpin_engine.py`` and ``services/vpin_cdf.py`` call paths must agree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_BACKEND))

from domain.vpin import (
    bulk_volume_classify,
    compute_vpin,
    quote_imbalance,
    standard_normal_cdf,
    volume_imbalance,
)


class TestStandardNormalCdf:
    """Φ(x) = 0.5 · (1 + erf(x / √2)) — scalar + vector."""

    def test_phi_zero(self):
        """Φ(0) = 0.5 (the most-pinned normal-CDF fact)."""
        assert standard_normal_cdf(0.0) == pytest.approx(0.5, abs=1e-15)

    def test_phi_one(self):
        """Φ(1) ≈ 0.8413447."""
        assert standard_normal_cdf(1.0) == pytest.approx(0.841344746, abs=1e-6)

    def test_phi_positive_1p96(self):
        """Φ(1.96) ≈ 0.975 (two-sided 95% critical)."""
        assert standard_normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)

    def test_phi_negative_1p96(self):
        """Φ(−1.96) ≈ 0.025 (symmetry of Φ)."""
        assert standard_normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)

    def test_phi_symmetry(self):
        """Φ(−x) = 1 − Φ(x)."""
        for x in [0.1, 0.5, 1.0, 1.5, 2.0, 3.0]:
            assert standard_normal_cdf(-x) == pytest.approx(
                1.0 - standard_normal_cdf(x), abs=1e-12
            )

    def test_phi_range_zero_one(self):
        """Φ is bounded [0, 1] for any real input."""
        for x in [-10.0, -3.0, -0.5, 0.0, 0.5, 3.0, 10.0]:
            assert 0.0 <= standard_normal_cdf(x) <= 1.0

    def test_phi_vectorized(self):
        """Vectorized input returns an ndarray with the same values."""
        xs = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        out = standard_normal_cdf(xs)
        assert isinstance(out, np.ndarray)
        assert out.shape == xs.shape
        assert out[2] == pytest.approx(0.5, abs=1e-12)
        # Symmetry: x[0] + x[4] should sum to 1
        assert out[0] + out[4] == pytest.approx(1.0, abs=1e-9)
        assert out[1] + out[3] == pytest.approx(1.0, abs=1e-9)

    def test_phi_int_input_returns_scalar(self):
        """Integer input dispatches to the scalar branch."""
        v = standard_normal_cdf(0)
        assert isinstance(v, float)
        assert v == pytest.approx(0.5, abs=1e-15)


class TestBulkVolumeClassify:
    """BVC: V^B = V · Φ(ΔP / (σ √dt)); V^S = V − V^B."""

    def test_bvc_zero_pc_equal_split(self):
        """pc=0 ∀ entries ⇒ z=0 ⇒ Φ(z)=0.5 ⇒ exactly 50/50 split."""
        # Use pc=0 for every entry so z=0 deterministically (independent of σ).
        pc = np.zeros(5)
        v = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        buy, sell = bulk_volume_classify(pc, v, sigma=1.0, dt=1.0)
        assert np.allclose(buy, v * 0.5)
        assert np.allclose(sell, v * 0.5)

    def test_bvc_zero_sigma_zero_mean_50_50(self):
        """Zero std + zero mean → early-return branch gives 50/50."""
        pc = np.array([0.0, 0.0, 0.0])
        v = np.array([15.0, 25.0, 60.0])
        buy, sell = bulk_volume_classify(pc, v)  # sigma=None → std=0 → mean_abs=0
        assert np.allclose(buy, [7.5, 12.5, 30.0])
        assert np.allclose(sell, [7.5, 12.5, 30.0])

    def test_bvc_strong_up_tilt(self):
        """Strong upward price change (z = +3) → Φ≈0.9987 → almost all buy."""
        pc = np.array([3.0])
        v = np.array([100.0])
        buy, sell = bulk_volume_classify(pc, v, sigma=1.0, dt=1.0)
        # Φ(3) ≈ 0.99865 ⇒ buy[0] ≈ 99.865.
        assert buy[0] == pytest.approx(99.865, rel=1e-3)
        assert sell[0] == pytest.approx(0.135, rel=1e-2)

    def test_bvc_strong_down_tilt(self):
        """Strong downward price change (z = −3) → Φ≈0.00135 → ≈ 0.135 buy / 99.865 sell."""
        pc = np.array([-3.0])
        v = np.array([100.0])
        buy, sell = bulk_volume_classify(pc, v, sigma=1.0, dt=1.0)
        # Φ(-3) ≈ 0.00135 ⇒ buy[0] ≈ 0.135, sell[0] ≈ 99.865.
        assert buy[0] == pytest.approx(0.135, rel=1e-2)
        assert sell[0] == pytest.approx(99.865, rel=1e-3)

    def test_bvc_buy_plus_sell_equals_volume(self):
        """Identity: buy + sell == volume for arbitrary inputs."""
        rng = np.random.default_rng(7)
        pc = rng.normal(0, 0.5, size=100)
        v = rng.uniform(50, 500, size=100)
        buy, sell = bulk_volume_classify(pc, v)
        assert np.allclose(buy + sell, v)

    def test_bvc_inferred_sigma(self):
        """``sigma=None`` infers from std of price_changes."""
        pc = np.array([0.0, 0.0, 0.0])
        v = np.array([10.0, 20.0, 30.0])
        # std=0 → mean_abs=0 → 50/50
        buy, sell = bulk_volume_classify(pc, v)
        assert np.allclose(buy, v * 0.5)

    def test_bvc_dt_invalid_raises(self):
        """Negative dt must raise."""
        pc = np.array([0.1])
        v = np.array([100.0])
        with pytest.raises(ValueError, match="dt"):
            bulk_volume_classify(pc, v, dt=0.0)
        with pytest.raises(ValueError, match="dt"):
            bulk_volume_classify(pc, v, dt=-1.0)

    def test_bvc_shape_mismatch_raises(self):
        """price_changes and volumes of different shapes must raise."""
        pc = np.array([0.1, 0.2])
        v = np.array([100.0])
        with pytest.raises(ValueError, match="same shape"):
            bulk_volume_classify(pc, v)

    def test_bvc_dt_larger_dt_smaller_z_smaller_phi_for_positive_pc(self):
        """``dt`` enters as ``√dt``: z = pc / (σ √dt). Fix pc>0 ⇒ larger dt
        ⇒ smaller z ⇒ smaller Φ ⇒ smaller buy fraction.
        """
        pc = np.array([1.0])
        v = np.array([100.0])
        b1, _ = bulk_volume_classify(pc, v, sigma=1.0, dt=1.0)   # z=1.0, Φ≈0.8413
        b4, _ = bulk_volume_classify(pc, v, sigma=1.0, dt=4.0)   # z=0.5, Φ≈0.6915
        # Φ monotone increasing ⇒ smaller z ⇒ smaller Φ ⇒ smaller buy fraction.
        assert b4[0] < b1[0]


class TestVolumeImbalance:
    """|V^B − V^S| per bucket."""

    def test_imbalance_perfect_balance(self):
        """Equal sides → imbalance = 0."""
        b = np.array([50.0, 50.0, 50.0])
        s = np.array([50.0, 50.0, 50.0])
        assert np.allclose(volume_imbalance(b, s), 0.0)

    def test_imbalance_full_one_sided(self):
        """All-buy buckets → imbalance = total."""
        b = np.array([100.0, 200.0, 300.0])
        s = np.array([0.0, 0.0, 0.0])
        assert np.allclose(volume_imbalance(b, s), [100.0, 200.0, 300.0])

    def test_imbalance_pairwise(self):
        """Paired difference is the element-wise |b − s|."""
        b = np.array([80.0, 60.0, 50.0])
        s = np.array([20.0, 40.0, 50.0])
        assert np.allclose(volume_imbalance(b, s), [60.0, 20.0, 0.0])

    def test_imbalance_shape_mismatch_raises(self):
        """Different shapes raise ValueError."""
        with pytest.raises(ValueError, match="same shape"):
            volume_imbalance(np.array([1, 2]), np.array([1, 2, 3]))


class TestComputeVpin:
    """VPIN = Σ|V^B − V^S| / ΣV over the rolling window."""

    def test_vpin_balanced_is_zero(self):
        """Buy+sell equal in every bucket → VPIN == 0."""
        buy = np.array([100.0, 100.0, 100.0])
        sell = np.array([100.0, 100.0, 100.0])
        total = np.array([200.0, 200.0, 200.0])
        assert compute_vpin(buy, sell, total) == pytest.approx(0.0, abs=1e-12)

    def test_vpin_one_sided_is_one(self):
        """All-buy buckets (V^S = 0) → VPIN = ΣV / ΣV = 1."""
        buy = np.array([100.0, 200.0])
        sell = np.array([0.0, 0.0])
        total = np.array([100.0, 200.0])
        assert compute_vpin(buy, sell, total) == pytest.approx(1.0)

    def test_vpin_classic_egan_paper(self):
        """The dollar-bars example from Easley/ODE: 80-buy, 20-sell → VPIN = 0.6."""
        buy = np.array([80.0])
        sell = np.array([20.0])
        total = np.array([100.0])
        # |80 − 20| / 100 = 60 / 100 = 0.6
        assert compute_vpin(buy, sell, total) == pytest.approx(0.6)

    def test_vpin_aggregates_across_buckets(self):
        """VPIN aggregates by Σ(.) not by per-bucket mean."""
        buy = np.array([100.0, 0.0])
        sell = np.array([0.0, 100.0])
        total = np.array([100.0, 100.0])
        # Σ|b−s| = 100+100 = 200; ΣV = 200 → VPIN = 1.0
        assert compute_vpin(buy, sell, total) == pytest.approx(1.0)

    def test_vpin_zero_total_returns_zero(self):
        """Degenerate window of zero volume → VPIN = 0 (not a divide-by-zero)."""
        buy = np.array([0.0, 0.0])
        sell = np.array([0.0, 0.0])
        total = np.array([0.0, 0.0])
        assert compute_vpin(buy, sell, total) == 0.0

    def test_vpin_accepts_lists(self):
        """Lists are coerced to ndarray so the API is forgiving."""
        assert compute_vpin([80.0], [20.0], [100.0]) == pytest.approx(0.6)

    def test_vpin_in_unit_interval(self):
        """For valid non-negative buckets, VPIN ∈ [0, 1]."""
        rng = np.random.default_rng(11)
        total = rng.uniform(50, 200, size=50)
        # random buy fractions in [0, 1] → sell = total*(1−f), buy = total*f
        frac = rng.uniform(0, 1, size=50)
        buy = total * frac
        sell = total * (1.0 - frac)
        v = compute_vpin(buy, sell, total)
        assert 0.0 <= v <= 1.0


class TestQuoteImbalance:
    """QI = (B − A) / (B + A) ∈ [-1, 1]."""

    def test_qi_balanced_is_zero(self):
        """Equal bid and ask size → QI = 0."""
        assert quote_imbalance(100.0, 100.0) == 0.0

    def test_qi_bid_heavy_positive(self):
        """All-bid, zero ask → QI = 1.0 (maximum bidder pressure)."""
        assert quote_imbalance(150.0, 50.0) == pytest.approx(0.5)
        assert quote_imbalance(1000.0, 0.0) == pytest.approx(1.0)

    def test_qi_ask_heavy_negative(self):
        """All-ask, zero bid → QI = −1.0 (maximum seller pressure)."""
        assert quote_imbalance(0.0, 1000.0) == pytest.approx(-1.0)
        assert quote_imbalance(50.0, 150.0) == pytest.approx(-0.5)

    def test_qi_zero_total_returns_zero(self):
        """Zero bid + ask → 0.0 (avoid divide-by-zero)."""
        assert quote_imbalance(0.0, 0.0) == 0.0
        assert quote_imbalance(-1.0, -2.0) == 0.0

    def test_qi_in_unit_interval(self):
        """For non-negative B, A: QI ∈ [-1, 1]."""
        rng = np.random.default_rng(13)
        for _ in range(20):
            b = rng.uniform(0, 500)
            a = rng.uniform(0, 500)
            assert -1.0 <= quote_imbalance(b, a) <= 1.0
