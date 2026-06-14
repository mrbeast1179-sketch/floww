"""Tests for services/hawkes_process.py — Hawkes Process models."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.hawkes_process import HawkesProcess


# ── Constructor ──────────────────────────────────────────────────────────


class TestHawkesProcessInit:
    def test_default_params(self):
        hp = HawkesProcess()
        assert hp.mu == 1.0
        assert hp.alpha == 0.5
        assert hp.beta == 1.0
        assert hp.kernel == "exponential"

    def test_custom_params(self):
        hp = HawkesProcess(mu=2.0, alpha=0.3, beta=1.5, kernel="power_law")
        assert hp.mu == 2.0
        assert hp.alpha == 0.3
        assert hp.beta == 1.5
        assert hp.kernel == "power_law"

    def test_invalid_mu_raises(self):
        with pytest.raises(ValueError, match="mu must be > 0"):
            HawkesProcess(mu=0.0)

    def test_negative_alpha_raises(self):
        with pytest.raises(ValueError, match="alpha must be >= 0"):
            HawkesProcess(alpha=-1.0)

    def test_invalid_beta_raises(self):
        with pytest.raises(ValueError, match="beta must be > 0"):
            HawkesProcess(beta=0.0)

    def test_invalid_kernel_raises(self):
        with pytest.raises(ValueError, match="kernel must be"):
            HawkesProcess(kernel="gaussian")


# ── Intensity ────────────────────────────────────────────────────────────


class TestIntensity:
    def test_no_events_returns_mu(self):
        hp = HawkesProcess(mu=1.5)
        assert hp.intensity(10.0, np.array([])) == 1.5

    def test_none_events_returns_mu(self):
        hp = HawkesProcess(mu=2.0)
        assert hp.intensity(10.0, None) == 2.0

    def test_intensity_increases_after_event(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        events = np.array([1.0])
        lam_before = hp.intensity(0.5, events)
        lam_after = hp.intensity(1.01, events)
        assert lam_after > lam_before
        assert lam_after > hp.mu

    def test_intensity_decays_over_time(self):
        hp = HawkesProcess(mu=1.0, alpha=1.0, beta=2.0)
        events = np.array([1.0])
        lam_near = hp.intensity(1.1, events)
        lam_far = hp.intensity(5.0, events)
        assert lam_near > lam_far

    def test_power_law_kernel(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0, kernel="power_law")
        events = np.array([1.0, 2.0])
        lam = hp.intensity(3.0, events)
        assert lam > hp.mu
        assert np.isfinite(lam)

    def test_vectorized_intensity(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        events = np.array([1.0, 2.0, 3.0])
        t_array = np.array([0.5, 1.5, 2.5, 4.0])
        result = hp._intensity_vectorized(t_array, events)
        assert len(result) == 4
        assert result[0] == hp.mu  # before any event
        assert result[1] > hp.mu  # after first event


# ── Fit ──────────────────────────────────────────────────────────────────


class TestFit:
    def test_fit_returns_expected_keys(self):
        rng = np.random.default_rng(42)
        events = np.sort(rng.exponential(0.5, size=200))
        hp = HawkesProcess()
        result = hp.fit(events)
        for key in ("mu", "alpha", "beta", "log_likelihood", "branching_ratio", "n_events", "T"):
            assert key in result

    def test_fit_fewer_than_2_events(self):
        hp = HawkesProcess()
        result = hp.fit(np.array([1.0]))
        assert result["n_events"] == 1
        assert result["T"] == 0.0

    def test_fit_sets_fitted_flag(self):
        rng = np.random.default_rng(42)
        events = np.sort(rng.exponential(0.5, size=200))
        hp = HawkesProcess()
        assert not hp._fitted
        hp.fit(events)
        assert hp._fitted

    def test_fit_subcritical_branching_ratio(self):
        """Fit data generated from a known subcritical process."""
        rng = np.random.default_rng(42)
        hp_true = HawkesProcess(mu=2.0, alpha=0.3, beta=1.0)
        events = hp_true.simulate(T=500.0, n_events=5000)
        if len(events) < 10:
            pytest.skip("Simulated too few events")
        hp_fit = HawkesProcess()
        result = hp_fit.fit(events)
        assert result["branching_ratio"] < 1.0


# ── Simulate ─────────────────────────────────────────────────────────────


class TestSimulate:
    def test_simulate_returns_array(self):
        hp = HawkesProcess(mu=1.0, alpha=0.3, beta=1.0)
        events = hp.simulate(T=50.0)
        assert isinstance(events, np.ndarray)

    def test_simulate_events_within_horizon(self):
        hp = HawkesProcess(mu=1.0, alpha=0.3, beta=1.0)
        events = hp.simulate(T=100.0)
        if len(events) > 0:
            assert events[-1] <= 100.0

    def test_simulate_sorted(self):
        hp = HawkesProcess(mu=2.0, alpha=0.3, beta=1.0)
        events = hp.simulate(T=100.0)
        assert np.all(np.diff(events) >= 0)

    def test_simulate_invalid_T_raises(self):
        hp = HawkesProcess()
        with pytest.raises(ValueError, match="T must be > 0"):
            hp.simulate(T=0.0)

    def test_simulate_higher_mu_produces_more_events(self):
        hp_low = HawkesProcess(mu=0.5, alpha=0.1, beta=1.0)
        hp_high = HawkesProcess(mu=5.0, alpha=0.1, beta=1.0)
        np.random.seed(42)
        events_low = hp_low.simulate(T=100.0)
        np.random.seed(42)
        events_high = hp_high.simulate(T=100.0)
        assert len(events_high) > len(events_low)


# ── Predict ──────────────────────────────────────────────────────────────


class TestPredictNextArrival:
    def test_predict_with_no_events(self):
        hp = HawkesProcess(mu=2.0)
        assert hp.predict_next_arrival(np.array([])) == 0.5

    def test_predict_with_none_events(self):
        hp = HawkesProcess(mu=4.0)
        assert hp.predict_next_arrival(None) == 0.25

    def test_predict_after_events(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
        events = np.array([1.0, 1.1, 1.15])
        wait = hp.predict_next_arrival(events)
        assert wait > 0
        assert wait < 1.0  # high intensity → short wait


# ── Cluster Probability ─────────────────────────────────────────────────


class TestClusterProbability:
    def test_cluster_prob_no_events(self):
        hp = HawkesProcess()
        assert hp.get_cluster_probability(np.array([])) == 0.0

    def test_cluster_prob_with_events(self):
        hp = HawkesProcess(mu=1.0, alpha=2.0, beta=1.0)
        events = np.array([1.0, 1.01, 1.02])
        prob = hp.get_cluster_probability(events, window=0.1)
        assert 0.0 <= prob <= 1.0
        assert prob > 0.0  # should be clustered

    def test_cluster_prob_decays(self):
        hp = HawkesProcess(mu=1.0, alpha=2.0, beta=1.0)
        events = np.array([1.0])
        prob_near = hp.get_cluster_probability(events, window=0.1)
        prob_far = hp.get_cluster_probability(events, window=100.0)
        assert prob_near > prob_far


# ── State & Repr ─────────────────────────────────────────────────────────


class TestStateAndRepr:
    def test_get_state_keys(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=2.0)
        state = hp.get_state()
        for key in ("mu", "alpha", "beta", "kernel", "current_intensity", "cluster_prob", "branching_ratio", "fitted"):
            assert key in state

    def test_repr(self):
        hp = HawkesProcess(mu=1.0, alpha=0.5, beta=2.0)
        r = repr(hp)
        assert "HawkesProcess" in r
        assert "1.0000" in r
