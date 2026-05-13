"""Black-Scholes pricing and Greeks for SPY options analytics.

All inputs in standard units: S (spot), K (strike), T (years to expiry),
r (risk-free rate, decimal), sigma (implied vol, decimal), q (dividend yield, decimal).
Option type: "C" or "P".
"""
from __future__ import annotations
import math
from typing import Literal
from scipy.stats import norm

OptType = Literal["C", "P"]


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return None, None
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S, K, T, r, sigma, opt: OptType, q: float = 0.0) -> float:
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if d1 is None:
        # Intrinsic value fallback
        if opt == "C":
            return max(S - K, 0.0)
        return max(K - S, 0.0)
    if opt == "C":
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def implied_vol(price, S, K, T, r, opt: OptType, q: float = 0.0,
                tol: float = 1e-5, max_iter: int = 60) -> float | None:
    """Newton-Raphson with bisection fallback. Returns None if no convergence."""
    if T <= 0 or price <= 0:
        return None
    # Initial guess
    sigma = 0.25
    for _ in range(max_iter):
        d1, d2 = _d1_d2(S, K, T, r, sigma, q)
        if d1 is None:
            sigma = 0.5
            continue
        theo = bs_price(S, K, T, r, sigma, opt, q)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if vega < 1e-8:
            break
        diff = theo - price
        if abs(diff) < tol:
            return max(sigma, 1e-4)
        sigma -= diff / vega
        if sigma <= 0 or sigma > 5:
            sigma = 0.5
    # Bisection fallback
    lo, hi = 1e-4, 5.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        p = bs_price(S, K, T, r, mid, opt, q)
        if p > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-5:
            return mid
    return None


def greeks(S, K, T, r, sigma, opt: OptType, q: float = 0.0) -> dict:
    """Return per-contract greeks. Standard scaling (per 1 unit). Caller decides
    whether to multiply by 100 (contract multiplier) and OI."""
    d1, d2 = _d1_d2(S, K, T, r, sigma, q)
    if d1 is None:
        return {k: 0.0 for k in ("delta", "gamma", "vega", "theta", "vanna", "charm", "vomma")}

    pdf_d1 = norm.pdf(d1)
    sqrtT = math.sqrt(T)

    if opt == "C":
        delta = math.exp(-q * T) * norm.cdf(d1)
    else:
        delta = math.exp(-q * T) * (norm.cdf(d1) - 1.0)

    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * sqrtT)
    vega = S * math.exp(-q * T) * pdf_d1 * sqrtT  # per 1.0 vol change
    # Theta per year (annualized)
    term1 = -(S * math.exp(-q * T) * pdf_d1 * sigma) / (2.0 * sqrtT)
    if opt == "C":
        term2 = -r * K * math.exp(-r * T) * norm.cdf(d2)
        term3 = q * S * math.exp(-q * T) * norm.cdf(d1)
        theta = term1 + term2 + term3
    else:
        term2 = r * K * math.exp(-r * T) * norm.cdf(-d2)
        term3 = -q * S * math.exp(-q * T) * norm.cdf(-d1)
        theta = term1 + term2 + term3
    theta_per_day = theta / 365.0

    # Vanna: dDelta/dVol = -e^(-qT) * phi(d1) * d2 / sigma
    vanna = -math.exp(-q * T) * pdf_d1 * d2 / sigma
    # Charm: dDelta/dt (per year)
    charm_num = 2.0 * (r - q) * T - d2 * sigma * sqrtT
    charm_den = 2.0 * T * sigma * sqrtT
    if opt == "C":
        charm = q * math.exp(-q * T) * norm.cdf(d1) - math.exp(-q * T) * pdf_d1 * (charm_num / charm_den)
    else:
        charm = -q * math.exp(-q * T) * norm.cdf(-d1) - math.exp(-q * T) * pdf_d1 * (charm_num / charm_den)
    charm_per_day = charm / 365.0
    # Vomma: dVega/dVol
    vomma = vega * d1 * d2 / sigma

    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega / 100.0,        # per 1 vol point (1%)
        "theta": theta_per_day,
        "vanna": vanna / 100.0,      # per 1 vol point
        "charm": charm_per_day,
        "vomma": vomma / 10000.0,    # per 1 vol point squared
    }
