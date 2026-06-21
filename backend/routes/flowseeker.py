"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.
Chain and screen endpoints use yfinance with background cache warming.
"""

import asyncio
import logging
import math
import time

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

# ── Cache ──
_chain_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60
_WARM_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "TLT"]
_DEFAULT_FIELDS = ["bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]


def _get_cached(symbol: str) -> dict | None:
    if symbol in _chain_cache:
        ts, data = _chain_cache[symbol]
        if time.time() - ts < _CACHE_TTL:
            return data
        del _chain_cache[symbol]
    return None


def _set_cached(symbol: str, data: dict) -> None:
    _chain_cache[symbol] = (time.time(), data)


def _fetch_chain_sync(sym: str, fields: list[str]) -> dict:
    """Synchronous yfinance chain fetch. Returns {symbol, params, chain}."""
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


def _safe_float(v):
    """Convert to float, handling NaN/None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


async def _warm_cache():
    """Background task to pre-fetch chain data for popular tickers."""
    # Initial delay to let server start
    await asyncio.sleep(10)
    while True:
        for sym in _WARM_TICKERS:
            try:
                data = await asyncio.to_thread(_fetch_chain_sync, sym, _DEFAULT_FIELDS)
                _set_cached(sym, data)
                logger.info(f"flowseeker: warmed {sym} ({len(data.get('chain', []))} expirations)")
            except Exception as e:
                logger.warning(f"flowseeker: warm failed {sym}: {e}")
            await asyncio.sleep(5)
        await asyncio.sleep(_CACHE_TTL)


# ── Router ──
router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.on_event("startup")
async def start_cache_warmer():
    asyncio.create_task(_warm_cache())


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
async def options_chain(
    symbol: str,
    fields: str | None = Query(None),
):
    """
    Return options chain for a symbol using yfinance.
    Cached for 60s. Background warmer pre-fetches popular tickers.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    requested = [f.strip().lower() for f in fields.split(",") if f.strip()] if fields else _DEFAULT_FIELDS

    # Return cached if available
    cached = _get_cached(sym)
    if cached is not None:
        return cached

    # Fetch fresh (slow — first call only)
    try:
        data = await asyncio.to_thread(_fetch_chain_sync, sym, requested)
        _set_cached(sym, data)
        return data
    except Exception as e:
        logger.warning(f"flowseeker chain: {sym}: {e}")
        return {"symbol": sym, "params": requested, "chain": [], "error": str(e)}


@router.get("/screen")
async def screen_options(
    ticker: str = Query(...),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None, description="call, put, or all"),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen options by criteria using yfinance."""
    sym = (ticker or "").strip().upper()

    cached = _get_cached(sym)
    if cached is None or not cached.get("chain"):
        try:
            await asyncio.to_thread(_fetch_chain_sync, sym, _DEFAULT_FIELDS)
            cached = _get_cached(sym)
        except Exception:
            return {"ticker": sym, "count": 0, "results": []}

    contracts = []
    for exp in (cached or {}).get("chain", []):
        exp_str = exp.get("expiration", "")
        for strike_data in exp.get("strikes", []):
            strike = strike_data[0]
            call_vals = strike_data[1] or []
            put_vals = strike_data[2] or []
            # Estimate premium from lastPrice (index 2) * 100
            call_premium = (call_vals[2] or 0) * 100 if len(call_vals) > 2 else 0
            put_premium = (put_vals[2] or 0) * 100 if len(put_vals) > 2 else 0
            call_oi = int(call_vals[4] or 0) if len(call_vals) > 4 else 0
            put_oi = int(put_vals[4] or 0) if len(put_vals) > 4 else 0

            for ctype, prem, oi, vals in [("CALL", call_premium, call_oi, call_vals), ("PUT", put_premium, put_oi, put_vals)]:
                if prem >= min_premium and oi >= min_oi:
                    if not option_type or option_type.upper() == ctype:
                        contracts.append({
                            "ticker": sym, "strike": strike, "expiration": exp_str,
                            "type": ctype,
                            "bid": vals[0] if len(vals) > 0 else None,
                            "ask": vals[1] if len(vals) > 1 else None,
                            "lastPrice": vals[2] if len(vals) > 2 else None,
                            "volume": int(vals[3] or 0) if len(vals) > 3 else 0,
                            "openInterest": oi,
                            "impliedVolatility": vals[5] if len(vals) > 5 else None,
                            "premium": prem,
                        })

    contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
    return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}
