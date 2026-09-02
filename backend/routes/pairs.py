"""
Russell 3000 Statistical Pairs Route
=====================================
GET /api/pairs/scan  — cointegrated pairs scan from the Russell 3000 universe.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from services.russell_pairs import RUSSELL3000, scan

router = APIRouter(tags=["pairs"])

__all__ = ["router"]


@router.get("/pairs/scan")
async def pairs_scan(
    top_n: int = Query(default=8, ge=1, le=50, description="Number of pairs to return"),
    lookback_days: int = Query(default=252, ge=60, le=504,
                                description="Trading days of price history"),
):
    """Scan the Russell 3000 universe for cointegrated statistical arbitrage pairs."""
    return scan(top_n=top_n, lookback_days=lookback_days)
