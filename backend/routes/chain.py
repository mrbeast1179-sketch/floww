"""
backend/routes/chain.py

Options chain API.

Endpoints:
    GET /api/chain?ticker=SPY  - Get options chain data for a ticker
"""

from __future__ import annotations

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api", tags=["chain"])


@router.get("/chain")
async def get_chain(ticker: str = Query(default="SPY", min_length=1, max_length=10)):
    """Return options chain data for a given ticker."""
    from server import fetch_spot_and_chains_merged
    data = await fetch_spot_and_chains_merged(ticker.upper())
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "spot": data.get("spot", 0),
        "expiries": data.get("expiries", []),
        "n_contracts": len(data.get("contracts", [])),
        "data_source": data.get("data_source", "unknown"),
    }
