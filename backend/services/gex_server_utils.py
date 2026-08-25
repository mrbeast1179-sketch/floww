"""
services/gex_server_utils.py

GEX computation utilities extracted from server.py.
Pure functions with no FastAPI, MongoDB, or cache dependencies.

Extracted 2026-08-07 to reduce server.py from 3321 lines.
"""
import math
from datetime import UTC, datetime
from typing import Any

from scipy.stats import norm

from bs_greeks import (
    bs_charm,
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
    bs_zomma,
    dollar_charm_per_contract,
    dollar_gex_per_contract,
    dollar_vex_per_contract,
)

# Dividend yields for Black-Scholes (moved from server.py)
DIV_YIELD = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}


def safe_float(v, default=0.0):
    """Safely convert a value to float, handling None and NaN."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


# --- restored: compute_gex_grid ---
def compute_gex_grid(spot: float, contracts: list[dict[str, Any]], ticker: str = "") -> dict[str, Any]:
    """2D grid: GEX per (strike, expiry). Skylit-style heatmap layout."""
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}, "charm_grid": {}, "vex_grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    grid: dict[str, dict[float, float]] = {}
    charm_grid: dict[str, dict[float, float]] = {}
    vex_grid: dict[str, dict[float, float]] = {}
    strike_totals: dict[float, float] = {}
    for c in contracts:
        oi = c.get("oi", 0) or 0
        if oi <= 0:
            continue
        iv = c.get("iv")
        if iv is None or (isinstance(iv, float) and math.isnan(iv)):
            continue
        T = c.get("T", 0) or 0
        if T <= 0:
            continue
        gamma = bs_gamma(spot, c["strike"], T, iv, q=q)
        charm = bs_charm(spot, c["strike"], T, iv, q=q, kind=c["type"])
        vanna = bs_vanna(spot, c["strike"], T, iv, q=q)
        if gamma <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, c["oi"], spot)
        charm_unit = dollar_charm_per_contract(charm, c["oi"], spot)
        vex_unit = dollar_vex_per_contract(vanna, c["oi"], spot)
        sign = 1.0 if c["type"] == "call" else -1.0
        cell = sign * gex_unit
        charm_cell = sign * charm_unit
        vex_cell = sign * vex_unit
        d = grid.setdefault(c["expiry"], {})
        d[c["strike"]] = d.get(c["strike"], 0.0) + cell
        dc = charm_grid.setdefault(c["expiry"], {})
        dc[c["strike"]] = dc.get(c["strike"], 0.0) + charm_cell
        dv = vex_grid.setdefault(c["expiry"], {})
        dv[c["strike"]] = dv.get(c["strike"], 0.0) + vex_cell
        strike_totals[c["strike"]] = strike_totals.get(c["strike"], 0.0) + cell

    expiries = sorted(grid.keys())
    strikes = sorted(strike_totals.keys())

    def _k(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else str(x)

    return {
        "expiries": expiries,
        "strikes": strikes,
        "grid": {e: {_k(k): v for k, v in grid[e].items()} for e in expiries},
        "charm_grid": {e: {_k(k): v for k, v in charm_grid[e].items()} for e in expiries},
        "vex_grid": {e: {_k(k): v for k, v in vex_grid[e].items()} for e in expiries},
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }
# Import from shared module to avoid circular imports with portfolio.py
# DOLLAR_MOVE_CONVENTION  = 0.01   (industry-standard 1%-move convention; see bs_greeks.py)
# CONTRACT_MULTIPLIER     = 100    (shares per equity option contract)


# --- restored: calc_probability_distribution ---
def calc_probability_distribution(spot: float, contracts: list[dict[str, Any]],
                                   risk_free_rate: float = 0.05) -> list[dict[str, Any]]:
    """Risk-neutral probability distribution from option prices.
    Returns list of {strike, prob_above, prob_below, delta} per strike."""
    if spot <= 0 or not contracts:
        return []
    strikes = sorted(set(c["strike"] for c in contracts))
    result = []
    for k in strikes:
        # Get call IV at this strike
        calls = [c for c in contracts if c["strike"] == k and c["type"] == "call"]
        puts = [c for c in contracts if c["strike"] == k and c["type"] == "put"]
        iv = None
        T = None
        if calls:
            iv = calls[0].get("iv") or 0.2
            T = calls[0].get("T") or 1/365
        elif puts:
            iv = puts[0].get("iv") or 0.2
            T = puts[0].get("T") or 1/365
        if not iv or iv <= 0 or not T or T <= 0:
            continue
        try:
            d1 = (math.log(spot / k) + (risk_free_rate + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            prob_above = float(norm.cdf(d2))  # risk-neutral prob of finishing above K
            prob_below = 1.0 - prob_above
            delta_call = float(norm.cdf(d1))
            result.append({
                "strike": k,
                "prob_above": round(prob_above, 4),
                "prob_below": round(prob_below, 4),
                "delta": round(delta_call, 4),
                "iv": round(iv, 4),
            })
        except Exception:
            continue
    return result


def detect_opportunities(strikes: list[dict[str, Any]], nodes: dict[str, Any],
                          spot: float, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect trading opportunities from GEX analysis.
    Categories: gamma_squeeze, wall_support, wall_resistance, vol_expansion, vol_compression, pin_risk, gamma_ladder"""
    opportunities = []
    if not strikes or spot <= 0:
        return opportunities

    king = nodes.get("king")
    if not king:
        return opportunities
    king_gex_abs = abs(king.get("gex", 0)) or 1.0  # noqa: F841  used for future concentration calc
    total_gex = nodes.get("total_gex", 0)
    polarity = nodes.get("polarity_level", spot)
    regime = nodes.get("regime", "neutral")

    # --- Gamma Squeeze: price approaching call wall from below ---
    call_wall = nodes.get("ceilings", [{}])
    call_wall_strike = call_wall[0]["strike"] if call_wall else None
    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            # Concentration of call GEX at wall
            calls_above = [s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0]
            total_call_gex = sum(s.get("call_gex", 0) for s in calls_above)
            max_call_gex = max((s.get("call_gex", 0) for s in calls_above), default=0)
            concentration = max_call_gex / total_call_gex if total_call_gex > 0 else 0
            proximity = 1 - (dist_pct / 3.0)
            confidence = min((concentration + proximity) / 2, 1.0)
            if confidence >= 0.3:
                opportunities.append({
                    "type": "gamma_squeeze",
                    "name": "Gamma Squeeze Setup",
                    "direction": "bullish",
                    "risk": "high",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Breakout could trigger dealer hedging acceleration.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.995, 2), round(call_wall_strike * 0.99, 2)),
                    "target": round(call_wall_strike * 1.02, 2),
                    "stop": round(spot * 0.97, 2),
                })

    # --- Put Wall Support ---
    put_wall = nodes.get("floors", [{}])
    put_wall_strike = put_wall[0]["strike"] if put_wall else None
    if put_wall_strike and spot > put_wall_strike:
        dist_pct = (spot - put_wall_strike) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "put_wall_support",
                    "name": "Put Wall Support",
                    "direction": "bullish",
                    "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% above put wall at {put_wall_strike:.1f}. Dealers likely to buy dips here.",
                    "trigger": {"put_wall": put_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(put_wall_strike * 1.005, 2), round(spot * 1.01, 2)),
                    "target": round(polarity, 2),
                    "stop": round(put_wall_strike * 0.98, 2),
                })

    # --- Call Wall Resistance ---
    if call_wall_strike and spot < call_wall_strike:
        dist_pct = (call_wall_strike - spot) / spot * 100
        if dist_pct < 3.0:
            proximity = 1 - (dist_pct / 3.0)
            regime_bonus = 0.2 if regime == "positive" else 0
            confidence = min(proximity + regime_bonus, 1.0)
            if confidence >= 0.4:
                opportunities.append({
                    "type": "call_wall_resistance",
                    "name": "Call Wall Resistance",
                    "direction": "bearish",
                    "risk": "low",
                    "confidence": round(confidence, 2),
                    "description": f"Price {dist_pct:.1f}% below call wall at {call_wall_strike:.1f}. Dealers likely to sell rallies here.",
                    "trigger": {"call_wall": call_wall_strike, "distance_pct": round(dist_pct, 2), "regime": regime},
                    "entry": (round(call_wall_strike * 0.99, 2), round(call_wall_strike * 1.005, 2)),
                    "target": round(polarity, 2),
                    "stop": round(call_wall_strike * 1.02, 2),
                })

    # --- Volatility Expansion (negative gamma regime) ---
    if regime in ("negative", "neutral") and total_gex < 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(abs(dist_to_flip) / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_expansion",
                "name": "Volatility Expansion",
                "direction": "neutral",
                "risk": "medium",
                "confidence": round(confidence, 2),
                "description": "Negative gamma regime. Dealers amplifying moves. Expect increased volatility.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    # --- Volatility Compression (positive gamma regime) ---
    if regime == "positive" and total_gex > 0:
        dist_to_flip = ((spot - polarity) / spot) * 100 if polarity else 0
        confidence = min(dist_to_flip / 5, 1.0)
        if confidence >= 0.3:
            opportunities.append({
                "type": "volatility_compression",
                "name": "Volatility Compression",
                "direction": "neutral",
                "risk": "low",
                "confidence": round(confidence, 2),
                "description": "Positive gamma regime. Dealers dampening moves. Good for selling premium.",
                "trigger": {"regime": regime, "total_gex": total_gex, "dist_to_flip_pct": round(dist_to_flip, 2)},
            })

    # --- Pin Risk: high OI at ATM strike near expiration ---
    if contracts:
        # Find nearest expiry
        expiries = sorted(set(c["expiry"] for c in contracts))
        if expiries:
            nearest_exp = expiries[0]
            try:
                exp_date = datetime.strptime(nearest_exp, "%Y-%m-%d").date()
                dte = (exp_date - datetime.now(UTC).date()).days
            except Exception:
                dte = 999
            if dte <= 5:
                # Find ATM strike with highest OI
                atm_strike_val = min(strikes, key=lambda s: abs(s["strike"] - spot))["strike"]
                atm_strikes_data = [s for s in strikes if abs(s["strike"] - atm_strike_val) < spot * 0.01]
                if atm_strikes_data:
                    max_oi = max(s.get("total_oi", 0) for s in atm_strikes_data)
                    if max_oi > 1000:
                        confidence = min(0.3 + (max_oi / 10000) * 0.3 + (1 - dte / 5) * 0.3, 1.0)
                        if confidence >= 0.4:
                            opportunities.append({
                                "type": "pin_risk",
                                "name": "Expiration Pin Risk",
                                "direction": "neutral",
                                "risk": "medium",
                                "confidence": round(confidence, 2),
                                "description": f"High OI ({max_oi:,.0f}) at {atm_strike_val:.0f} with {dte} DTE. Price may gravitate here.",
                                "trigger": {"pin_strike": atm_strike_val, "oi": max_oi, "dte": dte},
                                "target": atm_strike_val,
                            })

    # --- Gamma Ladder: multiple call strikes with increasing GEX above price ---
    calls_above = sorted([s for s in strikes if s["strike"] > spot and s.get("call_gex", 0) > 0],
                         key=lambda s: s["strike"])
    if len(calls_above) >= 3:
        call_gex_vals = [s.get("call_gex", 0) for s in calls_above[:5]]
        ascending = sum(1 for i in range(len(call_gex_vals) - 1) if call_gex_vals[i + 1] > call_gex_vals[i] * 0.8)
        if ascending >= 2:
            pattern_strength = ascending / (len(call_gex_vals) - 1)
            total_call_gex_above = sum(call_gex_vals)
            total_call_gex_all = sum(s.get("call_gex", 0) for s in strikes if s.get("call_gex", 0) > 0)
            concentration = total_call_gex_above / total_call_gex_all if total_call_gex_all > 0 else 0
            confidence = min((pattern_strength + concentration) / 2, 1.0)
            if confidence >= 0.35:
                rungs = [s["strike"] for s in calls_above[:3]]
                opportunities.append({
                    "type": "gamma_ladder",
                    "name": "Gamma Call Ladder",
                    "direction": "bullish",
                    "risk": "medium",
                    "confidence": round(confidence, 2),
                    "description": f"Call ladder with {ascending} rungs. Targets: {', '.join(f'{r:.0f}' for r in rungs)}.",
                    "trigger": {"rungs": rungs, "ascending": ascending, "concentration": round(concentration, 2)},
                    "entry": (round(spot * 0.99, 2), round(rungs[0] * 0.995, 2)),
                    "target": rungs[-1],
                    "stop": round(spot * 0.97, 2),
                })

    # Sort by confidence
    opportunities.sort(key=lambda o: o.get("confidence", 0), reverse=True)
    return opportunities[:8]  # max 8 opportunities


# ----------------------------- Node Hierarchy ---------------------------------


# ----------------------------- GEX Aggregation --------------------------------

def compute_gex_by_strike(spot: float, contracts: list[dict[str, Any]], ticker: str = "") -> list[dict[str, Any]]:
    """Per-strike net GEX, VEX, and Vega. Convention: dealer-positive convention."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: dict[float, dict[str, float]] = {}
    for c in contracts:
        oi = safe_float(c.get("oi"))
        if oi <= 0:
            continue
        iv = safe_float(c.get("iv"))
        if iv <= 0:
            continue
        T = safe_float(c.get("T"))
        if T <= 0:
            continue
        strike = safe_float(c.get("strike"))
        if strike <= 0:
            continue
        try:
            gamma = float(bs_gamma(spot, strike, T, iv, q=q) or 0)
            vanna = float(bs_vanna(spot, strike, T, iv, q=q) or 0)
            vega_val = float(bs_vega(spot, strike, T, iv, q=q) or 0)
            charm = float(bs_charm(spot, strike, T, iv, q=q, kind=c["type"]) or 0)
            vomma = float(bs_vomma(spot, strike, T, iv, q=q) or 0)
            zomma = float(bs_zomma(spot, strike, T, iv, q=q) or 0)
        except (TypeError, ValueError):
            continue
        if gamma <= 0 and abs(vanna) <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, oi, spot)
        vex_unit = dollar_vex_per_contract(vanna, oi, spot)
        vega_unit = vega_val * oi * 100.0  # per unit-σ; see bs_greeks normalization note
        charm_unit = dollar_charm_per_contract(charm, oi, spot)
        vomma_unit = vomma * oi * 100.0  # per unit-σ
        zomma_unit = zomma * oi * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
            "vex": 0.0, "call_vex": 0.0, "put_vex": 0.0,
            "vega": 0.0, "call_vega": 0.0, "put_vega": 0.0,
            "charm": 0.0, "call_charm": 0.0, "put_charm": 0.0,
            "vomma": 0.0, "call_vomma": 0.0, "put_vomma": 0.0,
            "zomma": 0.0, "call_zomma": 0.0, "put_zomma": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        bucket["vex"] += sign * vex_unit
        bucket["vega"] += sign * vega_unit
        bucket["charm"] += sign * charm_unit
        bucket["vomma"] += sign * vomma_unit
        bucket["zomma"] += sign * zomma_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_vex"] += vex_unit
            bucket["call_vega"] += vega_unit
            bucket["call_charm"] += charm_unit
            bucket["call_vomma"] += vomma_unit
            bucket["call_zomma"] += zomma_unit
            bucket["call_oi"] += oi
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_vex"] += vex_unit
            bucket["put_vega"] += vega_unit
            bucket["put_charm"] += charm_unit
            bucket["put_vomma"] += vomma_unit
            bucket["put_zomma"] += zomma_unit
            bucket["put_oi"] += oi
        bucket["total_oi"] += oi

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


# ----------------------------- Implied Move & Probability (from EzOptions) ------

def calc_implied_move(spot: float, contracts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Calculate implied move from ATM straddle price. Returns expected move in $ and %."""
    if spot <= 0 or not contracts:
        return None
    # Find ATM strike
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return None
    atm = min(strikes, key=lambda s: abs(s - spot))
    # Get ATM call and put mid prices
    atm_calls = [c for c in contracts if c["strike"] == atm and c["type"] == "call"]
    atm_puts = [c for c in contracts if c["strike"] == atm and c["type"] == "put"]
    if not atm_calls or not atm_puts:
        return None
    # Use IV to estimate straddle price via BS
    # .get(k, default) returns None when the key exists with a None value
    # (cvserver 429-degraded payloads do this) — coalesce explicitly.
    call_iv = atm_calls[0].get("iv") or 0.2
    put_iv = atm_puts[0].get("iv") or 0.2
    T = atm_calls[0].get("T") or 1/365
    if T <= 0:
        T = 1/365
    avg_iv = (call_iv + put_iv) / 2
    # Straddle price ≈ 0.8 * S * σ * sqrt(T) (market standard approximation)
    straddle = 0.8 * spot * avg_iv * math.sqrt(T)
    return {
        "atm_strike": atm,
        "straddle_price": round(straddle, 2),
        "implied_move_pct": round((straddle / spot) * 100, 2),
        "implied_move_dollars": round(straddle, 2),
        "upper_range": round(spot + straddle, 2),
        "lower_range": round(spot - straddle, 2),
        "avg_iv": round(avg_iv, 4),
        "tte_years": round(T, 6),
    }


def calc_aggregate_gex_curve(spot: float, contracts: list[dict[str, Any]],
                              ticker: str = "") -> list[dict[str, float]]:
    """Aggregate GEX curve: total GEX if spot moved to each price point.
    Shows how dealer gamma changes as spot moves."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    strikes = sorted(set(c["strike"] for c in contracts))
    if not strikes:
        return []
    min_s = min(strikes)
    max_s = max(strikes)
    # Range: +/- 15% from current spot, or min/max strikes
    lo = max(min_s, spot * 0.85)
    hi = min(max_s, spot * 1.15)
    step = (hi - lo) / 100
    if step <= 0:
        return []
    # Pre-filter contracts to only those within relevant range (optimization)
    relevant = [c for c in contracts if c.get("oi", 0) and float(c.get("oi", 0) or 0) > 0
                and c.get("strike", 0) >= lo * 0.5 and c.get("strike", 0) <= hi * 1.5]
    curve = []
    price = lo
    while price <= hi:
        total_gex = 0.0
        for c in relevant:
            gamma = bs_gamma(price, c["strike"], c["T"], c["iv"], q=q)
            if gamma <= 0:
                continue
            gex = dollar_gex_per_contract(gamma, c["oi"], price)
            sign = 1.0 if c["type"] == "call" else -1.0
            total_gex += sign * gex
        curve.append({"price": round(price, 2), "gex": round(total_gex / 1e9, 4) if not (math.isnan(total_gex) or math.isinf(total_gex)) else 0.0})
        price += step
    return curve


# ----------------------------- Opportunity Detection (from GEX-Dashboard) ------

def classify_nodes(strikes: list[dict[str, Any]], spot: float) -> dict[str, Any]:
    if not strikes or spot <= 0:
        return {"king": None, "floors": [], "ceilings": [], "gatekeepers": [], "air_pockets": [],
                "polarity_level": None, "regime": "unknown", "total_gex": 0, "near_gex": 0,
                "vex_flip": None, "stacked_nodes": [], "tug_of_war": [], "total_vega": 0}

    # King = largest absolute exposure
    king = max(strikes, key=lambda r: abs(r["gex"]))
    max_abs = abs(king["gex"]) or 1.0

    floors = sorted(
        [s for s in strikes if s["strike"] < spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )
    ceilings = sorted(
        [s for s in strikes if s["strike"] > spot and s["gex"] > 0],
        key=lambda r: r["gex"], reverse=True,
    )

    # Gatekeepers: positive nodes between spot and king
    gk_threshold = 0.15 * max_abs
    if king and king["strike"] != spot:
        lo, hi = sorted([spot, king["strike"]])
        gks = [s for s in strikes
               if lo < s["strike"] < hi and s["strike"] != king["strike"]
               and abs(s["gex"]) >= gk_threshold]
        gatekeepers = sorted(gks, key=lambda r: abs(r["gex"]), reverse=True)
    else:
        gatekeepers = []

    # Air Pockets: contiguous stretches where |gex| < 8% of max_abs
    ap_threshold = 0.08 * max_abs
    air_pockets = []
    run_start = None
    run_strikes: list[float] = []
    for s in strikes:
        weak = abs(s["gex"]) < ap_threshold
        if weak:
            if run_start is None:
                run_start = s["strike"]
            run_strikes.append(s["strike"])
        else:
            if run_start is not None and len(run_strikes) >= 3:
                air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                                    "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})
            run_start = None
            run_strikes = []
    if run_start is not None and len(run_strikes) >= 3:
        air_pockets.append({"low": min(run_strikes), "high": max(run_strikes),
                            "width": len(run_strikes), "mid": (min(run_strikes) + max(run_strikes)) / 2})

    # Polarity / regime - use total GEX
    total_gex = sum(s["gex"] for s in strikes)
    spot_window = [s for s in strikes if abs(s["strike"] - spot) / spot < 0.02]
    near_gex = sum(s["gex"] for s in spot_window)
    if total_gex > 0:
        regime = "positive"
    elif total_gex < 0:
        regime = "negative"
    else:
        regime = "neutral"

    # Gamma flip point: weighted average of all strikes by absolute GEX
    # This gives the "center of gravity" for gamma exposure
    # A more useful flip point than cumulative zero-crossing
    total_abs_gex = sum(abs(s["gex"]) for s in strikes)
    polarity = sum(s["strike"] * abs(s["gex"]) for s in strikes) / total_abs_gex if total_abs_gex > 0 else spot

    # VEX flip point: same weighted average approach for vanna
    total_abs_vex = sum(abs(s.get("vex", 0.0) or 0) for s in strikes)
    if total_abs_vex > 0:
        vex_flip = sum(s["strike"] * abs(s.get("vex", 0.0) or 0) for s in strikes) / total_abs_vex
    else:
        vex_flip = spot

    # Stacked nodes: strikes where both call and put GEX are significant
    stacked = []
    for s in strikes:
        if abs(s["strike"] - spot) / spot > 0.03:
            continue
        total = abs(s.get("call_gex", 0)) + abs(s.get("put_gex", 0))
        if total > 0:
            call_pct = abs(s.get("call_gex", 0)) / total
            put_pct = abs(s.get("put_gex", 0)) / total
            if call_pct > 0.2 and put_pct > 0.2:
                stacked.append({"strike": s["strike"], "call_pct": round(call_pct, 2), "put_pct": round(put_pct, 2)})

    # Tug-of-war: zones where positive and negative GEX are within 3% of spot
    tug_of_war = []
    near_strikes = sorted([s for s in strikes if abs(s["strike"] - spot) / spot < 0.03], key=lambda r: r["strike"])
    for i in range(1, len(near_strikes)):
        a, b = near_strikes[i-1], near_strikes[i]
        if (a["gex"] > 0 and b["gex"] < 0) or (a["gex"] < 0 and b["gex"] > 0):
            tug_of_war.append({"low": a["strike"], "high": b["strike"],
                                "positive": a["gex"] if a["gex"] > 0 else b["gex"],
                                "negative": a["gex"] if a["gex"] < 0 else b["gex"]})

    # Total vega
    total_vega = sum((s.get("vega") or 0.0) for s in strikes)
    if math.isnan(total_vega) or math.isinf(total_vega):
        total_vega = 0.0

    # Total charm
    total_charm = sum((s.get("charm") or 0.0) for s in strikes)
    if math.isnan(total_charm) or math.isinf(total_charm):
        total_charm = 0.0

    # Total vomma
    total_vomma = sum((s.get("vomma") or 0.0) for s in strikes)
    if math.isnan(total_vomma) or math.isinf(total_vomma):
        total_vomma = 0.0

    # Total zomma
    total_zomma = sum((s.get("zomma") or 0.0) for s in strikes)
    if math.isnan(total_zomma) or math.isinf(total_zomma):
        total_zomma = 0.0

    # Charm flip point: weighted average of all strikes by absolute charm
    total_abs_charm = sum(abs(s.get("charm") or 0.0) for s in strikes)
    if total_abs_charm > 0:
        charm_flip = sum(s["strike"] * abs(s.get("charm") or 0.0) for s in strikes) / total_abs_charm
    else:
        charm_flip = spot

    # Max Pain: strike where total OI-weighted pain is minimized
    max_pain = None
    if strikes:
        strike_range = sorted(set(s["strike"] for s in strikes))
        min_pain = float("inf")
        for test_strike in strike_range:
            pain = 0.0
            for s in strikes:
                oi = s.get("total_oi", 0) or 0
                pain += oi * abs(s["strike"] - test_strike)
            if pain < min_pain:
                min_pain = pain
                max_pain = test_strike

    # Put/Call ratio
    total_call_oi = sum(s.get("call_oi", 0) or 0 for s in strikes)
    total_put_oi = sum(s.get("put_oi", 0) or 0 for s in strikes)
    put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None

    # ---- Risk Metrics (from gex-backtesting repo) ----

    # GCI: Gamma Concentration Index (Herfindahl-Hirschman)
    # Measures how concentrated gamma is across strikes. Range [0, 1].
    # 1/N if perfectly uniform; approaches 1.0 if all gamma at one strike.
    total_abs = sum(abs(s["gex"]) for s in strikes) or 1.0
    gamma_shares = [abs(s["gex"]) / total_abs for s in strikes]
    gci = sum(s * s for s in gamma_shares)

    # PGR: Protective Gamma Ratio
    # Fraction of total gamma within 20 points of spot.
    gdw_decay = 20.0  # decay constant for GDW
    near_spot = 20.0  # points for PGR window
    gamma_near = sum(abs(s["gex"]) for s in strikes if abs(s["strike"] - spot) <= near_spot)
    pgr = gamma_near / total_abs if total_abs > 0 else 0.0

    # GDW: Gamma Distance Weighted
    # Exponentially-weighted gamma favoring strikes near spot.
    gdw = sum(abs(s["gex"]) * math.exp(-abs(s["strike"] - spot) / gdw_decay) for s in strikes)

    # CAR: Convexity Acceleration Risk
    # Composite of zomma (60%) and vomma (40%) with time decay amplification.
    # Captures feedback loop risk: vol spike -> gamma change -> hedging -> more vol.
    # Time amplifier: 1/sqrt(TTE) capped at 30x. Use 1 day as default TTE.
    avg_tte = 1.0 / 252.0  # ~1 trading day default
    time_amp = min(30.0, 1.0 / math.sqrt(max(avg_tte, 0.001)))
    gamma_sign = -1.0 if total_gex < 0 else 1.0
    car_net = gamma_sign * (0.6 * total_zomma + 0.4 * total_vomma) * time_amp / 1e6
    car_gross = (0.6 * abs(total_zomma) + 0.4 * abs(total_vomma)) * time_amp / 1e6

    # Charm Risk: aggregate delta decay exposure
    charm_risk = total_charm / 1e6

    return {
        "king": king,
        "floors": floors[:5],
        "ceilings": ceilings[:5],
        "gatekeepers": gatekeepers[:6],
        "air_pockets": air_pockets,
        "polarity_level": polarity,
        "regime": regime,
        "total_gex": total_gex,
        "near_gex": near_gex,
        "vex_flip": vex_flip,
        "charm_flip": charm_flip,
        "max_pain": max_pain,
        "put_call_ratio": put_call_ratio,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "stacked_nodes": stacked[:10],
        "tug_of_war": tug_of_war[:5],
        "total_vega": total_vega,
        "total_charm": total_charm,
        "total_vomma": total_vomma,
        "total_zomma": total_zomma,
        "risk_metrics": {
            "gci": round(gci, 4),
            "pgr": round(pgr, 4),
            "gdw": round(gdw, 2),
            "car_net": round(car_net, 2),
            "car_gross": round(car_gross, 2),
            "charm_risk": round(charm_risk, 2),
            "time_amp": round(time_amp, 1),
        },
    }


# ----------------------------- Pattern Detection ------------------------------


def detect_patterns(strikes: list[dict[str, Any]], nodes: dict[str, Any], spot: float) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    if not strikes or spot <= 0:
        return patterns

    king = nodes.get("king")
    if not king:
        return patterns
    max_abs = abs(king["gex"]) or 1.0

    above = [s for s in strikes if s["strike"] > spot]
    below = [s for s in strikes if s["strike"] < spot]
    big_pos_above = [s for s in above if s["gex"] > 0.25 * max_abs]
    big_pos_below = [s for s in below if s["gex"] > 0.25 * max_abs]
    big_neg_above = [s for s in above if s["gex"] < -0.20 * max_abs]
    big_neg_below = [s for s in below if s["gex"] < -0.20 * max_abs]

    # Rug: positive above, negative below
    if big_pos_above and big_neg_below:
        patterns.append({
            "name": "Rug",
            "bias": "bearish",
            "severity": min(1.0, (big_pos_above[0]["gex"] + abs(big_neg_below[0]["gex"])) / (2 * max_abs)),
            "note": "Positive ceiling stacks above, negative below — rejection w/ pro-cyclical acceleration down.",
        })

    # Reverse Rug
    if big_pos_below and big_neg_above:
        patterns.append({
            "name": "Reverse Rug",
            "bias": "bullish",
            "severity": min(1.0, (big_pos_below[0]["gex"] + abs(big_neg_above[0]["gex"])) / (2 * max_abs)),
            "note": "Positive floor below, negative above — support holds, bounce runs.",
        })

    # Pika Cloud: 3+ positive nodes within ~1.5% strike range
    pos_sorted = sorted([s for s in strikes if s["gex"] > 0.15 * max_abs], key=lambda r: r["strike"])
    for i in range(len(pos_sorted)):
        cluster = [pos_sorted[i]]
        for j in range(i + 1, len(pos_sorted)):
            if (pos_sorted[j]["strike"] - cluster[0]["strike"]) / spot <= 0.015:
                cluster.append(pos_sorted[j])
            else:
                break
        if len(cluster) >= 3:
            lo = cluster[0]["strike"]
            hi = cluster[-1]["strike"]
            mid = (lo + hi) / 2
            patterns.append({
                "name": "Pika Cloud",
                "bias": "resistance" if mid > spot else "support",
                "severity": min(1.0, sum(c["gex"] for c in cluster) / (2 * max_abs)),
                "note": f"Dense positive cluster {lo:.2f}-{hi:.2f}. Inefficient transit zone.",
                "range": [lo, hi],
            })
            break

    # Beach Ball: spot near a major positive node but slightly past it
    near_king = abs(spot - king["strike"]) / spot < 0.01
    if king["gex"] > 0 and near_king and abs(spot - king["strike"]) > 0:
        side = "below" if spot < king["strike"] else "above"
        patterns.append({
            "name": "Beach Ball",
            "bias": "reversion",
            "severity": 0.7,
            "note": f"Spot stretched {side} king node — overshoot/reversion setup.",
        })

    # Whipsaw: high disagreement (multiple sign flips around spot)
    near = sorted([s for s in strikes if abs(s["strike"] - spot) / spot < 0.03], key=lambda r: r["strike"])
    sign_flips = 0
    for i in range(1, len(near)):
        if (near[i - 1]["gex"] > 0) != (near[i]["gex"] > 0):
            sign_flips += 1
    if sign_flips >= 3:
        patterns.append({
            "name": "Whipsaw",
            "bias": "trap",
            "severity": min(1.0, sign_flips / 6),
            "note": f"Conflicting signs near spot ({sign_flips} flips). Fade extremes only.",
        })

    # Rainbow Road: chaos — magnitude diffuse, no dominant node
    total_abs = sum(abs(s["gex"]) for s in strikes) or 1.0
    king_share = abs(king["gex"]) / total_abs
    if king_share < 0.08 and len(strikes) > 20:
        patterns.append({
            "name": "Rainbow Road",
            "bias": "do not trade",
            "severity": 1 - king_share * 10,
            "note": "No dominant structure. Pre/post-catalyst chaos. Sit out.",
        })

    return patterns


# ----------------------------- Tap Probability -------------------------------


def compute_gex_by_strike_volume(spot: float, contracts: list[dict[str, Any]], ticker: str) -> list[dict[str, Any]]:
    """Volume-weighted GEX — shows where the action is RIGHT NOW.
    Uses volume instead of OI for weighting. Same BS gamma formula."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: dict[float, dict[str, float]] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        # Use volume instead of OI for intraday focus
        vol = c.get("volume", 0) or 0
        if vol <= 0:
            continue
        gex_unit = dollar_gex_per_contract(gamma, vol, spot)
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
            "call_vol": 0.0, "put_vol": 0.0, "total_vol": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_vol"] += vol
            bucket["call_oi"] += c["oi"]
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_vol"] += vol
            bucket["put_oi"] += c["oi"]

