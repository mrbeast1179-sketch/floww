"""
WTI Crude Oil Volatility Forecast Route
========================================
GET /api/wti/vol  — HAR-IV forecast for front-month WTI (CL=F).
"""

from __future__ import annotations

from fastapi import APIRouter

from services.wti_vol import forecast

router = APIRouter(tags=["wti"])

__all__ = ["router"]


@router.get("/wti/vol")
async def wti_vol_forecast():
    """HAR-IV realized vol forecast for WTI crude (CL=F)."""
    return forecast()
