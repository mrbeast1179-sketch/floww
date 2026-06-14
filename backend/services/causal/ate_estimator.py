"""
backend/services/causal/ate_estimator.py

Average Treatment Effect (ATE) estimation.

Implements:
  - Propensity score estimation (logistic regression)
  - Inverse Probability of Treatment Weighting (IPTW)
  - Doubly-robust ATE estimation
  - Bootstrap confidence intervals

Reference: Imbens, Rubin (2015) Causal Inference for Statistics.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class PropensityScoreEstimator:
    """Estimate propensity scores using logistic regression."""

    def __init__(self):
        self._weights: np.ndarray | None = None
        self._bias: float = 0.0

    def fit(self, X: np.ndarray, treatment: np.ndarray, max_iter: int = 1000):
        """Fit propensity score model.

        Args:
            X: Covariates (n_samples, n_features)
            treatment: Binary treatment indicator (n_samples,)
            max_iter: Maximum gradient descent iterations
        """
        n, p = X.shape
        # Add intercept
        X_aug = np.column_stack([np.ones(n), X])
        # Initialize weights
        w = np.zeros(p + 1)
        lr = 0.01

        for _ in range(max_iter):
            # Logistic regression gradient
            z = X_aug @ w
            prob = 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))
            gradient = X_aug.T @ (prob - treatment) / n
            w -= lr * gradient

        self._weights = w[1:]
        self._bias = w[0]

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict propensity scores."""
        if self._weights is None:
            raise RuntimeError("Model not fitted")
        z = X @ self._weights + self._bias
        return 1.0 / (1.0 + np.exp(-np.clip(z, -500, 500)))


class ATEEstimator:
    """Estimate Average Treatment Effect using IPTW and doubly-robust methods."""

    @staticmethod
    def iptw_ate(
        outcome: np.ndarray,
        treatment: np.ndarray,
        propensity: np.ndarray,
    ) -> float:
        """Compute ATE using Inverse Probability of Treatment Weighting.

        Args:
            outcome: Observed outcomes (n_samples,)
            treatment: Binary treatment indicator (n_samples,)
            propensity: Estimated propensity scores (n_samples,)

        Returns:
            ATE estimate
        """
        # Clip propensity scores to avoid division by zero
        p = np.clip(propensity, 0.01, 0.99)

        # IPTW estimator
        treated_mask = treatment == 1
        control_mask = treatment == 0

        if not np.any(treated_mask) or not np.any(control_mask):
            # No variation in treatment — cannot compute IPTW
            return 0.0

        treated_outcome = np.sum(treatment * outcome / p) / np.sum(treatment / p)
        control_outcome = np.sum((1 - treatment) * outcome / (1 - p)) / np.sum((1 - treatment) / (1 - p))

        return float(treated_outcome - control_outcome)

    @staticmethod
    def doubly_robust_ate(
        outcome: np.ndarray,
        treatment: np.ndarray,
        propensity: np.ndarray,
        covariates: np.ndarray,
    ) -> float:
        """Compute ATE using doubly-robust estimation.

        Fits outcome models for treated and control groups, then combines
        with propensity scores for robustness.
        """
        n = len(outcome)
        p = np.clip(propensity, 0.01, 0.99)

        # Simple linear outcome models
        X_aug = np.column_stack([np.ones(n), covariates])

        # Fit outcome model for treated
        treated_mask = treatment == 1
        if np.sum(treated_mask) > 1:
            X_t = X_aug[treated_mask]
            y_t = outcome[treated_mask]
            w_t = np.linalg.lstsq(X_t, y_t, rcond=None)[0]
            mu1 = X_aug @ w_t
        else:
            mu1 = np.full(n, np.mean(outcome))

        # Fit outcome model for control
        control_mask = treatment == 0
        if np.sum(control_mask) > 1:
            X_c = X_aug[control_mask]
            y_c = outcome[control_mask]
            w_c = np.linalg.lstsq(X_c, y_c, rcond=None)[0]
            mu0 = X_aug @ w_c
        else:
            mu0 = np.full(n, np.mean(outcome))

        # Doubly robust estimator
        ate = np.mean(
            treatment * (outcome - mu1) / p
            - (1 - treatment) * (outcome - mu0) / (1 - p)
            + (mu1 - mu0)
        )
        return float(ate)

    @staticmethod
    def bootstrap_ci(
        outcome: np.ndarray,
        treatment: np.ndarray,
        propensity: np.ndarray,
        n_bootstrap: int = 1000,
        ci: float = 0.95,
    ) -> tuple[float, float, float]:
        """Compute bootstrap confidence interval for ATE.

        Returns:
            (ate_estimate, lower_bound, upper_bound)
        """
        n = len(outcome)
        ate_estimates = []

        for _ in range(n_bootstrap):
            idx = np.random.choice(n, size=n, replace=True)
            try:
                ate = ATEEstimator.iptw_ate(
                    outcome[idx], treatment[idx], propensity[idx]
                )
                ate_estimates.append(ate)
            except Exception:
                continue

        if not ate_estimates:
            return 0.0, 0.0, 0.0

        ate_estimates = np.array(ate_estimates)
        alpha = 1.0 - ci
        lower = float(np.percentile(ate_estimates, alpha / 2 * 100))
        upper = float(np.percentile(ate_estimates, (1 - alpha / 2) * 100))
        point = float(np.mean(ate_estimates))

        return point, lower, upper
