"""
backend/services/heatseeker.py

Skylit-parity Heatseeker Wave 1: flip zones, node lifecycle, air pockets.

Pure functions. No DB access — the route layer fetches the chain and passes
it in. Input shape mirrors backend/advanced_analytics.py: each contract is a
dict with at least `strike`, `type` ("C"/"CALL"/"call" or "P"/"PUT"/"put"),
`gamma`, `open_interest` (or `oi`). Robust to missing fields and empty input.

Formula references (mirroring `calc_gamma_flip_levels` in advanced_analytics.py
at line 633):
    gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
    signed_gex = gex_unit if type=="call" else -gex_unit

All three functions return JSON-serializable dicts and never raise on empty or
degenerate input.
"""

from __future__ import annotations

from statistics import median
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _is_call(c: Dict[str, Any]) -> bool:
    """True if contract is a call. Accepts 'C', 'CALL', 'call' (any case)."""
    t = str(c.get("type", "")).upper()
    return t in ("C", "CALL")


def _oi(c: Dict[str, Any]) -> float:
    """Open interest, tolerant to 'open_interest' or 'oi' field names."""
    val = c.get("open_interest")
    if val is None:
        val = c.get("oi", 0)
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _strike(c: Dict[str, Any]) -> float:
    try:
        return float(c.get("strike", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _gamma(c: Dict[str, Any]) -> float:
    try:
        return float(c.get("gamma", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _gex_per_strike(spot: float, contracts: List[Dict[str, Any]]) -> Dict[float, float]:
    """
    Aggregate signed GEX per strike using the same convention as
    `calc_gamma_flip_levels` in advanced_analytics.py:

        gex_unit  = gamma * oi * 100 * spot * spot * 0.01
        signed    = +gex_unit for calls, -gex_unit for puts
    """
    out: Dict[float, float] = {}
    if not contracts or not spot or spot <= 0:
        return out
    for c in contracts:
        oi = _oi(c)
        if oi <= 0:
            continue
        gamma = _gamma(c)
        if gamma <= 0:
            continue
        strike = _strike(c)
        if strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if _is_call(c) else -1.0
        out[strike] = out.get(strike, 0.0) + sign * gex_unit
    return out


# ---------------------------------------------------------------------------
# Function 1: Flip zones
# ---------------------------------------------------------------------------

def calc_flip_zones(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    window_pct: float = 0.05,
) -> Dict[str, Any]:
    """
    All price levels where cumulative GEX changes sign, within
    ``spot * (1 ± window_pct)``.

    A flip zone is interpolated linearly between adjacent strikes where the
    running cumulative GEX crosses zero. ``strength`` is the magnitude of the
    cumulative-sum change at the crossing strike, which proxies dealer hedging
    urgency through that level.

    Returns
    -------
    dict with keys: ``flip_zones`` (list), ``window_low``, ``window_high``,
    ``count``. Empty list on degenerate input.
    """
    if not spot or spot <= 0:
        return {"flip_zones": [], "window_low": 0.0, "window_high": 0.0, "count": 0}

    window_low = spot * (1.0 - window_pct)
    window_high = spot * (1.0 + window_pct)

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {
            "flip_zones": [],
            "window_low": round(window_low, 4),
            "window_high": round(window_high, 4),
            "count": 0,
        }

    strikes = sorted(gex.keys())
    cumulative: List[float] = []
    running = 0.0
    for k in strikes:
        running += gex[k]
        cumulative.append(running)

    zones: List[Dict[str, Any]] = []
    for i in range(1, len(strikes)):
        prev_c, curr_c = cumulative[i - 1], cumulative[i]
        # Only count true sign changes (excludes prev==0 to avoid duplicate
        # crossings when a strike has exactly zero net cumulative GEX).
        if prev_c == 0 or curr_c == 0:
            continue
        if (prev_c > 0) == (curr_c > 0):
            continue

        k1, k2 = strikes[i - 1], strikes[i]
        # Linear interpolation: f(k1)=prev_c, f(k2)=curr_c, find where f=0.
        denom = curr_c - prev_c
        if denom == 0:
            flip_price = (k1 + k2) / 2.0
        else:
            flip_price = k1 + (k2 - k1) * (-prev_c / denom)

        if not (window_low <= flip_price <= window_high):
            continue

        zones.append({
            "price": round(flip_price, 4),
            "from_sign": "positive" if prev_c > 0 else "negative",
            "to_sign": "positive" if curr_c > 0 else "negative",
            "strength": round(abs(curr_c - prev_c), 4),
        })

    return {
        "flip_zones": zones,
        "window_low": round(window_low, 4),
        "window_high": round(window_high, 4),
        "count": len(zones),
    }


# ---------------------------------------------------------------------------
# Function 2: Node lifecycle
# ---------------------------------------------------------------------------

def calc_node_lifecycle(
    spot: float,
    contracts: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Classify the top 10 strikes by |GEX| as Fresh / Tested / Delivered /
    Decaying based on how many times spot has come within 0.1% of them in the
    supplied ``history`` (typically last 24h of spot snapshots).

    Tap-probability schedule (Skylit's documented decay curve):
        fresh      → 80
        tested     → 66
        delivered  → 33
        decaying   → 10

    ``history`` is a list of dicts with at least ``spot`` (and ``timestamp``,
    unused here but kept in the signature for the caller's contract).
    """
    if not spot or spot <= 0:
        return {"nodes": []}

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {"nodes": []}

    # Top 10 strikes by absolute net GEX.
    ranked = sorted(gex.items(), key=lambda kv: abs(kv[1]), reverse=True)[:10]

    history = history or []
    history_spots: List[float] = []
    for h in history:
        try:
            history_spots.append(float(h.get("spot")))
        except (TypeError, ValueError):
            continue

    nodes: List[Dict[str, Any]] = []
    for strike, net_gex in ranked:
        if strike <= 0:
            continue
        taps = sum(
            1 for s in history_spots
            if abs(s - strike) / strike <= 0.001
        )
        if taps == 0:
            state, prob = "fresh", 80
        elif taps == 1:
            state, prob = "tested", 66
        elif taps == 2:
            state, prob = "delivered", 33
        else:
            state, prob = "decaying", 10
        nodes.append({
            "strike": round(strike, 4),
            "net_gex": round(net_gex, 4),
            "taps": taps,
            "state": state,
            "tap_probability": prob,
        })

    return {"nodes": nodes}


# ---------------------------------------------------------------------------
# Function 3: Air pockets
# ---------------------------------------------------------------------------

def calc_air_pockets(
    spot: float,
    contracts: List[Dict[str, Any]],
    *,
    min_gap_pct: float = 0.005,
) -> Dict[str, Any]:
    """
    Contiguous ranges of strikes where ``|GEX|`` is below 20% of the local
    median (median of ``|GEX|`` for strikes within ±5% of spot) AND the range
    spans at least ``spot * min_gap_pct`` in price.

    These zones tend to see fast price moves because dealer hedging is thin.

    Returns
    -------
    dict with key ``air_pockets`` — list of ``{low, high, span_pct,
    max_abs_gex_in_run}`` dicts. Empty list on degenerate input.
    """
    if not spot or spot <= 0:
        return {"air_pockets": []}

    gex = _gex_per_strike(spot, contracts)
    if not gex:
        return {"air_pockets": []}

    strikes = sorted(gex.keys())
    abs_gex: Dict[float, float] = {k: abs(gex[k]) for k in strikes}

    # Local median of |GEX| using strikes within ±5% of spot.
    near_window_low = spot * 0.95
    near_window_high = spot * 1.05
    near_vals = [abs_gex[k] for k in strikes if near_window_low <= k <= near_window_high]
    if not near_vals:
        return {"air_pockets": []}
    local_median = median(near_vals)
    if local_median <= 0:
        # Degenerate: everything is zero in the local window. No pockets to
        # report (a flat-zero band is technically a giant pocket but isn't
        # actionable signal).
        return {"air_pockets": []}

    threshold = 0.2 * local_median
    min_span = spot * min_gap_pct

    pockets: List[Dict[str, Any]] = []
    run_start_idx: int | None = None
    run_max: float = 0.0

    def _flush(run_start_idx: int, run_end_idx: int, run_max_val: float) -> None:
        low_k = strikes[run_start_idx]
        high_k = strikes[run_end_idx]
        span = high_k - low_k
        if span < min_span:
            return
        pockets.append({
            "low": round(low_k, 4),
            "high": round(high_k, 4),
            "span_pct": round(span / spot, 6),
            "max_abs_gex_in_run": round(run_max_val, 4),
        })

    for i, k in enumerate(strikes):
        if abs_gex[k] < threshold:
            if run_start_idx is None:
                run_start_idx = i
                run_max = abs_gex[k]
            else:
                run_max = max(run_max, abs_gex[k])
        else:
            if run_start_idx is not None:
                _flush(run_start_idx, i - 1, run_max)
                run_start_idx = None
                run_max = 0.0
    # Trailing run.
    if run_start_idx is not None:
        _flush(run_start_idx, len(strikes) - 1, run_max)

    return {"air_pockets": pockets}
