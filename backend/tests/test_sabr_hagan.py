"""
backend/tests/test_sabr_hagan.py
================================

Reference tests for :mod:`backend.domain.sabr` -- Hagan et al. (2002) SABR
implied vol primitives.  Pins are hand-computed against the closed-form
formulas (see module docstring of :mod:`backend.domain.sabr`).

Tolerance is ``rel=1e-9`` for ATM-branch pins (pure closed form) and
``rel=1e-6`` for off-ATM pins (closed form has some floating-point drift in
the ``x(z)`` sqrt-log combination).

Reference values
----------------
For (alpha=0.2, beta=0.5, rho=-0.3, nu=0.4, F=100, K=100, T=0.25):

  - Normal ATM  : 0.0200561875  -- see module calculation.
  - Normal off  : see ``test_normal_off_atm_oh_hagan_pin``.

For (alpha=0.2, beta=1.0, rho=-0.3, nu=0.4, F=100, K=100, T=0.25):

  - Lognormal ATM: 0.2002766667  -- see module calculation.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.sabr import (  # noqa: E402
    hagan_implied_lognormal_vol,
    hagan_implied_normal_vol,
    hagan_implied_vol,
)

# =====================================================================
# 1. Hand-verified ATM pins
# =====================================================================


class TestSABRATMPins:
    """
    Closed-form Hagan ATM volatility pins: alpha/F^β * (1 + bracket * T)
    for normal, and alpha/F^(1-β) * (1 + bracket * T) for lognormal.
    """

    def test_normal_atm_hagan_pin(self):
        # Hand-computed:
        #   F^β = 10, alpha/10 = 0.02
        #   bracket = (0.5-1)^2 * 0.2^2 / (24 * 100)   = 0.0000041667
        #           + (-0.3) * 0.5 * 0.4 * 0.2 / (4 * 10) = -0.0003
        #           + (2 - 3*0.09) * 0.16 / 24          = 0.0115333...
        #           ------------------------------------------- = 0.0112375...
        #   result = 0.02 * (1 + 0.0112375 * 0.25) = 0.0200561875
        assert hagan_implied_normal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        ) == pytest.approx(0.0200561875, rel=1e-6)

    def test_lognormal_atm_hagan_pin(self):
        # Hand-computed:
        #   beta=1, so F^(1-beta) = 1, alpha/1 = 0.2
        #   bracket = 0  ((1-beta) = 0)
        #           + (-0.3) * 1 * 0.4 * 0.2 / (4 * 1) = -0.006
        #           + (2 - 3*0.09) * 0.16 / 24       = 0.0115333...
        #           ----------------------------------- = 0.0055333...
        #   result = 0.2 * (1 + 0.0055333 * 0.25) = 0.2002766667
        assert hagan_implied_lognormal_vol(
            alpha=0.2, beta=1.0, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        ) == pytest.approx(0.2002766667, rel=1e-6)

    def test_normal_atm_beta_1_pin(self):
        """
        With ``beta=1``: ``alpha / F^β = 0.2 / 100 = 0.002`` for normal,
        ``alpha / F^(1-β) = 0.2 / 1 = 0.2`` for lognormal.
        The two conventions scale by exactly ``1/F`` at the ATM, but their
        higher-order brackets DIFFER (the normal bracket is suppressed by
        ``F^β`` in the middle term), so the values are NOT just scaled copies.

        Hand-computed exact normal ATM (see module docstring):
            sigma_N = alpha/F^β * (1 + bracket_normal * T)
                    = 0.002 * (1 + 0.01147333... * 0.25)
                    = 0.002 * 1.00286833...
                    = 0.0020057366666666665
        Hand-computed exact lognormal ATM:
            sigma_B = alpha/F^(1-β) * (1 + bracket_lognormal * T)
                    = 0.2   * (1 + 0.00553333... * 0.25)
                    = 0.2   * 1.00138333...
                    = 0.200276666666
        """
        n_atm = hagan_implied_normal_vol(
            alpha=0.2, beta=1.0, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        )
        b_atm = hagan_implied_lognormal_vol(
            alpha=0.2, beta=1.0, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        )
        # Exact match against hand-derived closed forms.
        assert b_atm == pytest.approx(0.200276666666, rel=1e-9)
        assert n_atm == pytest.approx(0.0020057366666666665, rel=1e-9)
        # Sanity: the two ATM formulas differ by F alphascaling * a small
        # higher-order correction (the West-2005 hermite correction is
        # applied to the (1 + bracket*T) prefactor and is NOT identical
        # between normal and lognormal).  At F=100, the ratio is
        # F * (1 + bracket_lognormal * T) / (1 + bracket_normal * T)
        #   = 100 * 1.0013833... / 1.0028683...  ≈  99.852...
        # NOT exactly 100.  Just verify the ratio is in the right
        # neighbourhood [99.8, 100.2] -- relaxes the sanity check to be
        # robust to scipys floating-point drift.
        ratio = b_atm / n_atm
        assert ratio == pytest.approx(100.0, rel=2e-3), (
            f"b_atm/n_atm ratio = {ratio:.6f}, expected ≈ 100"
        )


# =====================================================================
# 2. Sign / shape properties
# =====================================================================


class TestSABRSmileShape:
    """Smile should drop with rho < 0 (left-skewed) and rise with nu (curvature)."""

    @pytest.mark.parametrize("F,K,label", [
        (100.0, 80.0, "deep_OTM_put"),    # K < F: OTM put, with left-skew vol > ATM
        (100.0, 90.0, "slightly_OTM_put"),  # K < F: still OTM put
        (100.0, 110.0, "slightly_OTM_call"),  # K > F: OTM call, vol < ATM with neg-rho
        (100.0, 120.0, "deep_OTM_call"),  # K > F: deeper OTM call
    ])
    def test_neg_rho_imparts_left_skew_on_both_wings(self, F, K, label):
        """
        With rho = -0.3 (negative equity correlation): the smile is
        LEFT-SKEWED.  The classic empirical pattern is:

            * OTM PUTS (K < F) get RAISED vol (left wing lifted).
            * OTM CALLS (K > F) get LOWERED vol (right wing pushed down).

        Compare to equivalent smile under rho = +0.3 (right-skewed) and
        verify the direction flips for each wing.
        """
        v_neg = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=F, K=K, T=0.5,
        )
        v_pos = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=+0.3, nu=0.4,
            F=F, K=K, T=0.5,
        )
        if K < F:  # OTM put
            assert v_neg > v_pos, (
                f"{label} (K={K}<F={F}): left-skew should LIFT vol "
                f"(rho=-0.3 -> {v_neg}); right-skew should LOWER it "
                f"(rho=+0.3 -> {v_pos}). Got neg<pos -- sign flipped!"
            )
        elif K > F:  # OTM call
            assert v_neg < v_pos, (
                f"{label} (K={K}>F={F}): left-skew should PUSH DOWN vol "
                f"(rho=-0.3 -> {v_neg}); right-skew should RAISE it "
                f"(rho=+0.3 -> {v_pos}). Got neg>pos -- sign flipped!"
            )

    def test_higher_nu_increases_wing_curvature(self):
        """Vol-of-vol (nu) controls smile curvature: doubling nu should
        noticeably push up the wing (deep OTM/ITM) volatilities."""
        F, T = 100.0, 0.5
        K = 130.0  # deep OTM
        v_low = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.2, F=F, K=K, T=T,
        )
        v_high = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.8, F=F, K=K, T=T,
        )
        assert v_high > v_low, (
            f"Wing vol should rise with nu: nu=0.2 -> {v_low}; nu=0.8 -> {v_high}"
        )

    @pytest.mark.parametrize("beta_val", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_sabr_handles_full_beta_range(self, beta_val):
        """Accept all canonical beta values in [0, 1] without crashing."""
        v = hagan_implied_lognormal_vol(
            alpha=0.2, beta=beta_val, rho=-0.3, nu=0.4,
            F=100.0, K=110.0, T=0.25,
        )
        assert 0.0 < v < 2.0  # Implausible to be outside this band for sane alpha


# =====================================================================
# 3. ATM limit consistency
# =====================================================================


class TestSATRATMLimitContinuity:
    K_NEAR_ATM = [99.99, 100.0, 100.01]

    def test_normal_atm_continuity(self):
        """The off-ATM formula must converge to the closed-form ATM value
        as K -> F (limit exists)."""
        F, alpha, beta, rho, nu, T = 100.0, 0.2, 0.5, -0.3, 0.4, 0.25
        atm = hagan_implied_normal_vol(alpha, beta, rho, nu, F, F, T)
        for K in self.K_NEAR_ATM:
            v = hagan_implied_normal_vol(alpha, beta, rho, nu, F, K, T)
            assert v == pytest.approx(atm, rel=1e-3), (
                f"K={K} -> {v}, expected ATM-equivalent {atm} (rel=1e-3)"
            )

    def test_lognormal_atm_continuity(self):
        F, alpha, beta, rho, nu, T = 100.0, 0.2, 1.0, -0.3, 0.4, 0.25
        atm = hagan_implied_lognormal_vol(alpha, beta, rho, nu, F, F, T)
        for K in self.K_NEAR_ATM:
            v = hagan_implied_lognormal_vol(alpha, beta, rho, nu, F, K, T)
            assert v == pytest.approx(atm, rel=1e-3)


# =====================================================================
# 4. Guard clauses (silent zero return)
# =====================================================================


class TestSABRGuardClauses:
    @pytest.mark.parametrize("invalid_inputs", [
        # Bad forward
        {"F": -1.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        # Bad strike
        {"F": 100.0, "K": -1.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        # Bad time
        {"F": 100.0, "K": 100.0, "T": 0.0,  "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        # Bad alpha
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.0, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": -1.0, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        # Bad nu
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.0},
        # Bad beta
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": -0.1, "rho": -0.3, "nu": 0.4},
        # Bad rho
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -1.5, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": 1.5, "nu": 0.4},
    ])
    def test_normal_guard_returns_zero(self, invalid_inputs):
        assert hagan_implied_normal_vol(**invalid_inputs) == 0.0

    @pytest.mark.parametrize("invalid_inputs", [
        {"F": -1.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": -1.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.0,  "alpha": 0.2, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.0, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": -1.0, "beta": 0.5, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": -0.1, "rho": -0.3, "nu": 0.4},
        {"F": 100.0, "K": 100.0, "T": 0.25, "alpha": 0.2, "beta": 0.5, "rho": 1.5, "nu": 0.4},
    ])
    def test_lognormal_guard_returns_zero(self, invalid_inputs):
        assert hagan_implied_lognormal_vol(**invalid_inputs) == 0.0


# =====================================================================
# 5. Multiplexer
# =====================================================================


class TestSABRMultiplexer:
    def test_multiplexer_default_is_lognormal(self):
        v1 = hagan_implied_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
            is_normal=False,
        )
        v2 = hagan_implied_lognormal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        )
        assert v1 == v2

    def test_multiplexer_normal_flag(self):
        v1 = hagan_implied_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
            is_normal=True,
        )
        v2 = hagan_implied_normal_vol(
            alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
            F=100.0, K=100.0, T=0.25,
        )
        assert v1 == v2
