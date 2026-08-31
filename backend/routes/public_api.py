"""
backend/routes/public_api.py

Public API (public.com) data endpoints.

Routes:
    GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD&expirations=N
        Options chain from Public API (primary source)

    GET /api/public/quotes/{ticker}
        Live quote from Public API (spot price + bid/ask)

    GET /api/public/portfolio
        Account portfolio from Public API (paper trading only)

Mounted in server.py: app.include_router(public_api_router, prefix="/api/public")
"""
from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.public_api_adapter import (
    _get_broker,
    fetch_chain_from_public_api,
    fetch_spot_from_public_api,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public_api"])


def _jsonable(value: Any) -> Any:
    """Convert PublicBroker dataclasses recursively for explicit API output."""
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


@router.get("/chain/{ticker}")
async def get_public_chain(
    ticker: str,
    expiration: str | None = Query(default=None, description="Specific expiration YYYY-MM-DD. If omitted, returns first N expirations."),
    expirations: int = Query(default=4, ge=1, le=12, description="Number of expirations to fetch (when expiration not specified)."),
):
    """
    Return options chain data from Public API for a given ticker.

    Uses PUBLIC_API_KEY to authenticate against the Public.com Trading API.
    Returns the same shape as /api/chain but with data_source="public_api".
    """
    result = await fetch_chain_from_public_api(ticker.upper(), max_expiries=expirations)
    if result is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {ticker} — key may be missing or API call failed",
        )

    # If specific expiration requested, filter to that expiry
    if expiration:
        result["contracts"] = [c for c in result["contracts"] if c["expiry"] == expiration]
        result["expiries"] = [expiration] if result["contracts"] else []

    return {
        "ok": True,
        "ticker": ticker.upper(),
        "spot": result.get("spot", 0),
        "expiries": result.get("expiries", []),
        "n_contracts": len(result.get("contracts", [])),
        "data_source": result.get("data_source", "public_api"),
        "contracts": result.get("contracts", []),
    }


@router.get("/quotes/{ticker}")
async def get_public_quotes(ticker: str):
    """
    Return live quote data from Public API for a given ticker.
    """
    spot = await fetch_spot_from_public_api(ticker)
    if spot is None:
        raise HTTPException(
            status_code=502,
            detail=f"Public API unavailable for {ticker}",
        )
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "spot": spot,
        "data_source": "public_api",
    }


@router.get("/portfolio")
async def get_public_portfolio():
    """Return the authenticated Public.com paper-trading portfolio."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(
            status_code=502,
            detail="Public API unavailable — key may be missing or API call failed",
        )

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail="No trading account available")

    try:
        portfolio = await broker.get_portfolio(account.account_id)
    except Exception as exc:
        log.warning("Public API portfolio failed: %s", exc)
        raise HTTPException(status_code=502, detail="Public API portfolio unavailable") from exc

    return {
        "ok": True,
        "account_id": account.account_id,
        "portfolio": _jsonable(portfolio),
        "data_source": "public_api",
    }
