"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.
Uses CVForge's cvserver API for real-time options data (32 expirations, 171 strikes).
Falls back to yfinance when CVForge is unavailable.
"""

import asyncio
import logging
import math
import os
import time

import httpx
from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

# ── CVForge cvserver config ──
CVFORGE_URL = os.environ.get("CVFORGE_URL", "http://localhost:63621")
CVFORGE_TIMEOUT = 10.0  # seconds

# ── Cache ──
_chain_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 120  # 2 minutes


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


async def _cvforge_chain(symbol: str, fields: list[str] | None = None) -> dict | None:
    """
    Fetch options chain from CVForge's cvserver API.
    Returns None on failure (caller should fallback to yfinance).
    """
    if not fields:
        fields = [
            "expiration_date", "strike_price", "contract_type",
            "implied_volatility", "delta", "gamma", "theta", "vega",
            "bid", "ask", "midpoint", "open_interest", "day_volume",
            "underlying_price",
        ]
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(
                f"{CVFORGE_URL}/api/data/chains",
                json={"symbol": symbol, "params": fields},
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"cvforge chain: HTTP {resp.status_code} for {symbol}")
            return None
    except Exception as e:
        logger.warning(f"cvforge chain: error for {symbol}: {e}")
        return None


def _yfinance_chain_sync(sym: str, fields: list[str]) -> dict:
    """Synchronous yfinance fallback."""
    import yfinance as yf
    t = yf.Ticker(sym)
    exps = list(t.options)[:6]
    if not exps:
        return {"symbol": sym, "params": ["strike"] + fields, "chain": []}
    result = []
    for exp in exps:
        try:
            oc = t.option_chain(exp)
            strikes_out = []
            for _, row in oc.calls.iterrows():
                strike = float(row.get("strike", 0))
                cv, pv = [], []
                for f in fields:
                    v1 = row.get(f)
                    pr = oc.puts[oc.puts["strike"] == strike]
                    v2 = pr.iloc[0].get(f) if len(pr) > 0 else None
                    cv.append(_safe_float(v1))
                    pv.append(_safe_float(v2))
                strikes_out.append([strike, cv, pv])
            result.append({"expiration": exp, "strikes": strikes_out})
        except Exception:
            continue
    return {"symbol": sym, "params": ["strike"] + fields, "chain": result}


# ── Router ──
router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """Live institutional options flow with classification."""
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(prints),
        "prints": prints,
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """Contract-level drilldown."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(symbol: str):
    """
    Options chain — tries CVForge first (32 exp, 171 strikes), falls back to yfinance.
    Cached for 120s.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    # Cache check
    if sym in _chain_cache:
        ts, data = _chain_cache[sym]
        if time.time() - ts < CACHE_TTL:
            return data

    # Try CVForge first (fast, rich data)
    data = await _cvforge_chain(sym)
    if data and data.get("chain"):
        _chain_cache[sym] = (time.time(), data)
        return data

    # Fallback to yfinance (slow but reliable)
    try:
        loop = asyncio.get_event_loop()
        fields = [
            "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility",
        ]
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _yfinance_chain_sync, sym, fields),
            timeout=60.0,
        )
        _chain_cache[sym] = (time.time(), data)
        return data
    except asyncio.TimeoutError:
        return {
            "symbol": sym,
            "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"],
            "chain": [],
            "error": "timeout",
        }
    except Exception as e:
        logger.warning(f"flowseeker chain: {sym}: {e}")
        return {"symbol": sym, "params": [], "chain": [], "error": str(e)}


@router.get("/screen")
async def screen_options(
    ticker: str = Query(...),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen options — uses CVForge screen API if available, else cached chain."""
    sym = (ticker or "").strip().upper()

    # Try CVForge screen API first
    cvforge_data = await _cvforge_screen(sym, min_premium, min_oi, option_type, limit)
    if cvforge_data:
        return cvforge_data

    # Fallback: use cached chain data
    if sym not in _chain_cache:
        await options_chain(sym)

    chain = _chain_cache.get(sym, (0, {})).get("1", {}).get("chain", [])
    contracts = []
    for exp in chain:
        for strike_data in exp.get("strikes", []):
            strike, cv, pv = strike_data[0], strike_data[1] or [], strike_data[2] or []
            for ctype, vals in [("CALL", cv), ("PUT", pv)]:
                prem = (vals[2] or 0) * 100 if len(vals) > 2 else 0
                oi = int(vals[4] or 0) if len(vals) > 4 else 0
                if prem >= min_premium and oi >= min_oi:
                    if not option_type or option_type.upper() == ctype:
                        contracts.append({
                            "ticker": sym, "strike": strike,
                            "expiration": exp.get("expiration", ""),
                            "type": ctype,
                            "bid": vals[0] if len(vals) > 0 else None,
                            "ask": vals[1] if len(vals) > 1 else None,
                            "lastPrice": vals[2] if len(vals) > 2 else None,
                            "volume": int(vals[3] or 0) if len(vals) > 3 else 0,
                            "openInterest": oi,
                            "premium": prem,
                        })

    contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
    return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}


async def _cvforge_screen(
    symbol: str,
    min_premium: float,
    min_oi: int,
    option_type: str | None,
    limit: int,
) -> dict | None:
    """Try CVForge screen API. Returns None on failure."""
    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "trade_size", "trade_price", "open_interest", "implied_volatility",
        "delta", "gamma", "theta", "vega", "bid", "ask",
    ]
    filters = [{"field": "underlying_ticker", "op": "eq", "value": symbol}]
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(
                f"{CVFORGE_URL}/api/data/screen",
                json={
                    "columns": columns,
                    "filters": filters,
                    "sort": [{"field": "trade_price", "direction": "desc"}],
                    "limit": limit,
                },
            )
            if resp.status_code == 200:
                d = resp.json()
                rows = d.get("rows", [])
                return {
                    "ticker": symbol,
                    "count": len(rows),
                    "results": [
                        {
                            "ticker": r[0], "strike": r[1], "expiration": r[2],
                            "type": r[3], "size": r[4], "price": r[5],
                            "oi": r[6], "iv": r[7], "delta": r[8],
                            "gamma": r[9], "theta": r[10], "vega": r[11],
                            "bid": r[12], "ask": r[13],
                        }
                        for r in rows
                    ],
                }
    except Exception as e:
        logger.warning(f"cvforge screen: {symbol}: {e}")
    return None
