"""
Confluence Decoder - Skylit-style Heatseeker GEX Analytics
- Databento: real-time/EOD Open Interest via OPRA.PILLAR statistics + Live trades for Flowseeker
- yfinance: spot + IV from option chains (fallback for OI when Databento has no data)
- Polygon: stock aggs, tap-count history
- Black-Scholes gamma -> per-strike (and per-strike×expiry) GEX
- Node hierarchy, patterns, velocity, rolling, trinity
"""
from fastapi import FastAPI, APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta
import os
import json
import logging
import asyncio
import math
import time
import httpx
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm

from databento_provider import init_cache, fetch_oi_for_ticker, PARENT_MAP, stream_live_trades
from portfolio import Position, Portfolio, calc_position_size
from vol_analytics import (
    calc_iv_surface_data,
    calc_skew_metrics,
    calc_realized_volatility,
    calc_iv_rank_percentile,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("heatseeker")

app = FastAPI(title="Confluence Decoder")
api = APIRouter(prefix="/api")

# ----------------------------- Constants & Config -----------------------------

DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD"]
TRINITY = ["^SPX", "SPY", "QQQ"]
RISK_FREE_RATE = 0.045
DIV_YIELD = {"SPY": 0.013, "QQQ": 0.006, "^SPX": 0.013, "IWM": 0.012}

# Live window config (ET hours)
LIVE_WINDOW = {"start_hhmm": "09:00", "stop_hhmm": "10:30"}
PREFETCH_HHMM = "08:55"  # pre-fetch SPY OI 5 min before market open

# Cache for spot/chains so we don't slam yfinance
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SEC = 25


def cache_get(key: str):
    item = _cache.get(key)
    if not item:
        return None
    if time.time() - item["ts"] > CACHE_TTL_SEC:
        return None
    return item["data"]


def cache_set(key: str, data: Any):
    _cache[key] = {"ts": time.time(), "data": data}


# ============ Data Fetching Functions (moved here to maintain correct order) ============

def fetch_spot_and_chains(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """Returns spot + flattened option contracts (limited expiries near term)."""
    key = f"chain:{ticker}:{max_expiries}"
    hit = cache_get(key)
    if hit:
        return hit

    t = yf.Ticker(ticker)
    try:
        fi = t.fast_info
        spot = float(fi.get("lastPrice") or fi.get("last_price") or 0)
    except Exception:
        spot = 0.0
    if not spot:
        try:
            spot = float(t.history(period="1d")["Close"].iloc[-1])
        except Exception:
            spot = 0.0

    expiries = list(t.options or [])[:max_expiries]
    contracts: List[Dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()

    for exp in expiries:
        try:
            ch = t.option_chain(exp)
        except Exception as e:
            log.warning(f"chain fail {ticker} {exp}: {e}")
            continue
        exp_date = pd.to_datetime(exp).date()
        T = max((exp_date - today).days, 1) / 365.0
        for df, kind in [(ch.calls, "call"), (ch.puts, "put")]:
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                strike = float(row.get("strike", 0))
                oi = float(row.get("openInterest", 0) or 0)
                iv = float(row.get("impliedVolatility", 0) or 0)
                vol = float(row.get("volume", 0) or 0)
                if strike <= 0 or oi <= 0 or iv <= 0:
                    continue
                contracts.append({
                    "expiry": exp, "T": T, "type": kind,
                    "strike": strike, "oi": oi, "iv": iv, "volume": vol,
                })

    data = {"ticker": ticker, "spot": spot, "expiries": expiries, "contracts": contracts}
    cache_set(key, data)
    return data


# Tickers allowed to use Databento OI (paid). Default: SPY only. Persisted in Mongo (db.live_policy).
DEFAULT_PAID_TICKERS = {"SPY"}
PAID_TICKERS: set = set(DEFAULT_PAID_TICKERS)

# Session tracking for cost meter
_session_state: Dict[str, Any] = {
    "live_tape_active": False,
    "live_tape_ticker": None,
    "live_tape_started_at": None,
    "live_tape_auto_stop_at": None,
    "live_tape_session_id": None,
    "msg_count": 0,
}


def _in_window_now_et() -> bool:
    """Check if current time is within configured live window (US/Eastern)."""
    try:
        from zoneinfo import ZoneInfo
        et = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        et = datetime.now(timezone.utc) - timedelta(hours=5)
    hhmm = et.strftime("%H:%M")
    return LIVE_WINDOW["start_hhmm"] <= hhmm <= LIVE_WINDOW["stop_hhmm"]


async def fetch_spot_and_chains_merged(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """yfinance for spot+IV + Databento for OI (only if ticker is in PAID_TICKERS).
    Falls back to pure yfinance for free-tier tickers."""
    yf_data = await asyncio.to_thread(fetch_spot_and_chains, ticker, max_expiries)
    spot = yf_data["spot"]

    # Free-tier short-circuit: use yfinance OI only
    short = ticker.upper().replace("^", "")
    if short not in PAID_TICKERS:
        for c in yf_data["contracts"]:
            c["oi_source"] = "yfinance"
        return {**yf_data, "data_source": "yfinance"}

    dbn_oi = {}
    try:
        dbn_oi = await fetch_oi_for_ticker(ticker)
    except Exception as e:
        log.warning(f"databento OI lookup fail {ticker}: {e}")

    if not dbn_oi:
        for c in yf_data["contracts"]:
            c["oi_source"] = "yfinance"
        return {**yf_data, "data_source": "yfinance"}

    # Build (strike, expiry, type) -> OI map from Databento
    dbn_map: Dict[tuple, int] = {}
    for sym, c in dbn_oi.items():
        dbn_map[(c["strike"], c["expiry"], c["type"])] = c["oi"]

    # Overlay Databento OI onto yfinance IV/strike contracts
    yf_keys = set()
    for c in yf_data["contracts"]:
        key = (c["strike"], c["expiry"], c["type"])
        dbn_val = dbn_map.get(key)
        if dbn_val is not None:
            c["oi"] = max(c["oi"], dbn_val)
            c["oi_source"] = "databento"
        else:
            c["oi_source"] = "yfinance"
        yf_keys.add(key)

    # Add DBN-only contracts
    today = datetime.now(timezone.utc).date()
    iv_lists: Dict[str, list] = {}
    for c in yf_data["contracts"]:
        iv_lists.setdefault(c["expiry"], []).append(c["iv"])
    iv_avg_by_expiry: Dict[str, float] = {e: (sum(vs) / len(vs)) for e, vs in iv_lists.items() if vs}

    for (strike, expiry, typ), oi in dbn_map.items():
        if (strike, expiry, typ) in yf_keys:
            continue
        if expiry not in iv_avg_by_expiry:
            continue
        try:
            exp_d = datetime.strptime(expiry, "%Y-%m-%d").date()
        except Exception:
            continue
        T = max((exp_d - today).days, 1) / 365.0
        yf_data["contracts"].append({
            "expiry": expiry, "T": T, "type": typ, "strike": strike,
            "oi": oi, "iv": iv_avg_by_expiry[expiry], "volume": 0,
            "oi_source": "databento",
        })

    yf_data["data_source"] = "databento+yfinance"
    yf_data["dbn_contracts"] = len(dbn_map)
    return yf_data


# ----------------------------- GEX Aggregation --------------------------------

def compute_gex_by_strike(spot: float, contracts: List[Dict[str, Any]], ticker: str = "") -> List[Dict[str, Any]]:
    """Per-strike net GEX, VEX, and Vega. Convention: dealer-positive convention."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: Dict[float, Dict[str, float]] = {}
    for c in contracts:
        oi = c.get("oi", 0) or 0
        if oi <= 0 or (isinstance(oi, float) and math.isnan(oi)):
            continue
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        vanna = bs_vanna(spot, c["strike"], c["T"], c["iv"], q=q)
        vega_val = bs_vega(spot, c["strike"], c["T"], c["iv"], q=q)
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q=q, kind=c["type"])
        vomma = bs_vomma(spot, c["strike"], c["T"], c["iv"], q=q)
        zomma = bs_zomma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0 and abs(vanna) <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        vex_unit = vanna * oi * 100.0 * spot * 0.01
        vega_unit = vega_val * oi * 100.0
        charm_unit = charm * oi * 100.0 * spot * 0.01
        vomma_unit = vomma * oi * 100.0
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


def compute_gex_grid(spot: float, contracts: List[Dict[str, Any]], ticker: str = "") -> Dict[str, Any]:
    """2D grid: GEX per (strike, expiry). Skylit-style heatmap layout."""
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}, "charm_grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    grid: Dict[str, Dict[float, float]] = {}
    charm_grid: Dict[str, Dict[float, float]] = {}
    strike_totals: Dict[float, float] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q=q, kind=c["type"])
        if gamma <= 0:
            continue
        gex_unit = gamma * c["oi"] * 100.0 * spot * spot * 0.01
        charm_unit = charm * c["oi"] * 100.0 * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        cell = sign * gex_unit
        charm_cell = sign * charm_unit
        d = grid.setdefault(c["expiry"], {})
        d[c["strike"]] = d.get(c["strike"], 0.0) + cell
        dc = charm_grid.setdefault(c["expiry"], {})
        dc[c["strike"]] = dc.get(c["strike"], 0.0) + charm_cell
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
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }
# Import from shared module to avoid circular imports with portfolio.py
from bs_greeks import (
    bs_gamma, bs_delta, bs_vanna, bs_charm, bs_vomma, bs_zomma, bs_vega,
    RISK_FREE_RATE as BS_RISK_FREE_RATE,
)
RISK_FREE_RATE = BS_RISK_FREE_RATE


# ----------------------------- Implied Move & Probability (from EzOptions) ------

def calc_implied_move(spot: float, contracts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
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
    from scipy.stats import norm as _norm
    call_iv = atm_calls[0].get("iv", 0.2)
    put_iv = atm_puts[0].get("iv", 0.2)
    T = atm_calls[0].get("T", 1/365)
    if T <= 0:
        T = 1/365
    avg_iv = (call_iv + put_iv) / 2
    # Straddle price ≈ S * σ * sqrt(T) * sqrt(2/π) for ATM
    straddle = spot * avg_iv * math.sqrt(T) * math.sqrt(2 / math.pi)
    # More accurate: use 0.8 * S * σ * sqrt(T) (market standard approximation)
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


def calc_probability_distribution(spot: float, contracts: List[Dict[str, Any]],
                                   risk_free_rate: float = RISK_FREE_RATE) -> List[Dict[str, Any]]:
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
            iv = calls[0].get("iv", 0.2)
            T = calls[0].get("T", 1/365)
        elif puts:
            iv = puts[0].get("iv", 0.2)
            T = puts[0].get("T", 1/365)
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


def calc_aggregate_gex_curve(spot: float, contracts: List[Dict[str, Any]],
                              ticker: str = "") -> List[Dict[str, float]]:
    """Aggregate GEX curve: total GEX if spot moved to each price point.
    Shows how dealer gamma changes as price moves."""
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
    curve = []
    price = lo
    while price <= hi:
        total_gex = 0.0
        for c in contracts:
            oi = c.get("oi", 0) or 0
            if oi <= 0:
                continue
            gamma = bs_gamma(price, c["strike"], c["T"], c["iv"], q=q)
            gex = gamma * oi * 100.0 * price * price * 0.01
            sign = 1.0 if c["type"] == "call" else -1.0
            total_gex += sign * gex
        curve.append({"price": round(price, 2), "gex": round(total_gex / 1e9, 4) if not (math.isnan(total_gex) or math.isinf(total_gex)) else 0.0})
        price += step
    return curve


# ----------------------------- Opportunity Detection (from GEX-Dashboard) ------

def detect_opportunities(strikes: List[Dict[str, Any]], nodes: Dict[str, Any],
                          spot: float, contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Detect trading opportunities from GEX analysis.
    Categories: gamma_squeeze, wall_support, wall_resistance, vol_expansion, vol_compression, pin_risk, gamma_ladder"""
    opportunities = []
    if not strikes or spot <= 0:
        return opportunities

    king = nodes.get("king")
    if not king:
        return opportunities
    max_abs = abs(king.get("gex", 0)) or 1.0
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
                "description": f"Negative gamma regime. Dealers amplifying moves. Expect increased volatility.",
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
                "description": f"Positive gamma regime. Dealers dampening moves. Good for selling premium.",
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
                dte = (exp_date - datetime.now(timezone.utc).date()).days
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

def classify_nodes(strikes: List[Dict[str, Any]], spot: float) -> Dict[str, Any]:
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
    run_strikes: List[float] = []
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
    if total_abs_gex > 0:
        polarity = sum(s["strike"] * abs(s["gex"]) for s in strikes) / total_abs_gex
    else:
        polarity = spot

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

def detect_patterns(strikes: List[Dict[str, Any]], nodes: Dict[str, Any], spot: float) -> List[Dict[str, Any]]:
    patterns: List[Dict[str, Any]] = []
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
            lo = cluster[0]["strike"]; hi = cluster[-1]["strike"]
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

async def tap_counts(ticker: str, strikes: List[float], days: int = 5) -> Dict[float, int]:
    """Count how many days price crossed each strike in last N trading days using Polygon aggs."""
    if not POLYGON_API_KEY or not strikes:
        return {s: 0 for s in strikes}
    end = datetime.now(timezone.utc).date()
    start = end - pd.Timedelta(days=days * 2)
    pg_ticker = ticker.replace("^SPX", "I:SPX") if ticker.startswith("^") else ticker
    url = f"https://api.polygon.io/v2/aggs/ticker/{pg_ticker}/range/1/day/{start}/{end}"
    out = {s: 0 for s in strikes}
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(url, params={"apiKey": POLYGON_API_KEY, "limit": days * 2})
            data = r.json()
        if not data.get("results"):
            return out
        results = data["results"][-days:]
        for bar in results:
            lo = bar.get("l", 0); hi = bar.get("h", 0)
            for s in strikes:
                if lo <= s <= hi:
                    out[s] += 1
    except Exception as e:
        log.warning(f"tap_counts fail {ticker}: {e}")
    return out


# ----------------------------- Snapshot persistence (velocity/rolling) --------

async def save_snapshot(ticker: str, payload: Dict[str, Any]):
    try:
        doc = {
            "ticker": ticker,
            "ts": datetime.now(timezone.utc).isoformat(),
            "spot": payload["spot"],
            "king_strike": payload["nodes"]["king"]["strike"] if payload["nodes"].get("king") else None,
            "king_gex": payload["nodes"]["king"]["gex"] if payload["nodes"].get("king") else None,
            "top_floor": payload["nodes"]["floors"][0]["strike"] if payload["nodes"].get("floors") else None,
            "top_ceiling": payload["nodes"]["ceilings"][0]["strike"] if payload["nodes"].get("ceilings") else None,
            "regime": payload["nodes"].get("regime"),
            "strikes_compact": [{"strike": s["strike"], "gex": s["gex"]} for s in payload["strikes"][:200]],
        }
        await db.snapshots.insert_one(doc)
        # Keep last 50 per ticker
        cursor = db.snapshots.find({"ticker": ticker}, {"_id": 1}).sort("ts", -1).skip(50)
        ids = [d["_id"] async for d in cursor]
        if ids:
            await db.snapshots.delete_many({"_id": {"$in": ids}})
    except Exception as e:
        log.warning(f"snapshot save fail: {e}")


async def velocity_and_rolling(ticker: str, current_nodes: Dict[str, Any]) -> Dict[str, Any]:
    """Compute rate of change vs prior snapshot + rolling floor/ceiling sequence."""
    cur = db.snapshots.find({"ticker": ticker}, {"_id": 0}).sort("ts", -1).limit(10)
    history = [d async for d in cur]
    if len(history) < 1:
        return {"velocity_score": 0, "rolling_floor": "stable", "rolling_ceiling": "stable", "history": []}

    floor_seq = [h["top_floor"] for h in history if h.get("top_floor")][:5]
    ceiling_seq = [h["top_ceiling"] for h in history if h.get("top_ceiling")][:5]

    def trend(seq):
        if len(seq) < 2:
            return "stable"
        # seq is newest-first; we want oldest -> newest order
        seq = list(reversed(seq))
        ups = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1])
        downs = sum(1 for i in range(1, len(seq)) if seq[i] < seq[i - 1])
        if ups >= 2 and downs == 0:
            return "rolling_up"
        if downs >= 2 and ups == 0:
            return "rolling_down"
        return "stable"

    # Velocity: how much the strike-level GEX has changed since last snapshot
    velocity = 0.0
    if history:
        prev = history[0]
        prev_map = {s["strike"]: s["gex"] for s in prev.get("strikes_compact", [])}
        cur_map = {s["strike"]: s["gex"] for s in current_nodes.get("strikes_compact", [])}
        common = set(prev_map.keys()) & set(cur_map.keys())
        if common:
            deltas = [abs(cur_map[k] - prev_map[k]) for k in common]
            base = max(sum(abs(prev_map[k]) for k in common), 1.0)
            velocity = min(1.0, sum(deltas) / base)

    return {
        "velocity_score": round(velocity, 3),
        "rolling_floor": trend(floor_seq),
        "rolling_ceiling": trend(ceiling_seq),
        "floor_sequence": floor_seq,
        "ceiling_sequence": ceiling_seq,
        "snapshots_count": len(history) + 1,
    }


# ----------------------------- Top Movers (Polygon) ---------------------------

POPULAR_UNIVERSE = ["AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD", "AVGO", "NFLX",
                    "COIN", "PLTR", "MU", "SMCI", "BABA", "CRM", "ORCL", "GME", "AMC", "INTC",
                    "DIS", "BA", "JPM", "GS", "XOM", "UBER", "SHOP", "SOFI", "F", "MARA"]


_movers_cache: Dict[str, Any] = {"ts": 0, "data": []}


def _fetch_movers_sync() -> List[Dict[str, Any]]:
    """Use yfinance bulk download for prev-day movers (fast, no rate limit)."""
    try:
        df = yf.download(POPULAR_UNIVERSE, period="2d", interval="1d",
                         group_by="ticker", progress=False, threads=True, auto_adjust=False)
    except Exception as e:
        log.warning(f"yfinance movers fail: {e}")
        return []
    out: List[Dict[str, Any]] = []
    for sym in POPULAR_UNIVERSE:
        try:
            sub = df[sym].dropna()
            if len(sub) < 2:
                continue
            prev_close = float(sub["Close"].iloc[-2])
            last_close = float(sub["Close"].iloc[-1])
            day_open = float(sub["Open"].iloc[-1])
            hi = float(sub["High"].iloc[-1]); lo = float(sub["Low"].iloc[-1])
            vol = float(sub["Volume"].iloc[-1])
            pct = ((last_close - prev_close) / prev_close * 100) if prev_close else 0
            out.append({"ticker": sym, "open": day_open, "close": last_close, "pct": round(pct, 2),
                        "volume": vol, "high": hi, "low": lo, "prev_close": prev_close})
        except Exception:
            continue
    return out


async def top_movers_polygon(limit: int = 10) -> List[Dict[str, Any]]:
    """Top movers via yfinance bulk download. Cached 60s."""
    if time.time() - _movers_cache["ts"] < 60 and _movers_cache["data"]:
        return sorted(_movers_cache["data"], key=lambda r: abs(r["pct"]), reverse=True)[:limit]
    rows = await asyncio.to_thread(_fetch_movers_sync)
    _movers_cache["ts"] = time.time()
    _movers_cache["data"] = rows
    return sorted(rows, key=lambda r: abs(r["pct"]), reverse=True)[:limit]


# ----------------------------- Models -----------------------------------------

class HeatmapResp(BaseModel):
    ticker: str
    spot: float
    expiries_used: List[str]
    strikes: List[Dict[str, Any]]
    nodes: Dict[str, Any]
    patterns: List[Dict[str, Any]]
    velocity: Dict[str, Any]
    tap_counts: Dict[str, int]
    asof: str


# ----------------------------- Volume-Weighted GEX (for intraday) --------------

def compute_gex_by_strike_volume(spot: float, contracts: List[Dict[str, Any]], ticker: str) -> List[Dict[str, Any]]:
    """Volume-weighted GEX — shows where the action is RIGHT NOW.
    Uses volume instead of OI for weighting. Same BS gamma formula."""
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: Dict[float, Dict[str, float]] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        # Use volume instead of OI for intraday focus
        vol = c.get("volume", 0) or 0
        if vol <= 0:
            continue
        gex_unit = gamma * vol * 100.0 * spot * spot * 0.01
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
        bucket["total_oi"] += c["oi"]
        bucket["total_vol"] += vol

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


# ----------------------------- Heatmap Core -----------------------------------

async def build_heatmap(ticker: str, max_expiries: int = 4, with_taps: bool = True, mode: str = "day", dte: Optional[int] = None, scalp: bool = False) -> Dict[str, Any]:
    if mode == "swing":
        max_expiries = max(max_expiries, 8)
    raw = await fetch_spot_and_chains_merged(ticker, max_expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    today = datetime.now(timezone.utc).date()

    # Scalp mode: force 0DTE only, tight band, volume-weighted
    if scalp:
        dte = 0
        mode = "scalp"

    # DTE filter
    if dte is not None:
        cutoff = today + timedelta(days=dte)
        raw["contracts"] = [c for c in raw["contracts"]
                            if datetime.strptime(c["expiry"], "%Y-%m-%d").date() <= cutoff]
        raw["expiries"] = sorted({c["expiry"] for c in raw["contracts"]})

    # Choose GEX computation: volume-weighted for scalp, OI for normal
    if scalp:
        strikes = compute_gex_by_strike_volume(spot, raw["contracts"], ticker)
        grid = {"expiries": raw["expiries"], "strikes": [], "grid": {}, "strike_totals": []}
    else:
        strikes = compute_gex_by_strike(spot, raw["contracts"], ticker)
        grid = compute_gex_grid(spot, raw["contracts"], ticker)

    # Band: scalp=±2%, day=±15%, swing=±25%
    if scalp:
        band = 0.02
    elif mode == "swing":
        band = 0.25
    else:
        band = 0.15

    strikes = [s for s in strikes if abs(s["strike"] - spot) / spot <= band]
    if not scalp:
        grid["strikes"] = [k for k in grid["strikes"] if abs(k - spot) / spot <= band]
        grid["strike_totals"] = [s for s in grid["strike_totals"] if abs(s["strike"] - spot) / spot <= band]

    # Tag fresh/tested via tap counts
    tap_map: Dict[float, int] = {}
    if with_taps and not scalp:
        tap_map = await tap_counts(ticker, [s["strike"] for s in strikes], days=5)
    for s in strikes:
        if scalp:
            s["taps"] = 0
            s["lifecycle"] = "live"
            s["tap_prob"] = 1.0
        else:
            tc = tap_map.get(s["strike"], 0)
            s["taps"] = tc
            if tc == 0:
                s["lifecycle"] = "fresh"
            elif tc == 1:
                s["lifecycle"] = "tested"
            elif tc == 2:
                s["lifecycle"] = "delivered"
            else:
                s["lifecycle"] = "decaying"
            s["tap_prob"] = [0.80, 0.66, 0.33, 0.10][min(tc, 3)]

    nodes = classify_nodes(strikes, spot)
    patterns = detect_patterns(strikes, nodes, spot)

    # --- New analytics (from EzOptions + GEX-Dashboard) ---
    implied_move = calc_implied_move(spot, raw["contracts"])
    prob_distribution = calc_probability_distribution(spot, raw["contracts"])
    aggregate_curve = calc_aggregate_gex_curve(spot, raw["contracts"], ticker)
    opportunities = detect_opportunities(strikes, nodes, spot, raw["contracts"])

    # --- Institutional vol analytics ---
    iv_surface = calc_iv_surface_data(spot, raw["contracts"])
    skew = calc_skew_metrics(spot, raw["contracts"])
    # Run yfinance calls in parallel threads to avoid blocking
    rv_task = asyncio.create_task(asyncio.to_thread(calc_realized_volatility, ticker.replace("^", ""), 20))
    iv_rank_task = asyncio.create_task(asyncio.to_thread(calc_iv_rank_percentile, ticker.replace("^", ""), skew.get("atm_iv", 0.2)))
    rv = await rv_task
    iv_rank = await iv_rank_task
    if rv:
        iv_rank["rv_iv_spread"] = round(skew.get("atm_iv", 0) - rv.get("rv_close", 0), 4)
        iv_rank["rv_close"] = rv.get("rv_close")

    # Velocity & rolling
    velocity = await velocity_and_rolling(ticker, {"strikes_compact": [{"strike": s["strike"], "gex": s["gex"]} for s in strikes]})

    payload = {
        "ticker": ticker,
        "spot": spot,
        "expiries_used": raw["expiries"],
        "strikes": strikes,
        "grid": grid,
        "nodes": nodes,
        "patterns": patterns,
        "velocity": velocity,
        "tap_counts": {str(k): v for k, v in tap_map.items()},
        "data_source": raw.get("data_source", "yfinance"),
        "mode": mode,
        "asof": datetime.now(timezone.utc).isoformat(),
        # New analytics
        "implied_move": implied_move,
        "prob_distribution": prob_distribution,
        "aggregate_curve": aggregate_curve,
        "opportunities": opportunities,
        # Institutional vol analytics
        "iv_surface": iv_surface,
        "skew": skew,
        "iv_rank": iv_rank,
        "realized_vol": rv,
    }

    asyncio.create_task(save_snapshot(ticker, payload))
    return _sanitize(payload)


def _sanitize(obj):
    """Replace NaN/Inf with None recursively for JSON safety."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


# ----------------------------- API Endpoints ----------------------------------

@api.get("/")
async def root():
    return {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(timezone.utc).isoformat()}


@api.get("/tickers")
async def list_tickers():
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


@api.get("/heatmap/{ticker}")
async def heatmap(ticker: str, expiries: int = Query(4, ge=1, le=12), taps: bool = True, mode: str = Query("day", pattern="^(day|swing|scalp)$"), dte: Optional[int] = Query(None, ge=0, le=30, description="DTE filter: 0=today only, 1=today+tomorrow, 7=within week, None=all"), scalp: bool = Query(False, description="Scalp mode: 0DTE only, volume-weighted GEX, ±2% band")):
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode, dte, scalp)


@api.get("/trinity")
async def trinity(tickers: str = Query(",".join(TRINITY)), mode: str = Query("day", pattern="^(day|swing)$"), dte: Optional[int] = Query(None, ge=0, le=30)):
    syms = [t.strip() for t in tickers.split(",") if t.strip()]
    out: Dict[str, Any] = {}
    results = await asyncio.gather(*[build_heatmap(s, 3, True, mode, dte) for s in syms], return_exceptions=True)
    for sym, res in zip(syms, results):
        if isinstance(res, Exception):
            out[sym] = {"error": str(res)}
        else:
            out[sym] = res
    # Confluence score: count how many tickers share each regime/bias
    regimes = [r["nodes"]["regime"] for r in out.values() if isinstance(r, dict) and r.get("nodes")]
    biases = []
    for r in out.values():
        if isinstance(r, dict) and r.get("patterns"):
            biases.extend(p["bias"] for p in r["patterns"])
    if regimes:
        most_regime = max(set(regimes), key=regimes.count)
        confluence = regimes.count(most_regime) / len(regimes)
    else:
        most_regime = "unknown"
        confluence = 0
    return {
        "tickers": out,
        "alignment": {
            "regime": most_regime,
            "confluence": round(confluence, 2),
            "biases": list(set(biases)),
            "verdict": (
                "full_alignment" if confluence == 1 and regimes else
                "partial_alignment" if confluence >= 0.66 else
                "divergence"
            ),
        },
        "asof": datetime.now(timezone.utc).isoformat(),
    }


@api.get("/movers")
async def movers(limit: int = 10):
    rows = await top_movers_polygon(limit=limit)
    return {"results": rows, "asof": datetime.now(timezone.utc).isoformat()}


@api.get("/history/{ticker}")
async def history(ticker: str, limit: int = 30):
    cursor = db.snapshots.find({"ticker": ticker}, {"_id": 0, "strikes_compact": 0}).sort("ts", -1).limit(limit)
    rows = [d async for d in cursor]
    return {"ticker": ticker, "snapshots": rows}


@api.get("/patterns/glossary")
async def glossary():
    return {
        "Rug": "Bearish: positive above + negative below spot. Rejection accelerates down.",
        "Reverse Rug": "Bullish: positive below + negative above spot. Support + pro-cyclical bounce.",
        "Pika Cloud": "Dense cluster of positive nodes. Gravity well — chops/sticks.",
        "Beach Ball": "Overshoot of major positive node — reversion back through.",
        "Whipsaw": "Conflicting signs near spot. Fade extremes only.",
        "Rainbow Road": "No structure. Sit out.",
        "King Node": "Largest absolute exposure — structural center of gravity.",
        "Floor": "Largest positive node below spot — mechanical support.",
        "Ceiling": "Largest positive node above spot — mechanical resistance.",
        "Gatekeeper": "Mid-magnitude node between spot and king. Checkpoint.",
        "Air Pocket": "Low-exposure stretch. Pathway, not target.",
    }


# ----------------------------- Drilldown / Contract details -------------------

@api.get("/contract/{ticker}")
async def contract_drilldown(ticker: str, expiry: Optional[str] = None, strike: Optional[float] = None):
    """Per-contract details: strike OI/IV breakdown, call vs put.
    Returns rows for ALL strikes at given expiry, or all expiries at given strike."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, 8)
    spot = raw["spot"]
    rows: List[Dict[str, Any]] = []
    for c in raw["contracts"]:
        if expiry and c["expiry"] != expiry:
            continue
        if strike and abs(c["strike"] - strike) > 0.01:
            continue
        q = DIV_YIELD.get(t, 0.0)
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        delta = bs_delta(spot, c["strike"], c["T"], c["iv"], q, c["type"])
        gex = gamma * c["oi"] * 100 * spot * spot * 0.01 * (1 if c["type"] == "call" else -1)
        rows.append({
            **c,
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "gex": gex,
        })
    return _sanitize({"ticker": t, "spot": spot, "rows": rows,
                      "count": len(rows), "data_source": raw.get("data_source")})


# ----------------------------- Flowseeker (SSE) -------------------------------

@api.get("/flow/{ticker}")
async def flow_stream(ticker: str, request: Request, max_seconds: int = Query(120, ge=10, le=600), enforce_window: bool = Query(True)):
    """SSE stream of live OPRA trades via Databento Live.
    Requires a Databento Live OPRA.PILLAR license (separate from Historical)."""
    t = ticker.strip().upper().replace("^", "")

    # Check Databento key exists
    key = os.environ.get("DATABENTO_API_KEY", "")
    if not key:
        async def no_key():
            err = {"error": "Databento API key not configured.",
                   "hint": "Set DATABENTO_API_KEY in backend/.env"}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"
            await asyncio.sleep(3)
        return StreamingResponse(no_key(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Gate: paid tickers check (before expensive license pre-flight)
    if t not in PAID_TICKERS:
        async def deny():
            yield f"event: error\ndata: {json.dumps({'error': f'{t} not in paid tickers. POST /api/live/policy to enable.'})}\n\n"
            await asyncio.sleep(3)
        return StreamingResponse(deny(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Gate: trading window check (before expensive license pre-flight)
    if enforce_window and not _in_window_now_et():
        async def out_of_window():
            window_str = f"{LIVE_WINDOW['start_hhmm']}-{LIVE_WINDOW['stop_hhmm']} ET"
            err = {"error": f"Outside live window ({window_str}). Toggle 'override window' to bypass.",
                   "window": LIVE_WINDOW}
            yield f"event: error\ndata: {json.dumps(err)}\n\n"
            await asyncio.sleep(3)
        return StreamingResponse(out_of_window(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Pre-flight: try to detect missing Live license early
    import databento as _db
    _license_err = None
    try:
        _test = _db.Live(key=key)
        _test.subscribe(dataset="OPRA.PILLAR", schema="trades", stype_in="parent", symbols="SPY.OPT")
        del _test
    except Exception as _e:
        _license_err = str(_e)
    if _license_err is not None:
        _le = _license_err  # capture for closure
        async def no_license():
            err = {
                "error": "Databento Live OPRA.PILLAR license required.",
                "detail": _le,
                "hint": "Your key has Historical data access but NOT Live streaming. These are separate entitlements.",
                "cost": "~$0.50-1.00 per SPY session. Your $125 credits can cover this.",
                "upgrade": "https://databento.com/dashboard/licenses → Add OPRA.PILLAR Live",
                "docs": "https://databento.com/docs/live/opra"
            }
            yield f"event: warning\ndata: {json.dumps(err)}\n\n"
            yield f"event: end\ndata: {json.dumps({'status': 'no_live_license'})}\n\n"
            await asyncio.sleep(3)
        return StreamingResponse(no_license(), media_type="text/event-stream",
                                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    parent = PARENT_MAP.get(t, f"{t}.OPT")
    queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    stop = asyncio.Event()

    # Begin session record
    import uuid
    session_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    auto_stop_at = (datetime.now(timezone.utc) + timedelta(seconds=max_seconds)).isoformat()
    _session_state.update({
        "live_tape_active": True,
        "live_tape_ticker": t,
        "live_tape_started_at": started_at,
        "live_tape_auto_stop_at": auto_stop_at,
        "live_tape_session_id": session_id,
        "msg_count": 0,
    })
    await db.live_sessions.insert_one({
        "session_id": session_id, "ticker": t, "parent": parent,
        "started_at": started_at, "auto_stop_at": auto_stop_at,
        "max_seconds": max_seconds, "msg_count": 0, "est_cost_usd": 0.0,
    })

    async def producer():
        try:
            await stream_live_trades(parent, queue, stop)
        finally:
            await queue.put({"_eof": True})

    task = asyncio.create_task(producer())
    deadline = time.time() + max_seconds

    async def gen():
        msg_count = 0
        bytes_count = 0
        first_msg_deadline = time.time() + 15  # wait 15s for first trade to detect license issues
        license_warned = False
        try:
            yield f"event: ready\ndata: {json.dumps({'parent': parent, 'session_id': session_id, 'auto_stop_at': auto_stop_at})}\n\n"
            while time.time() < deadline:
                if await request.is_disconnected() or stop.is_set() or not _session_state.get("live_tape_active"):
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # No trades yet — if past first-msg window and still nothing, warn about license
                    if not license_warned and time.time() > first_msg_deadline and msg_count == 0:
                        license_warned = True
                        warn = {"warning": "No trades received after 15s. Your Databento key may lack the OPRA Live license.",
                                "hint": "OPRA.PILLAR Live is a separate paid entitlement from Historical data. Check your Databento dashboard → Licenses.",
                                "docs": "https://databento.com/docs/live/opra"}
                        yield f"event: warning\ndata: {json.dumps(warn)}\n\n"
                    yield ": ping\n\n"
                    continue
                if msg.get("_eof"):
                    yield "event: end\ndata: {}\n\n"
                    break
                if msg.get("_error"):
                    yield f"event: error\ndata: {json.dumps(msg)}\n\n"
                    break
                payload = json.dumps(msg)
                msg_count += 1
                bytes_count += len(payload)
                _session_state["msg_count"] = msg_count
                yield f"data: {payload}\n\n"
        finally:
            stop.set()
            try:
                task.cancel()
            except Exception:
                pass
            # estimate cost: OPRA Live is roughly $1 per GB; conservative $0.000002/message
            est_cost = round(max(bytes_count / (1024**3), msg_count * 0.000002), 4)
            ended_at = datetime.now(timezone.utc).isoformat()
            await db.live_sessions.update_one(
                {"session_id": session_id},
                {"$set": {"ended_at": ended_at, "msg_count": msg_count,
                          "bytes": bytes_count, "est_cost_usd": est_cost}},
            )
            _session_state.update({
                "live_tape_active": False,
                "live_tape_ticker": None,
                "live_tape_session_id": None,
            })

    return StreamingResponse(gen(), media_type="text/event-stream")


@api.get("/databento/usage")
async def dbn_usage():
    """Quick view of Databento cache stats + estimated cost."""
    try:
        n = await db.databento_oi.count_documents({})
        recent = []
        async for doc in db.databento_oi.find({}, {"_id": 0, "parent": 1, "day": 1, "count": 1, "fetched_at": 1}).sort("fetched_at", -1).limit(20):
            recent.append(doc)
        # rough cost estimate: $0.15 per OI snapshot
        est_oi_cost = round(n * 0.15, 2)

        # Live tape sessions
        sessions = []
        async for s in db.live_sessions.find({}, {"_id": 0}).sort("started_at", -1).limit(20):
            sessions.append(s)
        est_tape_cost = sum(s.get("est_cost_usd", 0) for s in sessions)

        total = round(est_oi_cost + est_tape_cost, 2)
        budget = 125.0
        return {
            "cached_days": n,
            "recent": recent,
            "live_sessions": sessions,
            "est_oi_cost_usd": est_oi_cost,
            "est_tape_cost_usd": round(est_tape_cost, 2),
            "est_total_cost_usd": total,
            "budget_usd": budget,
            "budget_remaining_usd": round(budget - total, 2),
            "budget_pct_used": round((total / budget) * 100, 1) if budget else 0,
            "paid_tickers": sorted(PAID_TICKERS),
            "live_window_et": LIVE_WINDOW,
            "live_tape_state": _session_state,
            "in_window_now": _in_window_now_et(),
        }
    except Exception as e:
        return {"error": str(e)}


# ----------------------------- Live policy & spot refresh ---------------------

class LivePolicyReq(BaseModel):
    paid_tickers: Optional[List[str]] = None
    window_start: Optional[str] = None  # "HH:MM" ET
    window_stop: Optional[str] = None


@api.post("/live/policy")
async def set_live_policy(req: LivePolicyReq):
    """Update which tickers may use Databento (paid) + the live window. Persisted in Mongo."""
    global PAID_TICKERS
    if req.paid_tickers is not None:
        PAID_TICKERS = set(t.upper().replace("^", "") for t in req.paid_tickers)
    if req.window_start:
        LIVE_WINDOW["start_hhmm"] = req.window_start
    if req.window_stop:
        LIVE_WINDOW["stop_hhmm"] = req.window_stop
    await db.live_policy.update_one(
        {"_id": "singleton"},
        {"$set": {"paid_tickers": sorted(PAID_TICKERS), "live_window": LIVE_WINDOW,
                  "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"paid_tickers": sorted(PAID_TICKERS), "live_window_et": LIVE_WINDOW}


async def _load_policy_from_mongo():
    global PAID_TICKERS
    try:
        doc = await db.live_policy.find_one({"_id": "singleton"})
        if doc:
            PAID_TICKERS = set(doc.get("paid_tickers") or DEFAULT_PAID_TICKERS)
            lw = doc.get("live_window") or {}
            if lw.get("start_hhmm"):
                LIVE_WINDOW["start_hhmm"] = lw["start_hhmm"]
            if lw.get("stop_hhmm"):
                LIVE_WINDOW["stop_hhmm"] = lw["stop_hhmm"]
            log.info(f"live policy loaded: paid={sorted(PAID_TICKERS)} window={LIVE_WINDOW}")
    except Exception as e:
        log.warning(f"live policy load fail: {e}")


# ---------- Scheduled pre-fetch (APScheduler) ----------
_scheduler_started = False


async def _prefetch_paid_oi():
    """Pre-fetch OI for all paid tickers so first request after open is instant."""
    log.info(f"prefetch OI for {sorted(PAID_TICKERS)}")
    for t in list(PAID_TICKERS):
        try:
            r = await fetch_oi_for_ticker(t)
            log.info(f"  prefetched {t}: {len(r)} contracts")
        except Exception as e:
            log.warning(f"  prefetch {t} fail: {e}")


async def _scheduler_loop():
    """Lightweight scheduler — fires once per day at PREFETCH_HHMM ET. No extra deps.
    Also refreshes live policy from Mongo every 5 min for multi-worker sync."""
    fired_for_date = None
    policy_refresh_counter = 0
    while True:
        try:
            # Refresh live policy from Mongo every ~5 min (multi-worker sync)
            policy_refresh_counter += 1
            if policy_refresh_counter >= 5:
                policy_refresh_counter = 0
                await _load_policy_from_mongo()

            try:
                from zoneinfo import ZoneInfo
                et = datetime.now(ZoneInfo("America/New_York"))
            except Exception:
                et = datetime.now(timezone.utc) - timedelta(hours=5)
            hhmm = et.strftime("%H:%M")
            today_et = et.date().isoformat()
            if hhmm >= PREFETCH_HHMM and fired_for_date != today_et and et.weekday() < 5:
                fired_for_date = today_et
                asyncio.create_task(_prefetch_paid_oi())
        except Exception as e:
            log.warning(f"scheduler tick err: {e}")
        await asyncio.sleep(60)


@api.get("/spot/{ticker}")
async def quick_spot(ticker: str):
    """Cheap, fast spot price via yfinance. Free. Use for live GEX recompute (γ depends on S)."""
    SPOT_TTL = 5
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    cache_key = f"spot:{t}"
    item = _cache.get(cache_key)
    if item and (time.time() - item["ts"]) < SPOT_TTL:
        return item["data"]
    def _f():
        try:
            yt = yf.Ticker(t)
            fi = yt.fast_info
            return float(fi.get("lastPrice") or fi.get("last_price") or 0)
        except Exception:
            return 0.0
    spot = await asyncio.to_thread(_f)
    res = {"ticker": t, "spot": spot, "ts": datetime.now(timezone.utc).isoformat()}
    _cache[cache_key] = {"ts": time.time(), "data": res}
    return res


@api.post("/live/tape/stop")
async def stop_live_tape():
    """Hard-stop the live OPRA trade stream (Flowseeker). Returns final session stats."""
    sid = _session_state.get("live_tape_session_id")
    _session_state["live_tape_active"] = False
    if sid:
        ended_at = datetime.now(timezone.utc).isoformat()
        await db.live_sessions.update_one(
            {"session_id": sid},
            {"$set": {"ended_at": ended_at, "manually_stopped": True}},
        )
    return {"stopped": True, "session_id": sid, "msg_count": _session_state.get("msg_count", 0)}


# ============ Portfolio Position Tracking & Hedging ============

# In-memory portfolio store (persist to Mongo in production)
_portfolios: Dict[str, Portfolio] = {}


class PositionReq(BaseModel):
    symbol: str
    option_type: str  # "call" or "put"
    strike: float
    expiry: str  # "YYYY-MM-DD"
    quantity: int  # positive = long, negative = short
    entry_price: float
    entry_iv: float
    underlying_price: float


class HedgeReq(BaseModel):
    spot: float
    iv: float
    hedge_options: List[Dict[str, Any]]  # [{"strike": 745, "expiry": "2026-05-16", "type": "call", "iv": 0.15}]


@api.post("/portfolio/{name}/position")
async def add_position(name: str, req: PositionReq):
    """Add a position to a portfolio."""
    if name not in _portfolios:
        _portfolios[name] = Portfolio(name)
    pos = Position(
        symbol=req.symbol, option_type=req.option_type, strike=req.strike,
        expiry=req.expiry, quantity=req.quantity, entry_price=req.entry_price,
        entry_iv=req.entry_iv, underlying_price=req.underlying_price,
        is_long=req.quantity > 0,
    )
    _portfolios[name].add_position(pos)
    return {"status": "added", "positions": len(_portfolios[name].positions)}


@api.delete("/portfolio/{name}/position/{index}")
async def remove_position(name: str, index: int):
    """Remove a position by index."""
    if name not in _portfolios:
        raise HTTPException(404, "Portfolio not found")
    _portfolios[name].remove_position(index)
    return {"status": "removed", "positions": len(_portfolios[name].positions)}


@api.get("/portfolio/{name}")
async def get_portfolio(name: str, spot: float = Query(...), iv: float = Query(...)):
    """Get portfolio summary with aggregated Greeks and P&L."""
    if name not in _portfolios:
        raise HTTPException(404, "Portfolio not found")
    p = _portfolios[name]
    return {
        "name": name,
        "positions": len(p.positions),
        "cash": round(p.cash, 2),
        "greeks": p.aggregate_greeks(spot, iv),
        "pnl": p.total_pnl(spot, iv),
    }


@api.get("/portfolio/{name}/scenario")
async def portfolio_scenario(name: str, spot: float = Query(...), iv: float = Query(...)):
    """Run scenario analysis on portfolio."""
    if name not in _portfolios:
        raise HTTPException(404, "Portfolio not found")
    p = _portfolios[name]
    scenarios = p.scenario_analysis(spot, iv)
    return {"scenarios": scenarios}


@api.post("/portfolio/{name}/hedge")
async def portfolio_hedge(name: str, req: HedgeReq):
    """Calculate Greek-neutral hedge for portfolio."""
    if name not in _portfolios:
        raise HTTPException(404, "Portfolio not found")
    p = _portfolios[name]
    hedge = p.greek_neutral_hedge(req.spot, req.iv, req.hedge_options)
    return hedge


@api.post("/position-size")
async def position_size(
    account_size: float = Query(...),
    risk_per_trade_pct: float = Query(..., ge=0.001, le=0.1),
    spot: float = Query(...),
    gex_level: float = Query(0),
):
    """Calculate position size based on GEX levels and risk parameters."""
    return calc_position_size(account_size, risk_per_trade_pct, spot, gex_level)


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_start():
    await db.snapshots.create_index([("ticker", 1), ("ts", -1)])
    cache = init_cache(db)
    await cache.ensure_index()
    await _load_policy_from_mongo()
    global _scheduler_started
    if not _scheduler_started:
        _scheduler_started = True
        asyncio.create_task(_scheduler_loop())
        log.info(f"scheduler started · prefetch at {PREFETCH_HHMM} ET")
    log.info("databento cache initialized")


@app.on_event("shutdown")
async def on_stop():
    client.close()
