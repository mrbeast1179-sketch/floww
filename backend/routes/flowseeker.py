"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.
Chain and screen endpoints use yfinance (single-ticker only, no multi-fetch).
"""

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

# ── Cache (thread-safe GIL dict) ──
_chain_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 120  # 2 minutes


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except (TypeError, ValueError):
        return None


def _fetch_chain_sync(sym: str) -> dict:
    """Fetch single-ticker options chain. Disable yfinance multi-fetch."""
    import yfinance as yf
    t = yf.Ticker(sym)
    # Disable session sharing to avoid multi-fetch side effects
    exps = list(t.options)[:6]
    if not exps:
        return {"symbol": sym, "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"], "chain": []}
    result = []
    for exp in exps:
        try:
            oc = t.option_chain(exp)
            strikes_out = []
            for _, row in oc.calls.iterrows():
                strike = float(row["strike"])
                call_vals = [_safe_float(row.get(f)) for f in ["bid", "ask", "lastPrice", "volume", "openInterest"]]
                put_row = oc.puts[oc.puts["strike"] == strike]
                put_vals = [_safe_float(put_row.iloc[0].get(f)) if len(put_row) > 0 else None for f in ["bid", "ask", "lastPrice", "volume", "openInterest"]]
                strikes_out.append([strike, call_vals, put_vals])
            result.append({"expiration": exp, "strikes": strikes_out})
        except Exception:
            continue
    return {"symbol": sym, "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"], "chain": result}


async def _warm_cache():
    """Pre-fetch SPY chain on startup."""
    await asyncio.sleep(5)  # let server settle
    try:
        data = await asyncio.to_thread(_fetch_chain_sync, "SPY")
        _chain_cache["SPY"] = (time.time(), data)
        logger.info(f"flowseeker: SPY warmed ({len(data['chain'])} expirations)")
    except Exception as e:
        logger.warning(f"flowseeker: SPY warm failed: {e}")


# ── Router ──
router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.on_event("startup")
async def _startup():
    asyncio.create_task(_warm_cache())


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {"ticker": (ticker.strip().upper() if ticker else None), "count": len(prints), "prints": prints}


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(symbol: str):
    """Options chain from yfinance. Cached for 120s."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    if sym in _chain_cache:
        ts, data = _chain_cache[sym]
        if time.time() - ts < _CACHE_TTL:
            return data

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(_fetch_chain_sync, sym),
            timeout=60.0
        )
        _set_cached_chain(sym, data)
        return data
    except asyncio.TimeoutError:
        logger.warning(f"flowseeker chain: timeout for {sym}")
        return {"symbol": sym, "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"], "chain": [], "error": "timeout"}
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
    """Screen options from cached chain data."""
    sym = (ticker or "").strip().upper()

    # Ensure chain is cached
    if sym not in _chain_cache:
        try:
            data = await asyncio.to_thread(_fetch_chain_sync, sym)
            _chain_cache[sym] = (time.time(), data)
        except Exception:
            return {"ticker": sym, "count": 0, "results": []}

    chain = _chain_cache.get(sym, {}).get("chain", [])
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
                            "ticker": sym, "strike": strike, "expiration": exp["expiration"],
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
