"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.

Mirrors backend/routes/heatseeker.py's pattern: thin wrappers around
services/flowseeker.py with no business logic in the routes themselves.
Failures from the upstream provider degrade to 200 with empty payloads so
the frontend can render an empty state instead of crashing.
"""

import asyncio
import logging
import math
import time

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

# In-memory chain cache: {symbol: (timestamp, data)}
_chain_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 30  # seconds


def _get_cached_chain(symbol: str) -> dict | None:
    """Return cached chain data if still fresh."""
    if symbol in _chain_cache:
        ts, data = _chain_cache[symbol]
        if time.time() - ts < _CACHE_TTL:
            return data
        del _chain_cache[symbol]
    return None


def _set_cached_chain(symbol: str, data: dict) -> None:
    """Store chain data in cache."""
    _chain_cache[symbol] = (time.time(), data)


router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None, description="Optional ticker; omit for cross-ticker outliers"),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """Live institutional options flow with classification (sweep/block/unusual/regular)."""
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(prints),
        "prints": prints,
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """Contract-level drilldown: chain volume, OI, chain ratio, recent prints."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(
    symbol: str,
    fields: str | None = Query(None, description="Comma-separated list of fields"),
):
    """
    Return options chain for a symbol using yfinance.
    Results are cached for 30 seconds to avoid repeated slow yfinance calls.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    # Check cache first
    cached = _get_cached_chain(sym)
    if cached is not None:
        return cached

    requested_fields: list[str] = []
    if fields:
        requested_fields = [f.strip().lower() for f in fields.split(",") if f.strip()]
    if not requested_fields:
        requested_fields = ["bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]

    try:
        import yfinance as yf

        def _fetch_chain():
            t = yf.Ticker(sym)
            exps = list(t.options)[:6]
            if not exps:
                return {"symbol": sym, "params": ["strike"] + requested_fields, "chain": []}
            result = []
            for exp in exps:
                try:
                    oc = t.option_chain(exp)
                    calls, puts = oc.calls, oc.puts
                    strikes_out = []
                    for _, row in calls.iterrows():
                        strike = float(row.get("strike", 0))
                        cv, pv = [], []
                        for field in requested_fields:
                            v1 = row.get(field)
                            pr = puts[puts["strike"] == strike]
                            v2 = pr.iloc[0].get(field) if len(pr) > 0 else None
                            cv.append(float(v1) if v1 is not None and isinstance(v1, (int, float)) and not math.isnan(v1) else None)
                            pv.append(float(v2) if v2 is not None and isinstance(v2, (int, float)) and not math.isnan(v2) else None)
                        strikes_out.append([strike, cv, pv])
                    result.append({"expiration": exp, "strikes": strikes_out})
                except Exception:
                    continue
            return {"symbol": sym, "params": ["strike"] + requested_fields, "chain": result}

        chain_data = await asyncio.to_thread(_fetch_chain)
        _set_cached_chain(sym, chain_data)
        return chain_data
    except Exception as e:
        logger.warning(f"flowseeker chain: error for {sym}: {e}")
        return {"symbol": sym, "params": requested_fields, "chain": [], "error": str(e)}


@router.get("/screen")
async def screen_options(
    ticker: str = Query(..., description="Ticker symbol to screen"),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None, description="call, put, or all"),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen options by criteria using yfinance chain data with caching."""
    sym = (ticker or "").strip().upper()
    if not sym:
        raise HTTPException(400, "ticker required")

    try:
        import yfinance as yf

        def _screen():
            t = yf.Ticker(sym)
            exps = list(t.options)[:6]
            contracts = []
            for exp in exps:
                try:
                    oc = t.option_chain(exp)
                    for _, row in oc.calls.iterrows():
                        premium = float(row.get("lastPrice", 0) or 0) * 100
                        oi = int(row.get("openInterest", 0) or 0)
                        if premium >= min_premium and oi >= min_oi:
                            if not option_type or option_type.upper() == "CALL":
                                contracts.append({
                                    "ticker": sym, "strike": float(row.get("strike", 0)),
                                    "expiration": exp, "type": "CALL",
                                    "bid": float(row.get("bid", 0) or 0),
                                    "ask": float(row.get("ask", 0) or 0),
                                    "lastPrice": float(row.get("lastPrice", 0) or 0),
                                    "volume": int(row.get("volume", 0) or 0),
                                    "openInterest": oi,
                                    "impliedVolatility": float(row.get("impliedVolatility", 0) or 0),
                                    "premium": premium,
                                })
                    for _, row in oc.puts.iterrows():
                        premium = float(row.get("lastPrice", 0) or 0) * 100
                        oi = int(row.get("openInterest", 0) or 0)
                        if premium >= min_premium and oi >= min_oi:
                            if not option_type or option_type.upper() == "PUT":
                                contracts.append({
                                    "ticker": sym, "strike": float(row.get("strike", 0)),
                                    "expiration": exp, "type": "PUT",
                                    "bid": float(row.get("bid", 0) or 0),
                                    "ask": float(row.get("ask", 0) or 0),
                                    "lastPrice": float(row.get("lastPrice", 0) or 0),
                                    "volume": int(row.get("volume", 0) or 0),
                                    "openInterest": oi,
                                    "impliedVolatility": float(row.get("impliedVolatility", 0) or 0),
                                    "premium": premium,
                                })
                except Exception:
                    continue
            contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
            return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}

        return await asyncio.to_thread(_screen)
    except Exception as e:
        logger.warning(f"flowseeker screen: error for {sym}: {e}")
        return {"ticker": sym, "count": 0, "results": [], "error": str(e)}
