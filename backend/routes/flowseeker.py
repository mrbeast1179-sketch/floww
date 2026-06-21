"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.

Mirrors backend/routes/heatseeker.py's pattern: thin wrappers around
services/flowseeker.py with no business logic in the routes themselves.
Failures from the upstream provider degrade to 200 with empty payloads so
the frontend can render an empty state instead of crashing.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

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
    Returns { symbol, params, chain: [{ expiration, strikes: [[strike, [call_vals], [put_vals]]] }] }
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    requested_fields: list[str] = []
    if fields:
        requested_fields = [f.strip().lower() for f in fields.split(",") if f.strip()]

    if not requested_fields:
        requested_fields = ["bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]

    try:
        import yfinance as yf
        import asyncio

        loop = asyncio.get_event_loop()
        ticker = await loop.run_in_executor(None, lambda: yf.Ticker(sym))
        expirations = await loop.run_in_executor(None, lambda: list(ticker.options)[:6])

        if not expirations:
            return {"symbol": sym, "params": ["strike"] + requested_fields, "chain": []}

        chain_out = []
        for exp in expirations:
            try:
                opt_chain = await loop.run_in_executor(None, lambda e=exp: ticker.option_chain(e))
                calls = opt_chain.calls
                puts = opt_chain.puts

                strikes_out = []
                for _, row in calls.iterrows():
                    strike = float(row.get("strike", 0))
                    call_vals = []
                    put_vals = []
                    for field in requested_fields:
                        cv = row.get(field)
                        put_row = puts[puts["strike"] == strike]
                        pv = put_row.iloc[0].get(field) if len(put_row) > 0 else None
                        call_vals.append(float(cv) if cv is not None and isinstance(cv, (int, float)) else None)
                        put_vals.append(float(pv) if pv is not None and isinstance(pv, (int, float)) else None)
                    strikes_out.append([strike, call_vals, put_vals])

                chain_out.append({"expiration": exp, "strikes": strikes_out})
            except Exception as e:
                logger.warning(f"flowseeker chain: error fetching {sym} {exp}: {e}")
                continue

        return {"symbol": sym, "params": ["strike"] + requested_fields, "chain": chain_out}
    except Exception as e:
        logger.warning(f"flowseeker chain: error for {sym}: {e}")
        return {"symbol": sym, "params": ["strike"] + requested_fields, "chain": [], "error": str(e)}


@router.get("/screen")
async def screen_options(
    ticker: str = Query(..., description="Ticker symbol to screen"),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None, description="call, put, or all"),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Screen options by criteria using yfinance chain data.
    Returns filtered list of contracts matching all specified thresholds.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        raise HTTPException(400, "ticker required")

    try:
        import yfinance as yf
        import asyncio

        loop = asyncio.get_event_loop()
        ticker_obj = await loop.run_in_executor(None, lambda: yf.Ticker(sym))
        expirations = await loop.run_in_executor(None, lambda: list(ticker_obj.options)[:6])

        contracts = []
        for exp in expirations:
            try:
                opt_chain = await loop.run_in_executor(None, lambda e=exp: ticker_obj.option_chain(e))
                for _, row in opt_chain.calls.iterrows():
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
                for _, row in opt_chain.puts.iterrows():
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
            except Exception as e:
                logger.warning(f"flowseeker screen: error fetching {sym} {exp}: {e}")
                continue

        # Sort by premium descending, apply limit
        contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
        return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}
    except Exception as e:
        logger.warning(f"flowseeker screen: error for {sym}: {e}")
        return {"ticker": sym, "count": 0, "results": [], "error": str(e)}
