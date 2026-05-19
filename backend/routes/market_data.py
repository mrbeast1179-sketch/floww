"""
backend/routes/market_data.py

Market data routes: tickers, heatmap, trinity, spot, chain, gex-timeframes, uoa.
Uses lazy imports from server.py to avoid circular dependencies.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Query, HTTPException

router = APIRouter()


@router.get("/tickers")
async def list_tickers():
    from server import TRINITY, DEFAULT_TICKERS, POPULAR_UNIVERSE
    return {
        "trinity": TRINITY,
        "default": DEFAULT_TICKERS,
        "popular": POPULAR_UNIVERSE,
    }


@router.get("/heatmap/{ticker}")
async def heatmap(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    taps: bool = True,
    mode: str = Query("day", pattern="^(day|swing|scalp)$"),
    dte: Optional[int] = Query(None, ge=0, le=30),
    scalp: bool = Query(False),
):
    from server import build_heatmap
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await build_heatmap(t, expiries, taps, mode, dte, scalp)


@router.get("/trinity")
async def trinity(
    tickers: str = Query(None),
    mode: str = Query("day", pattern="^(day|swing)$"),
    dte: Optional[int] = Query(None, ge=0, le=30),
):
    from server import build_heatmap, TRINITY
    if tickers is None:
        tickers = ",".join(TRINITY)
    syms = [t.strip() for t in tickers.split(",") if t.strip()]
    out: Dict[str, Any] = {}
    results = await asyncio.gather(
        *[build_heatmap(s, 3, True, mode, dte) for s in syms],
        return_exceptions=True,
    )
    for sym, res in zip(syms, results):
        if isinstance(res, Exception):
            out[sym] = {"error": str(res)}
        else:
            out[sym] = res

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


@router.get("/spot/{ticker}")
async def spot(ticker: str):
    from server import fetch_spot_and_chains_merged
    from datetime import datetime, timezone
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, 1)
    return {"ticker": t, "spot": raw.get("spot", 0), "ts": datetime.now(timezone.utc).isoformat()}


@router.get("/chain/{ticker}")
async def chain(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
    min_oi: int = Query(0, ge=0),
    expiry: Optional[str] = None,
):
    from server import fetch_spot_and_chains_merged, _sanitize
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    if not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    contracts = raw["contracts"]
    if expiry:
        contracts = [c for c in contracts if c.get("expiry") == expiry]
    if min_oi:
        contracts = [c for c in contracts if (c.get("oi", 0) or c.get("open_interest", 0)) >= min_oi]
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
    return _sanitize({"ticker": t, "spot": raw["spot"], "expiries": raw.get("expiries", []), "rows": rows, "count": len(rows)})


@router.get("/gex-timeframes/{ticker}")
async def gex_timeframes(
    ticker: str,
    expiries: int = Query(4, ge=1, le=12),
):
    from server import fetch_spot_and_chains_merged, _sanitize
    from services.gex_history import calc_gex_timeframes
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    spot = raw.get("spot", 0)
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_gex_timeframes(spot, raw["contracts"], t)
    return _sanitize(result)


@router.get("/uoa/{ticker}")
async def uoa(
    ticker: str,
    min_premium: float = Query(100000, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    from server import fetch_spot_and_chains_merged, _sanitize
    from services.uoa import calc_uoa
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, 4)
    spot = raw.get("spot", 0)
    if not spot or not raw.get("contracts"):
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_uoa(spot, raw["contracts"], t, min_premium, limit)
    return _sanitize(result)
