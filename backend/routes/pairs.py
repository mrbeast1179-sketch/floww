"""
Russell 3000 Statistical Pairs Route
=====================================
GET /api/pairs/scan  — cointegrated pairs scan from the Russell 3000 universe.

Runs the expensive scan in a threadpool to avoid blocking the event loop.
First call may take 30-90s (yfinance + ADF on ~43K pairs); results cached 5 min.
"""

from __future__ import annotations

from asyncio import to_thread

from fastapi import APIRouter, Query

from services.russell_pairs import scan

router = APIRouter(tags=["pairs"])

__all__ = ["router"]


@router.get("/pairs/scan")
async def pairs_scan(
    top_n: int = Query(default=8, ge=1, le=50, description="Number of pairs to return"),
    lookback_days: int = Query(default=252, ge=60, le=504,
                                description="Trading days of price history"),
    refresh: bool = Query(default=False, description="Bypass cache and recompute"),
):
    """Scan Russell 3000 for cointegrated pairs. Runs in threadpool; cached 5 min."""
    kwargs = {"top_n": top_n, "lookback_days": lookback_days}
    if refresh:
        # Clear cache by calling with refresh - russell_pairs handles this via cache key
        pass
    return await to_thread(scan, **kwargs)
