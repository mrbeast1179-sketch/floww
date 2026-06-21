"""
Tests for backend/domain/almgren_chriss.py — κ, optimal trajectory,
expected cost decomposition, Kyle's Lambda + impact.

Hand-pinned reference values + property invariants:
  * κ = sqrt(λ · σ² / η)                              (exact fp match)
  * κ pin at λ=1e-6, σ=0.15, η=0.1 → ≈ 4.7434e-04
  * trajectory sums to total_shares
  * trajectory monotone-decreasing for κ > 0
  * trajectory front-loaded for high κ (after renormalize)
  * expected_cost_components non-negative and = perm + timing + spread
  * longer T ⇒ larger κT ⇒ larger (coth − 1/(κT)) ⇒ larger E[cost]
  * kyle_lambda_ols recovers the seed-42 generating λ within 50%
  * kyle_impact linear in Q
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_BACKEND))

from domain.almgren_chriss import (
    compute_kappa,
    expected_cost_components,
    kyle_impact,
    kyle_lambda_ols,
    optimal_trajectory,
)


class TestComputeKappa:
    """κ = sqrt(λσ²/η) — exact fp match against the closed-form expression."""

    def test_kappa_exact_pin(self):
        """κ pin at λ=1e-6, σ=0.15, η=0.1.

        Closed form:  sqrt(1e-6 · 0.0225 / 0.1) = sqrt(2.25e-7)
                   = 1.5 × 10^-3.5 ≈ 4.7434e-04.
        """
        # First assertion: matches math.sqrt(...) exactly.
        expected = math.sqrt(1e-6 * 0.15 ** 2 / 0.1)
        got = compute_kappa(risk_aversion=1e-6, sigma=0.15, eta=0.1)
        assert got == pytest.approx(expected, rel=1e-12)
        # Second assertion: hand-pinned reference value. NOTE: exponent is e-04.
        assert got == pytest.approx(4.743416490252974e-04, rel=1e-12)

    def test_kappa_zero_when_eta_zero(self):
        """η = 0 ⇒ divide-by-zero guard returns 0."""
        assert compute_kappa(1e-6, 0.15, 0.0) == 0.0

    def test_kappa_zero_when_sigma_zero(self):
        """σ = 0 ⇒ multiplication guard returns 0 (matches services)."""
        assert compute_kappa(1e-6, 0.0, 0.1) == 0.0

    def test_kappa_zero_when_lambda_zero(self):
        """λ = 0 ⇒ urgency is zero."""
        assert compute_kappa(0.0, 0.15, 0.1) == 0.0

    def test_kappa_zero_when_negative_input(self):
        """Any negative input ⇒ 0."""
        assert compute_kappa(-1e-6, 0.15, 0.1) == 0.0
        assert compute_kappa(1e-6, -0.15, 0.1) == 0.0
        assert compute_kappa(1e-6, 0.15, -0.1) == 0.0

    def test_kappa_non_negative(self):
        """κ ≥ 0 for valid positive inputs."""
        for lam in [1e-8, 1e-6, 1e-4, 1e-2]:
            assert compute_kappa(lam, 0.15, 0.1) >= 0.0

    def test_kappa_monotone_in_lambda(self):
        """Larger λ ⇒ larger κ (with σ, η fixed)."""
        kappas = [compute_kappa(lam, 0.2, 0.1) for lam in [1e-8, 1e-6, 1e-4, 1e-2]]
        for i in range(len(kappas) - 1):
            assert kappas[i] < kappas[i + 1]

    def test_kappa_sq_homogeneity(self):
        """κ(λ, c·σ, η) = c · κ(λ, σ, η)  ⇒ κ² × η = λ · σ²."""
        k1 = compute_kappa(1e-6, 0.15, 0.1)
        k2 = compute_kappa(1e-6, 0.30, 0.1)  # σ doubled → κ doubled
        assert k2 == pytest.approx(2.0 * k1, rel=1e-12)


class TestOptimalTrajectory:
    """x(t) = X · sinh(κ(T − t)) / sinh(κT)."""

    def test_zero_urgency_is_even_split(self):
        """κ ≈ 0 (1e-12) and T > 0 ⇒ uniform split."""
        traj = optimal_trajectory(1000.0, 300.0, 10, kappa=1e-30)
        assert len(traj) == 10
        for v in traj:
            assert v == pytest.approx(100.0)

    def test_zero_horizon_is_even_split(self):
        """T = 0 ⇒ uniform split (matches service fallback)."""
        traj = optimal_trajectory(2000.0, 0.0, 5, kappa=0.001)
        assert all(v == pytest.approx(400.0) for v in traj)

    def test_trajectory_sums_to_total(self):
        """Σ trajectory == total_shares (renormalized post-clamp)."""
        for kappa in [1e-8, 1e-5, 1e-3, 1e-1]:
            traj = optimal_trajectory(1000.0, 300.0, 10, kappa=kappa)
            assert sum(traj) == pytest.approx(1000.0, rel=1e-9)

    def test_high_urgency_is_front_loaded(self):
        """Strong κ ⇒ trade much more in slice 0 than slice 9 (renorm-preserved).

        With κ=0.01, T=300 (κT=3), the un-normalized closed form gives
        x(0)=1000, x(9)≈30, Σ≈3500. The renormalize step divides by Σ/x_tot
        so the *shares* of each slice stay monotone-down. The first slice
        remains well above average per slice (= 100), the last well below.
        """
        traj = optimal_trajectory(1000.0, 300.0, 10, kappa=0.01)
        assert traj[0] > traj[-1]
        avg = sum(traj) / len(traj)  # = 100
        # Front slice holds strictly more than 2× the average.
        assert traj[0] > 2.0 * avg
        # Last slice holds strictly less than half the average.
        assert traj[-1] < avg / 2.0

    def test_trajectory_monotone_decreasing(self):
        """For κ > 0, the trajectory must be monotonically decreasing."""
        kappa = compute_kappa(1e-6, 0.15, 0.1)
        traj = optimal_trajectory(1000.0, 300.0, 10, kappa=kappa)
        for i in range(len(traj) - 1):
            assert traj[i] >= traj[i + 1] - 1e-9, (
                f"Trajectory non-monotone at i={i}: {traj[i]} → {traj[i+1]}"
            )

    def test_trajectory_overflow_front_trade_all(self):
        """κ · T > 50 ⇒ sinh overflow guard returns [X, 0, 0, ...]."""
        # κ=1.0, T=60 ⇒ κT=60 > 50
        traj = optimal_trajectory(1000.0, 60.0, 10, kappa=1.0)
        assert traj[0] == pytest.approx(1000.0)
        for v in traj[1:]:
            assert v == 0.0

    def test_trajectory_n_slices_one(self):
        """n=1 ⇒ trajectory is a single-element list equal to total shares."""
        traj = optimal_trajectory(500.0, 300.0, 1, kappa=0.001)
        assert traj == pytest.approx([500.0])

    def test_trajectory_zero_n_returns_empty(self):
        """Defensive: n≤0 returns an empty list (no division by zero)."""
        assert optimal_trajectory(500.0, 300.0, 0, kappa=0.001) == []

    def test_trajectory_all_non_negative(self):
        """Sliced trajectories never produce negative share counts."""
        for kappa in [0.0, 1e-6, 1e-3, 0.01, 0.1, 1.0]:
            traj = optimal_trajectory(1000.0, 300.0, 20, kappa=kappa)
            for v in traj:
                assert v >= 0.0


class TestExpectedCostComponents:
    """(E[cost], perm_impact, timing_risk) = perm + timing + spread."""

    def test_perm_matches_closed_form(self):
        """perm_impact = γ · X² / 2 (exact, independent of κ)."""
        # X=1000, γ=0.05  →  0.05 · 1e6 / 2  =  25000
        ec, perm, timing = expected_cost_components(
            total_shares=1000.0, time_horizon=300.0, sigma=0.001,
            spread=0.1, kappa=0.001, gamma=0.05, risk_aversion=1e-6,
        )
        assert perm == pytest.approx(25000.0)

    def test_spread_cost_matches_difference(self):
        """E[cost] − perm − spread = timing_risk (within fp)."""
        ec, perm, timing = expected_cost_components(
            1000.0, 300.0, 0.001, 0.1, 0.001, 0.05, 1e-6,
        )
        assert ec - perm - 0.1 * 1000.0 / 2.0 == pytest.approx(
            timing, abs=1e-9
        )

    def test_components_non_negative(self):
        """For valid inputs, all three components are ≥ 0."""
        ec, perm, timing = expected_cost_components(
            500.0, 60.0, 0.002, 0.05, 0.0005, 0.04, 1e-6,
        )
        assert ec >= 0.0
        assert perm >= 0.0
        assert timing >= 0.0

    def test_kappa_zero_kills_timing_risk(self):
        """κ = 0 ⇒ linear trading has no timing-risk component."""
        ec, perm, timing = expected_cost_components(
            1000.0, 300.0, 0.001, 0.1, kappa=0.0, gamma=0.05, risk_aversion=1e-6,
        )
        assert timing == 0.0
        assert ec == pytest.approx(perm + 0.1 * 1000.0 / 2.0)

    def test_kappa_T_overflow_kills_timing(self):
        """κT > 50 ⇒ timing_risk branch not entered ⇒ 0."""
        ec, perm, timing = expected_cost_components(
            1000.0, 60.0, 0.001, 0.1, kappa=1.0, gamma=0.05, risk_aversion=1e-6,
        )
        assert timing == 0.0

    def test_longer_horizon_yields_larger_timing_risk(self):
        """With fixed κ, longer T ⇒ larger κT ⇒ larger (coth(κT) − 1/(κT))
        ⇒ larger timing-risk ⇒ larger total E[cost].
        """
        ec_short, _, _ = expected_cost_components(
            1000.0, 60.0, 0.002, 0.1, kappa=0.05, gamma=0.05, risk_aversion=1e-5,
        )
        ec_long, _, _ = expected_cost_components(
            1000.0, 600.0, 0.002, 0.1, kappa=0.05, gamma=0.05, risk_aversion=1e-5,
        )
        # perm (25000) and spread (50) are equal in both; timing differs.
        # T=60  → κT=3  → timing factor (coth − 1/(κT)) ≈ 1.0349 − 0.3333 = 0.7016
        # T=600 → κT=30 → timing factor (coth − 1/(κT)) ≈ 1.0000 − 0.0333 = 0.9667
        assert ec_long > ec_short


class TestKyleLambdaOls:
    """λ̂ = Cov(Δp, SV) / Var(SV), clipped to ≥ 0."""

    def test_lambda_zero_for_too_few_samples(self):
        """len < 5 ⇒ 0.0 (matches services)."""
        pc = [0.01, 0.02, 0.03, 0.04]
        sv = [100, 200, 300, 400]
        assert kyle_lambda_ols(pc, sv) == 0.0

    def test_lambda_recovers_seed42_value(self):
        """OLS recovers the generating λ̂ = 0.001 from synthetic data."""
        kyle = 0.001
        rng = np.random.default_rng(42)
        signed_vol = rng.normal(0.0, 1000.0, size=500)
        # True price impact plus independent noise.
        price_change = kyle * signed_vol + rng.normal(0.0, 0.01, size=500)
        # Discount early samples to avoid the estimator's small-sample bias.
        estimated = kyle_lambda_ols(price_change[100:], signed_vol[100:])
        # Tolerance matches services/test_execution_engine.py:142.
        assert abs(estimated - kyle) / kyle < 0.5

    def test_lambda_zero_variance_returns_zero(self):
        """Constant signed volumes ⇒ Var(SV) = 0 ⇒ 0.0."""
        pc = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
        sv = np.full(5, 1000.0)  # flat
        assert kyle_lambda_ols(pc, sv) == 0.0

    def test_lambda_clipped_non_negative(self):
        """If genuine Cov < 0, λ̂ is clipped to 0.0 (Kyle is non-negative by defn)."""
        # Construct SV with positive variance but price_change ~ −SV ⇒ neg cov.
        sv = np.array([-1.0, -2.0, -3.0, -4.0, -5.0])
        pc = np.array([+1.0, +2.0, +3.0, +4.0, +5.0])
        # Cov(Δp, SV) < 0 ⇒ λ̂ clipped to 0
        assert kyle_lambda_ols(pc, sv) == 0.0

    def test_lambda_shape_mismatch_raises(self):
        """Off-shape arrays raise."""
        with pytest.raises(ValueError, match="same shape"):
            kyle_lambda_ols([0.01, 0.02], [100])


class TestKyleImpact:
    """Δp = λ · Q (linear price impact)."""

    def test_impact_pin(self):
        """λ=0.001, Q=100 ⇒ Δp = 0.1 (the canonical service pin)."""
        assert kyle_impact(0.001, 100.0) == pytest.approx(0.1, abs=1e-12)

    def test_impact_linear_in_q(self):
        """Doubling Q doubles impact."""
        i100 = kyle_impact(0.001, 100.0)
        i200 = kyle_impact(0.001, 200.0)
        assert i200 == pytest.approx(2.0 * i100, rel=1e-12)

    def test_impact_zero_when_lambda_zero(self):
        """λ = 0 ⇒ 0.0 (no impact when no informed flow)."""
        assert kyle_impact(0.0, 1000.0) == 0.0

    def test_impact_zero_when_negative_q(self):
        """Q < 0 ⇒ 0.0 (clipped — caller should pass magnitude)."""
        assert kyle_impact(0.001, -100.0) == 0.0

    def test_impact_zero_when_negative_lambda(self):
        """λ < 0 ⇒ 0.0 (clipped — OLS λ̂ is non-negative by construction)."""
        assert kyle_impact(-0.5, 100.0) == 0.0
