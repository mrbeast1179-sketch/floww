"""
Almgren–Chriss & Kyle–Lambda domain primitives.

Pure-function mathematical kernel for optimal-execution cost modelling.

References
----------
Almgren, R. & Chriss, N. (2000). "Optimal Execution of Portfolio Transactions."
Journal of Risk, 3, 5-39.

Kyle, A.S. (1985). "Continuous Auctions and Insider Trading."
Econometrica, 53(6), 1315-1335.

Functions
---------
``compute_kappa(risk_aversion, sigma, eta)``
    Urgency:   ``κ = sqrt(λσ² / η)``.
``optimal_trajectory(total_shares, time_horizon, n_slices, kappa)``
    Closed-form Almgren–Chriss trading rate:
    ``x(t) = X · sinh(κ(T − t)) / sinh(κT)``.
``expected_cost_components(total_shares, time_horizon, sigma, spread,
                           kappa, gamma, risk_aversion)``
    ``(E[cost], perm_impact, timing_risk)`` decomposition.
``kyle_lambda_ols(price_changes, signed_volumes)``
    OLS estimator:   ``λ = Cov(Δp, SV) / Var(SV)`` (clipped to non-negative).
``kyle_impact(lambda_hat, order_size)``
    Linear price impact:   ``Δp = λ · Q``.
"""

from __future__ import annotations

import math

import numpy as np

# ----------------------------------------------------------------------
# Urgency parameter   κ = sqrt(λ · σ² / η)
# ----------------------------------------------------------------------

def compute_kappa(risk_aversion: float, sigma: float, eta: float) -> float:
    """Compute the Almgren–Chriss urgency parameter.

    ``κ = sqrt(λ · σ² / η)``   with guards for non-positive inputs.

    Parameters
    ----------
    risk_aversion : float
        Risk-aversion parameter ``λ ≥ 0``.
    sigma : float
        Volatility ``σ ≥ 0`` (per-second for service layer; raw units OK).
    eta : float
        Temporary-impact coefficient ``η > 0``.

    Returns
    -------
    float
        ``κ ≥ 0``. Returns ``0.0`` when any input is non-positive.
    """
    if risk_aversion <= 0.0 or sigma <= 0.0 or eta <= 0.0:
        return 0.0
    if math.isnan(risk_aversion) or math.isnan(sigma) or math.isnan(eta):
        return 0.0
    return math.sqrt(risk_aversion * (sigma ** 2) / eta)


# ----------------------------------------------------------------------
# Optimal trading trajectory   x(t) = X · sinh(κ(T − t)) / sinh(κT)
# ----------------------------------------------------------------------

def optimal_trajectory(
    total_shares: float,
    time_horizon: float,
    n_slices: int,
    kappa: float,
) -> list[float]:
    """Almgren–Chriss optimal trading trajectory.

    Closed-form trade rate at each evenly-spaced slice ``t_i = i · T / N``::

        x(t_i) = X · sinh(κ · (T − t_i)) / sinh(κ · T)

    The returned list sums to ``total_shares`` (renormalized after the
    closed-form evaluation to absorb floating-point drift).

    Parameters
    ----------
    total_shares : float
        Total shares ``X`` to execute.
    time_horizon : float
        Execution window ``T`` (in the same time unit as kappa).
    n_slices : int
        Number of slices ``N``.
    kappa : float
        Urgency κ from ``compute_kappa``.

    Returns
    -------
    list[float]
        Length-``n_slices`` trajectory of trade sizes per slice,
        monotonically decreasing in ``kappa`` for ``kappa > 0``.
    """
    if n_slices <= 0:
        return []
    if kappa < 1e-12 or time_horizon < 1e-12:
        # No urgency: even split.
        per = float(total_shares) / n_slices
        return [per] * n_slices

    kappa_T = kappa * time_horizon
    if kappa_T > 50.0:
        # sinh overflow: trade everything immediately.
        return [float(total_shares)] + [0.0] * (n_slices - 1)

    sinh_kT = math.sinh(kappa_T)
    traj: list[float] = []
    for i in range(n_slices):
        t = i * time_horizon / n_slices
        remaining = time_horizon - t
        x = total_shares * math.sinh(kappa * remaining) / sinh_kT
        traj.append(max(float(x), 0.0))

    s_total = sum(traj)
    if s_total > 0.0 and total_shares > 0.0:
        traj = [v * float(total_shares) / s_total for v in traj]
    return traj


# ----------------------------------------------------------------------
# Expected cost decomposition
#   perm   = γ · X² / 2
#   timing = (λ σ² X² / (2 κ)) · (coth(κT) − 1/(κT))
#   spread = spread · X / 2
#   E[cost] = perm + timing + spread
# ----------------------------------------------------------------------

def expected_cost_components(
    total_shares: float,
    time_horizon: float,
    sigma: float,
    spread: float,
    kappa: float,
    gamma: float,
    risk_aversion: float,
) -> tuple[float, float, float]:
    """Decompose expected execution cost into permanent + timing + spread.

    Parameters
    ----------
    total_shares : float
        Order size ``X``.
    time_horizon : float
        Execution window ``T``.
    sigma : float
        Volatility ``σ``.
    spread : float
        Half-spread (one side) ``s``.
    kappa : float
        Urgency ``κ``.
    gamma : float
        Permanent-impact coefficient ``γ``.
    risk_aversion : float
        Risk-aversion ``λ``.

    Returns
    -------
    (expected_cost, permanent_impact, timing_risk) : tuple[float, float, float]
        All three are non-negative for valid inputs.
    """
    perm_impact = gamma * (total_shares ** 2) / 2.0
    spread_cost = spread * total_shares / 2.0

    if kappa < 1e-12 or kappa * time_horizon > 50.0:
        timing_risk = 0.0
    else:
        coth = 1.0 / math.tanh(kappa * time_horizon)
        timing_risk = (
            (risk_aversion * (sigma ** 2) * (total_shares ** 2) / (2.0 * kappa))
            * (coth - 1.0 / (kappa * time_horizon))
        )

    expected_cost = perm_impact + max(timing_risk, 0.0) + spread_cost
    return expected_cost, perm_impact, max(timing_risk, 0.0)


# ----------------------------------------------------------------------
# Kyle's Lambda   λ = Cov(Δp, SV) / Var(SV)
# ----------------------------------------------------------------------

def kyle_lambda_ols(
    price_changes: np.ndarray | list[float],
    signed_volumes: np.ndarray | list[float],
) -> float:
    """Estimate Kyle's Lambda from rolling signed-volume price observations.

    Fits ``Δp_t = λ · SV_t + ε_t`` by OLS::

        λ̂ = Cov(Δp, SV) / Var(SV),   clipped to ≥ 0.

    Parameters
    ----------
    price_changes, signed_volumes : array-like of float
        Paired observations (same length).

    Returns
    -------
    float
        ``λ̂ ≥ 0``. Returns ``0.0`` when ``len < 5`` or ``Var(SV) < 1e-15``.
    """
    pc = np.asarray(price_changes, dtype=np.float64)
    sv = np.asarray(signed_volumes, dtype=np.float64)
    if pc.shape != sv.shape:
        raise ValueError("price_changes and signed_volumes must have the same shape")
    if pc.size < 5:
        return 0.0
    var_sv = float(np.var(sv))
    if var_sv < 1e-15:
        return 0.0
    if math.isnan(var_sv):
        return 0.0
    cov = float(np.cov(pc, sv)[0, 1])
    lam = cov / var_sv
    return max(lam, 0.0)


def kyle_impact(lambda_hat: float, order_size: float) -> float:
    """Linear price impact under Kyle's Lambda model.

    ``Δp = λ · Q``. Negative λ or negative Q are clipped to 0.

    Parameters
    ----------
    lambda_hat : float
        Kyle's Lambda ``λ ≥ 0``.
    order_size : float
        Signed order size ``Q`` (use magnitude for one-sided estimate).

    Returns
    -------
    float
        ``Δp ≥ 0``.
    """
    return max(lambda_hat, 0.0) * max(order_size, 0.0)
