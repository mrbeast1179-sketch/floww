"""
backend/domain/sabr.py
======================

Pure-function SABR (Stochastic Alpha Beta Rho) implied volatility primitives.

This is the ``domain`` half of the SABR stack: deterministic, stateless,
no I/O, no logging. The class-based wrapper ``SABRModel`` in
``backend/services/stochastic_vol.py`` orchestrates calibration (scipy.optimize)
and serialization on top of these primitives.

Mathematical model
------------------
SABR describes the joint evolution of forward ``F`` and stochastic volatility
``alpha`` under the forward measure:

    dF     = alpha * F^beta * dW1
    dalpha = nu    * alpha * dW2
    dW1 dW2 = rho * dt

The four SABR parameters map to observable smile features:

    alpha -- overall vol level   (sets ATM vol)
    beta  -- backbone type       (0=normal, 0.5=CIR-like, 1=lognormal)
    rho   -- skew/sign correlation (-1..1, typically negative for equities)
    nu    -- vol-of-vol          (sets smile curvature / kurtosis)

The Hagan et al. (2002) asymptotic expansion produces a closed-form implied
vol approximation in either the **normal (Bachelier)** or **lognormal (Black)**
vol convention.  Use lognormal for equity options, normal for low-rate
fixed-income / swapped normal vol quotes.

References
----------
  * Hagan, P., Kumar, D., Lesniewski, A., & Woodward, D. (2002).
    "Managing Smile Risk." Wilmott Magazine.  -- the closed-form formulas used
    here are from this paper.
  * Hagan, P. & Woodward, D. (1999). "Equivalent Black Volatilities."
    -- early heuristic corrections for short-maturity regimes.
  * West, G. (2005). "Correction to Hagan et al." -- the well-known
    first-order correction (zeta / x_zeta) used below.

Sign conventions
----------------
  rho < 0 means *negative correlation* between spot and vol, which gives the
  classic left-skewed equity smile (OTM puts expensive, OTM calls cheap).
  The formulas below preserve this convention automatically.
"""

from __future__ import annotations

import math


def _sabr_z_x(alpha: float, beta: float, rho: float, nu: float,
              F: float, K: float) -> tuple[float, float]:
    """
    Compute the two scalar intermediate quantities ``z`` and ``x(z)`` used in
    the Hagan formulas.

        z = (nu / alpha) * (F K)^((1 - beta) / 2) * log(F / K)
        x(z) = log((sqrt(1 - 2 rho z + z^2) + z - rho) / (1 - rho))

    Both quantities degenerate to 0 at the ATM (F == K) and are excluded from
    the closed-form approximation there; the ATM-specific branch in the public
    functions captures the limit.

    Returns
    -------
    (z, x_z) : tuple[float, float]
        Both will be 0.0 when ``F == K`` or ``alpha == 0`` or ``K == 0``.
    """
    if F <= 0.0 or K <= 0.0 or alpha <= 0.0:
        return 0.0, 0.0
    if abs(F - K) < 1e-12:
        return 0.0, 0.0

    log_fk = math.log(F / K)
    fk_mid = (F * K) ** ((1.0 - beta) / 2.0)
    z = (nu / alpha) * fk_mid * log_fk

    # West (2005) expansion: x(z) = log((sqrt(1-2ρz+z^2) + z - ρ) / (1 - ρ))
    # Numerically fragile when |rho| ~ 1 or z large.
    denom = 1.0 - rho
    if abs(denom) < 1e-12:
        # As rho -> 1 the formula collapses; use the asymptotic form.
        # For numerically robust evaluation, fall back to a Taylor expansion
        # around z=0: x(z) ~ z + (rho/3) z^3 + ... -- first-order is enough
        # given guard above.
        x_z = z
    else:
        inner = math.sqrt(max(1.0 - 2.0 * rho * z + z * z, 1e-300))
        x_z = math.log((inner + z - rho) / denom)
    return z, x_z


def _sabr_atm_lognormal(alpha: float, beta: float, rho: float, nu: float,
                         F: float, T: float) -> float:
    """Closed-form SABR ATM lognormal (Black) implied vol."""
    # F^(1-beta)
    f1mb = F ** (1.0 - beta)
    f2m2b = f1mb * f1mb
    term_bracket = (
        (1.0 - beta) ** 2 * alpha ** 2 / (24.0 * f2m2b)
        + rho * beta * nu * alpha / (4.0 * f1mb)
        + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
    )
    return (alpha / f1mb) * (1.0 + term_bracket * T)


def _sabr_atm_normal(alpha: float, beta: float, rho: float, nu: float,
                      F: float, T: float) -> float:
    """Closed-form SABR ATM normal (Bachelier) implied vol."""
    fb = F ** beta
    f2b = fb * fb
    term_bracket = (
        (beta - 1.0) ** 2 * alpha ** 2 / (24.0 * f2b)
        + rho * beta * nu * alpha / (4.0 * fb)
        + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
    )
    return (alpha / fb) * (1.0 + term_bracket * T)


def hagan_implied_lognormal_vol(
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    F: float,
    K: float,
    T: float,
) -> float:
    """
    Hagan et al. (2002) implied **lognormal** (Black) volatility under SABR.

    Parameters
    ----------
    alpha : float
        Initial volatility level (sigma_0). Typical equity range [0.05, 0.6].
    beta : float
        CEV elasticity in [0, 1].  0 = normal backbone, 0.5 = CIR-like,
        1 = lognormal backbone (most equity options use beta in [0.5, 1]).
    rho : float
        Spot-vol correlation in (-1, 1).  Negative rho gives left-skewed smile.
    nu : float
        Vol-of-vol, in (0, 2] typical.  Higher nu produces more smile curvature.
    F : float
        Forward price (or ATM spot when no carry).
    K : float
        Strike.
    T : float
        Time to expiry in years.

    Returns
    -------
    float
        Implied Black (lognormal) volatility.  Returns 0.0 for any of the
        invalid input conditions: ``F <= 0``, ``K <= 0``, ``T <= 0``,
        ``alpha <= 0``, ``nu <= 0``, ``beta < 0``, ``|rho| >= 1``.

    Notes
    -----
    Hand-verified pin (for unit tests):

    >>> round(
    ...     hagan_implied_lognormal_vol(
    ...         alpha=0.2, beta=1.0, rho=-0.3, nu=0.4,
    ...         F=100.0, K=100.0, T=0.25
    ...     ), 6,
    ... )
    0.200277
    """
    # Guard clauses (silent at the math layer).
    if F <= 0.0 or K <= 0.0 or T <= 0.0:
        return 0.0
    if alpha <= 0.0 or nu <= 0.0 or beta < 0.0 or beta > 1.0:
        return 0.0
    if abs(rho) >= 1.0:
        return 0.0

    try:
        # ATM closed-form branch (Hagan limit as K -> F).
        if abs(F - K) < 1e-12:
            return _sabr_atm_lognormal(alpha, beta, rho, nu, F, T)

        z, x_z = _sabr_z_x(alpha, beta, rho, nu, F, K)
        if abs(x_z) < 1e-12:
            # Shouldn't happen given F != K branch above; safeguard only.
            return _sabr_atm_lognormal(alpha, beta, rho, nu, F, T)

        log_fk = math.log(F / K)
        fk_pow = (F * K) ** ((1.0 - beta) / 2.0)
        # Geometric mean prefactor with West (2005) higher-order correction:
        #   (FK)^((1-b)/2) * (1 + (1-b)^2/24 * log^2 + (1-b)^4/1920 * log^4)
        geom = (
            fk_pow
            * (1.0
               + (1.0 - beta) ** 2 / 24.0 * log_fk ** 2
               + (1.0 - beta) ** 4 / 1920.0 * log_fk ** 4)
        )

        denom_bracket = (
            (1.0 - beta) ** 2 * alpha ** 2 / (24.0 * fk_pow ** 2)
            + rho * beta * nu * alpha / (4.0 * fk_pow)
            + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
        )

        sigma_b = (alpha / geom) * (z / x_z) * (1.0 + denom_bracket * T)

        if math.isnan(sigma_b) or math.isinf(sigma_b):
            return 0.0
        return max(sigma_b, 0.0)
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.0


def hagan_implied_normal_vol(
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    F: float,
    K: float,
    T: float,
) -> float:
    """
    Hagan et al. (2002) implied **normal** (Bachelier) volatility under SABR.

    Same parameter conventions as :func:`hagan_implied_lognormal_vol`, but
    the output convention is normal (Bachelier) which is used in fixed-income
    swapped-vol products and Asian / quanto quotes.

    Notes
    -----
    Hand-verified pin (for unit tests):

    >>> round(
    ...     hagan_implied_normal_vol(
    ...         alpha=0.2, beta=0.5, rho=-0.3, nu=0.4,
    ...         F=100.0, K=100.0, T=0.25
    ...     ), 6,
    ... )
    0.020056
    """
    # Guard clauses.
    if F <= 0.0 or K <= 0.0 or T <= 0.0:
        return 0.0
    if alpha <= 0.0 or nu <= 0.0 or beta < 0.0 or beta > 1.0:
        return 0.0
    if abs(rho) >= 1.0:
        return 0.0

    try:
        if abs(F - K) < 1e-12:
            return _sabr_atm_normal(alpha, beta, rho, nu, F, T)

        z, x_z = _sabr_z_x(alpha, beta, rho, nu, F, K)
        if abs(x_z) < 1e-12:
            return _sabr_atm_normal(alpha, beta, rho, nu, F, T)

        log_fk = math.log(F / K)
        fk_pow = (F * K) ** (beta / 2.0)
        # Beta-symmetric prefactor (normal convention uses beta/2 not (1-beta)/2).
        geom = (
            fk_pow
            * (1.0
               + (1.0 - beta) ** 2 / 24.0 * log_fk ** 2
               + (1.0 - beta) ** 4 / 1920.0 * log_fk ** 4)
        )

        denom_bracket = (
            (1.0 - beta) ** 2 * alpha ** 2 / (24.0 * fk_pow ** 2)
            + rho * beta * nu * alpha / (4.0 * fk_pow)
            + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
        )

        sigma_n = (alpha / geom) * (z / x_z) * (1.0 + denom_bracket * T)

        if math.isnan(sigma_n) or math.isinf(sigma_n):
            return 0.0
        return max(sigma_n, 0.0)
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.0


def hagan_implied_vol(
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
    F: float,
    K: float,
    T: float,
    *,
    is_normal: bool = False,
) -> float:
    """
    Convenience multiplexer around :func:`hagan_implied_lognormal_vol` and
    :func:`hagan_implied_normal_vol`. Choose ``is_normal=True`` for Bachelier
    (e.g. rates / fixed-income), ``is_normal=False`` (default) for Black
    (e.g. equity options).
    """
    if is_normal:
        return hagan_implied_normal_vol(alpha, beta, rho, nu, F, K, T)
    return hagan_implied_lognormal_vol(alpha, beta, rho, nu, F, K, T)


__all__ = [
    "hagan_implied_normal_vol",
    "hagan_implied_lognormal_vol",
    "hagan_implied_vol",
]
