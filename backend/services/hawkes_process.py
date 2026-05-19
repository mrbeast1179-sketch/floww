"""
Hawkes Process Models for Trade Arrival Rates in Market Microstructure
========================================================================

A Hawkes process is a self-exciting point process where the conditional intensity
function depends on the history of past events. In market microstructure, it
models the clustering of trade arrivals: one trade increases the probability
of subsequent trades occurring shortly after.

The conditional intensity is defined as:

    lambda(t) = mu + sum_{t_i < t} phi(t - t_i)

where:
    - mu: baseline intensity (exogenous event rate)
    - phi: excitation kernel (how past events boost current intensity)
    - t_i: past event times

For the exponential kernel:  phi(delta) = alpha * exp(-beta * delta)
For the power-law kernel:   phi(delta) = alpha / (delta + c)^(1+gamma)

Key market microstructure applications:
    - Trade arrival clustering: large orders, news, and algorithmic activity
      create bursts of trades.
    - Order flow toxicity: VPIN and related metrics use Hawkes intensity as
      a proxy for informed trading.
    - Cross-excitation: trades in one symbol can trigger trades in related
      symbols (e.g., ETF and underlying, correlated equities).
    - Granger causality: the cross-excitation parameters alpha_ij quantify
      lead-lag relationships between assets.

The branching ratio n = alpha / beta (for exponential kernel) represents the
expected number of child events per parent event. When n < 1, the process
is subcritical and stationary. When n >= 1, the process can explode (not
realistic for real markets).

References:
    - Hawles, A.G. (1971). "Spectra of some self-exciting and mutually
      exciting point processes." Biometrika.
    - Bacry, E., Mastromatteo, I., & Muzy, J.F. (2015). "Hawkes processes
      in finance." Market Microstructure and Liquidity.
    - Ogata, Y. (1981). "On Lewis' simulation method for point processes."
      IEEE Transactions on Information Theory.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


class HawkesProcess:
    """
    Univariate Hawkes process with exponential or power-law excitation kernel.

    The conditional intensity function is:

        lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))

    for the exponential kernel, and:

        lambda(t) = mu + sum_{t_i < t} alpha / (t - t_i + c)^(1 + gamma)

    for the power-law kernel.

    Parameters
    ----------
    mu : float
        Baseline intensity (events per unit time). Must be > 0.
    alpha : float
        Jump size / excitation magnitude. Must be >= 0.
        Controls how much each event boosts the intensity.
    beta : float
        Decay rate of the excitation kernel. Must be > 0.
        Higher beta = faster decay = shorter memory.
    kernel : str
        Kernel type: "exponential" or "power_law".

    Examples
    --------
    >>> hp = HawkesProcess(mu=1.0, alpha=0.5, beta=1.0)
    >>> events = hp.simulate(T=100.0)
    >>> result = hp.fit(events)
    >>> print(f"Fitted mu={result['mu']:.3f}, alpha={result['alpha']:.3f}")
    """

    def __init__(
        self,
        mu: float = 1.0,
        alpha: float = 0.5,
        beta: float = 1.0,
        kernel: str = "exponential",
    ) -> None:
        if mu <= 0:
            raise ValueError(f"mu must be > 0, got {mu}")
        if alpha < 0:
            raise ValueError(f"alpha must be >= 0, got {alpha}")
        if beta <= 0:
            raise ValueError(f"beta must be > 0, got {beta}")
        if kernel not in ("exponential", "power_law"):
            raise ValueError(f"kernel must be 'exponential' or 'power_law', got '{kernel}'")

        self.mu = float(mu)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.kernel = kernel

        # Power-law kernel parameters (fixed defaults)
        self._pl_c = 0.01  # offset to avoid singularity
        self._pl_gamma = 0.5  # power-law exponent parameter

        # Fitted state
        self._fitted = False
        self._last_event_times: Optional[np.ndarray] = None
        self._last_log_likelihood: Optional[float] = None

    # ------------------------------------------------------------------
    # Intensity computation
    # ------------------------------------------------------------------

    def intensity(self, t: float, event_times: np.ndarray) -> float:
        """
        Compute the conditional intensity lambda(t) at time t given past events.

        For exponential kernel:
            lambda(t) = mu + sum_{t_i < t} alpha * exp(-beta * (t - t_i))

        Parameters
        ----------
        t : float
            Time at which to evaluate intensity.
        event_times : np.ndarray
            Sorted array of event times.

        Returns
        -------
        float
            Conditional intensity at time t. Always >= mu.
        """
        if event_times is None or len(event_times) == 0:
            return self.mu

        event_times = np.asarray(event_times, dtype=np.float64)
        past = event_times[event_times < t]

        if len(past) == 0:
            return self.mu

        dt = t - past

        if self.kernel == "exponential":
            excitation = self.alpha * np.sum(np.exp(-self.beta * dt))
        else:  # power_law
            excitation = self.alpha * np.sum(1.0 / (dt + self._pl_c) ** (1.0 + self._pl_gamma))

        return self.mu + excitation

    def _intensity_vectorized(self, t_array: np.ndarray, event_times: np.ndarray) -> np.ndarray:
        """Vectorized intensity computation for an array of time points."""
        result = np.full_like(t_array, self.mu, dtype=np.float64)
        for i, t in enumerate(t_array):
            result[i] = self.intensity(t, event_times)
        return result

    # ------------------------------------------------------------------
    # Log-likelihood
    # ------------------------------------------------------------------

    def _log_likelihood(self, params: np.ndarray, event_times: np.ndarray) -> float:
        """
        Compute the negative log-likelihood for parameter estimation.

        The log-likelihood of a Hawkes process is:

            L(mu, alpha, beta) = sum_i log(lambda(t_i)) - integral_0^T lambda(t) dt

        For the exponential kernel, the integral has a closed form:

            integral = mu * T + (alpha / beta) * sum_i [1 - exp(-beta * (T - t_i))]

        We return the negative because scipy.optimize.minimize minimizes.

        Parameters
        ----------
        params : np.ndarray
            Parameter vector [mu, alpha, beta].
        event_times : np.ndarray
            Sorted event times.

        Returns
        -------
        float
            Negative log-likelihood.
        """
        mu, alpha, beta = params

        # Enforce positivity via barrier (should be handled by bounds, but safety net)
        if mu <= 0 or alpha < 0 or beta <= 0:
            return 1e15

        T = event_times[-1] - event_times[0] if len(event_times) > 1 else 1.0
        t0 = event_times[0]

        # Compute log(lambda(t_i)) for each event
        log_lambdas = np.empty(len(event_times), dtype=np.float64)
        for i, ti in enumerate(event_times):
            past = event_times[:i]
            if len(past) == 0:
                lam = mu
            else:
                dt = ti - past
                if self.kernel == "exponential":
                    lam = mu + alpha * np.sum(np.exp(-beta * dt))
                else:
                    lam = mu + alpha * np.sum(1.0 / (dt + self._pl_c) ** (1.0 + self._pl_gamma))
            log_lambdas[i] = np.log(max(lam, 1e-300))

        sum_log = np.sum(log_lambdas)

        # Compute integral of lambda(t) from t0 to T_end
        T_end = event_times[-1]
        if self.kernel == "exponential":
            # integral = mu * (T_end - t0) + (alpha / beta) * sum_i [1 - exp(-beta * (T_end - t_i))]
            integral = mu * (T_end - t0) + (alpha / beta) * np.sum(
                1.0 - np.exp(-beta * (T_end - event_times))
            )
        else:
            # Numerical integration for power-law kernel
            n_steps = max(1000, len(event_times) * 10)
            t_grid = np.linspace(t0, T_end, n_steps)
            dt_grid = t_grid[1] - t_grid[0]
            lam_grid = np.empty(n_steps, dtype=np.float64)
            for j, t in enumerate(t_grid):
                past = event_times[event_times < t]
                if len(past) == 0:
                    lam_grid[j] = mu
                else:
                    dt_vals = t - past
                    lam_grid[j] = mu + alpha * np.sum(
                        1.0 / (dt_vals + self._pl_c) ** (1.0 + self._pl_gamma)
                    )
            integral = float(np.trapezoid(lam_grid, dx=dt_grid))

        ll = sum_log - integral
        return -ll  # negative for minimization

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(self, event_times: np.ndarray) -> Dict[str, float]:
        """
        Fit Hawkes process parameters via Maximum Likelihood Estimation.

        Uses scipy.optimize.minimize with L-BFGS-B to find parameters
        (mu, alpha, beta) that maximize the log-likelihood.

        Parameters
        ----------
        event_times : np.ndarray
            Array of observed event times. Will be sorted internally.

        Returns
        -------
        Dict[str, float]
            Dictionary with keys:
            - 'mu': fitted baseline intensity
            - 'alpha': fitted excitation magnitude
            - 'beta': fitted decay rate
            - 'log_likelihood': maximized log-likelihood value
            - 'branching_ratio': alpha / beta (expected children per parent)
            - 'n_events': number of events used for fitting
            - 'T': observation window length

        Raises
        ------
        ValueError
            If event_times has fewer than 2 events.
        """
        event_times = np.asarray(event_times, dtype=np.float64)
        event_times = np.sort(event_times)

        if len(event_times) < 2:
            logger.warning("Need at least 2 events to fit Hawkes process. Returning current params.")
            return {
                "mu": self.mu,
                "alpha": self.alpha,
                "beta": self.beta,
                "log_likelihood": 0.0,
                "branching_ratio": self.alpha / self.beta,
                "n_events": len(event_times),
                "T": 0.0,
            }

        # Initial parameter guesses
        T = event_times[-1] - event_times[0]
        n = len(event_times)
        mu0 = n / T * 0.5  # assume half the rate is baseline
        alpha0 = self.alpha
        beta0 = self.beta

        x0 = np.array([mu0, alpha0, beta0])

        # Bounds: mu > 0, alpha >= 0, beta > 0
        bounds = [(1e-8, None), (0.0, None), (1e-8, None)]

        result = minimize(
            fun=self._log_likelihood,
            x0=x0,
            args=(event_times,),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if result.success:
            self.mu, self.alpha, self.beta = result.x
            self._fitted = True
            self._last_event_times = event_times
            self._last_log_likelihood = -result.fun
            logger.info(
                "Hawkes fit converged: mu=%.4f, alpha=%.4f, beta=%.4f, LL=%.2f",
                self.mu, self.alpha, self.beta, -result.fun,
            )
        else:
            logger.warning("Hawkes fit did not converge: %s", result.message)
            # Still use the best result found
            self.mu, self.alpha, self.beta = result.x
            self._fitted = True
            self._last_event_times = event_times
            self._last_log_likelihood = -result.fun

        branching_ratio = self.alpha / self.beta

        return {
            "mu": float(self.mu),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "log_likelihood": float(-result.fun),
            "branching_ratio": float(branching_ratio),
            "n_events": int(n),
            "T": float(T),
        }

    # ------------------------------------------------------------------
    # Simulation (Ogata's thinning algorithm)
    # ------------------------------------------------------------------

    def simulate(self, T: float, n_events: int = 1000) -> np.ndarray:
        """
        Simulate event times using Ogata's thinning algorithm.

        Ogata's algorithm generates candidate events from a homogeneous Poisson
        process with rate lambda* >= lambda(t) for all t, then accepts each
        candidate with probability lambda(t) / lambda*.

        For the exponential kernel, we can compute lambda* analytically since
        the intensity is bounded above by mu + alpha * N_events / beta (roughly).
        We use an adaptive upper bound.

        Parameters
        ----------
        T : float
            Simulation time horizon.
        n_events : int
            Maximum number of events to generate (safety limit).

        Returns
        -------
        np.ndarray
            Array of simulated event times in [0, T].
        """
        if T <= 0:
            raise ValueError(f"T must be > 0, got {T}")

        events: list[float] = []
        t = 0.0

        # For exponential kernel, the maximum intensity after n events is
        # approximately mu + alpha * n / beta (steady-state upper bound).
        # We use a conservative lambda_star.
        lambda_star = self.mu + self.alpha * n_events / self.beta + 1.0

        max_iterations = n_events * 100  # safety limit
        iteration = 0

        while t < T and len(events) < n_events and iteration < max_iterations:
            iteration += 1

            # Generate candidate inter-event time from Exp(lambda_star)
            w = np.random.exponential(1.0 / lambda_star)
            t += w

            if t >= T:
                break

            # Compute actual intensity at candidate time
            lam_t = self.intensity(t, np.array(events))

            # Accept with probability lam_t / lambda_star
            u = np.random.uniform(0, 1)
            if u <= lam_t / lambda_star:
                events.append(t)

        result = np.array(events, dtype=np.float64)
        logger.debug("Simulated %d events in [0, %.2f]", len(result), T)
        return result

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_next_arrival(self, event_times: np.ndarray) -> float:
        """
        Predict the expected time to the next event.

        Given the current intensity lambda(t_now), the expected waiting time
        for a Poisson process with that rate is 1 / lambda(t_now).

        Parameters
        ----------
        event_times : np.ndarray
            Observed event times so far.

        Returns
        -------
        float
            Expected time until next event (in same units as event_times).
        """
        if event_times is None or len(event_times) == 0:
            return 1.0 / self.mu

        event_times = np.asarray(event_times, dtype=np.float64)
        t_now = event_times[-1]
        lam = self.intensity(t_now, event_times)

        return 1.0 / max(lam, 1e-300)

    def get_cluster_probability(
        self, event_times: np.ndarray, window: float = 1.0
    ) -> float:
        """
        Compute the probability that the next event is due to self-excitation
        (clustering) rather than the baseline.

        This is the ratio of the excitation component to the total intensity:

            P(cluster) = excitation / (mu + excitation)

        A high cluster probability indicates that the process is in a "burst"
        state, which in market microstructure often corresponds to informed
        trading or algorithmic activity.

        Parameters
        ----------
        event_times : np.ndarray
            Observed event times.
        window : float
            Time window for computing the cluster probability (used to
            evaluate intensity at t_last + window).

        Returns
        -------
        float
            Probability in [0, 1] that the next event is clustered.
        """
        if event_times is None or len(event_times) == 0:
            return 0.0

        event_times = np.asarray(event_times, dtype=np.float64)
        t_eval = event_times[-1] + window
        lam = self.intensity(t_eval, event_times)

        if lam <= 0:
            return 0.0

        excitation = lam - self.mu
        return float(np.clip(excitation / lam, 0.0, 1.0))

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """
        Return the full state of the Hawkes process for API serialization.

        Returns
        -------
        Dict[str, Any]
            Dictionary with keys:
            - 'mu': baseline intensity
            - 'alpha': excitation magnitude
            - 'beta': decay rate
            - 'kernel': kernel type
            - 'current_intensity': intensity at the last event time
            - 'cluster_prob': probability of clustered next event
            - 'branching_ratio': alpha / beta
            - 'fitted': whether the model has been fitted
        """
        current_intensity = self.mu
        cluster_prob = 0.0

        if self._last_event_times is not None and len(self._last_event_times) > 0:
            t_last = self._last_event_times[-1]
            current_intensity = self.intensity(t_last, self._last_event_times)
            cluster_prob = self.get_cluster_probability(self._last_event_times)

        return {
            "mu": float(self.mu),
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "kernel": self.kernel,
            "current_intensity": float(current_intensity),
            "cluster_prob": float(cluster_prob),
            "branching_ratio": float(self.alpha / self.beta),
            "fitted": self._fitted,
        }

    def __repr__(self) -> str:
        return (
            f"HawkesProcess(mu={self.mu:.4f}, alpha={self.alpha:.4f}, "
            f"beta={self.beta:.4f}, kernel='{self.kernel}')"
        )


class HawkesBivariate:
    """
    Bivariate Hawkes process for cross-excitation between two symbols.

    Models two point processes where events in each process can excite
    both itself and the other process:

        lambda_1(t) = mu_1 + sum_{t_j1 < t} alpha_11 * exp(-beta * (t - t_j1))
                            + sum_{t_j2 < t} alpha_12 * exp(-beta * (t - t_j2))

        lambda_2(t) = mu_2 + sum_{t_j2 < t} alpha_22 * exp(-beta * (t - t_j2))
                            + sum_{t_j1 < t} alpha_21 * exp(-beta * (t - t_j1))

    The cross-excitation parameters alpha_12 and alpha_21 measure Granger
    causality between the two processes:
        - alpha_12 > 0: events in process 2 Granger-cause events in process 1
        - alpha_21 > 0: events in process 1 Granger-cause events in process 2

    In market microstructure, this captures lead-lag relationships such as:
        - SPY trades -> QQQ trades (or vice versa)
        - Option trades -> underlying stock trades
        - Large-cap stock trades -> small-cap stock trades

    Parameters
    ----------
    mu1, mu2 : float
        Baseline intensities for processes 1 and 2.
    alpha11, alpha22 : float
        Self-excitation parameters.
    alpha12, alpha21 : float
        Cross-excitation parameters (Granger causality measures).
    beta : float
        Shared decay rate for all excitation kernels.
    """

    def __init__(
        self,
        mu1: float = 1.0,
        mu2: float = 1.0,
        alpha11: float = 0.3,
        alpha12: float = 0.1,
        alpha21: float = 0.1,
        alpha22: float = 0.3,
        beta: float = 1.0,
    ) -> None:
        if mu1 <= 0 or mu2 <= 0:
            raise ValueError(f"mu1 and mu2 must be > 0, got mu1={mu1}, mu2={mu2}")
        if alpha11 < 0 or alpha12 < 0 or alpha21 < 0 or alpha22 < 0:
            raise ValueError("All alpha parameters must be >= 0")
        if beta <= 0:
            raise ValueError(f"beta must be > 0, got {beta}")

        self.mu1 = float(mu1)
        self.mu2 = float(mu2)
        self.alpha11 = float(alpha11)
        self.alpha12 = float(alpha12)
        self.alpha21 = float(alpha21)
        self.alpha22 = float(alpha22)
        self.beta = float(beta)

        self._fitted = False
        self._last_log_likelihood: Optional[float] = None

    # ------------------------------------------------------------------
    # Intensity computation
    # ------------------------------------------------------------------

    def _intensity_1(self, t: float, events1: np.ndarray, events2: np.ndarray) -> float:
        """Compute lambda_1(t) given histories of both processes."""
        lam = self.mu1

        past1 = events1[events1 < t] if len(events1) > 0 else np.array([])
        past2 = events2[events2 < t] if len(events2) > 0 else np.array([])

        if len(past1) > 0:
            lam += self.alpha11 * np.sum(np.exp(-self.beta * (t - past1)))
        if len(past2) > 0:
            lam += self.alpha12 * np.sum(np.exp(-self.beta * (t - past2)))

        return lam

    def _intensity_2(self, t: float, events1: np.ndarray, events2: np.ndarray) -> float:
        """Compute lambda_2(t) given histories of both processes."""
        lam = self.mu2

        past1 = events1[events1 < t] if len(events1) > 0 else np.array([])
        past2 = events2[events2 < t] if len(events2) > 0 else np.array([])

        if len(past1) > 0:
            lam += self.alpha21 * np.sum(np.exp(-self.beta * (t - past1)))
        if len(past2) > 0:
            lam += self.alpha22 * np.sum(np.exp(-self.beta * (t - past2)))

        return lam

    # ------------------------------------------------------------------
    # Log-likelihood
    # ------------------------------------------------------------------

    def _neg_log_likelihood(self, params: np.ndarray, events1: np.ndarray, events2: np.ndarray) -> float:
        """
        Negative log-likelihood for the bivariate Hawkes process.

        L = L1 + L2 where:

        L1 = sum_i log(lambda_1(t1_i)) - integral_0^T lambda_1(t) dt
        L2 = sum_j log(lambda_2(t2_j)) - integral_0^T lambda_2(t) dt
        """
        mu1, mu2, alpha11, alpha12, alpha21, alpha22, beta = params

        if mu1 <= 0 or mu2 <= 0 or alpha11 < 0 or alpha12 < 0 or alpha21 < 0 or alpha22 < 0 or beta <= 0:
            return 1e15

        all_events = np.concatenate([events1, events2])
        T_start = np.min(all_events)
        T_end = np.max(all_events)

        # Log-likelihood for process 1
        sum_log_1 = 0.0
        for ti in events1:
            past1 = events1[events1 < ti]
            past2 = events2[events2 < ti]
            lam = mu1
            if len(past1) > 0:
                lam += alpha11 * np.sum(np.exp(-beta * (ti - past1)))
            if len(past2) > 0:
                lam += alpha12 * np.sum(np.exp(-beta * (ti - past2)))
            sum_log_1 += np.log(max(lam, 1e-300))

        # Integral for process 1
        integral_1 = mu1 * (T_end - T_start)
        if len(events1) > 0:
            integral_1 += (alpha11 / beta) * np.sum(
                1.0 - np.exp(-beta * (T_end - events1))
            )
        if len(events2) > 0:
            integral_1 += (alpha12 / beta) * np.sum(
                1.0 - np.exp(-beta * (T_end - events2))
            )

        # Log-likelihood for process 2
        sum_log_2 = 0.0
        for ti in events2:
            past1 = events1[events1 < ti]
            past2 = events2[events2 < ti]
            lam = mu2
            if len(past1) > 0:
                lam += alpha21 * np.sum(np.exp(-beta * (ti - past1)))
            if len(past2) > 0:
                lam += alpha22 * np.sum(np.exp(-beta * (ti - past2)))
            sum_log_2 += np.log(max(lam, 1e-300))

        # Integral for process 2
        integral_2 = mu2 * (T_end - T_start)
        if len(events1) > 0:
            integral_2 += (alpha21 / beta) * np.sum(
                1.0 - np.exp(-beta * (T_end - events1))
            )
        if len(events2) > 0:
            integral_2 += (alpha22 / beta) * np.sum(
                1.0 - np.exp(-beta * (T_end - events2))
            )

        ll = (sum_log_1 - integral_1) + (sum_log_2 - integral_2)
        return -ll

    # ------------------------------------------------------------------
    # Fitting
    # ------------------------------------------------------------------

    def fit(
        self, events1: np.ndarray, events2: np.ndarray
    ) -> Dict[str, float]:
        """
        Fit bivariate Hawkes process parameters via MLE.

        Parameters
        ----------
        events1 : np.ndarray
            Event times for process 1.
        events2 : np.ndarray
            Event times for process 2.

        Returns
        -------
        Dict[str, float]
            Dictionary with fitted parameters and diagnostics:
            - 'mu1', 'mu2': baseline intensities
            - 'alpha11', 'alpha12', 'alpha21', 'alpha22': excitation parameters
            - 'beta': shared decay rate
            - 'log_likelihood': maximized log-likelihood
            - 'n_events1', 'n_events2': number of events per process
        """
        events1 = np.asarray(events1, dtype=np.float64)
        events2 = np.asarray(events2, dtype=np.float64)
        events1 = np.sort(events1)
        events2 = np.sort(events2)

        if len(events1) < 2 or len(events2) < 2:
            logger.warning("Need at least 2 events per process for bivariate fit.")
            return {
                "mu1": self.mu1, "mu2": self.mu2,
                "alpha11": self.alpha11, "alpha12": self.alpha12,
                "alpha21": self.alpha21, "alpha22": self.alpha22,
                "beta": self.beta, "log_likelihood": 0.0,
                "n_events1": len(events1), "n_events2": len(events2),
            }

        all_events = np.concatenate([events1, events2])
        T = np.max(all_events) - np.min(all_events)

        # Initial guesses
        mu1_0 = len(events1) / T * 0.5
        mu2_0 = len(events2) / T * 0.5
        x0 = np.array([mu1_0, mu2_0, self.alpha11, self.alpha12, self.alpha21, self.alpha22, self.beta])

        bounds = [
            (1e-8, None),  # mu1
            (1e-8, None),  # mu2
            (0.0, None),   # alpha11
            (0.0, None),   # alpha12
            (0.0, None),   # alpha21
            (0.0, None),   # alpha22
            (1e-8, None),  # beta
        ]

        result = minimize(
            fun=self._neg_log_likelihood,
            x0=x0,
            args=(events1, events2),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 2000, "ftol": 1e-12},
        )

        if result.success:
            (
                self.mu1, self.mu2, self.alpha11, self.alpha12,
                self.alpha21, self.alpha22, self.beta,
            ) = result.x
            self._fitted = True
            self._last_log_likelihood = -result.fun
            logger.info(
                "Bivariate Hawkes fit converged: LL=%.2f", -result.fun
            )
        else:
            logger.warning("Bivariate Hawkes fit did not converge: %s", result.message)
            (
                self.mu1, self.mu2, self.alpha11, self.alpha12,
                self.alpha21, self.alpha22, self.beta,
            ) = result.x
            self._fitted = True
            self._last_log_likelihood = -result.fun

        return {
            "mu1": float(self.mu1),
            "mu2": float(self.mu2),
            "alpha11": float(self.alpha11),
            "alpha12": float(self.alpha12),
            "alpha21": float(self.alpha21),
            "alpha22": float(self.alpha22),
            "beta": float(self.beta),
            "log_likelihood": float(-result.fun),
            "n_events1": int(len(events1)),
            "n_events2": int(len(events2)),
        }

    # ------------------------------------------------------------------
    # Granger causality
    # ------------------------------------------------------------------

    def granger_causality(self) -> Dict[str, float]:
        """
        Compute Granger causality measures from cross-excitation parameters.

        In the context of Hawkes processes, Granger causality is quantified
        by the cross-excitation parameters:
            - alpha_12: strength of 2 -> 1 causality
            - alpha_21: strength of 1 -> 2 causality

        The normalized measures divide by the total excitation to give
        the proportion of excitation that comes from the other process.

        Returns
        -------
        Dict[str, float]
            Dictionary with keys:
            - 'alpha_12': raw cross-excitation from process 2 to 1
            - 'alpha_21': raw cross-excitation from process 1 to 2
            - 'gc_12': normalized Granger causality 2 -> 1
            - 'gc_21': normalized Granger causality 1 -> 2
            - 'net_gc': net Granger causality (positive = 1 leads 2)
            - 'branching_ratio_1': alpha_11 / beta (self-excitation of process 1)
            - 'branching_ratio_2': alpha_22 / beta (self-excitation of process 2)
            - 'total_branching_1': (alpha_11 + alpha_21) / beta
            - 'total_branching_2': (alpha_22 + alpha_12) / beta
        """
        br1_self = self.alpha11 / self.beta
        br2_self = self.alpha22 / self.beta
        br1_total = (self.alpha11 + self.alpha21) / self.beta
        br2_total = (self.alpha22 + self.alpha12) / self.beta

        # Normalized Granger causality
        total_exc1 = self.alpha11 + self.alpha12
        total_exc2 = self.alpha22 + self.alpha21

        gc_12 = self.alpha12 / total_exc1 if total_exc1 > 0 else 0.0
        gc_21 = self.alpha21 / total_exc2 if total_exc2 > 0 else 0.0

        return {
            "alpha_12": float(self.alpha12),
            "alpha_21": float(self.alpha21),
            "gc_12": float(gc_12),
            "gc_21": float(gc_21),
            "net_gc": float(gc_21 - gc_12),
            "branching_ratio_1": float(br1_self),
            "branching_ratio_2": float(br2_self),
            "total_branching_1": float(br1_total),
            "total_branching_2": float(br2_total),
        }

    def __repr__(self) -> str:
        return (
            f"HawkesBivariate(mu1={self.mu1:.4f}, mu2={self.mu2:.4f}, "
            f"alpha11={self.alpha11:.4f}, alpha12={self.alpha12:.4f}, "
            f"alpha21={self.alpha21:.4f}, alpha22={self.alpha22:.4f}, "
            f"beta={self.beta:.4f})"
        )
