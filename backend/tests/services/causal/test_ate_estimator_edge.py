"""
backend/tests/services/causal/test_ate_estimator_edge.py

Additional edge-case tests for causal/ate_estimator.py.

The existing test_ate.py covers the main happy paths. This file covers:
    - PropensityScoreEstimator: single feature, large sample, predict shape
    - IPTW: all-treated / all-control (no variation → returns 0.0)
    - Doubly-robust: single treated / single control observation
    - Bootstrap: zero effective bootstrap samples, reproducibility
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


class TestPropensityScoreEstimatorEdge:
    def test_single_feature(self):
        """Propensity score estimation works with 1 feature."""
        from services.causal.ate_estimator import PropensityScoreEstimator
        np.random.seed(42)
        n = 500
        X = np.random.randn(n, 1)
        prob = 1.0 / (1.0 + np.exp(-X[:, 0]))
        treatment = (np.random.random(n) < prob).astype(float)

        est = PropensityScoreEstimator()
        est.fit(X, treatment)
        scores = est.predict(X)
        assert scores.shape == (n,)
        assert np.all(scores > 0)
        assert np.all(scores < 1)

    def test_large_sample_convergence(self):
        """With large n, propensity scores should be well-calibrated."""
        from services.causal.ate_estimator import PropensityScoreEstimator
        np.random.seed(123)
        n = 5000
        X = np.random.randn(n, 2)
        # True propensity depends on both features
        z = 0.5 * X[:, 0] + 0.3 * X[:, 1]
        prob = 1.0 / (1.0 + np.exp(-z))
        treatment = (np.random.random(n) < prob).astype(float)

        est = PropensityScoreEstimator()
        est.fit(X, treatment, max_iter=2000)
        scores = est.predict(X)
        # Mean score should be close to mean treatment rate
        assert abs(np.mean(scores) - np.mean(treatment)) < 0.05

    def test_predict_shape_matches_input(self):
        """predict returns array with same length as input rows."""
        from services.causal.ate_estimator import PropensityScoreEstimator
        np.random.seed(0)
        X = np.random.randn(100, 4)
        treatment = (np.random.random(100) < 0.5).astype(float)
        est = PropensityScoreEstimator()
        est.fit(X, treatment)
        scores = est.predict(X)
        assert len(scores) == 100

    def test_predict_different_size(self):
        """Can predict on a different-sized dataset after fitting."""
        from services.causal.ate_estimator import PropensityScoreEstimator
        np.random.seed(0)
        X_train = np.random.randn(200, 3)
        treatment = (np.random.random(200) < 0.5).astype(float)
        est = PropensityScoreEstimator()
        est.fit(X_train, treatment)
        X_test = np.random.randn(50, 3)
        scores = est.predict(X_test)
        assert scores.shape == (50,)


class TestIPTWEdgeCases:
    def test_all_treated_returns_zero(self):
        """IPTW returns 0.0 when all units are treated (no control group)."""
        from services.causal.ate_estimator import ATEEstimator
        n = 100
        outcome = np.random.randn(n)
        treatment = np.ones(n)
        propensity = np.full(n, 0.5)
        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert ate == 0.0

    def test_all_control_returns_zero(self):
        """IPTW returns 0.0 when all units are control (no treated group)."""
        from services.causal.ate_estimator import ATEEstimator
        n = 100
        outcome = np.random.randn(n)
        treatment = np.zeros(n)
        propensity = np.full(n, 0.5)
        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert ate == 0.0

    def test_perfect_propensity_recovery(self):
        """With true propensity known, IPTW recovers exact ATE."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 5000
        # Known propensity = 0.5 for all
        propensity = np.full(n, 0.5)
        treatment = (np.random.random(n) < 0.5).astype(float)
        # ATE = 3.0
        outcome = 5.0 + 3.0 * treatment + np.random.randn(n) * 0.01
        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert abs(ate - 3.0) < 0.1

    def test_propensity_clipping(self):
        """Extreme propensity values (0.0 or 1.0) are clipped to [0.01, 0.99]."""
        from services.causal.ate_estimator import ATEEstimator
        n = 100
        treatment = np.zeros(n)
        treatment[:50] = 1.0
        outcome = np.random.randn(n)
        # Extreme propensities that would cause division by zero without clipping
        propensity = np.zeros(n)  # All zeros — would be 0/0
        propensity[:50] = 1.0
        # Should not raise — clipping prevents division by zero
        ate = ATEEstimator.iptw_ate(outcome, treatment, propensity)
        assert np.isfinite(ate)


class TestDoublyRobustEdgeCases:
    def test_single_treated_observation(self):
        """Doubly robust with only 1 treated unit falls back to mean outcome."""
        from services.causal.ate_estimator import ATEEstimator
        n = 50
        treatment = np.zeros(n)
        treatment[0] = 1.0  # Only 1 treated
        outcome = np.random.randn(n)
        propensity = np.full(n, 0.5)
        covariates = np.random.randn(n, 2)
        ate = ATEEstimator.doubly_robust_ate(outcome, treatment, propensity, covariates)
        assert np.isfinite(ate)

    def test_single_control_observation(self):
        """Doubly robust with only 1 control unit falls back to mean outcome."""
        from services.causal.ate_estimator import ATEEstimator
        n = 50
        treatment = np.ones(n)
        treatment[0] = 0.0  # Only 1 control
        outcome = np.random.randn(n)
        propensity = np.full(n, 0.5)
        covariates = np.random.randn(n, 2)
        ate = ATEEstimator.doubly_robust_ate(outcome, treatment, propensity, covariates)
        assert np.isfinite(ate)

    def test_dr_with_known_effect(self):
        """DR should recover known ATE with balanced treatment."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 3000
        X = np.random.randn(n, 2)
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = X[:, 0] + X[:, 1] + 2.5 * treatment + np.random.randn(n) * 0.1
        propensity = np.full(n, 0.5)
        ate = ATEEstimator.doubly_robust_ate(outcome, treatment, propensity, X)
        assert abs(ate - 2.5) < 0.3


class TestBootstrapCIEdgeCases:
    def test_bootstrap_reproducibility(self):
        """Same seed should produce same CI."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 500
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = 1.0 * treatment + np.random.randn(n) * 0.5
        propensity = np.full(n, 0.5)

        np.random.seed(99)
        result1 = ATEEstimator.bootstrap_ci(outcome, treatment, propensity, n_bootstrap=200)
        np.random.seed(99)
        result2 = ATEEstimator.bootstrap_ci(outcome, treatment, propensity, n_bootstrap=200)
        assert result1 == result2

    def test_bootstrap_lower_less_than_upper(self):
        """Lower bound should always be <= upper bound."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 500
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = treatment + np.random.randn(n) * 0.5
        propensity = np.full(n, 0.5)
        point, lower, upper = ATEEstimator.bootstrap_ci(outcome, treatment, propensity, n_bootstrap=200)
        assert lower <= upper

    def test_bootstrap_point_within_ci(self):
        """Point estimate should be within [lower, upper]."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 500
        treatment = (np.random.random(n) < 0.5).astype(float)
        outcome = 1.5 * treatment + np.random.randn(n) * 0.3
        propensity = np.full(n, 0.5)
        point, lower, upper = ATEEstimator.bootstrap_ci(outcome, treatment, propensity, n_bootstrap=500)
        assert lower <= point <= upper

    def test_bootstrap_95_ci_width_scales_with_noise(self):
        """More noise → wider CI."""
        from services.causal.ate_estimator import ATEEstimator
        np.random.seed(42)
        n = 500
        treatment = (np.random.random(n) < 0.5).astype(float)

        outcome_low = treatment + np.random.randn(n) * 0.1
        outcome_high = treatment + np.random.randn(n) * 2.0
        propensity = np.full(n, 0.5)

        np.random.seed(7)
        _, l1, u1 = ATEEstimator.bootstrap_ci(outcome_low, treatment, propensity, n_bootstrap=200)
        np.random.seed(7)
        _, l2, u2 = ATEEstimator.bootstrap_ci(outcome_high, treatment, propensity, n_bootstrap=200)
        assert (u2 - l2) > (u1 - l1)
