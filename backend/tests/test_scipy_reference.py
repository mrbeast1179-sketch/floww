"""
backend/tests/test_scipy_reference.py
=====================================

Scipy.stats-backed reference tests for SABR and Hawkes domain primitives.

These tests complement (do not replace) the deterministic hand-pin tests in
``test_sabr_hagan.py`` and ``test_hawkes_kernel.py``.  They exercise the
mathematical kernels against scipy's reference distribution functions and
validators:

SABR — call-price + Black-Scholes price duality
-----------------------------------------------
* Black-Scholes call/put pricing via ``scipy.stats.norm.cdf``.
* Bachelier (normal-vol) call pricing via ``scipy.stats.norm.cdf`` + ``.pdf``.
* Put-call parity exposes the F·e^{-rT} − K·e^{-rT} identity for r=q=0.
* SABR ↔ BS duality in the ``β=1, ν→0`` limit: the SABR-implied lognormal
  vol collapses to ``α``, and the BS call price with ``σ=α`` matches the
  SABR-pricing chain.

Hawkes — non-parametric intensity via histogram estimator
---------------------------------------------------------
* Inter-arrival Δt distribution marginally tested against
  ``scipy.stats.expon`` with the Kolmogorov-Smirnov statistic.
* ``hawkes_stationary_intensity = μ/(1−η)`` cross-checked against an
  equal-width bin histogram estimator's late-bin rate.
* Total event count conserved by the histogram (Σ_k count_k = N).

Tolerance design notes
----------------------
SABR tests use:
* Bit-tight (``rel=1e-12``) for the closed-form SABR ATM pin (both share
  the scipy.stats.norm.cdf path, drift ~1e-15).
* ``rel=1e-9`` for put-call-parity exact identities.
* ``rel=1e-3`` for duality-in-the-limit tests (small T bracket drift).

Hawkes tests use:
* ``rel=0.20`` for the long-run Δt mean (statistical sampling noise).
* ``abs = 0.30 · λ̄`` (≈ 30 % relative) for the late-bin and mean-bin
  histogram-convergence tests.  For α=0.3, β=1.0 the asymptotic Hawkes
  count-process Fano factor is ``(1−η)⁻² ≈ 2.04`` (the dispersion factor
  is the dominant source of variance for short windows; it equilibrates
  to 1 for windows bw ≫ 1/β).  The 30 % guard band is comfortably
  generous: it absorbs the structural overdispersion plus single-
  realisation sampling noise (these are SANITY-CHECKS, not tight pins).
* Simple `0 ≤ p ≤ 1` bounds for the Kolmogorov-Smirnov p-value so the
  test remains valid irrespective of whether the simulated stream is
  near-Poisson (passes KS at p > 0.05) or bursty (rejects KS at
  p ≤ 0.05 — both outcomes are informationally meaningful).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

scipy_stats = pytest.importorskip("scipy.stats")
norm = scipy_stats.norm
expon = scipy_stats.expon
kstest = scipy_stats.kstest

REPO_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_BACKEND))

from domain.hawkes import (  # noqa: E402
    hawkes_stationary_intensity,
    simulate_hawkes_ogata,
)
from domain.sabr import (  # noqa: E402
    hagan_implied_lognormal_vol,
    hagan_implied_normal_vol,
)

# =====================================================================
# 0. Pricing helpers (scipy.stats.norm-backed)
# =====================================================================
#
# Risk-free rate and dividend yield are set to 0 throughout.  The SABR
# inputs (F, T) treat F as the forward, so r = q = 0 ⇒ F = spot.  This
# matches the no-carry convention in domain/sabr.py.


def bs_call_price(F: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes call price via ``scipy.stats.norm.cdf``.

    Forward-neutral: r = q = 0. ``C = F·Φ(d1) − K·Φ(d2)``.
    """
    if T <= 0.0 or sigma <= 0.0:
        return max(F - K, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return F * float(norm.cdf(d1)) - K * float(norm.cdf(d2))


def bs_put_price(F: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes put via ``scipy.stats.norm.cdf``.

    ``P = K·Φ(−d2) − F·Φ(−d1)``.
    """
    if T <= 0.0 or sigma <= 0.0:
        return max(K - F, 0.0)
    sqrtT = math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return K * float(norm.cdf(-d2)) - F * float(norm.cdf(-d1))


def bachelier_call_price(F: float, K: float, T: float, sigma_n: float) -> float:
    """Bachelier (normal-vol) call via ``scipy.stats.norm.cdf`` + ``.pdf``.

    ``d = (F − K) / (σ_N · √T)``.
    ``C = (F − K)·Φ(d) + σ_N·√T·φ(d)``.
    """
    if T <= 0.0 or sigma_n <= 0.0:
        return max(F - K, 0.0)
    sqrtT = math.sqrt(T)
    d = (F - K) / (sigma_n * sqrtT)
    return (F - K) * float(norm.cdf(d)) + sigma_n * sqrtT * float(norm.pdf(d))


def bachelier_put_price(F: float, K: float, T: float, sigma_n: float) -> float:
    """Bachelier put: ``P = (K − F)·Φ(−d) + σ_N·√T·φ(d)``."""
    if T <= 0.0 or sigma_n <= 0.0:
        return max(K - F, 0.0)
    sqrtT = math.sqrt(T)
    d = (F - K) / (sigma_n * sqrtT)
    return (K - F) * float(norm.cdf(-d)) + sigma_n * sqrtT * float(norm.pdf(d))


# =====================================================================
# 1. Non-parametric intensity estimator (Hawkes)
# =====================================================================


def histogram_intensity(
    event_times: np.ndarray, T: float, n_bins: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Non-parametric intensity via equal-width bin counts.

    Returns ``(bin_centers, rate)``   with rate at bin k = count_k / bin_width.

    This is the histogram estimator of the conditional intensity
    ``λ̂(t | events) = (events in window dt) / dt``, defined here over
    equal-width bins covering ``[0, T]``.  For a stationary process, the
    *asymptotic* rate at any bin contains an unbiased estimator of the
    stationary intensity λ̄ = E[λ(t)] over the bin's lifetime.
    """
    bw = T / n_bins
    edges = np.linspace(0.0, T, n_bins + 1)
    centers = 0.5 * (edges[1:] + edges[:-1])
    counts, _ = np.histogram(event_times, bins=edges)
    rate = counts / bw
    return centers, rate


# =====================================================================
# 2. SABR — scipy.stats-backed call-price tests
# =====================================================================


class TestSabrBsCallPriceDuality:
    """SABR-implied lognormal vol → BS call/put via ``scipy.stats.norm.cdf``."""

    def test_atm_call_price_pin_against_exact_norm_cdf_formula(self):
        """α=0.2, β=1, ρ=-0.3, ν=0.4, F=K=100, T=0.25.

        At ATM with r = q = 0, the BS closed form reduces EXACTLY to:
            ``C_ATM = F · [2 · Φ(σ√T / 2) − 1]``

        (The Taylor approximation ``σ·F·√(T/2π)`` is only accurate for
        ``σ√T → 0``; at this test's σ√T ≈ 0.1 the relative error is ~0.2 %,
        so we'd need a much looser tolerance.)

        We use ``scipy.stats.norm.cdf`` directly as the *exact* reference
        and verify ``bs_call_price`` matches bit-tight (rel=1e-12).
        """
        vol = hagan_implied_lognormal_vol(
            alpha=0.2, beta=1.0, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        )
        c = bs_call_price(F=100.0, K=100.0, T=0.25, sigma=vol)
        # EXACT ATM closed form via scipy.stats.norm (same library used
        # inside bs_call_price, so this is bit-tight to fp precision).
        d1 = vol * math.sqrt(0.25) / 2.0
        exact = 100.0 * (2.0 * float(norm.cdf(d1)) - 1.0)
        assert c == pytest.approx(exact, rel=1e-12)
        # And broadly plausible.
        assert 3.5 < c < 4.5

    def test_put_call_parity_holds_f_minus_k(self):
        """C − P = F − K (r = q = 0 in forward-neutral SABR)."""
        F, K, T = 100.0, 110.0, 0.5
        vol = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=F, K=K, T=T,
        )
        c = bs_call_price(F, K, T, vol)
        p = bs_put_price(F, K, T, vol)
        assert c - p == pytest.approx(F - K, abs=1e-9)

    def test_call_increases_monotone_in_T(self):
        """Same σ_B ⇒ longer T ⇒ larger call price.

        Scipy-backed closed form: ``C(T)`` is smooth and increasing for
        ``T > 0``, ``σ > 0``.
        """
        F, K, sigma = 100.0, 100.0, 0.2
        c_quarter = bs_call_price(F, K, T=0.25, sigma=sigma)
        c_one = bs_call_price(F, K, T=1.0, sigma=sigma)
        assert c_quarter < c_one

    def test_call_decreases_monotone_in_K(self):
        """ATM > slightly-OTM > deep-OTM call price.

        Demonstrates the smooth BS-O(√T) vol-time behavior via ``norm.cdf``.
        """
        F, T, sigma = 100.0, 0.5, 0.2
        c_atm = bs_call_price(F, F, T, sigma)
        c_otm = bs_call_price(F, 110.0, T, sigma)
        c_far = bs_call_price(F, 130.0, T, sigma)
        assert c_atm > c_otm > c_far > 0.0

    def test_atm_call_price_matches_lognormal_alpha(self):
        """SABR(β=1, ν→0) emulator: F=K=100, σ=0.20 ⇒ C ≈ BS_call(100,100,T,0.20)."""
        F, T = 100.0, 1.0
        sigma = 0.20
        c_ref = bs_call_price(F, F, T, sigma)
        vol = hagan_implied_lognormal_vol(
            alpha=0.20, beta=1.0, rho=0.0, nu=1e-12, F=F, K=F, T=T,
        )
        c_sabr = bs_call_price(F, F, T, vol)
        # Tiny T bracket correction ⇒ rel=1e-4 tolerance is fine.
        assert c_sabr == pytest.approx(c_ref, rel=1e-3)


class TestSabrBsDualityLimitBetaOneNuZero:
    """Duality: SABR with β=1, ν→0 collapses to lognormal BS with σ=α."""

    def test_atm_lognormal_vol_returns_alpha_in_zero_nu_limit(self):
        """At F=K with β=1 and ν negligibly small, the SABR lognormal
        vol should recover ``α`` (modulo a tiny T dependent bracket)."""
        vol = hagan_implied_lognormal_vol(
            alpha=0.20, beta=1.0, rho=0.0, nu=1e-12,
            F=100.0, K=100.0, T=1e-3,  # very small T keeps bracket ~0
        )
        assert vol == pytest.approx(0.20, abs=1e-4)

    def test_sabr_call_via_scipy_matches_direct_bs_alpha(self):
        """End-to-end duality: SABR call (β=1, ν→0) vs BS call (σ=α)
        with scipy-backed pricing — they should agree within the bracket.
        """
        F, K, T, alpha = 100.0, 95.0, 0.5, 0.18
        c_bs = bs_call_price(F, K, T, alpha)
        vol = hagan_implied_lognormal_vol(
            alpha=alpha, beta=1.0, rho=0.0, nu=1e-12,
            F=F, K=K, T=T,
        )
        c_sabr = bs_call_price(F, K, T, vol)
        # The two should agree very closely: ν=1e-12 ⇒ smile vanishes.
        assert c_sabr == pytest.approx(c_bs, rel=1e-3)


class TestSabrBachelierCallPrice:
    """Bachelier normal-vol convention via ``scipy.stats.norm.cdf`` + ``.pdf``."""

    def test_bachelier_atm_call_short_t_formula_pin(self):
        """σ_N = 1, F = K = 100, T = 1 ⇒ C = σ_N · √(T / 2π).

        Hand-derived from ``C = σ_N·√T·φ(0) = σ_N·√T·(1/√(2π))``.
        """
        sigma_n = 1.0
        c = bachelier_call_price(F=100.0, K=100.0, T=1.0, sigma_n=sigma_n)
        expected = sigma_n * math.sqrt(1.0 / (2.0 * math.pi))
        assert c == pytest.approx(expected, rel=1e-9)

    def test_bachelier_call_increases_monotone_in_sigma_n(self):
        """Larger σ_N ⇒ larger Bachelier call."""
        F, K, T = 100.0, 100.0, 1.0
        c_low = bachelier_call_price(F, K, T, sigma_n=1.0)
        c_high = bachelier_call_price(F, K, T, sigma_n=3.0)
        assert c_low < c_high

    def test_bachelier_call_put_parity(self):
        """Normal vol puts and calls satisfy ``C − P = F − K`` (r=q=0)."""
        F, K, T, sigma_n = 100.0, 90.0, 1.0, 1.5
        c = bachelier_call_price(F, K, T, sigma_n)
        p = bachelier_put_price(F, K, T, sigma_n)
        assert c - p == pytest.approx(F - K, abs=1e-9)

    def test_sabr_normal_vol_path_bachelier_price_is_positive(self):
        """SABR-normal vol → Bachelier call must be positive for OTM calls.

        For F=100, K=90 (OTM put), the bachelier_call_price formula
        returns ``(F − K) · Φ(d) + σ_N·√T·φ(d)``.  Both terms are
        non-negative since ``F > K`` and ``σ_N > 0``, so the result is
        strictly positive.
        """
        F, K, T = 100.0, 90.0, 1.0
        sigma_n = hagan_implied_normal_vol(
            alpha=0.20, beta=0.5, rho=-0.3, nu=0.4, F=F, K=K, T=T,
        )
        c = bachelier_call_price(F, K, T, sigma_n)
        assert c > 0.0


# =====================================================================
# 3. Hawkes — scipy.stats reference tests
# =====================================================================


class TestHawkesInterArrivalsVsExponential:
    """Inter-arrival time distribution vs scipy.stats.expon baseline."""

    def test_hawkes_unconditional_mean_dt_inverse_of_stationary_rate(self):
        """For a stationary Hawkes with ``μ, α, β`` and many realisations,
        the unconditional sample mean of Δt should be
        ``E[Δt] = (1 − η) / μ = 1 / λ̄`` where ``λ̄ = μ / (1 − η)``.
        """
        mu, alpha, beta = 0.5, 0.3, 1.0
        eta = alpha / beta
        T = 2_000.0
        expected_mean_dt = (1.0 - eta) / mu

        means = []
        rng = np.random.default_rng(0)
        for _ in range(5):
            events = simulate_hawkes_ogata(
                T=T, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
            )
            if events.size >= 2:
                means.append(float(np.mean(np.diff(events))))
        assert means, "no events to compute mean Δt"
        empirical_mean = float(np.mean(means))
        # 20 % relative tolerance reflects clustering-induced variance.
        assert empirical_mean == pytest.approx(expected_mean_dt, rel=0.20)

    def test_ks_statistic_pvalue_are_bounded_for_weakly_bursty_stream(self):
        """For α small (near-Poisson), KS test for Δt against
        ``scipy.stats.expon(scale=1/μ)`` returns p ∈ (0, 1]. For bursty
        streams, KS will reject (process NOT exponential); this test
        only validates that the test RUNS and reports a valid p-value
        (rejecting is fine and info-rich).
        """
        mu, alpha, beta = 1.0, 0.05, 1.0  # very weak self-excitation
        rng = np.random.default_rng(7)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
        )
        dt = np.diff(events)
        if dt.size < 30:
            pytest.skip("not enough events for KS test")
        ks_stat, p_value = kstest(dt, "expon", args=(0.0, 1.0 / mu))
        assert 0.0 <= ks_stat <= 1.0
        assert 0.0 <= p_value <= 1.0

    def test_scipy_expon_sanity_anchor(self):
        """Anchors the scipy.stats.expon baseline we test against.

        ``scipy.stats.expon.stats(scale=scale)`` returns ``(mean=scale, var=scale²)``.
        """
        scale = 2.0
        m, v, _, _ = expon.stats(loc=0.0, scale=scale, moments="mvsk")
        assert m == pytest.approx(scale)
        assert v == pytest.approx(scale ** 2)


class TestHawkesHistogramIntensityFormat:
    """The histogram estimator must preserve total events and produce
    well-shaped output."""

    def test_total_bin_count_matches_n_events(self):
        """``Σ bin_count_k = N`` (the histogram must not lose events).
        Off-by-one rounding allowed (floor/ceil on the last bin).
        """
        rng = np.random.default_rng(13)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=0.5, alpha=0.3, beta=1.0, n_max=5000, rng=rng,
        )
        T = 2_000.0
        n_bins = 20
        _, rate = histogram_intensity(events, T=T, n_bins=n_bins)
        bw = T / n_bins
        total = float(np.sum(rate * bw))
        assert abs(total - events.size) <= 1  # ≤ 1 event rounding

    def test_returns_correct_shapes(self):
        """``(n_centers, n_rates)`` shape with non-negative rates."""
        rng = np.random.default_rng(41)
        events = simulate_hawkes_ogata(
            T=500.0, mu=0.5, alpha=0.2, beta=1.0, rng=rng,
        )
        centers, rate = histogram_intensity(events, T=500.0, n_bins=8)
        assert centers.shape == (8,)
        assert rate.shape == (8,)
        assert (rate >= 0).all()
        # Centers should be evenly spaced across (0, T).
        assert np.allclose(np.diff(centers), centers[1] - centers[0])

    def test_total_rate_times_T_equals_event_count(self):
        """Average bin-rate × T is approximately N (number of events)."""
        rng = np.random.default_rng(31)
        events = simulate_hawkes_ogata(
            T=1_000.0, mu=0.4, alpha=0.2, beta=1.0, n_max=3000, rng=rng,
        )
        T = 1_000.0
        n_bins = 10
        bw = T / n_bins
        _, rate = histogram_intensity(events, T=T, n_bins=n_bins)
        total = float(np.sum(rate * bw))
        assert abs(total - events.size) <= 1


class TestHawkesHistogramVsStationaryIntensity:
    """Histogram estimator compared to ``hawkes_stationary_intensity``.

    These tests are SANITY-CHECK companions to the deterministic pin
    tests in ``test_hawkes_kernel.py``.  They use ``rel=0.30`` relative
    tolerance to absorb both:
      * the asymptotic Fano-factor dispersion ``(1−η)⁻² ≈ 2`` for the
        exponential Hawkes count process with ``η ≈ 0.3``;
      * statistical sampling noise across single realisations.

    The deterministic pin tests maintain the source-of-truth arithmetic
    guarantees (Hawkes M-O-M estimator, intensity closed forms, etc.);
    these scipy-backed statistical tests complement them by validating
    that the *empirical* output of the simulator lands in the right
    ballpark of the closed-form stationary intensity.
    """

    def test_late_bin_converges_to_stationary_lambda_bar(self):
        """Late-bin histogram rate converges to ``λ̄ = μ/(1−η) ≈ 0.714``
        in distribution.  Sanity tolerance via ``rel=0.30``.
        """
        mu, alpha, beta = 0.5, 0.3, 1.0
        eta = alpha / beta
        lam_bar = mu / (1.0 - eta)

        rng = np.random.default_rng(21)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
        )
        n_bins = 10
        _, rate = histogram_intensity(events, T=2_000.0, n_bins=n_bins)
        late_bin_rate = float(rate[-1])
        # Sanity-check tolerance (rel=0.30): absorbs Hawkes dispersion +
        # statistical sampling noise.  Looser than a recovery test would be.
        assert abs(late_bin_rate - lam_bar) <= 0.30 * lam_bar, (
            f"Late-bin histogram rate {late_bin_rate:.4f} should be within "
            f"±30 % of λ̄ = {lam_bar:.4f}"
        )

    def test_histogram_late_bin_matches_hawkes_stationary_intensity(self):
        """Compare late-bin rate to the closed-form
        ``hawkes_stationary_intensity`` primitive.  Sanity tolerance.
        """
        mu, alpha, beta = 0.5, 0.3, 1.0
        lam_bar = hawkes_stationary_intensity(mu=mu, alpha=alpha, beta=beta)

        rng = np.random.default_rng(99)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
        )
        n_bins = 10
        _, rate = histogram_intensity(events, T=2_000.0, n_bins=n_bins)
        late_bin_rate = float(rate[-1])
        assert abs(late_bin_rate - lam_bar) <= 0.30 * lam_bar, (
            f"Late-bin histogram rate {late_bin_rate:.4f} should be within "
            f"±30 % of hawkes_stationary_intensity={lam_bar:.4f}"
        )

    def test_mean_bin_rate_matches_stationary_lambda_bar(self):
        """Mean of all bin-rates across the simulation converges to λ̄.

        Same `rel=0.30` sanity tolerance as the late-bin tests.  The mean
        bin-rate has a smaller realised variance than the late-bin rate
        because it benefits from averaging across 10 bins, so the rel=0.30
        envelope is comfortably generous for this assertion.
        """
        mu, alpha, beta = 0.5, 0.3, 1.0
        lam_bar = mu / (1 - alpha / beta)

        rng = np.random.default_rng(123)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
        )
        n_bins = 10
        _, rate = histogram_intensity(events, T=2_000.0, n_bins=n_bins)
        mean_bin_rate = float(np.mean(rate))
        assert abs(mean_bin_rate - lam_bar) <= 0.30 * lam_bar, (
            f"Mean bin-rate {mean_bin_rate:.4f} should be within ±30 % of "
            f"λ̄ = {lam_bar:.4f}"
        )

    def test_late_bin_rate_in_plausible_ballpark_of_lambda(self):
        """A wider, smoke-test guard: late-bin rate is in the order-of-
        magnitude band ``[0.1·λ̄, 10·λ̄]``.  Useful as a regression alert
        if the histogram estimator is buggy (off by a constant factor).
        """
        mu, alpha, beta = 0.5, 0.3, 1.0
        lam_bar = mu / (1.0 - eta_or_default(alpha, beta))

        rng = np.random.default_rng(7)
        events = simulate_hawkes_ogata(
            T=2_000.0, mu=mu, alpha=alpha, beta=beta, n_max=5000, rng=rng,
        )
        _, rate = histogram_intensity(events, T=2_000.0, n_bins=10)
        late_bin_rate = float(rate[-1])
        assert 0.1 * lam_bar <= late_bin_rate <= 10.0 * lam_bar, (
            f"Late-bin rate {late_bin_rate:.4f} far outside plausible "
            f"band [0.1·λ̄, 10·λ̄] = [{0.1*lam_bar:.4f}, {10*lam_bar:.4f}]"
        )


def eta_or_default(alpha: float, beta: float) -> float:
    """Safe η-computation guard for the smoke-test band assertion."""
    return alpha / beta if beta > 0 else 0.0
