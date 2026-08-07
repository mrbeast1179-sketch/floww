"""
Dual-GEX + Hedging-Intensity Activity Ratio (steal-list rank #1)
================================================================

A second, INDEPENDENT GEX computation alongside ``GexAggregator.compute()``
that weights gamma by SAME-DAY VOLUME rather than resting OI. Combined with
the OI-weighted GEX that ``compute()`` already emits, this gives the
"dealer-positioning-as-a-movie" input floww currently lacks:

    activity_ratio = |gex_volume_total / gex_oi_total|

  * ratio > 1.0 → activity badge "live"    — flow fights structural book
  * ratio > 0.3 → activity badge "active"  — meaningful intraday hedging pulse
  * ratio ≤ 0.3 → activity badge "quiet"   — structure dominates (pin-day setup)

This module is STRICTLY ADDITIVE: it does NOT modify ``gex_aggregator.compute()``
and reuses ``aggregate_gex_1d`` from that module (re-exported read-only).
Keeping it decoupled keeps us collision-safe against any other session
editing ``gex_aggregator.py``.

Steal from: iAmGiG/gex-llm-patterns ``src/gex/gex_calculator.py::calculate_dual_gex``
Lands in:    route-level merge in the steal-three sidecar (``steal_three_server.py``)
             on :8001, leaving the main ``backend/server.py`` untouched.

Audit: docs/reports/2026-07-11-steal-list-integration-roadmap.md #1
       tests/services/test_gex_dual.py
"""

from typing import Any

import numba
import numpy as np

# Re-use the platform-wide dollar-GEX constants. If bs_greeks is on the
# path, import them; otherwise fall back to the published values
# (Perfiliev 2022 / SqueezeMetrics / SpotGamma)
try:  # pragma: no cover - import-time guard
    from bs_greeks import CONTRACT_MULTIPLIER, DOLLAR_MOVE_CONVENTION
except ImportError:  # running standalone (e.g. unit tests without backend on path)
    CONTRACT_MULTIPLIER = 100.0
    DOLLAR_MOVE_CONVENTION = 0.01

try:
    from services.gex_aggregator import GexAggregator, aggregate_gex_1d
except ImportError:  # pragma: no cover - allow sibling-folder import
    from gex_aggregator import GexAggregator, aggregate_gex_1d


@numba.njit(cache=True)
def _aggregate_volume_weighted(
    spot: float,
    strikes: np.ndarray,
    gammas: np.ndarray,
    volumes: np.ndarray,
    types: np.ndarray,
    unique_strikes: np.ndarray,
) -> np.ndarray:
    """Per-strike GEX weighted by SAME-DAY VOLUME.

    Sign convention: + for calls, − for puts (matches GexAggregator /
    ``dollar_gex_per_contract`` callers). Same per-contract dollars-per-1%-move
    scale (spot² × 0.01 × 100).
    """
    n_strikes = len(unique_strikes)
    result = np.zeros(n_strikes, dtype=np.float64)
    spot_sq_scale = spot * spot * DOLLAR_MOVE_CONVENTION * CONTRACT_MULTIPLIER
    n = len(strikes)
    for i in range(n):
        si = -1
        for s in range(n_strikes):
            if unique_strikes[s] == strikes[i]:
                si = s
                break
        if si < 0:
            continue
        sign = 1.0 if types[i] == 0 else -1.0
        result[si] += sign * gammas[i] * volumes[i] * spot_sq_scale
    return result


class DualGexCalculator:
    """Compute OI-weighted + volume-weighted GEX and the activity-ratio badge."""

    _VOLUME_KEYS = (
        "volume",
        "vol",
        "today_volume",
        "total_volume",
        "day_volume",
    )

    @staticmethod
    def _resolve_volume(contract: dict, oi_fallback: float) -> float:
        """Resolve contract volume, gracefully falling back to OI.

        This mirrors the aaguiar10/gflows volume-for-OI convention used
        in ``is_short_dte``: when 'volume' is missing, substitute OI.
        """
        for key in DualGexCalculator._VOLUME_KEYS:
            v = contract.get(key)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f >= 0.0:
                return f
        return oi_fallback

    @staticmethod
    def compute(spot: float, contracts: list[dict]) -> dict[str, Any]:
        """Return both 1D GEX series + summary metrics + activity badge."""
        empty: dict[str, Any] = {
            "strikes": [],
            "gex_oi_1d": [],
            "gex_volume_1d": [],
            "total_gex": 0.0,
            "net_gex_oi": 0.0,
            "net_gex_volume": 0.0,
            "gex_oi_total": 0.0,
            "gex_volume_total": 0.0,
            "activity_ratio": 0.0,
            "activity_badge": "quiet",
            "positive_gex_oi": 0.0,
            "positive_gex_volume": 0.0,
        }
        if not contracts or spot <= 0.0:
            return empty

        n = len(contracts)
        strikes = np.empty(n, dtype=np.float64)
        gammas = np.empty(n, dtype=np.float64)
        ois = np.empty(n, dtype=np.float64)
        vols = np.empty(n, dtype=np.float64)
        types = np.empty(n, dtype=np.int64)

        for i, c in enumerate(contracts):
            strikes[i] = float(GexAggregator._resolve(c, GexAggregator._STRIKE_KEYS))
            gammas[i] = float(GexAggregator._resolve(c, GexAggregator._GAMMA_KEYS))
            oi = float(GexAggregator._resolve(c, GexAggregator._OI_KEYS))
            ois[i] = oi
            vols[i] = DualGexCalculator._resolve_volume(c, oi)
            types[i] = GexAggregator._parse_option_type(
                GexAggregator._resolve(c, GexAggregator._TYPE_KEYS)
            )

        unique_strikes = np.unique(strikes)
        # Re-use the existing OI-weighted 1D aggregator (zero-touch).
        gex_oi_1d = aggregate_gex_1d(spot, strikes, gammas, ois, types, unique_strikes)
        # New volume-weighted 1D aggregator (parallel Numba kernel).
        gex_volume_1d = _aggregate_volume_weighted(
            spot, strikes, gammas, vols, types, unique_strikes
        )

        pos_oi = float(np.sum(gex_oi_1d[gex_oi_1d > 0]))
        pos_vol = float(np.sum(gex_volume_1d[gex_volume_1d > 0]))
        net_oi = float(np.sum(gex_oi_1d))
        net_vol = float(np.sum(gex_volume_1d))

        ratio = abs(net_vol / net_oi) if abs(net_oi) > 1e-9 else 0.0
        if ratio > 1.0 and net_vol != 0.0:
            badge = "live"
        elif ratio > 0.3 and net_vol != 0.0:
            badge = "active"
        else:
            badge = "quiet"

        return {
            "strikes": unique_strikes.tolist(),
            "gex_oi_1d": gex_oi_1d.tolist(),
            "gex_volume_1d": gex_volume_1d.tolist(),
            "total_gex": pos_oi,            # backward-compatible key
            "positive_gex_oi": pos_oi,
            "positive_gex_volume": pos_vol,
            "net_gex_oi": net_oi,
            "net_gex_volume": net_vol,
            "gex_oi_total": pos_oi,
            "gex_volume_total": net_vol,
            "activity_ratio": round(ratio, 4),
            "_spot": float(spot) if spot else None,  # for paper metrics computation
            "activity_badge": badge,
        }


# Convenience for callers that just want the badge (UI surfaces).
def activity_badge_from_ratio(ratio: float, vol_nonzero: bool = True) -> str:
    if not vol_nonzero:
        return "quiet"
    if ratio > 1.0:
        return "live"
    if ratio > 0.3:
        return "active"
    return "quiet"
