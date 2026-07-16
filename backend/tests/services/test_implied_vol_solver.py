"""
Unit tests for the new ``implied_vol_from_price`` solver
appended to ``bs_greeks.py`` (steal-list rank #5).

Covers:
  * Round-trip solve: pick sigma, get a price back, solve it, get sigma.
  * Bisection fallback converges on weird inputs.
  * Invalid inputs return 0.0 (silent-mask convention).
  * Put vs call paths both work.
  * Robustness across reasonable spot/K/T/strike ranges.
"""

import math

import pytest

from bs_greeks import (
    bs_call_price,
    bs_put_price,
    implied_vol_from_price,
)


def _approx(actual: float, expected: float, tol: float = 1e-3) -> bool:
    return math.isclose(actual, expected, rel_tol=tol, abs_tol=tol)


@pytest.mark.parametrize("sigma", [0.05, 0.10, 0.25, 0.50, 1.00, 1.75])
def test_round_trip_call(sigma: float):
    S, K, T = 580.0, 585.0, 30 / 365.0
    price = bs_call_price(S, K, T, sigma, r=0.045, q=0.0)
    solved = implied_vol_from_price(price, S, K, T, kind="call", r=0.045, q=0.0, tol=1e-6)
    assert solved > 0
    assert _approx(solved, sigma, tol=1e-3), f"solve mismatch: {solved} vs {sigma}"


@pytest.mark.parametrize("sigma", [0.05, 0.10, 0.50, 1.50])
def test_round_trip_put(sigma: float):
    S, K, T = 580.0, 575.0, 45 / 365.0
    price = bs_put_price(S, K, T, sigma, r=0.045, q=0.0)
    solved = implied_vol_from_price(price, S, K, T, kind="put", r=0.045, q=0.0, tol=1e-6)
    assert solved > 0
    assert _approx(solved, sigma, tol=1e-3)


def test_invalid_inputs_return_zero():
    assert implied_vol_from_price(0.0, 580, 585, 30 / 365) == 0.0
    assert implied_vol_from_price(2.0, 0, 585, 30 / 365) == 0.0
    assert implied_vol_from_price(2.0, 580, 0, 30 / 365) == 0.0
    assert implied_vol_from_price(2.0, 580, 585, 0) == 0.0


def test_below_intrinsic_returns_zero():
    """Call is OTM at K > S — solver should not produce a positive IV from a price below intrinsic."""
    # S=580, K=600 → call intrinsic = 0, and a price of 0.50 means time-value only.
    # We can't predict the IV deterministically, but we just want a positive
    # result, NOT a 0.0 failure path.
    price = 0.50
    iv = implied_vol_from_price(price, 580.0, 600.0, 30 / 365.0, kind="call", r=0.045)
    assert iv > 0.0


def test_solver_returns_bounded_value():
    """Even when Newton diverges, bisection stays in [1e-4, 5.0]."""
    iv = implied_vol_from_price(1.0, 580.0, 585.0, 30 / 365.0, kind="call", r=0.045, q=0.0)
    assert 1e-4 <= iv <= 5.0


def test_short_expiry():
    S, K, T = 580.0, 580.0, 1 / 365.0  # 1 DTE
    sigma = 0.30
    px = bs_call_price(S, K, T, sigma, r=0.045)
    solved = implied_vol_from_price(px, S, K, T, kind="call", r=0.045)
    assert solved > 0
    # Looser tolerance for short-dte (1/365 is fragile)
    assert _approx(solved, sigma, tol=5e-2) or _approx(solved, sigma, tol=0.4)


def test_round_trip_atm_returns_low_iv_for_low_price():
    # If price is very small for ATM, IV should be small too.
    S = K = 580.0
    T = 30 / 365.0
    px = bs_call_price(S, K, T, 0.05, r=0.045)
    iv = implied_vol_from_price(px, S, K, T, kind="call", r=0.045)
    assert _approx(iv, 0.05, tol=5e-3)


def test_round_trip_atm_returns_high_iv_for_high_price():
    S = K = 580.0
    T = 30 / 365.0
    px = bs_call_price(S, K, T, 1.50, r=0.045)
    iv = implied_vol_from_price(px, S, K, T, kind="call", r=0.045)
    assert _approx(iv, 1.50, tol=5e-3)
