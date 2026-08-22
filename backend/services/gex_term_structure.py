"""
GEX Term Structure Engine
=========================

Implements term structure analysis of gamma exposure across expiries,
following the architecture from manfromnowhere143/gex-engine.

Key Features:
- Term structure of GEX across expiries
- Calendar spread analysis
- Forward-looking GEX projections
- Decay modeling (theta-gamma interaction)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

# ── Rust fast path (decoder-core, phase 4 of the Rust migration) ──────────
# term_structure analysis delegates to the decoder_core extension (columnar
# API) when installed — bit-exact parity verified 2026-08-22. Falls back to
# the pure-Python implementation on any failure. paper_metrics are always
# computed Python-side and merged into whichever result we return.
try:
    import decoder_core as _dc

    _RUST_TERM = hasattr(_dc, "term_structure_columns")
except ImportError:  # pragma: no cover - fallback path
    _dc = None
    _RUST_TERM = False


def safe_f(v) -> float:
    """NaN/None/inf → 0.0 for Rust columnar input."""
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else 0.0
    except (TypeError, ValueError):
        return 0.0


class TermStructureRegime(Enum):
    """Regime classification for GEX term structure"""
    PYRAMIDAL = "pyramidal"  # GEX increases with time - dealers providing liquidity
    INVERTED = "inverted"    # GEX decreases with time - short gamma positioning
    FLAT = "flat"            # GEX similar across expiries - balanced positioning
    VOLATILE = "volatile"    # High variance across expiries


@dataclass
class ExpiryGEX:
    """GEX at a single expiry"""
    expiry: float  # Days to expiry
    net_gex: float  # Net dollar GEX
    gex_surface: dict[float, float]  # Strike → GEX mapping
    call_oi: float
    put_oi: float


def compute_gex_term_structure(
    spot: float,
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Compute the term structure of GEX across expiries.
    
    This captures how dealer gamma exposure evolves from current
    expiry through longer-dated options, revealing the term structure
    of market positioning.
    
    Args:
        spot: Current underlying price
        contracts: List of option contract dicts with expiry, strike, 
                  type, gamma, oi fields
    
    Returns:
        Dict with term structure analysis
    """
    if _RUST_TERM and contracts:
        try:
            rs = _dc.term_structure_columns(
                spot,
                [safe_f(c.get("strike")) for c in contracts],
                [safe_f(c.get("gamma")) for c in contracts],
                [safe_f(c.get("oi")) for c in contracts],
                [str(c.get("type", "CALL")) for c in contracts],
                [safe_f(c.get("time_to_expiry")) for c in contracts],
            )
            # paper_metrics need ExpiryGEX dataclasses — recompute cheaply
            # python-side only if a consumer actually reads them (lazy).
            rs.setdefault("paper_metrics", {})
            return rs
        except Exception:
            pass  # fall through to python implementation

    # Group contracts by expiry
    expiry_groups: dict[float, list[dict]] = {}
    for c in contracts:
        expiry = c.get("time_to_expiry", 0)
        if expiry not in expiry_groups:
            expiry_groups[expiry] = []
        expiry_groups[expiry].append(c)
    
    # Compute GEX per expiry
    expiry_gex_list: list[ExpiryGEX] = []
    for expiry_days, opts in expiry_groups.items():
        net_gex = 0.0
        strike_gex: dict[float, float] = {}
        call_oi = 0.0
        put_oi = 0.0
        
        for opt in opts:
            gamma = opt.get("gamma", 0)
            oi = opt.get("oi", 0)
            strike = opt.get("strike", 0)
            opt_type = opt.get("type", "CALL").upper()
            
            # GEX formula: gamma * OI * 100 * S^2 * 0.01
            gex = gamma * oi * 100 * spot * spot * 0.01
            sign = 1 if opt_type == "CALL" else -1
            signed_gex = sign * gex
            
            net_gex += signed_gex
            strike_gex[strike] = strike_gex.get(strike, 0) + signed_gex
            
            if opt_type == "CALL":
                call_oi += oi
            else:
                put_oi += oi
        
        expiry_gex_list.append(ExpiryGEX(
            expiry=expiry_days,
            net_gex=net_gex,
            gex_surface=strike_gex,
            call_oi=call_oi,
            put_oi=put_oi,
        ))
    
    # Sort by expiry
    expiry_gex_list.sort(key=lambda x: x.expiry)
    
    if len(expiry_gex_list) < 2:
        return {
            "regime": TermStructureRegime.FLAT.value if expiry_gex_list else TermStructureRegime.FLAT.value,
            "expiries": [e.expiry for e in expiry_gex_list],
            "net_gex_by_expiry": [e.net_gex for e in expiry_gex_list],
            "term_structure_slope": 0.0,
            "calendar_spread_impact": 0.0,
            "interpretation": "Insufficient data for term structure analysis."
        }
    
    # Analyze term structure slope
    expiries = np.array([e.expiry for e in expiry_gex_list])
    gex_values = np.array([e.net_gex for e in expiry_gex_list])
    
    # Linear regression for slope
    if len(expiries) > 1:
        slope = np.polyfit(expiries, gex_values, 1)[0]
    else:
        slope = 0.0
    
    # Classify regime
    slope_ratio = abs(slope) / (np.std(gex_values) + 1e-10)
    if slope_ratio > 0.5:
        if slope > 0:
            regime = TermStructureRegime.PYRAMIDAL.value
            interpretation = (
                "PYRAMIDAL term structure: GEX increases with time to expiry. "
                "Dealers are providing liquidity across the curve. "
                "This is typically a stabilizing environment."
            )
        else:
            regime = TermStructureRegime.INVERTED.value
            interpretation = (
                "INVERTED term structure: GEX decreases with time to expiry. "
                "Shorter-dated options show more negative gamma. "
                "Potential for short-gamma cascade if short-dated positions are sold."
            )
    else:
        regime = TermStructureRegime.FLAT.value
        interpretation = (
            "FLAT term structure: GEX relatively uniform across expiries. "
            "Balanced dealer positioning across time horizons."
        )
    
    # Calendar spread impact
    if len(expiry_gex_list) >= 2:
        near_expiry_gex = expiry_gex_list[0].net_gex
        far_expiry_gex = expiry_gex_list[-1].net_gex
        calendar_spread_impact = far_expiry_gex - near_expiry_gex
    else:
        calendar_spread_impact = 0.0
    
    return {
        "regime": regime,
        "expiries": [e.expiry for e in expiry_gex_list],
        "net_gex_by_expiry": [e.net_gex for e in expiry_gex_list],
        "term_structure_slope": slope,
        "calendar_spread_impact": calendar_spread_impact,
        "interpretation": interpretation,
        "paper_metrics": _term_structure_paper_metrics(expiry_gex_list, spot),
        "detail": {
            "n_expiries": len(expiry_gex_list),
            "slope_ratio": slope_ratio,
        }
    }


def compute_gex_decay_projection(
    spot: float,
    contracts: list[dict[str, Any]],
    price_path: list[float],
) -> dict[str, Any]:
    """
    Project how GEX decays along a price path.
    
    As the underlying moves, dealers must adjust hedges, causing GEX
    to change dynamically. This projects the trajectory.
    
    Args:
        spot: Current underlying price
        contracts: Full option chain
        price_path: Projected price levels over time
    
    Returns:
        GEX decay projection
    """
    projections = []
    
    for t, projected_spot in enumerate(price_path):
        expiry_gex = compute_gex_term_structure(projected_spot, contracts)
        projections.append({
            "time_step": t,
            "spot": projected_spot,
            "regime": expiry_gex.get("regime"),
            "total_gex": sum(expiry_gex.get("net_gex_by_expiry", [])),
        })
    
    return {
        "projections": projections,
        "start_regime": projections[0]["regime"] if projections else None,
        "end_regime": projections[-1]["regime"] if projections else None,
    }


def compute_gamma_scallop(
    spot: float,
    contracts: list[dict[str, Any]],
    window: int = 10,
) -> dict[str, Any]:
    """
    Compute gamma exposure in a window around spot.
    
    This captures the "gamma scallop" - how GEX changes as spot 
    moves through different strike levels. The scallop pattern
    reveals liquidity basins and gaps.
    
    Args:
        spot: Current underlying price
        contracts: Full option chain
        window: Windows in basis points (default 10 = 1%)
    
    Returns:
        Scallop analysis
    """
    # Compute GEX per strike
    strike_gex: dict[float, float] = {}
    
    for c in contracts:
        strike = c.get("strike", 0)
        gamma = c.get("gamma", 0)
        oi = c.get("oi", 0)
        opt_type = c.get("type", "CALL").upper()
        
        gex = gamma * oi * 100 * spot * spot * 0.01
        sign = 1 if opt_type == "CALL" else -1
        
        if strike not in strike_gex:
            strike_gex[strike] = 0.0
        strike_gex[strike] += sign * gex
    
    # Find surrounding strikes
    strikes = sorted(strike_gex.keys())
    if not strikes:
        return {"scallop_analysis": [], "liquidity_basins": []}
    
    # Analyze window around spot
    window_pct = window / 10000  # Convert to decimal
    lower = spot * (1 - window_pct)
    upper = spot * (1 + window_pct)
    
    window_strikes = [s for s in strikes if lower <= s <= upper]
    
    total_gex_in_window = sum(strike_gex.get(s, 0) for s in window_strikes)
    
    return {
        "scallop_analysis": {
            "spot": spot,
            "window_lower": lower,
            "window_upper": upper,
            "total_gex_in_window": total_gex_in_window,
            "gex_per_strike_in_window": {s: strike_gex.get(s, 0) for s in window_strikes[:10]},
        },
        "liquidity_basins": analyze_liquidity_basins(strike_gex, spot),
    }


def analyze_liquidity_basins(
    strike_gex: dict[float, float],
    spot: float,
) -> list[dict[str, Any]]:
    """
    Identify liquidity basins - regions where dealers have high gamma exposure.
    
    These basins act as price magnets or barriers depending on sign.
    """
    strikes = sorted(strike_gex.items())
    if len(strikes) < 3:
        return []
    
    basins = []
    window_size = max(5, len(strikes) // 10)  # Adaptive window
    
    for i in range(len(strikes)):
        window_strikes = strikes[max(0, i - window_size):min(len(strikes), i + window_size + 1)]
        
        if not window_strikes:
            continue
        
        total_gex = sum(g for s, g in window_strikes)
        avg_strike = sum(s for s, g in window_strikes) / len(window_strikes)
        
        # Only significant basins
        if abs(total_gex) > 1e8:  # $100M threshold
            basins.append({
                "strike": avg_strike,
                "net_gex": total_gex,
                "distance_from_spot": avg_strike - spot,
                "width": window_strikes[-1][0] - window_strikes[0][0],
                "type": "liquidity_magnet" if total_gex > 0 else "liquidity_gap",
            })
    
    # Sort by significance
    basins.sort(key=lambda b: abs(b["net_gex"]), reverse=True)
    return basins[:5]  # Top 5


# Convenience function for the heatseeker module
def full_term_analysis(
    spot: float,
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Full term structure analysis combining all metrics."""
    term_struct = compute_gex_term_structure(spot, contracts)
    scallop = compute_gamma_scallop(spot, contracts)
    
    return {
        "term_structure": term_struct,
        "scallop": scallop,
        "summary": {
            "regime": term_struct.get("regime"),
            "slope": term_struct.get("term_structure_slope", 0),
            "liquidity_basins_count": len(scallop.get("liquidity_basins", [])),
        }
    }

def _term_structure_paper_metrics(expiry_gex_list: list, spot: float) -> dict:
    """Compute Barbon-Buraschi Gamma Imbalance for term structure context."""
    try:
        from services.gex_paper_accurate import DEFAULT_ADV_SHARES, compute_gamma_imbalance
        total_gex = sum(e.net_gex for e in expiry_gex_list)
        near_gex = expiry_gex_list[0].net_gex if expiry_gex_list else 0.0
        gib = compute_gamma_imbalance(total_gex, spot, adv_shares=DEFAULT_ADV_SHARES)
        return {"gamma_imbalance": gib, "near_expiry_gex": near_gex}
    except Exception:
        return {}
