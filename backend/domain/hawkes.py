"""
backend/domain/hawkes.py
========================

Pure-function Hawkes process primitives for self-exciting point processes
on market microstructure event streams (trade arrivals, quote updates,
order submissions).

This is the ``domain`` half of the Hawkes stack: deterministic, stateless,
no I/O. The class-based wrapper ``HawkesProcess`` in
``backend/services/hawkes_process.py`` orchestrates stateful workflows
(MLE fitting, multi-step simulation, JSON serialization) on top of
these primitives.

Mathematical model
------------------
The univariate exponential-kernel Hawkes process has conditional intensity

    lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))

with three canonical parameters:

    mu     -- baseline intensity (events per unit time).  Must be > 0.
    alpha  -- jump size / excitation magnitude per past event. >= 0.
    beta   -- decay rate of the excitation kernel. > 0.

A useful derived quantity is the **branching ratio**

    n = alpha / beta

which is the expected number of *child* events per *parent* event. For
finite-mean stationarity we need n < 1; when n >= 1 the process can
explode (not realistic for real markets, but a numerical hazard in
simulation if a fitted alpha/beta from sparse data overshoots).

Stationary mean intensity:

    E[lambda] = mu / (1 - n) = mu * beta / (beta - alpha)
                                              (only defined when alpha < beta)

Closed-form log-likelihood (Daley & Vere-Jones, 2003; Laub et al., 2015):

    L = sum_i log(lambda(t_i)) - integral_{t_0}^{T} lambda(s) ds
      = sum_i log(lambda(t_i))
        - mu * (T - t_0)
        - (alpha / beta) * sum_i [1 - exp(-beta * (T - t_i))]

where ``t_0`` is the first observed event time and ``T = t_N`` is the last.
The integral term has *no* closed form for the power-law kernel; we
implement only the exponential-kernel case here.

Simulation uses Ogata's (1981) thinning algorithm: generate candidate
events from a homogeneous Poisson process with rate
``lambda_star >= sup_{t in [0, T]} lambda(t)``, then accept each
candidate with probability ``lambda(t_candidate) / lambda_star``.

References
----------
  * Hawkes, A.G. (1971). "Spectra of some self-exciting and mutually
    exciting point processes." *Biometrika*.
  * Daley, D.J. & Vere-Jones, D. (2003). *An Introduction to the Theory
    of Point Processes, Vol. 1*.  Springer.
  * Laub, P.J., Taimre, T., & Pollett, P.K. (2015). "Hawkes processes."
    *arXiv:1507.02822*.
  * Ogata, Y. (1981). "On Lewis' simulation method for point processes."
    *IEEE Transactions on Information Theory*.
  * Bacry, E., Mastromatteo, I., & Muzy, J.F. (2015). "Hawkes processes
    in finance." *Market Microstructure and Liquidity*.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize

# ------------------------------------------------------------------- #
# Intensity
# ------------------------------------------------------------------- #


def exponential_intensity(
    t: float,
    event_times: np.ndarray | list[float],
    mu: float,
    alpha: float,
    beta: float,
) -> float:
    r"""
    Compute the conditional intensity ``lambda(t)`` of an exponential-kernel
    Hawkes process at time ``t`` given past event times.

        lambda(t) = mu + alpha * sum_{t_i < t} exp(-beta * (t - t_i))

    Parameters
    ----------
    t : float
        Query point in time (same units as ``event_times``).
    event_times : array-like of float
        Past event times.  Will be sorted and pre-events filtered; the input
        itself is *not* mutated.
    mu : float
        Baseline intensity.  Must be > 0.
    alpha : float
        Excitation magnitude.  Must be >= 0.
    beta : float
        Decay rate.  Must be > 0.

    Returns
    -------
    float
        Non-negative intensity at ``t``.  Returns ``mu`` (the floor) if
        ``event_times`` is empty or contains no events before ``t``.  Guard
        clauses return ``0.0`` for invalid parameter combinations.

    Notes
    -----
    Hand-verified pin (for unit tests):

    >>> round(
    ...     exponential_intensity(
    ...         t=10.0,
    ...         event_times=[1.0, 3.0, 7.0],
    ...         mu=0.5, alpha=0.8, beta=1.5,
    ...     ), 6,
    ... )
    0.508910
    """
    # Guard clauses.
    if mu <= 0.0 or beta <= 0.0 or alpha < 0.0:
        return 0.0

    if event_times is None:
        return mu

    arr = np.asarray(event_times, dtype=np.float64).ravel()
    if arr.size == 0:
        return mu

    past = arr[arr < t]
    if past.size == 0:
        return mu

    try:
        dt = t - past
        excitation = float(alpha * np.sum(np.exp(-beta * dt)))
        if math.isnan(excitation) or math.isinf(excitation):
            return mu
        return mu + excitation
    except (ValueError, FloatingPointError):
        return mu


# ------------------------------------------------------------------- #
# Log-likelihood
# ------------------------------------------------------------------- #


def exponential_log_likelihood(
    event_times: np.ndarray | list[float],
    mu: float,
    alpha: float,
    beta: float,
) -> float:
    r"""
    Closed-form exponential-kernel Hawkes log-likelihood.

        L = sum_i log(lambda(t_i)) - integral_{t_0}^{T} lambda(s) ds
          = sum_i log(lambda(t_i))
            - mu * (T - t_0)
            - (alpha / beta) * sum_i [1 - exp(-beta * (T - t_i))]

    Parameters
    ----------
    event_times : array-like of float, length >= 2
        Sorted or unsorted event times; will be sorted internally.
    mu : float
        Baseline intensity.  Must be > 0.
    alpha : float
        Excitation magnitude.  Must be >= 0.
    beta : float
        Decay rate.  Must be > 0.

    Returns
    -------
    float
        Log-likelihood value (negative if model is poor).  Returns ``-inf``
        for invalid inputs (mu/beta <= 0; alpha < 0) or fewer than 2 events.

    Notes
    -----
    Hand-verified pin (for unit tests):

    >>> round(
    ...     exponential_log_likelihood(
    ...         event_times=[1.0, 3.0, 7.0],
    ...         mu=0.5, alpha=0.8, beta=1.5,
    ...     ), 4,
    ... )
    -6.0639
    """
    if mu <= 0.0 or beta <= 0.0 or alpha < 0.0:
        return -math.inf

    arr = np.sort(np.asarray(event_times, dtype=np.float64).ravel())
    if arr.size < 2:
        return -math.inf

    try:
        # sum_i log(lambda(t_i))
        log_lams = np.empty(arr.size, dtype=np.float64)
        for i, ti in enumerate(arr):
            lam = exponential_intensity(ti, arr[:i], mu, alpha, beta)
            log_lams[i] = math.log(max(lam, 1e-300))
        sum_log = float(np.sum(log_lams))

        # integral_{t_0}^{T} lambda(s) ds, closed form for exp kernel
        t0 = arr[0]
        T = arr[-1]
        integral = (
            mu * (T - t0)
            + (alpha / beta) * float(np.sum(1.0 - np.exp(-beta * (T - arr))))
        )

        ll = sum_log - integral
        if math.isnan(ll) or math.isinf(ll):
            return -math.inf
        return ll
    except (ValueError, FloatingPointError):
        return -math.inf


# ------------------------------------------------------------------- #
# Derived quantities
# ------------------------------------------------------------------- #


def hawkes_branching_ratio(alpha: float, beta: float) -> float:
    r"""
    Branching ratio ``n = alpha / beta``.

    For finite-mean stationarity of the exponential-kernel Hawkes process
    we require ``n < 1``.  Returns 0.0 for ``beta <= 0``.
    """
    if beta <= 0.0:
        return 0.0
    return alpha / beta


def hawkes_stationary_intensity(mu: float, alpha: float, beta: float) -> float:
    r"""
    Stationary mean intensity for an exponential-kernel Hawkes process:

        E[lambda] = mu / (1 - alpha/beta) = mu * beta / (beta - alpha)

    Only finite when the branching ratio is strictly less than 1; otherwise
    the process is non-stationary (explodes).  Returns ``+inf`` as a sentinel
    in that case.

    Parameters
    ----------
    mu : float
        Baseline intensity > 0.
    alpha : float
        Excitation magnitude >= 0.
    beta : float
        Decay rate > 0.

    Returns
    -------
    float
        Stationary mean intensity, or ``+inf`` if ``alpha >= beta``.
    """
    if mu <= 0.0 or beta <= 0.0 or alpha < 0.0:
        return 0.0
    n = alpha / beta
    if n >= 1.0:
        return math.inf
    return mu / (1.0 - n)


# ------------------------------------------------------------------- #
# Simulation (Ogata's thinning)
# ------------------------------------------------------------------- #


def simulate_hawkes_ogata(
    T: float,
    mu: float,
    alpha: float,
    beta: float,
    *,
    n_max: int = 1000,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    r"""
    Simulate exponential-kernel Hawkes event times on ``[0, T]`` using
    Ogata's (1981) thinning algorithm.

    Algorithm:
      1. Pick a homogeneous Poisson rate ``lambda_star`` that dominates
         ``lambda(t)`` on ``[0, T]``.  We use the conservative estimate
         ``lambda_star = mu + alpha * n_max / beta``.
      2. Draw inter-arrival times ``w`` from ``Exp(lambda_star)``.
      3. At each candidate time ``t``, accept with probability
         ``lambda(t) / lambda_star``.

    Parameters
    ----------
    T : float
        Simulation horizon.  Must be > 0.
    mu : float
        Baseline intensity > 0.
    alpha : float
        Excitation >= 0.
    beta : float
        Decay rate > 0.
    n_max : int
        Safety upper bound on the event count.  Default 1000.
    rng : numpy.random.Generator, optional
        Random number generator for determinism.  If ``None``, a fresh
        ``np.random.default_rng()`` is used.

    Returns
    -------
    np.ndarray
        Sorted event times in ``[0, T]``.  Empty array for invalid inputs.
    """
    if T <= 0.0 or mu <= 0.0 or beta <= 0.0 or alpha < 0.0:
        return np.array([], dtype=np.float64)

    if rng is None:
        rng = np.random.default_rng()

    if alpha == 0.0:
        # Degenerate case: pure homogeneous Poisson process.
        return _homogeneous_poisson(T, mu, n_max, rng)

    lambda_star = max(mu + alpha * n_max / beta, mu)
    # Budget = λ★·T (expected thinning iters + 3× headroom); floor n_max·50
    # prevents the small-T regime from under-budgeting on bursty streams.
    max_iterations = max(n_max * 50, int(lambda_star * T * 3.0))
    events: list[float] = []
    t = 0.0
    iterations = 0

    try:
        arr_buf = np.empty(0, dtype=np.float64)
        while t < T and len(events) < n_max and iterations < max_iterations:
            iterations += 1
            w = rng.exponential(1.0 / lambda_star)
            t += w
            if t >= T:
                break
            if events:
                arr_buf[:0] = 0  # cheap no-op; just keeps the buffer live
                arr_buf = np.array(events, dtype=np.float64)
            lam_t = exponential_intensity(t, arr_buf, mu, alpha, beta)
            u = rng.uniform(0.0, 1.0)
            if u <= lam_t / lambda_star:
                events.append(t)
        # DEBUG-ONLY (`assert` is skipped under ``python -O``): flag silent
        # early exit on iteration-budget exhaustion so downstream analyses
        # never silently consume a truncated trace.
        assert t >= T or len(events) >= n_max, (
            f"simulate_hawkes_ogata exited early: "
            f"t={t:.4f}<T={T:.4f}, len(events)={len(events)}<n_max={n_max}, "
            f"iterations={iterations}>=max_iterations={max_iterations}"
        )
        return np.sort(np.asarray(events, dtype=np.float64))
    except (ValueError, FloatingPointError):
        return np.sort(np.asarray(events, dtype=np.float64))


def _homogeneous_poisson(
    T: float,
    rate: float,
    n_max: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Private helper: simulate a homogeneous Poisson process on [0, T]."""
    if T <= 0.0 or rate <= 0.0:
        return np.array([], dtype=np.float64)
    events: list[float] = []
    t = 0.0
    for _ in range(n_max * 20):
        w = rng.exponential(1.0 / rate)
        t += w
        if t >= T:
            break
        events.append(t)
    return np.asarray(events, dtype=np.float64)


# ------------------------------------------------------------------- #
# Maximum Likelihood Estimation (deterministic wrapper around scipy.optimize)
# ------------------------------------------------------------------- #


def mle_exponential_hawkes(
    event_times: np.ndarray | list[float],
    mu0: float = 1.0,
    alpha0: float = 0.5,
    beta0: float = 1.0,
    *,
    max_iter: int = 200,
    ftol: float = 1e-9,
) -> dict[str, float]:
    r"""
    Fit exponential-kernel Hawkes parameters via Maximum Likelihood Estimation.

    Uses scipy.optimize.minimize with L-BFGS-B over ``(mu, alpha, beta)``,
    maximizing the closed-form log-likelihood in
    :func:`exponential_log_likelihood`.

    Parameters
    ----------
    event_times : array-like of float, length >= 2
        Observed event times.
    mu0, alpha0, beta0 : float
        Starting values for L-BFGS-B (default sensible for unit-rate streams).
    max_iter : int
        Maximum number of optimizer iterations.
    ftol : float
        Convergence tolerance on the objective.

    Returns
    -------
    dict with keys:
        'mu', 'alpha', 'beta' : float   -- fitted parameter values
        'log_likelihood'      : float   -- final log-likelihood value
        'branching_ratio'     : float   -- alpha / beta
        'n_events'            : int     -- number of events seen
        'T'                   : float   -- last event time - first event time
        'converged'           : bool    -- whether the optimizer succeeded

    Notes
    -----
    The optimizer is bounded (``mu >= 1e-8``, ``alpha >= 0``, ``beta >= 1e-8``).
    Convergence is not guaranteed for very sparse / noisy data.
    """
    arr = np.sort(np.asarray(event_times, dtype=np.float64).ravel())
    n = arr.size
    out: dict[str, Any] = {
        "mu": float(mu0),
        "alpha": float(alpha0),
        "beta": float(beta0),
        "log_likelihood": -math.inf,
        "branching_ratio": float(alpha0 / beta0) if beta0 > 0 else 0.0,
        "n_events": int(n),
        "T": float(arr[-1] - arr[0]) if n >= 2 else 0.0,
        "converged": False,
    }
    if n < 2:
        return out

    def _neg_ll(params: np.ndarray) -> float:
        mu, alpha, beta = params
        ll = exponential_log_likelihood(arr, mu, alpha, beta)
        # scipy minimises; convert to large positive on invalid.
        if math.isinf(ll) or math.isnan(ll):
            return 1e15
        return -ll

    x0 = np.array(
        [
            max(mu0, 1e-6),
            max(alpha0, 1e-6),
            max(beta0, 1e-6),
        ],
        dtype=np.float64,
    )
    bounds = [(1e-8, None), (0.0, None), (1e-8, None)]

    try:
        result = minimize(
            _neg_ll,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": max_iter, "ftol": ftol},
        )
        mu_fit, alpha_fit, beta_fit = result.x
        out["mu"] = float(mu_fit)
        out["alpha"] = float(alpha_fit)
        out["beta"] = float(beta_fit)
        out["log_likelihood"] = float(-result.fun)
        out["branching_ratio"] = float(alpha_fit / beta_fit) if beta_fit > 0 else 0.0
        out["converged"] = bool(result.success)
    except (ValueError, FloatingPointError):
        pass

    return out


# ------------------------------------------------------------------- #
# Method-of-Moments Estimation (deterministic, no scipy.optimize)
# ------------------------------------------------------------------- #


def fit_exponential_hawkes_method_of_moments(
    event_times: np.ndarray | list[float],
    T: float | None = None,
) -> dict[str, Any]:
    r"""
    Deterministic Method-of-Moments estimator for exponential-kernel
    Hawkes parameters.  Closed-form; does NOT call any
    :mod:`scipy.optimize` routine.  Replaces the L-BFGS-B MLE for CI
    and smoke-test use cases where the optimizer's local-optimum
    behaviour causes brittleness.

    Algorithm
    ---------
    Part A -- Branching ratio from the bin-count Fano factor
        Bin the observation window into ``K = max(20, N // 10)``
        equal-width bins; compute the Fano factor ``F = Var(N_k) / E[N_k]``.
        For the exponential-kernel Hawkes process, ``F = 1 + eta``
        (Hawkes & Oakes, 1974), so ``eta_hat = max(0, F - 1)``.

    Part B -- Decay rate from sample-ACF log-linear decay
        Compute the empirical autocorrelation of bin counts at lags
        ``k = 1 .. L`` where ``L = min(10, K - 1)``.  Filter to lags
        where the ACF is strictly positive.  Log-linear regression

            log(ACF_k) ~ intercept - beta * (k * delta_t)

        yields slope -> ``-beta_hat`` (no scipy.optimize -- closed-form
        OLS or :func:`numpy.polyfit`).  Beta is bounded below by 1e-4.
        If the fitted slope is non-negative (pathological -- ACF rising
        instead of decaying), we fall back to ``beta = 1.0`` and set
        ``beta_from_acf_recovered = False`` so callers can detect the
        silent fallback.

    Part C -- Baseline intensity from total event rate
        The empirical rate ``N/T`` approaches the *total* stationary
        intensity ``mu / (1 - eta)``.  Solve for ``mu``:

            mu_hat = (N / T) * (1 - eta_hat)

    Part D -- Excitation magnitude
        From the branching-ratio identity:

            alpha_hat = eta_hat * beta_hat

    Part E -- Stationarity clipping
        If the variance-derived estimator overshoots 1 (``eta_hat >= 1``),
        clip to ``0.95`` so the fitted process remains subcritical.

    Part F -- Log-likelihood cross-check
        Evaluate the closed-form ``exponential_log_likelihood`` at the
        fitted parameters as a diagnostic.  Does NOT drive the fit.

    Returns
    -------
    dict with keys:
        ``mu``, ``alpha``, ``beta`` : float -- fitted parameters
        ``log_likelihood``         : float -- closed-form LL at fit
        ``branching_ratio``        : float -- ``alpha / beta``
        ``n_events``               : int   -- number of events seen
        ``T``                      : float -- observation window length
        ``converged``              : bool  -- True iff N >= 2 and T > 0
        ``method``                 : str   -- always ``"method_of_moments"``
        ``eta_fano``               : float -- raw ``F - 1`` estimator
        ``beta_from_acf_slope``    : float -- ACF-recovery value
                                                (== ``beta`` on success)
        ``beta_from_acf_recovered``: bool   -- True iff log-ACF
                                                regression succeeded

    Notes
    -----
    Pure function of the input array.  Reproducible to floating-point
    precision given the same observations.  No random state, no
    iterative optimizer, no local-optimum hazard.

    Why not Kullback-Leibler?
        KL divergence was considered as a goodness-of-fit diagnostic
        for inter-arrival times, but rejected because the Hawkes
        inter-arrival distribution is non-exponential and admits no
        closed form.  Closed-form Method-of-Moments is preferred for
        CI determinism.

    Accuracy caveat
        Accurate parameter recovery requires N >> 1/eta events and bins
        narrower than 1/beta.  Under finite-burst moderate-eta samples
        the bin-count Fano factor saturates the stationarity clip
        (1 - eta -> 0), causing mu_hat = (N/T) * (1 - eta) to
        under-estimate mu by up to 100x.  For tight recovery on bursty
        streams, prefer a Cox-Isham inter-arrival IDI estimator
        (forthcoming).  This estimator's contract is correctness
        invariants (subcritical, finite, positive, alpha = eta * beta),
        NOT parameter recovery.
    """
    arr = np.sort(np.asarray(event_times, dtype=np.float64).ravel())
    n = arr.size

    T_observed = float(T) if T is not None else (
        float(arr[-1] - arr[0]) if n >= 2 else 0.0
    )

    out: dict[str, Any] = {
        "mu": 1.0,
        "alpha": 0.0,
        "beta": 1.0,
        "log_likelihood": -math.inf,
        "branching_ratio": 0.0,
        "n_events": int(n),
        "T": T_observed,
        "converged": False,
        "method": "method_of_moments",
        "eta_fano": 0.0,
        "beta_from_acf_slope": 1.0,
        "beta_from_acf_recovered": False,
    }
    if n < 2 or T_observed <= 0.0:
        return out

    # ------------------------------------------------------------------
    # Part A -- Fano factor of binned counts -> branching ratio.
    # ------------------------------------------------------------------
    k_bins = max(20, n // 10)
    delta_t = T_observed / k_bins

    counts, _ = np.histogram(arr, bins=k_bins)
    mean_c = float(np.mean(counts))
    var_c = float(np.var(counts, ddof=1)) if k_bins > 1 else 0.0

    if mean_c > 0.0:
        f_factor = var_c / mean_c
        eta_fano = max(0.0, min(f_factor - 1.0, 0.95))
    else:
        f_factor = 0.0
        eta_fano = 0.0

    # ------------------------------------------------------------------
    # Part C -- mu from total rate with Fano-factor correction.
    # ------------------------------------------------------------------
    mu_hat = (n / T_observed) * (1.0 - eta_fano)

    # ------------------------------------------------------------------
    # Part B -- beta from sample-ACF log-linear decay.
    # Only accept the ACF slope if strictly negative (intensity MUST
    # decay for the exponential-kernel Hawkes).  A non-negative slope
    # is pathological -- fall back to the conservative mid-range beta.
    # ------------------------------------------------------------------
    beta_hat = 1.0  # conservative fallback if ACF is malformed.
    acf_recovered = False
    max_lag = min(10, k_bins - 1)
    if max_lag >= 2 and var_c > 0.0:
        centered = counts - mean_c
        acfs: list[float] = []
        for k in range(1, max_lag + 1):
            denom = float(k_bins - k)
            if denom <= 0.0:
                break
            cov_k = float(np.sum(centered[:-k] * centered[k:])) / denom
            acfs.append(cov_k / var_c if var_c > 0.0 else 0.0)

        positive_pairs = [
            (idx, val) for idx, val in enumerate(acfs, 1) if val > 0.0
        ]
        if len(positive_pairs) >= 2:
            ks_arr = np.array(
                [p[0] for p in positive_pairs], dtype=np.float64
            ) * delta_t
            ys_arr = np.log(
                np.array([p[1] for p in positive_pairs], dtype=np.float64)
            )
            # Closed-form OLS regression: log(ACF) ~ intercept - beta * tau.
            # np.polyfit is pure numpy -- safe to use here.
            coeffs = np.polyfit(ks_arr, ys_arr, 1)
            slope = float(coeffs[0])
            if slope < 0.0:
                beta_hat = max(-slope, 1e-4)
                acf_recovered = True
            # else: pathological rising ACF -- beta_hat stays at the
            # fallback 1.0; acf_recovered = False surfaces this in the
            # return dict so callers can detect the silent fallback.

    # ------------------------------------------------------------------
    # Part D -- alpha from branching-ratio identity.
    # ------------------------------------------------------------------
    alpha_hat = eta_fano * beta_hat

    # ------------------------------------------------------------------
    # Part F -- Log-likelihood cross-check (diagnostic only).
    # ------------------------------------------------------------------
    ll = exponential_log_likelihood(arr, mu_hat, alpha_hat, beta_hat)
    if math.isinf(ll) or math.isnan(ll):
        # Fall back: degenerate Poisson (alpha=0) for the LL diagnostic
        # so we always return a finite number for monitoring.
        ll = exponential_log_likelihood(arr, mu_hat, 0.0, beta_hat)
        if math.isinf(ll) or math.isnan(ll):
            ll = -math.inf

    out.update(
        {
            "mu": float(mu_hat),
            "alpha": float(alpha_hat),
            "beta": float(beta_hat),
            "log_likelihood": float(ll),
            "branching_ratio": float(alpha_hat / beta_hat) if beta_hat > 0.0 else 0.0,
            "converged": True,
            "eta_fano": float(eta_fano),
            "beta_from_acf_slope": float(beta_hat),
            "beta_from_acf_recovered": bool(acf_recovered),
        }
    )
    return out


__all__ = [
    "exponential_intensity",
    "exponential_log_likelihood",
    "hawkes_branching_ratio",
    "hawkes_stationary_intensity",
    "simulate_hawkes_ogata",
    "mle_exponential_hawkes",
    "fit_exponential_hawkes_method_of_moments",
]
