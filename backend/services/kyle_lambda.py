"""
backend/services/kyle_lambda.py

Kyle's Lambda (market-depth) service.

Implements the price-impact-per-unit-of-order-flow regression from the
Kyle (1985) framework, "Continuous Auctions and Insider Trading". Pure
Python only — no torch / numba / scipy (Round-9 freeze rule).

The academic model regresses log price change on signed order flow:

    Δ ln(P_t) = λ · x_t + ε_t

where ``x_t`` is the (signed) order-flow arrival. We extract both components
from chain snapshots in the Flowseeker pipeline:

  * ``y_t``  = log(spot_t / spot_{t-1})  (price impact)
  * ``x_t``  = (call_vol − put_vol) / (call_vol + put_vol)        ∈ [−1, 1]

``x_t`` is normalized so λ is comparable across tickers (SPY vs TSLA)
without per-ticker threshold calibration. The slope coefficient is the
empirical price impact we expect for a fully-imbalanced flow on a given
underlying.

Output schema (snake_case, mirrors :class:`VPINToxicity` +
:class:`GaussianHMMRegime`)::

    {
        "lambda_value":  float,    # OLS slope Δln(P) per unit of [−1,1] flow
        "intercept":     float,    # regression intercept
        "r_squared":     float,    # in-window goodness-of-fit
        "label":         "LIQUID" | "NORMAL" | "ILLIQUID",
        "label_color":   "#22c55e" | "#fbbf24" | "#ef4444",
        "n_obs":         int,
        "is_warming":    bool,
    }

Label thresholds (calibrated against published Kyle-λ values for liquid
US-equity markets; `[:1]` normalisation keeps thresholds ticker-agnostic)::

      lambda < 0.001           → LIQUID
      0.001 ≤ lambda < 0.005   → NORMAL
      lambda ≥ 0.005           → ILLIQUID

Usage::

    kyle = KylesLambda(window=20, history=64)
    for snapshot in chains_iter:
        call_vol, put_vol, _ = _chain_vol_oi(snapshot)
        spot = snapshot["spot"]
        kyle.push_snapshot(call_vol, put_vol, spot)
    out = kyle.compute()
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, Tuple


# ─────────────────────────────────────────────────────────────────────
# Label band + colour palette (mirrors brand chips in FlowseekerProTab.jsx)
# ─────────────────────────────────────────────────────────────────────

LABEL_LIQUID = "LIQUID"
LABEL_NORMAL = "NORMAL"
LABEL_ILLIQUID = "ILLIQUID"

LABEL_COLORS: Dict[str, str] = {
    LABEL_LIQUID:   "#22c55e",  # green  — deep / liquid
    LABEL_NORMAL:   "#fbbf24",  # amber  — fair depth
    LABEL_ILLIQUID: "#ef4444",  # red    — shallow / illiquid
}


def _classify_lambda(lam: float) -> str:
    """Map a Kyle's λ value to a 3-band label."""
    if lam < 0.001:
        return LABEL_LIQUID
    if lam < 0.005:
        return LABEL_NORMAL
    return LABEL_ILLIQUID


# ─────────────────────────────────────────────────────────────────────
# Pure-Python OLS ("numerically safe" — division guarded by eps)
# ─────────────────────────────────────────────────────────────────────

_EPS = 1e-9


class KylesLambda:
    """Market-depth estimator: OLS slope of Δln(P) on normalised flow."""

    def __init__(self, window: int = 20, history: int = 64):
        if window < 3:
            raise ValueError("window must be >= 3 to estimate slope + intercept")
        if history < window:
            raise ValueError("history must be >= window")
        self.window = int(window)
        self.history = int(history)
        # Buffered (x, y) observations.
        self._obs: "deque[Tuple[float, float]]" = deque(maxlen=self.history)
        self._last_spot: float | None = None

    # ── State mutators ────────────────────────────────────────────────

    def push_snapshot(self, call_vol: float, put_vol: float, spot: float) -> None:
        """Append a delta observation from one chain snapshot.

        ``x`` = directional flow share in [−1, 1] (skip when tot == 0).
        ``y`` = log return vs last push (skip on first push or bad spot).
        """
        # Skip malformed pushes silently — the route layer is responsible
        # for surfacing invalid data upstream.
        try:
            spot_f = float(spot)
        except (TypeError, ValueError):
            return
        if not math.isfinite(spot_f) or spot_f <= 0.0:
            return

        total_vol = float(call_vol or 0.0) + float(put_vol or 0.0)
        if self._last_spot is not None and total_vol > 0.0:
            x = (float(call_vol or 0.0) - float(put_vol or 0.0)) / total_vol
            # Clamp for floating-point safety.
            if x < -1.0:
                x = -1.0
            elif x > 1.0:
                x = 1.0
            y = math.log(spot_f / float(self._last_spot))
            self._obs.append((x, y))

        self._last_spot = spot_f

    # ── Read-side helpers ─────────────────────────────────────────────

    @property
    def n_obs(self) -> int:
        return len(self._obs)

    def compute(self) -> Dict[str, Any]:
        """OLS slope + intercept over the LAST ``window`` observations.

        Returns the snake_case dict per the schema in the module docstring.
        """
        n_total = len(self._obs)
        if n_total < self.window:
            return {
                "lambda_value": 0.0,
                "intercept": 0.0,
                "r_squared": 0.0,
                "label": LABEL_NORMAL,
                "label_color": LABEL_COLORS[LABEL_NORMAL],
                "n_obs": n_total,
                "is_warming": True,
            }

        recent = list(self._obs)[-self.window:]
        n_w = len(recent)
        # Batch sums — bounded N (≤ 64 in practice) so this is plenty fast.
        sum_x = 0.0
        sum_y = 0.0
        sum_x2 = 0.0
        sum_xy = 0.0
        sum_y2 = 0.0
        for x_i, y_i in recent:
            sum_x  += x_i
            sum_y  += y_i
            sum_x2 += x_i * x_i
            sum_xy += x_i * y_i
            sum_y2 += y_i * y_i
        mean_x = sum_x / n_w
        mean_y = sum_y / n_w
        ss_xx = sum_x2 - n_w * mean_x * mean_x
        ss_xy = sum_xy - n_w * mean_x * mean_y
        ss_yy = sum_y2 - n_w * mean_y * mean_y

        if ss_xx < _EPS:
            # Constant-flow edge case: slope is undefined → neutralise and
            # call it a normal reading rather than over-flag illiquidity.
            lam = 0.0
            intercept = mean_y
            r2 = 0.0
        else:
            lam = ss_xy / ss_xx
            intercept = mean_y - lam * mean_x
            r2 = (ss_xy * ss_xy) / (ss_xx * ss_yy) if ss_yy > _EPS else 0.0

        label = _classify_lambda(lam)
        return {
            "lambda_value": float(round(lam, 6)),
            "intercept":    float(round(intercept, 6)),
            "r_squared":    float(round(r2, 4)),
            "label":        label,
            "label_color":  LABEL_COLORS[label],
            "n_obs":        int(n_w),
            "is_warming":   False,
        }


__all__ = [
    "KylesLambda",
    "LABEL_LIQUID",
    "LABEL_NORMAL",
    "LABEL_ILLIQUID",
    "LABEL_COLORS",
]
