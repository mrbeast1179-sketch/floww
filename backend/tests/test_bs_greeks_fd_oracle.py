"""
backend/tests/test_bs_greeks_fd_oracle.py

Independent finite-difference oracle for the Black-Scholes Greeks.

Where ``test_bs_greeks_canonical.py`` pins values at known Hull textbook points,
this verifies each analytic Greek against a NUMERICAL derivative of a lower-order
quantity -- an oracle that shares no code with the analytic formula under test.
This is the check that catches a sign / factor error in the harder Greeks
(charm, vanna, vomma), which the canonical suite only sanity-checks (charm has
no canonical coverage at all).

Relationships verified (central differences):
    delta == d(price)/dS
    gamma == d(delta)/dS
    vega  == d(price)/dsigma
    vanna == d(delta)/dsigma     ( == d(vega)/dS )
    vomma == d(vega)/dsigma
    charm == -d(delta)/dT        (standard convention: delta decay per unit
                                  CALENDAR time = -d/d(time-to-expiry))
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs_greeks import (  # noqa: E402
    bs_call_price,
    bs_charm,
    bs_delta,
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
)

R = 0.05
Q = 0.0

# (S, K, T, sigma): ATM, ITM call, OTM call, longer-dated / higher-vol.
POINTS = [
    (100.0, 100.0, 0.50, 0.20),
    (105.0, 100.0, 0.50, 0.20),
    (95.0, 100.0, 0.50, 0.20),
    (100.0, 100.0, 1.00, 0.30),
]


def _cd(f, x, h):
    """Central-difference estimate of f'(x)."""
    return (f(x + h) - f(x - h)) / (2.0 * h)


@pytest.mark.parametrize("S,K,T,sigma", POINTS)
class TestGreeksVsFiniteDifference:
    def test_delta_is_dprice_dS(self, S, K, T, sigma):
        fd = _cd(lambda s: bs_call_price(s, K, T, sigma, R, Q), S, 1e-3)
        assert bs_delta(S, K, T, sigma, Q, kind="call", r=R) == pytest.approx(
            fd, rel=1e-5, abs=1e-6
        )

    def test_gamma_is_ddelta_dS(self, S, K, T, sigma):
        fd = _cd(lambda s: bs_delta(s, K, T, sigma, Q, kind="call", r=R), S, 1e-2)
        assert bs_gamma(S, K, T, sigma, Q, r=R) == pytest.approx(fd, rel=1e-4, abs=1e-7)

    def test_vega_is_dprice_dsigma(self, S, K, T, sigma):
        fd = _cd(lambda sig: bs_call_price(S, K, T, sig, R, Q), sigma, 1e-4)
        assert bs_vega(S, K, T, sigma, Q, r=R) == pytest.approx(fd, rel=1e-5, abs=1e-4)

    def test_vanna_is_ddelta_dsigma(self, S, K, T, sigma):
        fd = _cd(lambda sig: bs_delta(S, K, T, sig, Q, kind="call", r=R), sigma, 1e-4)
        assert bs_vanna(S, K, T, sigma, Q, r=R) == pytest.approx(fd, rel=1e-4, abs=1e-5)

    def test_vomma_is_dvega_dsigma(self, S, K, T, sigma):
        fd = _cd(lambda sig: bs_vega(S, K, T, sig, Q, r=R), sigma, 1e-4)
        assert bs_vomma(S, K, T, sigma, Q, r=R) == pytest.approx(fd, rel=1e-3, abs=1e-4)

    def test_charm_is_minus_ddelta_dT(self, S, K, T, sigma):
        fd_dT = _cd(lambda t: bs_delta(S, K, t, sigma, Q, kind="call", r=R), T, 1e-4)
        assert bs_charm(S, K, T, sigma, Q, kind="call", r=R) == pytest.approx(
            -fd_dT, rel=1e-3, abs=1e-5
        )
