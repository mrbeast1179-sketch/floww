"""
backend/services/amihud_illiquidity.py

Amihud (2002) illiquidity-ratio service.

Implements Yakov Amihud's "Illiquidity and Stock Returns: Cross-Section
and Time-Series Effects" (Journal of Financial Markets, 2002). Pure
Python only — no torch / numba / scipy (Round-9 freeze rule).

The Amihud ILLIQ ratio (sometimes denoted *Amihud illiquidity*) measures
how much price moves per dollar of traded volume over a window::

    Amihud_N = (1/N) * Σ_{i=1..N}  |r_i| / DV_i

where:
  * ``r_i`` is the log return over the i'th interval
  * ``DV_i`` is the dollar volume traded (price × volume)

In the original academic paper the inputs are daily; in the Flowseeker
pipeline we don't have per-trade data, so we use a chain-snapshot proxy:

    r_i   = log(spot_i / spot_{i-1})
    DV_i  = (call_vol_i + put_vol_i) * spot_i          # proxy for dollar volume

The proxy overstates DV by counting option-contract volume multiplied by
the spot price (rather than true option-notional volume), so the absolute
Amihud values are several orders of magnitude larger than the paper's
1e-9 .. 1e-6 calibration. We re-normalise the threshold bands for our
proxy scale (see below). The docstring is explicit about this convention.

Output schema (snake_case, mirrors :class:`KylesLambda` + :class:`VPINToxicity`
+ :class:`GaussianHMMRegime`)::

    {
        "amihud":         float,    # mean ILLIQ over the rolling window
        "abs_return":     float,    # latest |r| (log return)
        "dollar_volume":  float,    # latest DV (proxy)
        "label":          "LIQUID" | "NORMAL" | "ILLIQUID",
        "label_color":    "#22c55e" | "#fbbf24" | "#ef4444",
        "n_obs":          int,
        "is_warming":     bool,
    }

Label thresholds (calibrated against proxy-units; matches the slide in
``tests/test_amihud_illiquidity.py::test_label_thresholds_match_specification``)::

      amihud < 1e-7           → LIQUID
      1e-7 ≤ amihud < 1e-5    → NORMAL
      amihud ≥ 1e-5           → ILLIQUID

Usage::

    amihud = AmihudIlliquidity(window=20, history=64)
    for snapshot in chains_iter:
        call_vol, put_vol, _ = _chain_vol_oi(snapshot)
        spot = snapshot["spot"]
        amihud.push_snapshot(call_vol, put_vol, spot)
    out = amihud.compute()
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Label band + colour palette (mirrors brand chips in FlowseekerProTab.jsx)
# Colour palette and label naming match KylesLambda so the two illiquidity
# chips read consistently across the summary bar.
# ─────────────────────────────────────────────────────────────────────

LABEL_LIQUID = "LIQUID"
LABEL_NORMAL = "NORMAL"
LABEL_ILLIQUID = "ILLIQUID"

LABEL_COLORS: dict[str, str] = {
    LABEL_LIQUID:   "#22c55e",  # green
    LABEL_NORMAL:   "#fbbf24",  # amber
    LABEL_ILLIQUID: "#ef4444",  # red
}


def _classify_amihud(am: float) -> str:
    """Map an Amihud value to a 3-band label (LIQUID / NORMAL / ILLIQUID)."""
    if am < 1e-7:
        return LABEL_LIQUID
    if am < 1e-5:
        return LABEL_NORMAL
    return LABEL_ILLIQUID


# ─────────────────────────────────────────────────────────────────────
# Pure-Python Amihud estimator (rolling-mean over a bounded deque)
# ─────────────────────────────────────────────────────────────────────

class AmihudIlliquidity:
    """Amihud (2002) illiquidity estimator: |r| / DV averaged over a window."""

    def __init__(self, window: int = 20, history: int = 64):
        if window < 2:
            raise ValueError("window must be >= 2")
        if history < window:
            raise ValueError("history must be >= window")
        self.window = int(window)
        self.history = int(history)
        # Each observation is (illiq, abs_return, dollar_volume).
        self._obs: deque[tuple[float, float, float]] = deque(maxlen=self.history)
        # Stateful ``_last_spot`` mirrors the Kyle/Lambda service contract:
        # the first push seeds the spot and produces no observation; the
        # second push produces the first (r, dv) pair.
        self._last_spot: float | None = None

    # ── State mutators ────────────────────────────────────────────────

    def push_snapshot(self, call_vol: float, put_vol: float, spot: float) -> None:
        """Append a delta observation from one chain snapshot.

        ``r``  = log(spot / last_spot)
        ``DV`` = (call_vol + put_vol) * spot          # dollar-volume proxy
        ``illiq`` = |r| / DV

        Pushes with non-positive spot, non-finite spot, or zero dollar
        volume are silently dropped — they would otherwise pollute the
        rolling mean with sentinel values that don't represent the true
        no-flow state.
        """
        try:
            spot_f = float(spot)
        except (TypeError, ValueError):
            return
        if not math.isfinite(spot_f) or spot_f <= 0.0:
            return

        total_vol = float(call_vol or 0.0) + float(put_vol or 0.0)
        dv = total_vol * spot_f

        if self._last_spot is not None and dv > 0.0:
            r = math.log(spot_f / float(self._last_spot))
            illiq = abs(r) / dv
            self._obs.append((illiq, abs(r), dv))

        self._last_spot = spot_f

    # ── Read-side helpers ─────────────────────────────────────────────

    @property
    def n_obs(self) -> int:
        return len(self._obs)

    def compute(self) -> dict[str, Any]:
        """Rolling-mean Amihud over the LAST ``window`` observations.

        Returns the snake_case dict per the schema in the module docstring.
        """
        n_total = len(self._obs)
        if n_total < self.window:
            return {
                "amihud":        0.0,
                "abs_return":    0.0,
                "dollar_volume": 0.0,
                "label":         LABEL_NORMAL,
                "label_color":   LABEL_COLORS[LABEL_NORMAL],
                "n_obs":         n_total,
                "is_warming":    True,
            }

        recent = list(self._obs)[-self.window:]
        n_w = len(recent)
        mean_illiq = sum(o[0] for o in recent) / n_w
        last_abs_r = recent[-1][1]
        last_dv    = recent[-1][2]

        return {
            "amihud":        float(round(mean_illiq, 10)),
            "abs_return":    float(round(last_abs_r, 6)),
            "dollar_volume": float(round(last_dv, 2)),
            "label":         _classify_amihud(mean_illiq),
            "label_color":   LABEL_COLORS[_classify_amihud(mean_illiq)],
            "n_obs":         int(n_w),
            "is_warming":    False,
        }


__all__ = [
    "AmihudIlliquidity",
    "LABEL_LIQUID",
    "LABEL_NORMAL",
    "LABEL_ILLIQUID",
    "LABEL_COLORS",
]
