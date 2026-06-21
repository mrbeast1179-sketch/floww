"""
Black-Scholes Greeks calculations.
Shared between server.py and portfolio.py to avoid circular imports.

Dollar-GEX Convention (PLATFORM-WIDE)
=====================================
The ``GEX_per_contract`` helper below produces the industry-standard
"Dollar Gamma Exposure" value (US dollars of stock dealers must trade to
remain delta-neutral for a 1% upward spot move):

    GEX_per_contract = gamma * OI * CONTRACT_MULTIPLIER * spot^2 * DOLLAR_MOVE_CONVENTION

with the *SqueezeMetrics / SpotGamma / Perfiliev* constants:

    CONTRACT_MULTIPLIER  = 100.0      # shares per equity option contract
    DOLLAR_MOVE_CONVENTION = 0.01     # 1% spot move

References (open-access):
  - Perfiliev, S. (2022). "How to Calculate Gamma Exposure (GEX) and Zero
    Gamma Level." https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/
  - SqueezeMetrics / SpotGamma community implementations (the standard
    formula used by every retail GEX dashboard we cross-check against).
  - TradingView community-authored GEX scripts.

Second-order dollar exposures follow the same 1%-move convention but use
a linear (rather than quadratic) spot factor because the underlying greek's
unit [1/spot] for vanna/charm/vomma cancels one of the spot factors:

    VEX   = vanna  * OI * MULTIPLIER * spot    * 0.01   (per 1% move)
    charm = charm  * OI * MULTIPLIER * spot    * 0.01   (per 1% move)
    vomma = vomma  * OI * MULTIPLIER                 (per unit-σ; no 0.01)
    vega  = vega   * OI * MULTIPLIER                 (per unit-σ; no 0.01)

CRITICAL: This display/UI scale is **distinct from** the *frozen ML-feature*
scale used in ``services/gex_history.py`` (which uses a *single* spot factor
and fixed ``iv=0.20`` for model-input stability). The two scales differ by
exactly a factor of ``spot`` and are pinned by
``tests/services/test_gex_aggregator_oracle.py``.

If you change any of these constants, ALSO re-read the platform-wide audit
``docs/superpowers/specs/2026-06-13-gex-gamma-correctness-audit-design.md``
and run ``backend/tests/test_dollar_gex_convention.py`` to confirm parity
with the published SqueezeMetrics/SpotGamma band (SPY at $580 typically
$3B–$15B net in positive-gamma regimes; -$5B to -$15B in negative).
"""

import logging
import math
import sys

from scipy.stats import norm

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Platform-wide GEX/VE constants.  See module docstring for citations.
# ------------------------------------------------------------------
CONTRACT_MULTIPLIER: float = 100.0
DOLLAR_MOVE_CONVENTION: float = 0.01


def dollar_gex_per_contract(gamma: float, oi: float, spot: float) -> float:
    """Dollar Gamma Exposure per contract (industry-standard 1%-move convention).

    Returns ``gamma * OI * 100 * spot^2 * 0.01`` — the dollar amount of
    underlying stock a dealer must trade to remain delta-hedged if spot
    moves 1%. Matches SqueezeMetrics / SpotGamma / Perfiliev (2022).

    Sign convention: caller multiplies by ``+1`` for calls and ``-1`` for
    puts (dealer-shorts-what-customers-long ⇒ calls positive, puts negative).
    """
    return gamma * oi * CONTRACT_MULTIPLIER * spot * spot * DOLLAR_MOVE_CONVENTION


def dollar_vex_per_contract(vanna: float, oi: float, spot: float) -> float:
    """Dollar Vanna Exposure per contract (1%-move convention).

    Vanna has units ``[1/spot]`` so the formula is linear in spot (with
    the 0.01 convention still representing the 1% move). Matches the
    canonical VEX calculation used across ``backend``.
    """
    return vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION


def dollar_charm_per_contract(charm: float, oi: float, spot: float) -> float:
    """Dollar Charm Exposure per contract (1%-move convention)."""
    return charm * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION


def dollar_vomma_per_contract(vomma: float, oi: float) -> float:
    """Dollar Vomma Exposure per contract (per unit-σ; no 0.01 factor)."""
    return vomma * oi * CONTRACT_MULTIPLIER


def dollar_vega_per_contract(vega: float, oi: float) -> float:
    """Dollar Vega Exposure per contract (per unit-σ; no 0.01 factor)."""
    return vega * oi * CONTRACT_MULTIPLIER


def _mask_zero(exc: Exception) -> float:
    """Return 0.0 for an unexpected numerical error, but log it so the silent
    failure is observable instead of vanishing (B4 audit 2026-06-13).

    Guard-clause zeros (invalid/expired inputs) bypass this helper and stay
    silent -- only errors caught by ``except`` are surfaced. The 0.0 return is
    preserved so every caller (including the frozen ML-feature path) sees
    identical values; this adds observability, not a behavior change.
    """
    fn = sys._getframe(1).f_code.co_name
    log.warning("%s masked error -> 0.0: %s", fn, exc)
    return 0.0


def bs_gamma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_delta(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if kind == "call":
            return math.exp(-q * T) * norm.cdf(d1)
        else:
            return math.exp(-q * T) * (norm.cdf(d1) - 1)
    except Exception as exc:
        return _mask_zero(exc)


def bs_vanna(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        result = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_charm(S, K, T, sigma, q=0.0, kind="call", r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        charm = math.exp(-q * T) * (q * cdf_d1 - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm = math.exp(-q * T) * (-q * (1 - cdf_d1) - pdf_d1 * (2 * (r - q) * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if math.isnan(charm) or math.isinf(charm):
            return 0.0
        return charm
    except Exception as exc:
        return _mask_zero(exc)


def bs_vomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        result = vega * d1 * d2 / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_zomma(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        result = gamma * (d1 * d2 - 1) / sigma
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_vega(S, K, T, sigma, q=0.0, r=0.05):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if math.isnan(result) or math.isinf(result):
            return 0.0
        return result
    except Exception as exc:
        return _mask_zero(exc)


def bs_call_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes call option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        if math.isnan(price) or math.isinf(price):
            return 0.0
        return price
    except Exception as exc:
        return _mask_zero(exc)


def bs_put_price(S, K, T, sigma, r=0.045, q=0.0):
    """Black-Scholes put option price."""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)
        if math.isnan(price) or math.isinf(price):
            return 0.0
        return price
    except Exception as exc:
        return _mask_zero(exc)
