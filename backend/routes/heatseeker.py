"""
backend/routes/heatseeker.py

API routes for Skylit-parity Heatseeker Wave 1: flip zones, node lifecycle,
air pockets. Routes fetch the option chain and pass it into the pure
functions in `services.heatseeker`.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.heatseeker import (
    calc_air_pockets,
    calc_flip_zones,
    calc_node_lifecycle,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/heatseeker", tags=["heatseeker"])


async def _fetch_chain(ticker: str, expiries: int) -> Dict[str, Any]:
    """
    Resolve the option chain for ``ticker`` using the same fetcher the rest
    of server.py uses. Imported lazily so the routes module remains import-
    safe before ``app`` is constructed.
    """
    # Local import so the routes module doesn't trigger heavy server.py
    # initialization at import time.
    from server import fetch_spot_and_chains_merged, _sanitize  # noqa: F401
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    return raw


async def _fetch_history(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetch the last 24h of spot snapshots for ``ticker`` from the snapshots
    collection. Wave 1 returns an empty list if Mongo isn't available — the
    pure function treats this as "all nodes fresh".
    """
    try:
        from server import db
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cursor = db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "_id": 0},
        ).sort("ts", 1)
        history: List[Dict[str, Any]] = []
        async for doc in cursor:
            spot = doc.get("spot")
            if spot is None:
                continue
            ts = doc.get("ts")
            history.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "spot": float(spot),
            })
        return history
    except Exception as e:
        logger.warning(f"heatseeker history fetch fail for {ticker}: {e}")
        return []


@router.get("/flip-zones")
async def flip_zones_route(
    ticker: str = "SPY",
    window_pct: float = Query(0.05, gt=0.0, le=0.5),
    expiries: int = Query(4, ge=1, le=12),
):
    """All cumulative-GEX sign changes within ±window_pct of spot."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_flip_zones(spot, contracts, window_pct=window_pct)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


@router.get("/node-lifecycle")
async def node_lifecycle_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Top 10 |GEX| nodes classified Fresh/Tested/Delivered/Decaying."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    history = await _fetch_history(ticker.upper())
    result = calc_node_lifecycle(spot, contracts, history)
    return _sanitize({
        "ticker": ticker.upper(),
        "spot": spot,
        "history_points": len(history),
        **result,
    })


@router.get("/air-pockets")
async def air_pockets_route(
    ticker: str = "SPY",
    min_gap_pct: float = Query(0.005, gt=0.0, le=0.5),
    expiries: int = Query(4, ge=1, le=12),
):
    """Contiguous strike ranges with |GEX| below 20% of the local median."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_air_pockets(spot, contracts, min_gap_pct=min_gap_pct)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})
