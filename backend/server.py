"""
Confluence Decoder - Skylit-style Heatseeker GEX Analytics
- Databento: real-time/EOD Open Interest via OPRA.PILLAR statistics + Live trades for Flowseeker
- yfinance: spot + IV from option chains (fallback for OI when Databento has no data)
- Polygon: stock aggs, tap-count history
- Black-Scholes gamma -> per-strike (and per-strike×expiry) GEX
- Node hierarchy, patterns, velocity, rolling, trinity
"""
from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import os
import json
import logging
import asyncio
import math
import time
from collections import deque
import httpx
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm

from databento_provider import init_cache, fetch_oi_for_ticker, PARENT_MAP, stream_live_trades
from portfolio import Position, Portfolio, calc_position_size
from schwab import SCHWAB_CLIENT_ID
from vol_analytics import (
    calc_iv_surface_data,
    calc_skew_metrics,
    calc_realized_volatility,
    calc_iv_rank_percentile,
)
from advanced_analytics import (
    calc_implied_pdf,
    calc_market_regime,
    calc_hedge_impulse_curve,
    calc_pressure_cloud,
    calc_charm_integral,
    calc_gamma_flip_levels,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app.log", mode="a"),
    ],
)
log = logging.getLogger("heatseeker")

app = FastAPI(title="Confluence Decoder")
api = APIRouter(prefix="/api")

# ----------------------------- Rate Limiting -----------------------------
from collections import defaultdict

_rate_limits: dict = defaultdict(deque)  # ip -> deque[timestamp]

RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))  # requests per minute

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiter: RATE_LIMIT requests per minute per IP with sliding window.
    Uses a deque for O(1) cleanup and proper sliding window semantics."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60.0  # 1 minute
    
    if client_ip not in _rate_limits:
        _rate_limits[client_ip] = deque()
    
    # Remove entries outside the sliding window
    dq = _rate_limits[client_ip]
    while dq and now - dq[0] >= window:
        dq.popleft()
    
    if len(dq) >= RATE_LIMIT:
        retry_after = int(window - (now - dq[0])) + 1
        log.warning(f"Rate limit exceeded for {client_ip} ({len(dq)}/{RATE_LIMIT})")
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
    
    dq.append(now)
    
    # Periodically clean empty IPs to prevent memory leak
    if len(_rate_limits) > 10000:
        empty_ips = [ip for ip, dq in _rate_limits.items() if not dq]
        for ip in empty_ips:
            del _rate_limits[ip]
    
    response = await call_next(request)
    return response


# ----------------------------- Global Exception Handler ------------------------------

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    log.error(f"HTTP {exc.status_code} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "status_code": exc.status_code, "path": request.url.path},
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.error(f"Validation error {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"error": "Validation failed", "details": exc.errors(), "path": request.url.path},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled exception {request.url.path}: {type(exc).__name__}: {exc}", exc_info=True)
    # Track error
    try:
        from error_tracking import log_error
        log_error(
            error_type=type(exc).__name__,
            message=str(exc),
            data={"path": request.url.path, "method": request.method}
        )
    except Exception:
        pass
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "type": type(exc).__name__, "path": request.url.path},
    )


# ----------------------------- Error Tracking & Performance API -----------------------------

@app.middleware("http")
async def performance_middleware(request: Request, call_next):
    """Track request performance."""
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    
    try:
        from error_tracking import perf_monitor, set_request_id
        endpoint = f"{request.method} {request.url.path}"
        perf_monitor.record(endpoint, duration_ms)
        set_request_id()
    except Exception:
        pass
    
    response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
    return response


@api.get("/api/errors/summary")
async def api_error_summary():
    """Get error tracking summary."""
    from error_tracking import get_error_summary
    return get_error_summary()


@api.get("/api/performance/stats")
async def api_performance_stats():
    """Get API performance statistics."""
    from error_tracking import perf_monitor
    return {"endpoints": perf_monitor.get_all_stats()}


@api.post("/api/errors/clear")
async def api_clear_errors():
    """Clear error tracking data."""
    from error_tracking import clear_error_log
    clear_error_log()
    return {"status": "cleared"}

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


def cache_get_or_set(key: str, fn, ttl: int = CACHE_TTL_SEC):
    """Get from cache or compute and store. fn is a sync callable."""
    item = _cache.get(key)
    if item and (time.time() - item["ts"]) < ttl:
        return item["data"]
    data = fn()
    _cache[key] = {"ts": time.time(), "data": data}
    return data


# ============ Portfolio Persistence (Mongo) ============

def _pos_to_dict(p):
    """Serialize a Position to a dict for Mongo storage."""
    return {
        "symbol": p.symbol, "option_type": p.option_type, "strike": p.strike,
        "expiry": p.expiry, "quantity": p.quantity, "entry_price": p.entry_price,
        "entry_iv": p.entry_iv, "underlying_price": p.underlying_price,
        "is_long": p.is_long, "dte": p.dte, "T": p.T,
        "delta": p.delta, "gamma": p.gamma, "vega": p.vega, "theta": p.theta,
        "vanna": p.vanna, "charm": p.charm, "vomma": p.vomma, "zomma": p.zomma,
        "price": p.price,
    }

def _pos_from_dict(d: Dict[str, Any]) -> Position:
    """Reconstruct a Position from a Mongo dict."""
    p = Position.__new__(Position)
    p.symbol = d["symbol"]
    p.option_type = d["option_type"]
    p.strike = d["strike"]
    p.expiry = d["expiry"]
    p.quantity = d["quantity"]
    p.entry_price = d["entry_price"]
    p.entry_iv = d["entry_iv"]
    p.underlying_price = d["underlying_price"]
    p.is_long = d.get("is_long", d["quantity"] > 0)
    p.dte = d.get("dte", 0)
    p.T = d.get("T", 0)
    p.delta = d.get("delta", 0)
    p.gamma = d.get("gamma", 0)
    p.vega = d.get("vega", 0)
    p.theta = d.get("theta", 0)
    p.vanna = d.get("vanna", 0)
    p.charm = d.get("charm", 0)
    p.vomma = d.get("vomma", 0)
    p.zomma = d.get("zomma", 0)
    p.price = d.get("price", 0)
    p.entry_date = datetime.now(timezone.utc)
    return p

async def _save_portfolio_to_mongo(name: str, portfolio: Portfolio):
    """Persist portfolio to Mongo."""
    positions = [_pos_to_dict(p) for p in portfolio.positions]
    await db.portfolios.update_one(
        {"_id": name},
        {"$set": {"positions": positions, "cash": portfolio.cash,
                   "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )

async def _load_portfolio_from_mongo(name: str) -> Optional[Portfolio]:
    """Load portfolio from Mongo. Returns None if not found."""
    doc = await db.portfolios.find_one({"_id": name})
    if not doc:
        return None
    p = Portfolio(doc.get("name", name))
    p.cash = doc.get("cash", 0.0)
    for pd in doc.get("positions", []):
        try:
            p.positions.append(_pos_from_dict(pd))
        except Exception:
            continue
    return p


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
        # Fallback: use UTC-4 (EDT) during DST, UTC-5 (EST) otherwise
        import time
        is_dst = time.localtime().tm_isdst > 0
        offset = 4 if is_dst else 5
        et = datetime.now(timezone.utc) - timedelta(hours=offset)
    hhmm = et.strftime("%H:%M")
    return LIVE_WINDOW["start_hhmm"] <= hhmm <= LIVE_WINDOW["stop_hhmm"]


async def fetch_spot_and_chains_merged(ticker: str, max_expiries: int = 4) -> Dict[str, Any]:
    """yfinance for spot+IV + Databento for OI (only if ticker is in PAID_TICKERS).
    Falls back to pure yfinance for free-tier tickers."""
    yf_data = await asyncio.to_thread(fetch_spot_and_chains, ticker, max_expiries)
    yf_data["spot"]

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
    bs_call_price, bs_put_price,
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
    call_iv = atm_calls[0].get("iv", 0.2)
    put_iv = atm_puts[0].get("iv", 0.2)
    T = atm_calls[0].get("T", 1/365)
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
    abs(king.get("gex", 0)) or 1.0
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
    start = end - timedelta(days=days * 2)
    pg_ticker = ticker.replace("^SPX", "I:SPX") if ticker.startswith("^") else ticker
    url = f"https://api.polygon.io/v2/aggs/ticker/{pg_ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
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
    if not spot or spot != spot or not raw["contracts"]:  # spot != spot catches NaN
        raise HTTPException(404, f"No options data for {ticker}")

    today = datetime.now(timezone.utc).date()

    # Scalp mode: force 0DTE only, tight band, volume-weighted
    if scalp:
        dte = 0
        mode = "scalp"

    # DTE filter
    if dte is not None:
        cutoff = today + timedelta(days=dte)
        filtered = []
        for c in raw["contracts"]:
            try:
                if datetime.strptime(c["expiry"], "%Y-%m-%d").date() <= cutoff:
                    filtered.append(c)
            except Exception:
                continue
        raw["contracts"] = filtered
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

    # --- Advanced analytics (regime + implied PDF + gamma flip levels) ---
    market_regime = calc_market_regime(spot, raw["contracts"])
    implied_pdf = calc_implied_pdf(spot, raw["contracts"])
    gamma_flip_data = calc_gamma_flip_levels(spot, raw["contracts"], ticker)

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
        # Advanced analytics
        "market_regime": market_regime,
        "implied_pdf": implied_pdf,
        "gamma_flip": gamma_flip_data,
    }

    asyncio.create_task(save_snapshot(ticker, payload))
    return _sanitize(payload)


def _sanitize(obj):
    """Replace NaN/Inf with None recursively for JSON safety. Handles numpy types."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


@app.get("/health")
async def health_root():
    return await health()


# ----------------------------- API Endpoints ------------------------------

# Cache import (lazy — only loaded when Redis is available)
from functools import wraps as _wraps
_cache_available = False
try:
    from cache import cache_response
    _cache_available = True
except ImportError:
    def cache_response(ttl=60, key_prefix="api"):
        def decorator(func):
            @_wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator

@api.get("/")
async def root():
    return {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(timezone.utc).isoformat()}


@api.get("/health")
async def health():
    """Health check with dependency status."""
    status = {"app": "confluence-decoder", "version": "2.0", "ts": datetime.now(timezone.utc).isoformat(), "dependencies": {}}
    # Check Mongo
    try:
        await db.command("ping")
        status["dependencies"]["mongodb"] = "ok"
    except Exception as e:
        status["dependencies"]["mongodb"] = f"error: {str(e)}"
    # Check yfinance (lightweight)
    try:
        import yfinance as yf
        t = yf.Ticker("SPY")
        _ = t.fast_info
        status["dependencies"]["yfinance"] = "ok"
    except Exception as e:
        status["dependencies"]["yfinance"] = f"error: {str(e)}"
    # Overall
    all_ok = all(v == "ok" for v in status["dependencies"].values())
    status["status"] = "healthy" if all_ok else "degraded"
    return status


@api.get("/tickers")
async def list_tickers():
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


@api.get("/heatmap/{ticker}")
@cache_response(ttl=60, key_prefix="heatmap")
async def heatmap(ticker: str, expiries: int = Query(4, ge=1, le=12), taps: bool = True, mode: str = Query("day", pattern="^(day|swing|scalp)$"), dte: Optional[int] = Query(None, ge=0, le=30, description="DTE filter: 0=today only, 1=today+tomorrow, 7=within week, None=all"), scalp: bool = Query(False, description="Scalp mode: 0DTE only, volume-weighted GEX, ±2% band")):
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode, dte, scalp)


@api.get("/trinity")
@cache_response(ttl=60, key_prefix="trinity")
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


@api.get("/implied-pdf/{ticker}")
async def implied_pdf(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Breeden-Litzenberger implied probability distribution."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_implied_pdf(spot, raw["contracts"])
    return _sanitize(result)


@api.get("/regime/{ticker}")
async def regime(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Market regime detection from IV surface."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_market_regime(spot, raw["contracts"])
    return _sanitize(result)


@api.get("/hedge-impulse/{ticker}")
async def hedge_impulse(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Hedge impulse curve: gamma + vanna combined response."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_hedge_impulse_curve(spot, raw["contracts"], t)
    return _sanitize(result)


@api.get("/pressure-cloud/{ticker}")
async def pressure_cloud(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Pressure cloud: stability zones, acceleration zones, regime edges."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_pressure_cloud(spot, raw["contracts"], t)
    return _sanitize(result)


@api.get("/charm-integral/{ticker}")
async def charm_integral_endpoint(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Charm integral: time-decay pressure to close."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_charm_integral(spot, raw["contracts"], t)
    return _sanitize(result)


@api.get("/advanced/{ticker}")
@cache_response(ttl=120, key_prefix="advanced")
async def advanced_analytics(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Combined advanced analytics: PDF, regime, impulse, pressure, charm."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    # Run independent computations
    pdf = calc_implied_pdf(spot, raw["contracts"])
    regime_data = calc_market_regime(spot, raw["contracts"])
    impulse = calc_hedge_impulse_curve(spot, raw["contracts"], t)
    pressure = calc_pressure_cloud(spot, raw["contracts"], t)
    charm = calc_charm_integral(spot, raw["contracts"], t)

    return _sanitize({
        "ticker": t,
        "spot": spot,
        "implied_pdf": pdf,
        "regime": regime_data,
        "hedge_impulse": impulse,
        "pressure_cloud": pressure,
        "charm_integral": charm,
        "asof": datetime.now(timezone.utc).isoformat(),
    })


@api.get("/gamma-flip/{ticker}")
async def gamma_flip(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Gamma flip level, call/put walls, max pain, 0DTE magnet, hedging flows."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or spot != spot or not raw["contracts"]:  # spot != spot catches NaN
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_gamma_flip_levels(spot, raw["contracts"], t)
    return _sanitize(result)


@api.get("/daily-checklist/{ticker}")
async def daily_checklist(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Daily trading checklist: GEX regime, key levels, strategy recommendations."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw["spot"]
    if not spot or spot != spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    # Compute all analytics
    gf = calc_gamma_flip_levels(spot, raw["contracts"], t)
    regime_data = calc_market_regime(spot, raw["contracts"])
    iv_surface = calc_iv_surface_data(spot, raw["contracts"])
    skew = calc_skew_metrics(spot, raw["contracts"])

    # Build checklist
    checklist = {
        "ticker": t,
        "spot": spot,
        "asof": datetime.now(timezone.utc).isoformat(),
        "regime": {
            "gex_regime": gf["regime"],
            "market_regime": regime_data.get("regime", "unknown"),
            "iv_rank": iv_surface.get("atm_iv", 0),
            "skew": skew.get("risk_reversal_25d", 0),
        },
        "key_levels": {
            "gamma_flip": gf["gamma_flip"],
            "call_wall": gf["call_wall"],
            "put_wall": gf["put_wall"],
            "max_pain": gf["max_pain"],
            "dist_to_flip": gf["dist_to_flip"],
            "dist_to_call_wall_pct": gf["dist_to_call_wall_pct"],
            "dist_to_put_wall_pct": gf["dist_to_put_wall_pct"],
        },
        "hedging_flow": gf["hedging_flow"],
        "strategy": _get_strategy_recommendation(gf, regime_data, skew),
        "risk_management": _get_risk_levels(gf, spot),
    }
    return _sanitize(checklist)


def _get_strategy_recommendation(gf: Dict, regime: Dict, skew: Dict) -> Dict[str, Any]:
    """Generate strategy recommendations based on GEX regime and market conditions."""
    gex_regime = gf.get("regime", "unknown")
    dist_to_flip = gf.get("dist_to_flip")
    gf.get("call_wall")
    gf.get("put_wall")
    spot = gf.get("spot", 0)

    if gex_regime == "positive_gamma":
        regime_desc = "Positive gamma — dealers are long gamma, market is self-correcting"
        bias = "mean_reversion"
        strategies = [
            "Sell premium (iron condors, short strangles) between put wall and call wall",
            "Buy dips to put wall, sell rallies to call wall",
            "Short volatility strategies favored",
            "Avoid chasing breakouts — they tend to reverse",
        ]
        if dist_to_flip is not None and dist_to_flip < 0:
            warning = "CAUTION: Price is below gamma flip — regime may be transitioning to negative"
        else:
            warning = None
    elif gex_regime == "negative_gamma":
        regime_desc = "Negative gamma — dealers are short gamma, market is self-amplifying"
        bias = "momentum"
        strategies = [
            "Long volatility strategies (long straddles, strangles)",
            "Momentum/trend following — breakouts accelerate",
            "Buy breakouts above call wall, short breakdowns below put wall",
            "Avoid mean-reversion — moves tend to extend",
        ]
        if dist_to_flip is not None and dist_to_flip > 0:
            warning = "CAUTION: Price is above gamma flip — regime may be transitioning to positive"
        else:
            warning = None
    else:
        regime_desc = "Unknown regime — insufficient data"
        bias = "neutral"
        strategies = ["Wait for clearer signal before entering positions"]
        warning = None

    # Skew-based adjustments
    rr = skew.get("risk_reversal_25d", 0)
    if rr > 0.02:
        skew_note = "Put skew elevated — fear premium in puts, consider put selling or put spreads"
    elif rr < -0.02:
        skew_note = "Call skew elevated — bullish positioning, consider call buying or call spreads"
    else:
        skew_note = "Skew relatively balanced — no strong directional bias from options positioning"

    return {
        "regime_description": regime_desc,
        "directional_bias": bias,
        "recommended_strategies": strategies,
        "warning": warning,
        "skew_note": skew_note,
        "position_sizing_note": _get_position_sizing_note(gf, spot),
    }


def _get_risk_levels(gf: Dict, spot: float) -> Dict[str, Any]:
    """Calculate key risk levels for stop-loss and target placement."""
    call_wall = gf.get("call_wall")
    put_wall = gf.get("put_wall")
    gamma_flip = gf.get("gamma_flip")
    max_pain = gf.get("max_pain")

    # Support/resistance from GEX levels
    resistance_1 = call_wall
    resistance_2 = call_wall + (call_wall - spot) * 0.5 if call_wall else None
    support_1 = put_wall
    support_2 = put_wall - (spot - put_wall) * 0.5 if put_wall else None

    # Stop loss suggestions
    if put_wall and spot > put_wall:
        stop_below_put_wall = put_wall - (spot - put_wall) * 0.3
    else:
        stop_below_put_wall = None

    return {
        "resistance": {"R1": resistance_1, "R2": resistance_2},
        "support": {"S1": support_1, "S2": support_2},
        "gamma_flip_level": gamma_flip,
        "max_pain": max_pain,
        "stop_suggestion": {
            "below_put_wall": stop_below_put_wall,
            "note": "Place stops beyond GEX walls — dealer hedging can create temporary spikes through levels",
        },
    }


def _get_position_sizing_note(gf: Dict, spot: float) -> str:
    """Generate position sizing guidance based on GEX regime."""
    regime = gf.get("regime", "unknown")
    dist_to_flip = gf.get("dist_to_flip")

    if regime == "positive_gamma":
        if dist_to_flip is not None and abs(dist_to_flip) < 5:
            return "Near gamma flip — reduce position size, regime could flip. Max 1% account risk per trade."
        return "Positive gamma — standard position sizing OK. Max 2% account risk per trade."
    elif regime == "negative_gamma":
        if dist_to_flip is not None and dist_to_flip < -10:
            return "Deep negative gamma — reduce position size, moves can be violent. Max 0.5% account risk per trade."
        return "Negative gamma — reduce position size vs normal. Max 1% account risk per trade."
    return "Unknown regime — use minimal position size until regime clarifies."

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


@api.get("/live/policy")
async def get_live_policy():
    """Get current live trading policy."""
    return {"paid_tickers": sorted(PAID_TICKERS), "live_window_et": LIVE_WINDOW}


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
                import time
                is_dst = time.localtime().tm_isdst > 0
                offset = 4 if is_dst else 5
                et = datetime.now(timezone.utc) - timedelta(hours=offset)
            hhmm = et.strftime("%H:%M")
            today_et = et.date().isoformat()
            if hhmm >= PREFETCH_HHMM and fired_for_date != today_et and et.weekday() < 5:
                fired_for_date = today_et
                asyncio.create_task(_prefetch_paid_oi())
        except Exception as e:
            log.warning(f"scheduler tick err: {e}")
        await asyncio.sleep(60)


@api.get("/spot/{ticker}")
@cache_response(ttl=10, key_prefix="spot")
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
        _portfolios[name] = await _load_portfolio_from_mongo(name) or Portfolio(name)
    pos = Position(
        symbol=req.symbol, option_type=req.option_type, strike=req.strike,
        expiry=req.expiry, quantity=req.quantity, entry_price=req.entry_price,
        entry_iv=req.entry_iv, underlying_price=req.underlying_price,
        is_long=req.quantity > 0,
    )
    _portfolios[name].add_position(pos)
    await _save_portfolio_to_mongo(name, _portfolios[name])
    return {"status": "added", "positions": len(_portfolios[name].positions)}


@api.delete("/portfolio/{name}/position/{index}")
async def remove_position(name: str, index: int):
    """Remove a position by index."""
    if name not in _portfolios:
        loaded = await _load_portfolio_from_mongo(name)
        if not loaded:
            raise HTTPException(404, "Portfolio not found")
        _portfolios[name] = loaded
    if not _portfolios[name]:
        raise HTTPException(404, "Portfolio not found")
    _portfolios[name].remove_position(index)
    await _save_portfolio_to_mongo(name, _portfolios[name])
    return {"status": "removed", "positions": len(_portfolios[name].positions)}


@api.get("/portfolio/{name}")
async def get_portfolio(name: str, spot: float = Query(...), iv: float = Query(...)):
    """Get portfolio summary with aggregated Greeks and P&L."""
    if name not in _portfolios or not _portfolios[name]:
        loaded = await _load_portfolio_from_mongo(name)
        if not loaded:
            raise HTTPException(404, "Portfolio not found")
        _portfolios[name] = loaded
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
    if name not in _portfolios or not _portfolios[name]:
        loaded = await _load_portfolio_from_mongo(name)
        if not loaded:
            raise HTTPException(404, "Portfolio not found")
        _portfolios[name] = loaded
    p = _portfolios[name]
    scenarios = p.scenario_analysis(spot, iv)
    return {"scenarios": scenarios}


@api.post("/portfolio/{name}/hedge")
async def portfolio_hedge(name: str, req: HedgeReq):
    """Calculate Greek-neutral hedge for portfolio."""
    if name not in _portfolios or not _portfolios[name]:
        loaded = await _load_portfolio_from_mongo(name)
        if not loaded:
            raise HTTPException(404, "Portfolio not found")
        _portfolios[name] = loaded
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


# ============ Paper Trading Automation ============

from paper_trading import process_signals_for_ticker, execute_paper_trade


@api.post("/api/paper-trading/execute")
async def api_execute_paper_trade(
    ticker: str = Query(...),
    strategy: str = Query("iron_condor"),
    qty: int = Query(1, ge=1, le=10),
):
    """Execute a paper trade manually."""
    order = {"strategy": strategy, "ticker": ticker, "spot": 0}
    result = await execute_paper_trade(order, qty)
    return result


@api.post("/api/paper-trading/signals")
async def api_process_signals(
    ticker: str = Query(...),
    auto_trade: bool = Query(False),
):
    """Process trading signals for a ticker and optionally auto-trade."""
    from alert_engine import AlertEngine
    engine = AlertEngine()
    signals = engine.detect_alerts(ticker)
    signal_dicts = [s.to_dict() for s in signals]
    results = await process_signals_for_ticker(ticker, signal_dicts, auto_trade)
    return {
        "ticker": ticker,
        "signals_found": len(signals),
        "actions": results,
        "auto_trade": auto_trade,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api.get("/api/paper-trading/status")
async def api_paper_trading_status():
    """Get paper trading account status."""
    from alpaca_client import AlpacaClient
    client = AlpacaClient()
    if not client.enabled:
        return {"enabled": False, "message": "Alpaca not configured"}
    account = await client.get_account()
    positions = await client.get_positions()
    orders = await client.get_orders()
    return {
        "enabled": True,
        "account": account,
        "open_positions": len(positions),
        "open_orders": len(orders),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============ Morning Briefing Email ============

from morning_briefing import send_briefing_email, generate_briefing_data, format_briefing_email


@api.get("/api/briefing/{ticker}")
async def api_get_briefing(ticker: str):
    """Get morning briefing data (JSON)."""
    data = generate_briefing_data(ticker)
    return data


@api.get("/api/briefing/{ticker}/html")
async def api_get_briefing_html(ticker: str):
    """Get morning briefing as HTML (for email preview)."""
    data = generate_briefing_data(ticker)
    html = format_briefing_email(data)
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@api.post("/api/briefing/{ticker}/send")
async def api_send_briefing(ticker: str, to_email: str = Query(...)):
    """Send morning briefing email."""
    result = await send_briefing_email(to_email, ticker)
    return result


# ============ ML Training & Prediction ============

from ml_training import train_regime_prediction_model, predict_regime, extract_features_from_snapshot


@api.post("/api/ml/train/{ticker}")
async def api_train_model(ticker: str):
    """Train regime prediction model on historical GEX data."""
    result = await train_regime_prediction_model(ticker)
    return result


@api.get("/api/ml/predict/{ticker}")
async def api_predict_regime(ticker: str):
    """Predict regime using trained model."""
    result = await predict_regime(ticker)
    return result


@api.get("/api/ml/features/{ticker}")
async def api_get_features(ticker: str):
    """Get ML features from latest snapshot."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    latest = await db.snapshots.find_one({"ticker": ticker}, sort=[("ts", -1)])
    client.close()
    
    if not latest:
        raise HTTPException(404, f"No snapshots for {ticker}")
    
    features = extract_features_from_snapshot(latest)
    return {"ticker": ticker, "features": features, "timestamp": latest.get("ts", "")}


@api.get("/api/ml/data/{ticker}")
async def api_get_training_data(ticker: str, limit: int = Query(100, ge=1, le=10000)):
    """Get raw training data for a ticker."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    cursor = db.snapshots.find(
        {"ticker": ticker},
        {"_id": 0, "ts": 1, "spot": 1, "regime": 1, "total_gex": 1, "net_gex": 1, "king": 1}
    ).sort("ts", -1).limit(limit)
    
    data = await cursor.to_list(length=limit)
    client.close()
    
    return {"ticker": ticker, "count": len(data), "data": data}


# ============ Data Collection for ML ============

from data_collector import collect_and_store, collect_multiple_tickers


@api.post("/api/ml/collect/{ticker}")
async def api_collect_data(ticker: str):
    """Collect and store a GEX snapshot for ML training."""
    result = await collect_and_store(ticker)
    return result


@api.post("/api/ml/collect-all")
async def api_collect_all():
    """Collect snapshots for all major tickers (SPY, QQQ, IWM, DIA)."""
    results = await collect_multiple_tickers()
    return {"results": results}


@api.post("/api/ml/train-price/{ticker}")
async def api_train_price_model(ticker: str):
    """Train price direction prediction model."""
    from ml_price_prediction import train_price_direction_model
    result = await train_price_direction_model(ticker)
    return result


@api.get("/api/ml/predict-price/{ticker}")
async def api_predict_price(ticker: str):
    """Predict price direction using trained model."""
    from ml_price_prediction import predict_price_direction
    result = await predict_price_direction(ticker)
    return result


@api.post("/api/ml/train-advanced/{ticker}")
async def api_train_advanced(ticker: str):
    """Train model with walk-forward cross-validation."""
    from ml_advanced import train_with_walkforward_cv
    result = await train_with_walkforward_cv(ticker)
    return result


@api.get("/api/ml/model-info/{ticker}")
async def api_model_info(ticker: str):
    """Get model information and performance metrics."""
    import joblib
    import os
    
    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    model_path = os.path.join(model_dir, f"{ticker}_direction_v1.0.joblib")
    
    if not os.path.exists(model_path):
        return {"status": "no_model", "ticker": ticker}
    
    assert "_quarantine" not in str(model_path), f"refused to load quarantined model: {model_path}"
    model = joblib.load(model_path)

    return {
        "status": "ok",
        "ticker": ticker,
        "model_type": type(model).__name__,
        "n_estimators": getattr(model, "n_estimators", None),
        "max_depth": getattr(model, "max_depth", None),
        "feature_importances": dict(zip(
            [f"f{i}" for i in range(len(model.feature_importances_))],
            [round(f, 4) for f in model.feature_importances_],
        )),
        "model_size_mb": round(os.path.getsize(model_path) / 1024 / 1024, 2),
    }


# ============ LLM Analysis ============

from services.llm import get_llm_service, analyze_trade_with_llm


@api.post("/api/llm/analyze-trade")
async def api_analyze_trade(
    ticker: str = Query(...),
    spot: float = Query(...),
    regime: str = Query(...),
    net_gex: float = Query(0),
    prediction: str = Query(""),
    confidence: float = Query(0.5),
    provider: str = Query("cerebras"),
):
    """Analyze a trade opportunity using LLM."""
    result = await analyze_trade_with_llm(ticker, spot, regime, net_gex, prediction, confidence)
    return result


@api.post("/api/llm/generate-briefing")
async def api_generate_briefing(
    ticker: str = Query("SPY"),
    provider: str = Query("cerebras"),
):
    """Generate AI-powered morning briefing."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    # Get latest snapshot
    latest = await db.snapshots.find_one({"ticker": ticker}, sort=[("ts", -1)])
    client.close()
    
    if not latest:
        return {"status": "no_data", "ticker": ticker}
    
    # Get ML prediction
    from ml_price_prediction import predict_price_direction
    ml_result = await predict_price_direction(ticker)
    
    # Generate briefing
    result = await analyze_trade_with_llm(
        ticker=ticker,
        spot=latest.get("spot", 0),
        regime=latest.get("regime", "unknown"),
        net_gex=latest.get("net_gex", 0),
        prediction=ml_result.get("prediction", "unknown"),
        confidence=ml_result.get("confidence", 0),
    )
    
    return result


@api.get("/api/llm/providers")
async def api_llm_providers():
    """List available LLM providers."""
    llm = get_llm_service()
    return {
        "providers": list(llm.providers.keys()),
        "default": "cerebras",
    }


# ============ Quant Analytics ============

from services.analytics import GexSurfaceComputer, HistoricalGexAnalyzer, MultiTickerComparator


@api.get("/api/analytics/surface/{ticker}")
async def api_gex_surface(ticker: str):
    """Get GEX surface (strike × expiry matrix)."""
    from server import fetch_spot_and_chains_merged
    
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    
    raw = await fetch_spot_and_chains_merged(t, 8)
    if not raw.get("contracts"):
        return {"status": "no_data"}
    
    surface = GexSurfaceComputer.compute_surface(raw["spot"], raw["contracts"])
    return surface


@api.get("/api/analytics/regime-stats/{ticker}")
async def api_regime_stats(ticker: str, days: int = Query(30, ge=1, le=365)):
    """Get regime statistics for a ticker."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    from datetime import timedelta
    
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    # Get snapshots from last N days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    cursor = db.snapshots.find(
        {"ticker": ticker, "ts": {"$gte": cutoff}}
    ).sort("ts", 1)
    
    snapshots = await cursor.to_list(length=10000)
    client.close()
    
    if not snapshots:
        return {"status": "no_data", "ticker": ticker}
    
    stats = HistoricalGexAnalyzer.compute_regime_statistics(snapshots)
    stats["ticker"] = ticker
    stats["days"] = days
    stats["snapshots_analyzed"] = len(snapshots)
    
    return stats


@api.get("/api/analytics/compare")
async def api_compare_tickers(tickers: str = Query("SPY,QQQ,IWM,DIA")):
    """Compare GEX regimes across multiple tickers."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    snapshots_by_ticker = {}
    
    for ticker in ticker_list:
        cursor = db.snapshots.find({"ticker": ticker}).sort("ts", -1).limit(10)
        snaps = await cursor.to_list(length=10)
        if snaps:
            snapshots_by_ticker[ticker] = snaps
    
    client.close()
    
    if not snapshots_by_ticker:
        return {"status": "no_data"}
    
    comparison = MultiTickerComparator.compare_regimes(snapshots_by_ticker)
    return comparison


@api.get("/api/analytics/correlation")
async def api_gex_correlation(
    ticker1: str = Query(...),
    ticker2: str = Query(...),
    days: int = Query(30, ge=1, le=365),
):
    """Compute GEX correlation between two tickers."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    from datetime import timedelta
    
    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", ""))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    cursor1 = db.snapshots.find({"ticker": ticker1.upper(), "ts": {"$gte": cutoff}})
    snaps1 = await cursor1.to_list(length=10000)
    
    cursor2 = db.snapshots.find({"ticker": ticker2.upper(), "ts": {"$gte": cutoff}})
    snaps2 = await cursor2.to_list(length=10000)
    
    client.close()
    
    correlation = HistoricalGexAnalyzer.compute_gex_correlation(snaps1, snaps2)
    
    return {
        "ticker1": ticker1.upper(),
        "ticker2": ticker2.upper(),
        "correlation": correlation,
        "samples": min(len(snaps1), len(snaps2)),
        "days": days,
    }


# ============ Schwab API Integration ============

from schwab import SchwabTokenManager, SchwabClient, import_schwab_positions, detect_sweeps

_schwab_token_mgr = SchwabTokenManager()


class SchwabAuthReq(BaseModel):
    code: str  # Authorization code from OAuth callback


@api.get("/schwab/auth-url")
async def schwab_auth_url():
    """Get the Schwab OAuth2 authorization URL."""
    if not SCHWAB_CLIENT_ID:
        return {"error": "SCHWAB_CLIENT_ID not set in .env", "hint": "Get credentials at https://developer.schwab.com/"}
    mgr = SchwabTokenManager()
    return {"auth_url": mgr.get_auth_url()}


@api.post("/schwab/auth")
async def schwab_auth(req: SchwabAuthReq):
    """Exchange OAuth code for tokens."""
    try:
        token = await _schwab_token_mgr.exchange_code(req.code)
        return {"status": "authenticated", "expires_in": token.get("expires_in")}
    except Exception as e:
        raise HTTPException(400, f"Auth failed: {e}")


@api.get("/schwab/accounts")
async def schwab_accounts():
    """Get Schwab account numbers."""
    try:
        client = SchwabClient(_schwab_token_mgr)
        accounts = await client.get_accounts()
        return {"accounts": accounts}
    except Exception as e:
        raise HTTPException(401, f"Failed: {e}")


@api.get("/schwab/positions/{account_hash}")
async def schwab_positions(account_hash: str):
    """Import positions from Schwab account."""
    try:
        positions = await import_schwab_positions(account_hash)
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        raise HTTPException(401, f"Failed: {e}")


@api.get("/schwab/sweeps/{account_hash}")
async def schwab_sweeps(account_hash: str, days: int = Query(7, ge=1, le=90)):
    """Detect options sweeps from Schwab transaction history."""
    try:
        sweeps = await detect_sweeps(account_hash, days)
        return {"sweeps": sweeps, "count": len(sweeps)}
    except Exception as e:
        raise HTTPException(401, f"Failed: {e}")


@api.post("/schwab/import-to-portfolio/{name}/{account_hash}")
async def schwab_import_to_portfolio(name: str, account_hash: str):
    """Import Schwab positions directly into a portfolio."""
    positions = await import_schwab_positions(account_hash)
    if name not in _portfolios:
        _portfolios[name] = await _load_portfolio_from_mongo(name) or Portfolio(name)

    added = 0
    for pos_data in positions:
        if pos_data["option_type"] == "equity":
            continue  # Skip equity for now
        try:
            pos = Position(
                symbol=pos_data["symbol"], option_type=pos_data["option_type"],
                strike=pos_data["strike"], expiry=pos_data["expiry"],
                quantity=pos_data["quantity"], entry_price=pos_data["entry_price"],
                entry_iv=max(pos_data["entry_iv"], 0.01),
                underlying_price=max(pos_data["underlying_price"], 1.0),
                is_long=pos_data["is_long"],
            )
            _portfolios[name].add_position(pos)
            added += 1
        except Exception:
            continue

    await _save_portfolio_to_mongo(name, _portfolios[name])
    return {"status": "imported", "added": added, "total": len(_portfolios[name].positions)}


# ============ Options Chain Table ============

@api.get("/chain/{ticker}")
async def options_chain_table(
    ticker: str,
    expiry: Optional[str] = Query(None, description="Filter by expiry YYYY-MM-DD"),
    min_oi: int = Query(0, ge=0),
    min_volume: int = Query(0, ge=0),
    moneyness: Optional[str] = Query(None, pattern="^(itm|otm|atm|all)$", description="ITM/OTM/ATM/ALL"),
    sort_by: str = Query("strike", pattern="^(strike|expiry|oi|volume|iv|delta|gamma|gex|vanna|charm)$"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    """Full options chain table with per-contract Greeks and GEX. Sorted and filtered."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    cache_key = f"chain:{t}:{expiry}:{min_oi}:{min_volume}:{moneyness}:{sort_by}:{sort_dir}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    raw = await fetch_spot_and_chains_merged(t, 12)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    rows: List[Dict[str, Any]] = []
    q = DIV_YIELD.get(t, 0.0)
    today = datetime.now(timezone.utc).date()
    for c in raw["contracts"]:
        if expiry and c["expiry"] != expiry:
            continue
        if c["oi"] < min_oi:
            continue
        if (c.get("volume") or 0) < min_volume:
            continue

        # Moneyness filter
        if moneyness and moneyness != "all":
            if c["type"] == "call":
                if moneyness == "itm" and c["strike"] >= spot:
                    continue
                if moneyness == "otm" and c["strike"] <= spot:
                    continue
                if moneyness == "atm" and abs(c["strike"] - spot) / spot > 0.02:
                    continue
            else:
                if moneyness == "itm" and c["strike"] <= spot:
                    continue
                if moneyness == "otm" and c["strike"] >= spot:
                    continue
                if moneyness == "atm" and abs(c["strike"] - spot) / spot > 0.02:
                    continue

        gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
        delta = bs_delta(spot, c["strike"], c["T"], c["iv"], q, c["type"])
        vanna = bs_vanna(spot, c["strike"], c["T"], c["iv"], q)
        charm = bs_charm(spot, c["strike"], c["T"], c["iv"], q, c["type"])
        vega = bs_vega(spot, c["strike"], c["T"], c["iv"], q)
        gex = gamma * c["oi"] * 100 * spot * spot * 0.01 * (1 if c["type"] == "call" else -1)
        vanna_exposure = vanna * c["oi"] * 100 * spot * 0.01
        charm_exposure = charm * c["oi"] * 100 * spot * spot * 0.01

        # DTE from expiry string
        try:
            exp_date = datetime.strptime(c["expiry"], "%Y-%m-%d").date()
            dte = max((exp_date - today).days, 0)
        except Exception:
            dte = 0

        rows.append({
            "type": c["type"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "dte": dte,
            "iv": round(float(c["iv"]), 4),
            "oi": c["oi"],
            "volume": c.get("volume") or 0,
            "delta": round(float(delta), 4),
            "gamma": round(float(gamma), 6),
            "vega": round(float(vega), 4),
            "vanna": round(float(vanna), 4),
            "charm": round(float(charm), 4),
            "gex": round(gex, 0),
            "vanna_exposure": round(vanna_exposure, 0),
            "charm_exposure": round(charm_exposure, 0),
            "moneyness_pct": round((c["strike"] - spot) / spot * 100, 1),
        })

    # Sort
    reverse = sort_dir == "desc"
    if sort_by == "strike":
        rows.sort(key=lambda r: r["strike"], reverse=reverse)
    elif sort_by == "expiry":
        rows.sort(key=lambda r: r["expiry"], reverse=reverse)
    elif sort_by == "oi":
        rows.sort(key=lambda r: r["oi"], reverse=reverse)
    elif sort_by == "volume":
        rows.sort(key=lambda r: r["volume"], reverse=reverse)
    elif sort_by == "iv":
        rows.sort(key=lambda r: r["iv"], reverse=reverse)
    elif sort_by == "delta":
        rows.sort(key=lambda r: abs(r["delta"]), reverse=reverse)
    elif sort_by == "gamma":
        rows.sort(key=lambda r: r["gamma"], reverse=reverse)
    elif sort_by == "gex":
        rows.sort(key=lambda r: abs(r["gex"]), reverse=reverse)
    elif sort_by == "vanna":
        rows.sort(key=lambda r: abs(r["vanna"]), reverse=reverse)
    elif sort_by == "charm":
        rows.sort(key=lambda r: abs(r["charm"]), reverse=reverse)

    result = _sanitize({
        "ticker": t,
        "spot": spot,
        "rows": rows,
        "count": len(rows),
        "expiries": sorted({r["expiry"] for r in rows}),
        "data_source": raw.get("data_source"),
    })
    cache_set(cache_key, result)
    return result


# ============ Multi-Timeframe GEX ============

@api.get("/gex-timeframes/{ticker}")
async def multi_timeframe_gex(ticker: str):
    """GEX aggregated at multiple timeframes: 0DTE, 1DTE, weekly, monthly."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    cache_key = f"gextf:{t}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    raw = await fetch_spot_and_chains_merged(t, 12)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    today = datetime.now(timezone.utc).date()
    q = DIV_YIELD.get(t, 0.0)

    # Bucket contracts by timeframe
    buckets = {
        "0DTE": [], "1DTE": [], "weekly": [], "monthly": [], "all": []
    }
    for c in raw["contracts"]:
        try:
            exp_date = datetime.strptime(c["expiry"], "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (exp_date - today).days
        if dte <= 0:
            buckets["0DTE"].append(c)
        elif dte <= 1:
            buckets["1DTE"].append(c)
        elif dte <= 7:
            buckets["weekly"].append(c)
        else:
            buckets["monthly"].append(c)
        buckets["all"].append(c)

    result = {}
    for label, contracts in buckets.items():
        if not contracts:
            result[label] = {"gex_total": 0, "call_gex": 0, "put_gex": 0, "strikes": [], "net_gamma": 0}
            continue

        strikes = compute_gex_by_strike(spot, contracts, t)
        total_gex = sum(s["gex"] for s in strikes)
        call_gex = sum(s["gex"] for s in strikes if s["gex"] > 0)
        put_gex = sum(s["gex"] for s in strikes if s["gex"] < 0)

        # Net gamma exposure
        net_gamma = 0
        for c in contracts:
            gamma = bs_gamma(spot, c["strike"], c["T"], c["iv"], q=q)
            sign = 1 if c["type"] == "call" else -1
            net_gamma += gamma * c["oi"] * 100 * sign

        # Key levels
        positive = sorted([s for s in strikes if s["gex"] > 0], key=lambda x: x["gex"], reverse=True)
        negative = sorted([s for s in strikes if s["gex"] < 0], key=lambda x: x["gex"])

        result[label] = {
            "gex_total": round(total_gex, 0),
            "call_gex": round(call_gex, 0),
            "put_gex": round(put_gex, 0),
            "net_gamma": round(net_gamma, 0),
            "contract_count": len(contracts),
            "top_floors": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in positive[:5]],
            "top_ceilings": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in negative[:5]],
            "strikes": strikes,
        }

    result = _sanitize({
        "ticker": t,
        "spot": spot,
        "timeframes": result,
        "asof": datetime.now(timezone.utc).isoformat(),
    })
    cache_set(cache_key, result)
    return result


# ============ GEX Alerts ============

class AlertRule(BaseModel):
    ticker: str
    alert_type: str  # "gex_cross", "gex_spike", "oi_spike", "iv_spike"
    threshold: float
    direction: str = "above"  # "above" or "below"
    expiry: Optional[str] = None
    strike: Optional[float] = None
    label: Optional[str] = None


# In-memory alert store (persist to Mongo in production)
_alert_rules: List[Dict[str, Any]] = []
_alert_history: List[Dict[str, Any]] = []


@api.post("/alerts")
async def create_alert(rule: AlertRule):
    """Create a new GEX alert rule."""
    rule_dict = rule.dict()
    rule_dict["id"] = str(len(_alert_rules) + 1)
    rule_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    rule_dict["active"] = True
    rule_dict["trigger_count"] = 0
    _alert_rules.append(rule_dict)
    return {"status": "created", "rule": rule_dict}


@api.get("/alerts")
async def list_alerts(ticker: Optional[str] = None, active_only: bool = True):
    """List alert rules."""
    rules = _alert_rules
    if ticker:
        rules = [r for r in rules if r["ticker"] == ticker.upper()]
    if active_only:
        rules = [r for r in rules if r.get("active", True)]
    return {"rules": rules, "count": len(rules)}


@api.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    """Delete an alert rule."""
    global _alert_rules
    _alert_rules = [r for r in _alert_rules if r["id"] != alert_id]
    return {"status": "deleted"}


@api.get("/alerts/types")
async def list_alert_types():
    """List all available alert types."""
    from alert_engine import AlertEngine
    AlertEngine()
    # Get all alert type constants
    alert_types = [
        {"type": "GAMMA_FLIP", "priority": "HIGH", "description": "Regime change from positive to negative gamma"},
        {"type": "GAMMA_SQUEEZE", "priority": "HIGH", "description": "Negative gamma + spot near flip + volume spike"},
        {"type": "MOMENTUM_EXTREME", "priority": "HIGH", "description": "Strong bullish or bearish momentum"},
        {"type": "WALL_BREACH", "priority": "MEDIUM", "description": "Spot crosses through call/put wall"},
        {"type": "GEX_MAGNITUDE_SHIFT", "priority": "MEDIUM", "description": "Total GEX changed > 40%"},
        {"type": "GAMMA_FLIP_PROXIMITY", "priority": "MEDIUM", "description": "Spot within 0.3% of gamma flip point"},
        {"type": "PIN_RISK", "priority": "LOW", "description": "Spot near max gamma strike"},
        {"type": "CHARM_PINNING", "priority": "HIGH", "description": "Charm-driven pinning (0DTE)"},
        {"type": "VANNA_REGIME_CHANGE", "priority": "HIGH", "description": "Sign flip in net VEX above floor"},
        {"type": "UNUSUAL_PC_OI_RATIO", "priority": "MEDIUM", "description": "Put OI / call OI ratio > 2x"},
        {"type": "MAX_PAIN_MAGNET", "priority": "LOW", "description": "Spot within 1% of max pain in positive gamma"},
    ]
    return {"alert_types": alert_types, "count": len(alert_types)}


@api.get("/alerts/check/{ticker}")
async def check_alerts(ticker: str):
    """Check all alert rules against current data. Returns triggered alerts."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    raw = await fetch_spot_and_chains_merged(t, 8)
    spot = raw["spot"]
    if not spot:
        return {"triggered": [], "error": "No data"}

    triggered = []
    for rule in _alert_rules:
        if not rule.get("active", True):
            continue
        if rule["ticker"] != t:
            continue

        value = 0
        if rule["alert_type"] == "gex_cross":
            strikes = compute_gex_by_strike(spot, raw["contracts"], t)
            total_gex = sum(s["gex"] for s in strikes)
            value = total_gex
        elif rule["alert_type"] == "gex_spike":
            strikes = compute_gex_by_strike(spot, raw["contracts"], t)
            if rule.get("strike"):
                match = [s for s in strikes if abs(s["strike"] - rule["strike"]) < 0.5]
                value = match[0]["gex"] if match else 0
            else:
                value = max(abs(s["gex"]) for s in strikes) if strikes else 0
        elif rule["alert_type"] == "oi_spike":
            for c in raw["contracts"]:
                if rule.get("strike") and abs(c["strike"] - rule["strike"]) < 0.5:
                    value = c["oi"]
                    break
                elif rule.get("expiry") and c["expiry"] == rule["expiry"]:
                    value = max(value, c["oi"])
        elif rule["alert_type"] == "iv_spike":
            ivs = [c["iv"] for c in raw["contracts"] if c["iv"] > 0]
            value = max(ivs) if ivs else 0

        crossed = False
        if rule["direction"] == "above" and value > rule["threshold"]:
            crossed = True
        elif rule["direction"] == "below" and value < rule["threshold"]:
            crossed = True

        if crossed:
            trigger = {
                "rule_id": rule["id"],
                "ticker": t,
                "type": rule["alert_type"],
                "value": round(value, 2),
                "threshold": rule["threshold"],
                "direction": rule["direction"],
                "label": rule.get("label", ""),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }
            triggered.append(trigger)
            rule["trigger_count"] = rule.get("trigger_count", 0) + 1
            _alert_history.append(trigger)

    return {"triggered": triggered, "spot": spot, "asof": datetime.now(timezone.utc).isoformat()}


# ============ Unusual Options Activity (UOA) ============

@api.get("/uoa/{ticker}")
async def detect_uoa(
    ticker: str,
    min_premium: float = Query(50000, ge=1000, description="Minimum premium in USD"),
    min_oi_ratio: float = Query(2.0, ge=1.0, description="Min volume/OI ratio"),
    max_results: int = Query(20, ge=1, le=50),
):
    """Detect unusual options activity: high premium, volume spikes, OI anomalies."""
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    cache_key = f"uoa:{t}:{min_premium}:{min_oi_ratio}:{max_results}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    raw = await fetch_spot_and_chains_merged(t, 8)
    spot = raw["spot"]
    if not spot or not raw["contracts"]:
        raise HTTPException(404, f"No options data for {ticker}")

    today = datetime.now(timezone.utc).date()
    q = DIV_YIELD.get(t, 0.0)
    unusual = []

    # Compute per-strike volume and OI stats
    all_volumes = [c.get("volume", 0) for c in raw["contracts"] if c.get("volume", 0) > 0]
    avg_volume = sum(all_volumes) / len(all_volumes) if all_volumes else 0
    all_oi = [c["oi"] for c in raw["contracts"] if c["oi"] > 0]
    avg_oi = sum(all_oi) / len(all_oi) if all_oi else 0

    for c in raw["contracts"]:
        volume = c.get("volume") or 0
        oi = c["oi"]
        # Estimate premium using BS price (mid/last not available from yfinance chain)
        if c["type"] == "call":
            est_price = bs_call_price(spot, c["strike"], c["T"], c["iv"], r=RISK_FREE_RATE, q=q)
        else:
            est_price = bs_put_price(spot, c["strike"], c["T"], c["iv"], r=RISK_FREE_RATE, q=q)
        premium = volume * est_price * 100  # Contract multiplier

        # Skip if below minimum premium
        if premium < min_premium:
            continue

        # Volume/OI ratio
        vol_oi_ratio = volume / max(oi, 1)

        # Z-score for volume
        if len(all_volumes) > 1:
            vol_std = (sum((v - avg_volume) ** 2 for v in all_volumes) / len(all_volumes)) ** 0.5
            vol_zscore = (volume - avg_volume) / max(vol_std, 1)
        else:
            vol_zscore = 0

        # OI vs average
        oi_ratio = oi / max(avg_oi, 1)

        # DTE
        try:
            exp_date = datetime.strptime(c["expiry"], "%Y-%m-%d").date()
        except Exception:
            continue
        dte = (exp_date - today).days

        # Signal scoring
        score = 0
        signals = []

        if vol_oi_ratio >= min_oi_ratio:
            score += min(vol_oi_ratio * 10, 40)
            signals.append(f"vol/OI x{vol_oi_ratio:.1f}")

        if vol_zscore > 2:
            score += min(vol_zscore * 10, 30)
            signals.append(f"vol z{vol_zscore:.1f}")

        if oi_ratio > 3:
            score += min(oi_ratio * 5, 20)
            signals.append(f"OI x{oi_ratio:.1f} avg")

        if dte <= 7 and premium > min_premium * 2:
            score += 15
            signals.append("0-1DTE large")

        if premium > 500000:
            score += 20
            signals.append("block trade")

        if score < 20:
            continue

        # Determine sentiment
        if c["type"] == "call" and vol_oi_ratio > 3:
            sentiment = "bullish"
        elif c["type"] == "put" and vol_oi_ratio > 3:
            sentiment = "bearish"
        elif c["type"] == "call":
            sentiment = "mildly bullish"
        else:
            sentiment = "mildly bearish"

        unusual.append({
            "type": c["type"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "dte": dte,
            "iv": round(float(c["iv"]), 4),
            "volume": volume,
            "oi": oi,
            "est_price": round(float(est_price), 2),
            "premium": round(premium, 0),
            "vol_oi_ratio": round(vol_oi_ratio, 2),
            "vol_zscore": round(vol_zscore, 2),
            "score": round(score, 0),
            "signals": signals,
            "sentiment": sentiment,
            "moneyness_pct": round((c["strike"] - spot) / spot * 100, 1),
        })

    # Sort by score descending
    unusual.sort(key=lambda x: x["score"], reverse=True)

    result = _sanitize({
        "ticker": t,
        "spot": spot,
        "unusual": unusual[:max_results],
        "count": len(unusual[:max_results]),
        "stats": {
            "avg_volume": round(avg_volume, 0),
            "avg_oi": round(avg_oi, 0),
            "total_contracts_scanned": len(raw["contracts"]),
        },
        "asof": datetime.now(timezone.utc).isoformat(),
    })
    cache_set(cache_key, result)
    return result


# ============ WebSocket Live GEX Stream ============

@app.websocket("/ws/gex/{ticker}")
async def websocket_gex(websocket: WebSocket, ticker: str):
    """WebSocket stream pushing live spot + key GEX levels every 5 seconds.
    Includes heartbeat/ping-pong for connection health."""
    await websocket.accept()
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    
    consecutive_errors = 0
    max_errors = 10
    
    try:
        while True:
            try:
                raw = await fetch_spot_and_chains_merged(t, 4)
                spot = raw["spot"]
                if not spot or not raw["contracts"]:
                    await websocket.send_json({"error": "No data", "ticker": t})
                    consecutive_errors += 1
                else:
                    consecutive_errors = 0  # Reset on success
                    strikes = compute_gex_by_strike(spot, raw["contracts"], t)
                    total_gex = sum(s["gex"] for s in strikes)
                    positive = sorted([s for s in strikes if s["gex"] > 0], key=lambda x: x["gex"], reverse=True)
                    negative = sorted([s for s in strikes if s["gex"] < 0], key=lambda x: x["gex"])
                    nodes = classify_nodes(strikes, spot)
                    
                    payload = {
                        "ticker": t,
                        "spot": spot,
                        "total_gex": round(total_gex, 0),
                        "king": nodes.get("king"),
                        "floors": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in positive[:5]],
                        "ceilings": [{"strike": s["strike"], "gex": round(s["gex"], 0)} for s in negative[:5]],
                        "regime": nodes.get("regime"),
                        "asof": datetime.now(timezone.utc).isoformat(),
                    }
                    await websocket.send_json(_sanitize(payload))
                
                # Back off on repeated errors
                sleep_time = min(5 * (2 ** consecutive_errors), 60)
                await asyncio.sleep(sleep_time)
                
            except WebSocketDisconnect:
                raise
            except Exception as e:
                consecutive_errors += 1
                log.warning(f"WebSocket error for {t}: {e} (consecutive: {consecutive_errors})")
                await websocket.send_json({"error": str(e), "ticker": t})
                if consecutive_errors >= max_errors:
                    log.error(f"Too many consecutive errors for {t}, closing WebSocket")
                    await websocket.close(code=1011, reason="Too many errors")
                    break
                await asyncio.sleep(min(5 * consecutive_errors, 30))
    except WebSocketDisconnect:
        log.info(f"WebSocket disconnected: {t}")
    except Exception as e:
        log.error(f"WebSocket fatal error for {t}: {e}")


app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if os.environ.get("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' ws: wss: https:; "
        "font-src 'self' data:;"
    )
    return response

# Auth middleware — checks X-API-Key header for mutating routes
from auth import verify_api_key

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Verify API key for protected mutating routes."""
    try:
        await verify_api_key(request)
    except HTTPException as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    response = await call_next(request)
    return response


# ----------------------------- Memory Routes (Mem0) -----------------------------

from memory_integration import remember_trade, remember_gex_observation, recall_trading_context, get_trading_summary


class TradeMemoryRequest(BaseModel):
    ticker: str
    trade_type: str = "unknown"
    entry_price: float = 0
    exit_price: float = 0
    pnl: float = 0
    notes: str = ""


class GexMemoryRequest(BaseModel):
    ticker: str
    observation: str
    metadata: Optional[Dict[str, Any]] = None


@api.post("/memory/trade")
async def api_remember_trade(req: TradeMemoryRequest):
    """Store a trade in memory."""
    result = remember_trade(req.ticker, req.dict())
    return {"status": "ok", "id": result}


@api.post("/memory/gex")
async def api_remember_gex(req: GexMemoryRequest):
    """Store a GEX observation in memory."""
    result = remember_gex_observation(req.ticker, req.observation, req.metadata)
    return {"status": "ok", "id": result}


@api.get("/memory/recall/{ticker}")
async def api_recall_memory(ticker: str, query: str = ""):
    """Recall memories for a ticker."""
    results = recall_trading_context(ticker, query)
    return {"results": results}


@api.get("/memory/summary/{ticker}")
async def api_memory_summary(ticker: str):
    """Get a trading summary from memory."""
    summary = get_trading_summary(ticker)
    return {"summary": summary}


app.include_router(api)

from routes.heatseeker import router as heatseeker_router  # noqa: E402
app.include_router(heatseeker_router)


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
