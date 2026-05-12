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


# ----------------------------- Black-Scholes ----------------------------------

def bs_gamma(S: float, K: float, T: float, sigma: float, r: float = RISK_FREE_RATE, q: float = 0.0) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        return math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
    except Exception:
        return 0.0


def bs_delta(S: float, K: float, T: float, sigma: float, q: float = 0.0, kind: str = "call", r: float = RISK_FREE_RATE) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
        if kind == "call":
            return math.exp(-q * T) * norm.cdf(d1)
        return -math.exp(-q * T) * norm.cdf(-d1)
    except Exception:
        return 0.0


# ----------------------------- Data Layer -------------------------------------

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
                    "expiry": exp,
                    "T": T,
                    "type": kind,
                    "strike": strike,
                    "oi": oi,
                    "iv": iv,
                    "volume": vol,
                })

    data = {"ticker": ticker, "spot": spot, "expiries": expiries, "contracts": contracts}
    cache_set(key, data)
    return data


async def fetch_spot_and_chains_merged(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """yfinance for spot+IV + Databento for OI. Falls back gracefully."""
    yf_data = await asyncio.to_thread(fetch_spot_and_chains, ticker, max_expiries)
    spot = yf_data["spot"]
    dbn_oi = {}
    try:
        dbn_oi = await fetch_oi_for_ticker(ticker)
    except Exception as e:
        log.warning(f"databento OI lookup fail {ticker}: {e}")

    if not dbn_oi:
        # No Databento data — pure yfinance
        return {**yf_data, "data_source": "yfinance"}

    # Build (strike, expiry, type) -> OI map from Databento
    dbn_map: Dict[tuple, int] = {}
    for sym, c in dbn_oi.items():
        dbn_map[(c["strike"], c["expiry"], c["type"])] = c["oi"]

    # Overlay Databento OI onto yfinance IV/strike contracts. Add any DBN contracts missing in YF using avg IV.
    yf_keys = set()
    for c in yf_data["contracts"]:
        key = (c["strike"], c["expiry"], c["type"])
        dbn_val = dbn_map.get(key)
        if dbn_val is not None:
            c["oi"] = max(c["oi"], dbn_val)  # prefer larger (latest EOD vs YF intraday)
            c["oi_source"] = "databento"
        else:
            c["oi_source"] = "yfinance"
        yf_keys.add(key)

    # Add DBN-only contracts: estimate IV by per-expiry arithmetic mean of yfinance IVs
    today = datetime.now(timezone.utc).date()
    iv_lists: Dict[str, list] = {}
    for c in yf_data["contracts"]:
        iv_lists.setdefault(c["expiry"], []).append(c["iv"])
    iv_avg_by_expiry: Dict[str, float] = {e: (sum(vs) / len(vs)) for e, vs in iv_lists.items() if vs}

    for (strike, expiry, typ), oi in dbn_map.items():
        if (strike, expiry, typ) in yf_keys:
            continue
        if expiry not in iv_avg_by_expiry:
            # Skip if no IV reference (unknown expiry)
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
    """Per-strike net GEX. Convention: dealer-positive convention.
    GEX = OI * 100 * gamma * S^2 * 0.01, calls add positive, puts subtract.
    Returns sorted-by-strike list of {strike, gex, call_gex, put_gex, total_oi, call_oi, put_oi}.
    """
    if spot <= 0 or not contracts:
        return []
    q = DIV_YIELD.get(ticker, 0.0)
    agg: Dict[float, Dict[str, float]] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        # GEX in $ per 1% move (notional)
        gex_unit = gamma * c["oi"] * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        bucket = agg.setdefault(c["strike"], {
            "strike": c["strike"], "gex": 0.0, "call_gex": 0.0, "put_gex": 0.0,
            "call_oi": 0.0, "put_oi": 0.0, "total_oi": 0.0,
        })
        bucket["gex"] += sign * gex_unit
        if c["type"] == "call":
            bucket["call_gex"] += gex_unit
            bucket["call_oi"] += c["oi"]
        else:
            bucket["put_gex"] += gex_unit
            bucket["put_oi"] += c["oi"]
        bucket["total_oi"] += c["oi"]

    out = sorted(agg.values(), key=lambda r: r["strike"])
    return out


def compute_gex_grid(spot: float, contracts: List[Dict[str, Any]], ticker: str = "") -> Dict[str, Any]:
    """2D grid: GEX per (strike, expiry). Skylit-style heatmap layout.
    Returns {expiries: [...], strikes: [...], grid: {expiry: {strike: gex}}}"""
    if spot <= 0 or not contracts:
        return {"expiries": [], "strikes": [], "grid": {}}
    q = DIV_YIELD.get(ticker, 0.0)
    grid: Dict[str, Dict[float, float]] = {}
    strike_totals: Dict[float, float] = {}
    for c in contracts:
        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        if gamma <= 0:
            continue
        gex_unit = gamma * c["oi"] * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] == "call" else -1.0
        cell = sign * gex_unit
        d = grid.setdefault(c["expiry"], {})
        d[c["strike"]] = d.get(c["strike"], 0.0) + cell
        strike_totals[c["strike"]] = strike_totals.get(c["strike"], 0.0) + cell

    expiries = sorted(grid.keys())
    strikes = sorted(strike_totals.keys())

    def _k(x: float) -> str:
        # Normalize key: integer-valued floats become "739", otherwise "739.5"
        return str(int(x)) if float(x).is_integer() else str(x)

    return {
        "expiries": expiries,
        "strikes": strikes,
        "grid": {e: {_k(k): v for k, v in grid[e].items()} for e in expiries},
        "strike_totals": [{"strike": k, "gex": v} for k, v in sorted(strike_totals.items())],
    }


# ----------------------------- Node Hierarchy ---------------------------------

def classify_nodes(strikes: List[Dict[str, Any]], spot: float) -> Dict[str, Any]:
    if not strikes or spot <= 0:
        return {"king": None, "floors": [], "ceilings": [], "gatekeepers": [], "air_pockets": [],
                "polarity_level": None, "regime": "unknown"}

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

    # Gatekeepers: positive nodes between spot and king (smaller than king but meaningful >= 15% of king mag)
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

    # Polarity / regime
    total_gex = sum(s["gex"] for s in strikes)
    spot_window = [s for s in strikes if abs(s["strike"] - spot) / spot < 0.02]
    near_gex = sum(s["gex"] for s in spot_window)
    if near_gex > 0:
        regime = "positive"
    elif near_gex < 0:
        regime = "negative"
    else:
        regime = "neutral"

    # Gamma flip / polarity zero-crossing
    polarity = None
    cum = 0.0
    sorted_by_strike = sorted(strikes, key=lambda r: r["strike"])
    cum_arr = []
    for s in sorted_by_strike:
        cum += s["gex"]
        cum_arr.append((s["strike"], cum))
    for i in range(1, len(cum_arr)):
        a, b = cum_arr[i - 1], cum_arr[i]
        if a[1] == 0 or b[1] == 0 or (a[1] > 0) != (b[1] > 0):
            # zero crossing -> linear interp
            x1, y1 = a; x2, y2 = b
            if y2 - y1 != 0:
                polarity = x1 + (0 - y1) * (x2 - x1) / (y2 - y1)
            else:
                polarity = (x1 + x2) / 2
            break

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


# ----------------------------- Heatmap Core -----------------------------------

async def build_heatmap(ticker: str, max_expiries: int = 4, with_taps: bool = True, mode: str = "day") -> Dict[str, Any]:
    if mode == "swing":
        max_expiries = max(max_expiries, 8)
    raw = await fetch_spot_and_chains_merged(ticker, max_expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    strikes = compute_gex_by_strike(spot, raw["contracts"], ticker)
    grid = compute_gex_grid(spot, raw["contracts"], ticker)
    band = 0.25 if mode == "swing" else 0.15
    strikes = [s for s in strikes if abs(s["strike"] - spot) / spot <= band]
    grid["strikes"] = [k for k in grid["strikes"] if abs(k - spot) / spot <= band]
    grid["strike_totals"] = [s for s in grid["strike_totals"] if abs(s["strike"] - spot) / spot <= band]

    # Tag fresh/tested via tap counts
    tap_map: Dict[float, int] = {}
    if with_taps:
        tap_map = await tap_counts(ticker, [s["strike"] for s in strikes], days=5)
    for s in strikes:
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
        # Tap probability per Skylit: 80/66/33/10
        s["tap_prob"] = [0.80, 0.66, 0.33, 0.10][min(tc, 3)]

    nodes = classify_nodes(strikes, spot)
    patterns = detect_patterns(strikes, nodes, spot)

    # Velocity & rolling: compute against history BEFORE saving current snapshot
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
    }

    # Persist asynchronously
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
async def heatmap(ticker: str, expiries: int = Query(4, ge=1, le=12), taps: bool = True, mode: str = Query("day", pattern="^(day|swing)$")):
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode)


@api.get("/trinity")
async def trinity(tickers: str = Query(",".join(TRINITY)), mode: str = Query("day", pattern="^(day|swing)$")):
    syms = [t.strip() for t in tickers.split(",") if t.strip()]
    out: Dict[str, Any] = {}
    results = await asyncio.gather(*[build_heatmap(s, 3, True, mode) for s in syms], return_exceptions=True)
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
async def flow_stream(ticker: str, request: Request, max_seconds: int = Query(120, ge=10, le=300)):
    """SSE stream of live OPRA trades for a ticker via Databento Live.
    Cost-capped: max_seconds <= 300 (5 min). Filters to unusual/sweep/block by default in client."""
    t = ticker.strip().upper().replace("^", "")
    parent = PARENT_MAP.get(t, f"{t}.OPT")
    queue: asyncio.Queue = asyncio.Queue(maxsize=2000)
    stop = asyncio.Event()

    async def producer():
        try:
            await stream_live_trades(parent, queue, stop)
        finally:
            await queue.put({"_eof": True})

    task = asyncio.create_task(producer())
    deadline = time.time() + max_seconds

    async def gen():
        try:
            yield f"event: ready\ndata: {json.dumps({'parent': parent})}\n\n"
            while time.time() < deadline:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if msg.get("_eof"):
                    yield f"event: end\ndata: {{}}\n\n"
                    break
                if msg.get("_error"):
                    yield f"event: error\ndata: {json.dumps(msg)}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            stop.set()
            try:
                task.cancel()
            except Exception:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")


@api.get("/databento/usage")
async def dbn_usage():
    """Quick view of Databento cache stats."""
    try:
        n = await db.databento_oi.count_documents({})
        recent = []
        async for doc in db.databento_oi.find({}, {"_id": 0, "parent": 1, "day": 1, "count": 1, "fetched_at": 1}).sort("fetched_at", -1).limit(20):
            recent.append(doc)
        return {"cached_days": n, "recent": recent}
    except Exception as e:
        return {"error": str(e)}


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
    log.info("databento cache initialized")


@app.on_event("shutdown")
async def on_stop():
    client.close()
