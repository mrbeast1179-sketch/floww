"""
backend/services/hmm_regime.py

Hidden Markov Model market regime detector.

Implements paper #6 from the Blademap bibliography, "Market Regime Detection
using Hidden Markov Models", in pure Python (no torch / numba / scipy — the
Round-9 freeze rule applies here too).

Three regimes, dynamically relabelled by per-state mean of feature[0]
(call / put volume dominance):

  * ``TRENDING_BULL`` — strongest positive signed call-vs-put dominance
  * ``RANGING``       — sits between the two extremes
  * ``TRENDING_BEAR`` — strongest negative signed call-vs-put dominance

Observations are 2-D tuples:

  feature[0] = log((call_vol + 1) / (put_vol + 1))  clipped to [-3, 3]
  feature[1] = total_vol / (total_oi + 1)          clipped to [0, 5]

Public surface (matches the snapshot-deque + compute() shape used elsewhere
in this backend — see ``multi_level_ofi.py`` for the OFI equivalent)::

    hmm = GaussianHMMRegime(n_states=3, n_features=2, history=64)
    hmm.push_observation((f0, f1))   # one per chain fetch
    hmm.fit_iter(em_iterations=15)   # Baum-Welch EM
    out = hmm.classify()             # current_state, posterior, smoothed_path

The classify output dict schema is stable for the route layer::

    {
        "current_state":  "TRENDING_BULL" | "RANGING" | "TRENDING_BEAR",
        "posterior":      [p0, p1, p2]   (sums to 1.0 within float epsilon),
        "smoothed_path":  ["RANGING", "TRENDING_BULL", ...]   (one per obs),
        "confidence":     max(posterior),
        "n_obs":          int,
        "is_warming":     bool,   # True until n_obs >= 5 and fit has run,
    }

Numerics:

  * Forward + backward pass are kept in log-space; ``_logsumexp`` accumulates
    stable denominators.
  * Gaussian emission variance is clamped to ``>= 1e-6`` to keep log() finite.
  * ``_initialize_params`` runs a quantile-based mean init on the buffered
    observations so that the initial state 0 anchors the lowest-f0 segment,
    state ``n_states-1`` anchors the highest. Combined with the post-fit
    mean-sort relabelling in ``classify``, this gives stable
    BULL/RANGING/BEAR labelling across both bull-data and bear-data regimes.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from typing import Any

LOG_INF = float("-inf")


def _logsumexp(values: Sequence[float]) -> float:
    """Numerically stable logsumexp. Empty input → ``LOG_INF``."""
    if not values:
        return LOG_INF
    finite = [v for v in values if v != LOG_INF]
    if not finite:
        return LOG_INF
    m = max(finite)
    s = 0.0
    for v in finite:
        s += math.exp(v - m)
    return m + math.log(s)


def _log_gaussian(x: float, mu: float, var: float) -> float:
    """Log density of ``x`` under N(mu, var). Variance clamped to 1e-6."""
    v = max(float(var), 1e-6)
    diff = float(x) - float(mu)
    return -0.5 * (math.log(2.0 * math.pi * v) + (diff * diff) / v)


class GaussianHMMRegime:
    """Pure-Python 3-state (default) Gaussian HMM for regime detection."""

    STATE_LABELS = ["TRENDING_BULL", "RANGING", "TRENDING_BEAR"]
    STATE_COLORS: dict[str, str] = {
        "TRENDING_BULL": "#22c55e",   # green
        "RANGING":       "#94a3b8",   # slate
        "TRENDING_BEAR": "#ef4444",   # red
    }

    def __init__(self, n_states: int = 3, n_features: int = 2, history: int = 64):
        if n_states < 2:
            raise ValueError("n_states must be >= 2")
        if n_features < 1:
            raise ValueError("n_features must be >= 1")
        self.n_states = n_states
        self.n_features = n_features
        self.history = max(5, int(history))
        self._obs: deque = deque(maxlen=self.history)
        # Uniform initial log-probabilities
        self.log_pi: list[float] = [math.log(1.0 / n_states)] * n_states
        self.log_A: list[list[float]] = [
            [math.log(1.0 / n_states) for _ in range(n_states)]
            for _ in range(n_states)
        ]
        # Per-state means + variances (init to default; ``_initialize_params``
        # refits from the buffer on first ``fit_iter`` call).
        self.means: list[list[float]] = [[0.0] * n_features for _ in range(n_states)]
        self.vars: list[list[float]] = [[1.0] * n_features for _ in range(n_states)]
        self._fitted: bool = False

    # ── Public API ──────────────────────────────────────────────────────

    def push_observation(self, features: Sequence[float]) -> None:
        """Append a new observation. Older entries drop once the buffer fills."""
        if len(features) != self.n_features:
            raise ValueError(
                f"features must have length {self.n_features}, got {len(features)}"
            )
        self._fitted = False  # next classify() must wait for fit_iter() again
        self._obs.append(tuple(float(features[i]) for i in range(self.n_features)))

    def fit_iter(self, em_iterations: int = 15) -> None:
        """Run Baum-Welch EM until ``em_iterations`` or log-likelihood stabilises."""
        n_obs = len(self._obs)
        if n_obs < 5:
            return  # insufficient data — leave defaults in place
        self._initialize_params()
        prev_ll = LOG_INF
        for _ in range(max(1, em_iterations)):
            log_alpha = self._forward()
            log_beta = self._backward()
            ll = _logsumexp(
                [log_alpha[n_obs - 1][i] for i in range(self.n_states)]
            )
            if ll != LOG_INF and prev_ll != LOG_INF and (ll - prev_ll) < 1e-5:
                break  # converged
            prev_ll = ll
            self._m_step(log_alpha, log_beta)
        self._fitted = True

    def classify(self) -> dict[str, Any]:
        """Return current regime + smoothed path + posterior vector."""
        n_obs = len(self._obs)
        if n_obs < 5 or not self._fitted:
            return {
                "current_state": "RANGING",
                "posterior": [1.0 / self.n_states] * self.n_states,
                "smoothed_path": [],
                "confidence": 0.0,
                "n_obs": n_obs,
                "is_warming": True,
            }
        log_alpha = self._forward()
        log_beta = self._backward()
        label_by_state = self._dynamic_label_map(log_alpha, log_beta)
        # Final-observation posterior
        log_norm = _logsumexp(
            [log_alpha[n_obs - 1][i] + log_beta[n_obs - 1][i]
             for i in range(self.n_states)]
        )
        posterior: list[float] = [
            float(
                math.exp(
                    log_alpha[n_obs - 1][i] + log_beta[n_obs - 1][i] - log_norm
                )
            )
            for i in range(self.n_states)
        ]
        current_idx = max(range(self.n_states), key=lambda i: posterior[i])
        # Smoothed path: argmax of gamma (per observation)
        smoothed_path: list[str] = []
        for t in range(n_obs):
            ln = _logsumexp(
                [log_alpha[t][i] + log_beta[t][i] for i in range(self.n_states)]
            )
            gs = [
                float(math.exp(log_alpha[t][i] + log_beta[t][i] - ln))
                for i in range(self.n_states)
            ]
            sm_idx = max(range(self.n_states), key=lambda i: gs[i])
            smoothed_path.append(label_by_state[sm_idx])
        return {
            "current_state": label_by_state[current_idx],
            "posterior": posterior,
            "smoothed_path": smoothed_path,
            "confidence": float(posterior[current_idx]),
            "n_obs": n_obs,
            "is_warming": False,
        }

    # ── Internals ───────────────────────────────────────────────────────

    def _initialize_params(self) -> None:
        """Quantile-based mean init so ``state 0`` anchors the lowest-f0 segment."""
        n_obs = len(self._obs)
        sorted_obs = sorted(self._obs, key=lambda o: o[0])  # ascending by f0
        group_size = max(1, n_obs // self.n_states)
        self.means = [[0.0] * self.n_features for _ in range(self.n_states)]
        self.vars = [[1.0] * self.n_features for _ in range(self.n_states)]
        for s in range(self.n_states):
            start = s * group_size
            end = start + group_size if s < self.n_states - 1 else n_obs
            g = sorted_obs[start:end]
            if not g:
                continue
            for k in range(self.n_features):
                vals = [o[k] for o in g]
                m = sum(vals) / len(vals)
                v = sum((x - m) ** 2 for x in vals) / max(len(vals), 1)
                self.means[s][k] = m
                self.vars[s][k] = max(v, 1e-6)

    def _log_emit(self, obs: tuple[float, ...], state_i: int) -> float:
        s = 0.0
        for k in range(self.n_features):
            s += _log_gaussian(obs[k], self.means[state_i][k], self.vars[state_i][k])
        return s

    def _forward(self) -> list[list[float]]:
        n = self.n_states
        n_obs = len(self._obs)
        log_alpha: list[list[float]] = [[LOG_INF] * n for _ in range(n_obs)]
        for i in range(n):
            log_alpha[0][i] = self.log_pi[i] + self._log_emit(self._obs[0], i)
        for t in range(1, n_obs):
            for j in range(n):
                emit = self._log_emit(self._obs[t], j)
                log_alpha[t][j] = emit + _logsumexp(
                    [log_alpha[t - 1][i] + self.log_A[i][j] for i in range(n)]
                )
        return log_alpha

    def _backward(self) -> list[list[float]]:
        n = self.n_states
        n_obs = len(self._obs)
        log_beta: list[list[float]] = [[LOG_INF] * n for _ in range(n_obs)]
        for i in range(n):
            log_beta[n_obs - 1][i] = 0.0
        for t in range(n_obs - 2, -1, -1):
            for i in range(n):
                log_beta[t][i] = _logsumexp(
                    [
                        self.log_A[i][j]
                        + self._log_emit(self._obs[t + 1], j)
                        + log_beta[t + 1][j]
                        for j in range(n)
                    ]
                )
        return log_beta

    def _m_step(
        self, log_alpha: list[list[float]], log_beta: list[list[float]]
    ) -> None:
        """EM M-step: refresh log_pi, log_A, means, vars from gamma + xi."""
        n = self.n_states
        n_obs = len(self._obs)
        # gamma[t][i] in linear space
        gamma: list[list[float]] = [[0.0] * n for _ in range(n_obs)]
        for t in range(n_obs):
            log_norm = _logsumexp(
                [log_alpha[t][i] + log_beta[t][i] for i in range(n)]
            )
            for i in range(n):
                v = log_alpha[t][i] + log_beta[t][i] - log_norm
                gamma[t][i] = math.exp(v) if v != LOG_INF else 0.0
        # log_pi from gamma[0]
        for i in range(n):
            self.log_pi[i] = math.log(max(gamma[0][i], 1e-300))
        # log_A from xi — row-normalised per i
        A_counts = [[0.0] * n for _ in range(n)]
        row_counts = [0.0] * n
        for t in range(n_obs - 1):
            flat: list[float] = []
            for i in range(n):
                for j in range(n):
                    flat.append(
                        log_alpha[t][i]
                        + self.log_A[i][j]
                        + self._log_emit(self._obs[t + 1], j)
                        + log_beta[t + 1][j]
                    )
            log_norm = _logsumexp(flat)
            for k_idx, v in enumerate(flat):
                i, j = divmod(k_idx, n)
                p = math.exp(v - log_norm) if v != LOG_INF else 0.0
                A_counts[i][j] += p
                row_counts[i] += p
        for i in range(n):
            denom = max(row_counts[i], 1e-300)
            for j in range(n):
                self.log_A[i][j] = math.log(
                    max(A_counts[i][j] / denom, 1e-300)
                )
        # means + vars: gamma-weighted per state
        for i in range(n):
            denom_i = max(sum(gamma[t][i] for t in range(n_obs)), 1e-300)
            for k in range(self.n_features):
                m_new = sum(
                    gamma[t][i] * self._obs[t][k] for t in range(n_obs)
                ) / denom_i
                v_new = (
                    sum(
                        gamma[t][i] * (self._obs[t][k] - m_new) ** 2
                        for t in range(n_obs)
                    )
                    / denom_i
                )
                self.means[i][k] = m_new
                self.vars[i][k] = max(v_new, 1e-6)

    def _dynamic_label_map(
        self,
        log_alpha: list[list[float]],
        log_beta: list[list[float]],
    ) -> dict[int, str]:
        """Sort states by per-state mean of feature[0]; map top→BULL, mid→RANGING,
        bottom→BEAR (3-state case). Returns ``state_idx → label``.
        """
        n_obs = len(self._obs)
        state_mean_f0: list[float] = []
        for s in range(self.n_states):
            gamma_s_total = 0.0
            weighted = 0.0
            for t in range(n_obs):
                log_norm = _logsumexp(
                    [log_alpha[t][i] + log_beta[t][i]
                     for i in range(self.n_states)]
                )
                g = math.exp(log_alpha[t][s] + log_beta[t][s] - log_norm)
                gamma_s_total += g
                weighted += g * self._obs[t][0]
            state_mean_f0.append(
                weighted / max(gamma_s_total, 1e-9)
            )
        sorted_states = sorted(
            range(self.n_states),
            key=lambda i: state_mean_f0[i],
            reverse=True,
        )
        label_by_state: dict[int, str] = {}
        if self.n_states == 3:
            label_by_state[sorted_states[0]] = "TRENDING_BULL"
            label_by_state[sorted_states[1]] = "RANGING"
            label_by_state[sorted_states[2]] = "TRENDING_BEAR"
        elif self.n_states == 2:
            label_by_state[sorted_states[0]] = "TRENDING_BULL"
            label_by_state[sorted_states[1]] = "TRENDING_BEAR"
        else:
            for i in range(self.n_states):
                label_by_state[i] = f"STATE_{i}"
        return label_by_state


__all__ = ["GaussianHMMRegime"]
