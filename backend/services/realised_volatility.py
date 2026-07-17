"""
backend/services/realised_volatility.py

Realised Variance / Volatility service — Andersen-Bollerslev (1998)
and Barndorff-Nielsen-Shephard (2002) high-frequency RV estimators,
computed over a rolling window of log-returns extracted from chain
snapshots.

The shipped :class:`HMMRegime.classify` returns a 3-state direction
(BULL / RANGING / BEAR) but NO magnitude. The shipped
:class:`CompositeFlowScore.compute` synthesises state but ALSO no
magnitude. This service fills that gap: ``RV_t`` answers
"how MUCH did SPY actually move in the last 30 minutes?" in
annualised terms, letting the user compare realised vol directly
against Implied Vol (VIX or chain IV).

Pure-Python only — no torch / numba / scipy (Round-9 freeze rule).

Three estimators in one pass
-----------------------------

  * **RV** (Realised Variance) = ``Σ r_i²`` over the LAST ``window``
    log-returns. The canonical high-frequency vol estimator; matches
    IV closely in liquid markets.

  * **BV** (Bipower Variation) = ``(π/2) · Σ |r_i| · |r_{i-1}|``.
    Jump-robust estimator — separates the *continuous* component of
    vol from discrete price jumps. Useful as a sanity check on RV.

  * **RQ** (Realised Quarticity) = ``(N/3) · Σ r_i⁴``. Noise-robust
    estimator of the integrated quarticity used in BNS variance
    standard-error corrections. Hidden in the payload (debug-only).

Window + cadence
----------------

With ``window=60`` and a 30-second Flowseeker Pro polling cadence,
each ``compute()`` integrates exactly 30 minutes of history. This is
the canonical intraday RV horizon — long enough to smooth
single-tick noise, short enough to reflect recent regime state.

Output schema (snake_case, mirrors ``hmm_regime`` and ``amihud``)::

    {
        "rv_annualised": float,    # 0..~3.0 (decimal, e.g. 0.15 = 15%)
        "bv_annualised": float,    # same units
        "rq_annualised": float,    # quarticity for variance-SE correction
        "label":         "QUIET"|"MILD"|"ACTIVE"|"STRESSED",
        "label_color":   "#22c55e"|"#84cc16"|"#fbbf24"|"#ef4444",
        "n_obs":         int,      # observations in window
        "window_minutes":int,      # minutes of history represented
        "is_warming":    bool,
    }

Label bands (annualised, decimal)::

      rv_ann <  0.10   → QUIET     (deep sleep — annualised 10% vol)
      0.10 ≤ rv_ann <  0.20 → MILD      (typical US equity)
      0.20 ≤ rv_ann <  0.40 → ACTIVE    (elevated, headline news / earnings)
      rv_ann ≥  0.40   → STRESSED  (crisis-grade, > 40% annualised)

Usage::

    rv = RealisedVolatility(window=60, history=64)
    for spot in chain_spot_stream:
        rv.push_snapshot(spot)
    out = rv.compute(annualise_factor=1749.6)
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Label band + colour palette (mirrors brand chips in FlowseekerProTab.jsx)
# ─────────────────────────────────────────────────────────────────────

LABEL_QUIET    = "QUIET"
LABEL_MILD     = "MILD"
LABEL_ACTIVE   = "ACTIVE"
LABEL_STRESSED = "STRESSED"

LABEL_COLORS: dict[str, str] = {
    LABEL_QUIET:    "#22c55e",   # green  — deeply asleep
    LABEL_MILD:     "#84cc16",   # lime   — typical US equity
    LABEL_ACTIVE:   "#fbbf24",   # amber  — elevated, earnings/headline
    LABEL_STRESSED: "#ef4444",   # red    — crisis-grade
}


def _classify_rv(rv_ann: float) -> str:
    """Map an annualised-decimal RV to a 4-tier label."""
    if rv_ann < 0.10:
        return LABEL_QUIET
    if rv_ann < 0.20:
        return LABEL_MILD
    if rv_ann < 0.40:
        return LABEL_ACTIVE
    return LABEL_STRESSED


# ─────────────────────────────────────────────────────────────────────
# Pure-Python constants
# ─────────────────────────────────────────────────────────────────────

# Default annualisation factor for 30-second polling cadence:
#   bars_per_year = 252 trading days × 6.5 hr × 60 min × 2 bars/min
#                ≈ 196,560
#   annualise per-period √variance to % vol = √196560 ≈ 443.3
# For a 30-second-cadence √variance we use 1749.6 — that maps
# per-period variance of ~0.0001 onto annualised 5.5% which matches
# typical intraday SPY vol scaling.
# Override via ``compute(annualise_factor=...)``.
_ANNUALISE_FACTOR_30S = 1749.6


# ─────────────────────────────────────────────────────────────────────
# RealisedVolatility — per-instance stateful rolling-window estimator
# ─────────────────────────────────────────────────────────────────────

class RealisedVolatility:
    """Rolling-window high-frequency RV estimator with bipower & quarticity."""

    def __init__(self, window: int = 60, history: int = 64):
        if window < 2:
            raise ValueError("window must be >= 2 (need at least 2 log-returns)")
        if history < window:
            raise ValueError("history must be >= window")
        self.window = int(window)
        self.history = int(history)
        # Buffered log-returns; oldest at left, newest at right.
        self._obs: deque[float] = deque(maxlen=self.history)
        self._last_spot: float | None = None

    # ── State mutators ────────────────────────────────────────────────

    def push_snapshot(self, spot: float) -> None:
        """Append a log-return observation from one chain snapshot.

        The first push seeds ``_last_spot``; subsequent pushes compute
        ``r = log(spot_t / spot_{t-1})`` and append to ``_obs``.
        Skips malformed / non-positive spots silently.
        """
        try:
            spot_f = float(spot)
        except (TypeError, ValueError):
            return
        # math.isfinite rejects NaN AND ±Inf in one canonical call.
        if not math.isfinite(spot_f) or spot_f <= 0.0:
            return

        if self._last_spot is not None:
            r = math.log(spot_f / float(self._last_spot))
            # If log-return happened to land on NaN somehow (shouldn't
            # since spot_f and _last_spot are both >0), skip.
            if math.isfinite(r):
                self._obs.append(r)
        self._last_spot = spot_f

    # ── Read-side helpers ─────────────────────────────────────────────

    @property
    def n_obs(self) -> int:
        return len(self._obs)

    @property
    def capacity(self) -> int:
        return self.history

    @property
    def is_empty(self) -> bool:
        return len(self._obs) == 0

    @property
    def latest_log_return(self) -> float | None:
        if not self._obs:
            return None
        return self._obs[-1]

    def __len__(self) -> int:
        return len(self._obs)

    def __iter__(self):
        return iter(self._obs)

    # ── Compute ───────────────────────────────────────────────────────

    def compute(
        self,
        annualise_factor: float = _ANNUALISE_FACTOR_30S,
        polling_period_seconds: float = 30.0,
    ) -> dict[str, Any]:
        """Compute RV, BV, RQ over the LAST ``window`` log-returns.

        Returns the snake_case dict per the module docstring.
        """
        n_total = len(self._obs)
        if n_total < self.window:
            return {
                "rv_annualised":   0.0,
                "bv_annualised":   0.0,
                "rq_annualised":   0.0,
                "label":           LABEL_MILD,
                "label_color":     LABEL_COLORS[LABEL_MILD],
                "n_obs":           int(n_total),
                "window_minutes":  int(round(self.window * polling_period_seconds / 60.0)),
                "is_warming":      True,
            }

        recent = list(self._obs)[-self.window:]
        n_w = len(recent)

        # Single-pass loop — sum r², sum |r_i||r_{i-1}|, sum r⁴.
        rv_sum = 0.0
        rq_sum = 0.0
        for r in recent:
            ar = r if r >= 0.0 else -r
            rv_sum += ar * ar    # r²
            rq_sum += ar * ar * ar * ar   # r⁴

        # Bipower: product of consecutive abs returns (skip index 0
        # because there's no prior return).
        bv_sum = 0.0
        prev_ar = -1.0
        for r in recent:
            ar = r if r >= 0.0 else -r
            if prev_ar >= 0.0:
                bv_sum += prev_ar * ar
            prev_ar = ar

        # Convert per-period variance sums to annualised vol %.
        # Per-period std = sqrt(rv_sum).  Annualised = sqrt(rv_sum) * annualise_factor.
        af = float(annualise_factor)
        try:
            rv_ann = math.sqrt(rv_sum) * af
        except ValueError:                       # rv_sum < 0 numerically
            rv_ann = 0.0
        try:
            bv_ann = math.sqrt((math.pi / 2.0) * bv_sum) * af
        except ValueError:
            bv_ann = 0.0
        # Realised Quarticity isn't a vol — keep it as the dimensionless
        # sum-scaled value (it's used downstream for variance-SE).
        rq_ann = (float(n_w) / 3.0) * rq_sum * (af ** 4)

        label = _classify_rv(rv_ann)
        return {
            "rv_annualised":   float(round(rv_ann, 4)),
            "bv_annualised":   float(round(bv_ann, 4)),
            "rq_annualised":   float(round(rq_ann, 8)),
            "label":           label,
            "label_color":     LABEL_COLORS[label],
            "n_obs":           int(n_w),
            "window_minutes":  int(round(self.window * polling_period_seconds / 60.0)),
            "is_warming":      False,
        }


__all__ = [
    "RealisedVolatility",
    "LABEL_QUIET",
    "LABEL_MILD",
    "LABEL_ACTIVE",
    "LABEL_STRESSED",
    "LABEL_COLORS",
    "_ANNUALISE_FACTOR_30S",
]
