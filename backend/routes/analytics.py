"""
backend/routes/analytics.py

Analytics routes: implied-pdf, regime, hedge-impulse, pressure-cloud, charm-integral,
advanced, gamma-flip, daily-checklist, movers, history, patterns/glossary, contract, flow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


async def _fetch_chain(ticker: str, expiries: int):
    """Fetch option chain with lazy import."""
    from server import fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await fetch_spot_and_chains_merged(t, expiries)


def _check_chain(raw: dict, ticker: str):
    """Validate chain data exists."""
    spot = raw.get("spot")
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")


@router.get("/implied-pdf/{ticker}")
async def implied_pdf(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_implied_pdf, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_implied_pdf(raw["spot"], raw["contracts"]))


@router.get("/regime/{ticker}")
async def regime(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_market_regime, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_market_regime(raw["spot"], raw["contracts"]))


@router.get("/hedge-impulse/{ticker}")
async def hedge_impulse(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_hedge_impulse_curve, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_hedge_impulse_curve(raw["spot"], raw["contracts"], ticker.strip().upper()))


@router.get("/pressure-cloud/{ticker}")
async def pressure_cloud(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_pressure_cloud, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_pressure_cloud(raw["spot"], raw["contracts"], ticker.strip().upper()))


@router.get("/charm-integral/{ticker}")
async def charm_integral_endpoint(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_charm_integral, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_charm_integral(raw["spot"], raw["contracts"], ticker.strip().upper()))


@router.get("/advanced/{ticker}")
async def advanced_analytics(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import (
        calc_implied_pdf, calc_market_regime, calc_hedge_impulse_curve,
        calc_pressure_cloud, calc_charm_integral, _sanitize,
    )
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    spot = raw["spot"]
    contracts = raw["contracts"]
    t = ticker.strip().upper()

    return _sanitize({
        "ticker": t,
        "spot": spot,
        "implied_pdf": calc_implied_pdf(spot, contracts),
        "regime": calc_market_regime(spot, contracts),
        "hedge_impulse": calc_hedge_impulse_curve(spot, contracts, t),
        "pressure_cloud": calc_pressure_cloud(spot, contracts, t),
        "charm_integral": calc_charm_integral(spot, contracts, t),
        "asof": datetime.now(timezone.utc).isoformat(),
    })


@router.get("/gamma-flip/{ticker}")
async def gamma_flip(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import calc_gamma_flip_levels, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    if not spot or spot != spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    return _sanitize(calc_gamma_flip_levels(spot, raw["contracts"], ticker.strip().upper()))


@router.get("/daily-checklist/{ticker}")
async def daily_checklist(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    from server import (
        calc_gamma_flip_levels, calc_market_regime, calc_iv_surface_data,
        calc_skew_metrics, _sanitize,
    )
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    if not spot or spot != spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")

    gf = calc_gamma_flip_levels(spot, raw["contracts"], ticker.strip().upper())
    regime_data = calc_market_regime(spot, raw["contracts"])
    iv_surface = calc_iv_surface_data(spot, raw["contracts"])
    skew = calc_skew_metrics(spot, raw["contracts"])

    return _sanitize({
        "ticker": ticker.strip().upper(),
        "spot": spot,
        "asof": datetime.now(timezone.utc).isoformat(),
        "regime": {
            "gex_regime": gf["regime"],
            "market_regime": regime_data.get("regime", "unknown"),
            "iv_rank": iv_surface.get("atm_iv", 0),
            "skew": skew.get("risk_reversal_25d", 0),
        },
    })


@router.get("/movers")
async def movers(limit: int = Query(20, ge=1, le=100)):
    """Get top market movers."""
    from server import _fetch_movers_sync
    from datetime import datetime, timezone
    data = _fetch_movers_sync()
    return {"results": data[:limit], "asof": datetime.now(timezone.utc).isoformat()}


@router.get("/history/{ticker}")
async def history(ticker: str, days: int = Query(30, ge=1, le=365)):
    """Get historical snapshots for a ticker."""
    from server import db
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db.snapshots.find(
        {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("ts", -1)
    snapshots = await cursor.to_list(length=1000)
    return {"ticker": ticker.upper(), "snapshots": snapshots, "count": len(snapshots)}


@router.get("/patterns/glossary")
async def patterns_glossary():
    """Get pattern glossary."""
    from server import PATTERN_GLOSSARY
    return PATTERN_GLOSSARY


@router.get("/contract/{ticker}")
async def contract(ticker: str, expiry: Optional[str] = None):
    """Get contract details for a ticker."""
    from server import fetch_spot_and_chains_merged, _sanitize
    raw = await _fetch_chain(ticker, 12)
    _check_chain(raw, ticker)
    contracts = raw["contracts"]
    if expiry:
        contracts = [c for c in contracts if c.get("expiry") == expiry]
    spot = raw["spot"]
    rows = []
    for c in contracts:
        gamma = c.get("gamma", 0)
        oi = c.get("oi", c.get("open_interest", 0))
        gex = gamma * oi * 100 * spot * (1 if c["type"] == "call" else -1)
        rows.append({
            "type": c["type"],
            "strike": c["strike"],
            "expiry": c["expiry"],
            "iv": c.get("iv", 0),
            "delta": c.get("delta", 0),
            "gamma": c.get("gamma", 0),
            "vega": c.get("vega", 0),
            "theta": c.get("theta", 0),
            "oi": c.get("oi", c.get("open_interest", 0)),
            "volume": c.get("volume", 0),
            "bid": c.get("bid", 0),
            "ask": c.get("ask", 0),
            "gex": gex,
        })
    return _sanitize({"ticker": ticker.strip().upper(), "spot": spot, "rows": rows, "count": len(rows)})


@router.get("/flow/{ticker}")
async def flow(ticker: str, days: int = Query(7, ge=1, le=30)):
    """Get options flow data for a ticker."""
    from server import db
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db.flow.find(
        {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
        {"_id": 0},
    ).sort("ts", -1).limit(500)
    return await cursor.to_list(length=500)


@router.get("/surface/{ticker}")
async def surface(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Get IV surface data."""
    from server import fetch_spot_and_chains_merged, calc_iv_surface_data, _sanitize
    raw = await _fetch_chain(ticker, expiries)
    _check_chain(raw, ticker)
    return _sanitize(calc_iv_surface_data(raw["spot"], raw["contracts"]))


@router.get("/regime-stats/{ticker}")
async def regime_stats(ticker: str, days: int = Query(30, ge=1, le=365)):
    """Get regime statistics."""
    from server import db
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cursor = db.snapshots.find(
        {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
        {"regime": 1, "ts": 1, "_id": 0},
    ).sort("ts", -1)
    docs = await cursor.to_list(length=1000)
    return {"ticker": ticker.upper(), "n_samples": len(docs), "data": docs}


@router.get("/compare")
async def compare(tickers: str = Query(...)):
    """Compare analytics across multiple tickers."""
    from server import fetch_spot_and_chains_merged, calc_market_regime, _sanitize
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    out = {}
    for sym in syms:
        try:
            raw = await _fetch_chain(sym, 4)
            _check_chain(raw, sym)
            out[sym] = _sanitize(calc_market_regime(raw["spot"], raw["contracts"]))
        except HTTPException as e:
            out[sym] = {"error": e.detail}
    return out


@router.get("/correlation")
async def correlation(tickers: str = Query(...), days: int = Query(30, ge=1, le=365)):
    """Get correlation matrix for multiple tickers."""
    from server import db
    from datetime import timedelta
    import numpy as np
    import pandas as pd
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    data = {}
    for sym in syms:
        cursor = db.snapshots.find(
            {"ticker": sym, "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "_id": 0},
        ).sort("ts", 1)
        docs = await cursor.to_list(length=1000)
        if docs:
            data[sym] = pd.DataFrame(docs)
    
    if not data:
        return {"error": "No data found"}
    
    # Compute correlation
    closes = pd.DataFrame({sym: df.set_index("ts")["spot"] for sym, df in data.items() if "spot" in df.columns})
    corr = closes.corr().to_dict()
    return {"correlation": corr, "n_samples": len(closes)}
