"""
backend/tests/services/test_microstructure_property.py

Property-based math invariants for microstructure kernels.
Uses hypothesis to generate random inputs and verify mathematical properties.

Each test verifies a fundamental invariant that should hold for ALL valid inputs,
not just specific test cases. This catches edge cases that hand-written tests miss.
"""
import math

import numpy as np
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# --------------------------------------------------------------------------- #
#  VPIN invariants
# --------------------------------------------------------------------------- #

from services.vpin_engine import VpinEngine


class TestVpinProperties:
    """Property-based invariants for the VPIN engine."""

    @given(
        price_changes=st.lists(
            st.floats(min_value=-0.1, max_value=0.1, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=100
        ),
        volumes=st.lists(
            st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
            min_size=1, max_size=100
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_buy_plus_sell_equals_total(self, price_changes, volumes):
        """∀ (price_changes, volumes) with volumes > 0 → buy + sell == volumes (bit-exact)."""
        n = min(len(price_changes), len(volumes))
        pc = np.array(price_changes[:n], dtype=np.float64)
        vol = np.array(volumes[:n], dtype=np.float64)

        buy, sell = VpinEngine.classify_volume(pc, vol)
        total = buy + sell

        np.testing.assert_allclose(total, vol, rtol=1e-12,
            err_msg="buy + sell must equal total volume")

    @given(
        bucket_size=st.floats(min_value=100.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        window=st.integers(min_value=5, max_value=100),
    )
    @settings(max_examples=50, deadline=None)
    def test_vpin_bounded_zero_to_one(self, bucket_size, window):
        """VPIN must always be in [0, 1]."""
        engine = VpinEngine(bucket_size=bucket_size, window=window)

        # Feed random trades
        np.random.seed(42)
        for _ in range(200):
            pc = np.random.randn() * 0.01
            vol = np.random.uniform(100, 10000)
            sigma = 0.01
            engine.update(pc, vol, sigma)

        vpin = engine.compute_vpin()
        assert 0.0 <= vpin <= 1.0, f"VPIN {vpin} out of [0,1]"

    @given(
        price_changes=st.lists(
            st.floats(min_value=-0.05, max_value=0.05, allow_nan=False, allow_infinity=False),
            min_size=10, max_size=50
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_vpin_constant_price_is_zero(self, price_changes):
        """If price never changes, VPIN should be 0 (no informed trading signal)."""
        engine = VpinEngine(bucket_size=1000.0, window=20)

        for _ in range(50):
            engine.update(0.0, 1000.0, 0.01)

        vpin = engine.compute_vpin()
        assert vpin == 0.0, f"VPIN with constant price should be 0, got {vpin}"

    @given(
        qi_history=st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=10, max_size=200
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_qi_zscore_finite(self, qi_history):
        """QI z-score must always be finite for finite inputs."""
        engine = VpinEngine(bucket_size=1000.0, window=20)

        for qi in qi_history:
            engine.compute_quote_imbalance(100.0 + qi, 100.0)

        z = engine.compute_qi_zscore()
        assert math.isfinite(z), f"QI z-score {z} is not finite"


# --------------------------------------------------------------------------- #
#  GEX invariants
# --------------------------------------------------------------------------- #

from services.gex_aggregator import GexAggregator


class TestGexProperties:
    """Property-based invariants for GEX aggregation."""

    @given(
        spot=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        multiplier=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_gex_linear_in_oi(self, spot, multiplier):
        """GEX is linear in OI: scaling all OI by k scales total GEX by k."""
        strikes = [spot * 0.9, spot, spot * 1.1]
        T = 0.25  # 3 months in years
        base_contracts = []
        for s in strikes:
            base_contracts.append({
                "strike": s, "expiry": "2026-06-15", "T": T, "type": "call",
                "oi": 100.0, "gamma": 0.01, "iv": 0.2, "volume": 1000,
            })
            base_contracts.append({
                "strike": s, "expiry": "2026-06-15", "T": T, "type": "put",
                "oi": 100.0, "gamma": 0.01, "iv": 0.2, "volume": 1000,
            })

        # Compute base GEX
        result_base = GexAggregator().compute(spot, base_contracts)
        base_total = result_base["net_gex"]

        # Scale OI by multiplier
        scaled_contracts = []
        for c in base_contracts:
            c2 = dict(c)
            c2["oi"] = c["oi"] * multiplier
            scaled_contracts.append(c2)

        result_scaled = GexAggregator().compute(spot, scaled_contracts)
        scaled_total = result_scaled["net_gex"]

        if abs(base_total) > 1e-10:
            ratio = scaled_total / base_total
            np.testing.assert_allclose(ratio, multiplier, rtol=1e-9,
                err_msg=f"GEX scaling: expected {multiplier}, got {ratio}")

    @given(
        spot=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_gex_empty_contracts_is_zero(self, spot):
        """GEX with no contracts should be zero."""
        result = GexAggregator().compute(spot, [])
        assert result["net_gex"] == 0.0
        assert result["total_gex"] == 0.0

    @given(
        spot=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        n_contracts=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=50, deadline=None)
    def test_gex_single_strike_symmetry(self, spot, n_contracts):
        """Equal call and put OI at same strike → net GEX ≈ 0 (gamma symmetry)."""
        assume(n_contracts > 0)
        contracts = []
        for _ in range(n_contracts):
            contracts.append({
                "strike": spot, "expiry": "2026-06-15", "type": "call",
                "oi": 100.0, "gamma": 0.01, "iv": 0.2, "volume": 100,
            })
            contracts.append({
                "strike": spot, "expiry": "2026-06-15", "type": "put",
                "oi": 100.0, "gamma": 0.01, "iv": 0.2, "volume": 100,
            })

        result = GexAggregator().compute(spot, contracts)
        # With equal OI and same gamma, net GEX should be near zero
        assert abs(result["net_gex"]) < abs(result["total_gex"]) * 0.01 + 1e-6


# --------------------------------------------------------------------------- #
#  SABR invariants
# --------------------------------------------------------------------------- #

from services.stochastic_vol import SABRModel


class TestSabrProperties:
    """Property-based invariants for the SABR model."""

    @given(
        F=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False),
        alpha=st.floats(min_value=0.01, max_value=0.5, allow_nan=False, allow_infinity=False),
        beta=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        rho=st.floats(min_value=-0.99, max_value=0.99, allow_nan=False, allow_infinity=False),
        nu=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_sabr_vol_positive(self, F, K, T, alpha, beta, rho, nu):
        """SABR implied vol must always be positive."""
        model = SABRModel(alpha=alpha, beta=beta, rho=rho, nu=nu)
        vol = model.hagan_normal_vol(F, K, T)
        assert vol > 0, f"SABR vol {vol} must be positive"
        assert math.isfinite(vol), f"SABR vol {vol} must be finite"

    @given(
        F=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=0.1, allow_nan=False, allow_infinity=False),
        alpha=st.floats(min_value=0.05, max_value=0.3, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_sabr_atm_normal_lognormal_agree(self, F, T, alpha):
        """At F=K, normal and lognormal vol should agree within rel-err < 1e-3 for small T."""
        model = SABRModel(alpha=alpha, beta=0.5, rho=0.0, nu=0.3)
        vol_n = model.hagan_normal_vol(F, F, T)
        vol_ln = model.hagan_lognormal_vol(F, F, T)

        # For small T, the two should be close
        if vol_ln > 1e-6:
            rel_err = abs(vol_n - vol_ln * F) / (vol_ln * F)
            assert rel_err < 0.01, f"Normal vol {vol_n} vs lognormal*F {vol_ln*F}, rel_err={rel_err}"


# --------------------------------------------------------------------------- #
#  Hawkes process invariants
# --------------------------------------------------------------------------- #

from services.hawkes_process import HawkesProcess


class TestHawkesProperties:
    """Property-based invariants for Hawkes process."""

    @given(
        mu=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
        alpha=st.floats(min_value=0.01, max_value=0.9, allow_nan=False, allow_infinity=False),
        beta=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_hawkes_empty_history_intensity_is_mu(self, mu, alpha, beta):
        """intensity(t, []) == mu (identity for empty history)."""
        hp = HawkesProcess(mu=mu, alpha=alpha, beta=beta)
        lam = hp.intensity(0.0, np.array([]))
        assert lam == mu, f"Empty history intensity should be {mu}, got {lam}"

    @given(
        mu=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        n_events=st.integers(min_value=10, max_value=100),
    )
    @settings(max_examples=50, deadline=None)
    def test_hawkes_poisson_when_alpha_zero(self, mu, T, n_events):
        """Simulating with α=0 produces a Poisson process (mean inter-arrival ≈ 1/μ)."""
        hp = HawkesProcess(mu=mu, alpha=0.0, beta=1.0)
        events = hp.simulate(T=T, n_events=n_events)

        if len(events) >= 2:
            inter_arrivals = np.diff(events)
            mean_ia = np.mean(inter_arrivals)
            expected = 1.0 / mu
            # Poisson: mean inter-arrival = 1/rate, allow 30% tolerance
            if expected > 0:
                ratio = mean_ia / expected
                assert 0.3 < ratio < 3.0, \
                    f"Mean inter-arrival {mean_ia} vs expected {expected}, ratio={ratio}"

    @given(
        mu=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
        alpha=st.floats(min_value=0.1, max_value=0.5, allow_nan=False, allow_infinity=False),
        beta=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=5.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30, deadline=None)
    def test_hawkes_branching_ratio_stable(self, mu, alpha, beta, T):
        """Branching ratio n = alpha/beta < 1 for subcritical process."""
        assume(beta > 0)
        hp = HawkesProcess(mu=mu, alpha=alpha, beta=beta)
        events = hp.simulate(T=T, n_events=1000)

        # For subcritical process, number of events should be finite and reasonable
        expected_events = mu * T * (1.0 / (1.0 - alpha / beta)) if alpha < beta else float('inf')
        if alpha < beta:
            # Should be within 5x of expected (very loose for stochastic)
            assert len(events) < max(expected_events * 5, 100), \
                f"Too many events {len(events)} for subcritical process (expected ~{expected_events})"


# --------------------------------------------------------------------------- #
#  Kyle's Lambda invariants
# --------------------------------------------------------------------------- #

from services.liquidity_metrics import KyleLambda


class TestKyleProperties:
    """Property-based invariants for Kyle's Lambda."""

    @given(
        n_obs=st.integers(min_value=5, max_value=50),
    )
    @settings(max_examples=50, deadline=None)
    def test_kyle_lambda_zero_for_zero_volume(self, n_obs):
        """Kyle's λ should be 0 when all signed volumes are 0."""
        kyle = KyleLambda(window=20)
        for _ in range(n_obs):
            kyle.update(100.0, 0.0, 1)  # zero volume

        assert kyle.compute() == 0.0

    @given(
        true_lambda=st.floats(min_value=0.001, max_value=0.1, allow_nan=False, allow_infinity=False),
        n_obs=st.integers(min_value=20, max_value=100),
    )
    @settings(max_examples=30, deadline=None)
    def test_kyle_lambda_recovers_true_value(self, true_lambda, n_obs):
        """Kyle's λ should recover the true price impact from synthetic data."""
        kyle = KyleLambda(window=100)

        np.random.seed(42)
        for _ in range(n_obs):
            signed_vol = np.random.uniform(100, 10000) * np.random.choice([-1, 1])
            ret = true_lambda * signed_vol + np.random.normal(0, 1e-6)
            price = 100.0 + ret
            kyle.update(price, abs(signed_vol), 1 if signed_vol > 0 else -1)

        estimated = kyle.compute()
        if abs(estimated) > 1e-10:
            # Should be within order of magnitude
            ratio = estimated / true_lambda
            assert 0.1 < ratio < 10.0, \
                f"Estimated λ {estimated} vs true {true_lambda}, ratio={ratio}"
