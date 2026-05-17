"""API routes for free data providers."""

import os
import logging
from typing import Optional
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/quote/{ticker}")
async def get_quote(ticker: str):
    """Get aggregated spot price from all available sources."""
    try:
        from data_providers import DataAggregator
        agg = DataAggregator()
        spot = await agg.get_spot_price(ticker.upper())
        if spot:
            return {"ticker": ticker.upper(), **spot}
        return {"ticker": ticker.upper(), "error": "No data available", "price": None}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "price": None}


@router.get("/full/{ticker}")
async def get_full_data(
    ticker: str,
    include_news: bool = True,
    include_technicals: bool = False,
):
    """Get full aggregated data for a ticker (spot + news + earnings + technicals)."""
    try:
        from data_providers import DataAggregator
        agg = DataAggregator()
        result = await agg.get_full_quote(ticker.upper())
        
        if not include_news:
            result["news"] = []
        if not include_technicals:
            result["technicals"] = {}
        
        return result
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.get("/news/{ticker}")
async def get_news(ticker: str, count: int = Query(10, ge=1, le=50)):
    """Get news for a ticker from Finnhub."""
    try:
        from data_providers import FinnhubProvider
        provider = FinnhubProvider()
        news = await provider.get_news(ticker.upper(), count=count)
        return {"ticker": ticker.upper(), "news": news, "count": len(news)}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e), "news": []}


@router.get("/status")
async def get_data_status():
    """Get status of all data providers."""
    try:
        from data_providers import DataAggregator, FINNHUB_API_KEY, ALPHA_VANTAGE_KEY, POLYGON_API_KEY
        agg = DataAggregator()
        status = agg.get_status()
        return {
            "providers": status,
            "env_vars_set": {
                "FINNHUB_API_KEY": bool(FINNHUB_API_KEY),
                "ALPHA_VANTAGE_KEY": bool(ALPHA_VANTAGE_KEY),
                "POLYGON_API_KEY": bool(POLYGON_API_KEY),
            }
        }
    except Exception as e:
        return {"error": str(e)}
