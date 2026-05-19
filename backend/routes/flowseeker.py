"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown.

Mirrors backend/routes/heatseeker.py's pattern: thin wrappers around
services/flowseeker.py with no business logic in the routes themselves.
Failures from the upstream provider degrade to 200 with empty payloads so
the frontend can render an empty state instead of crashing.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: Optional[str] = Query(None, description="Optional ticker; omit for cross-ticker outliers"),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """
    Live institutional options flow with 20-column shape and Skylit-parity
    classification (sweep / block / unusual / regular).

    Returns ``{"ticker": str|None, "count": int, "prints": List[Dict]}``.
    """
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(prints),
        "prints": prints,
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """
    Contract-level drilldown: chain volume, OI, chain ratio, recent prints,
    and 20-day vol/OI history (when the upstream tier exposes it).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)
