"""
backend/routes/public_api.py

Public API (public.com) data endpoints — the SOLE live market-data source
(public-api-only policy, 2026-09-03).

Routes:
    GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD&expirations=N
        Options chain from Public API (primary source)

    GET /api/public/quotes/{ticker}
        Live quote from Public API (spot price + bid/ask)

    GET /api/public/bars/{ticker}?interval=daily
        OHLCV bars (daily/weekly/monthly/1min/5min/15min/30min/60min)

    GET /api/public/history/{ticker}?interval=daily
        OHLCV history shaped like the retired alpha historical endpoint

    GET /api/public/technical/{ticker}/{indicator}?time_period=14
        RSI/SMA/EMA/MACD computed locally from Public API bars

    GET /api/public/expirations/{ticker}
        Listed option expirations for a ticker

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
    compute_technical_from_bars,
    fetch_bars_from_public_api,
    fetch_chain_from_public_api,
    fetch_history_from_public_api,
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
        "stale": result.get("stale", False),
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


@router.get("/portfolio/raw")
async def get_public_portfolio():
    """Return the raw authenticated Public.com paper-trading portfolio.

    NOTE: the canonical UI-facing portfolio (flattened positions, money
    fields) lives at GET /api/public/portfolio (routes/public_brokerage.py),
    which takes precedence on that path. This raw view is kept for
    debugging/inspection.
    """
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


@router.get("/bars/{ticker}")
async def get_public_bars(
    ticker: str,
    interval: str = Query(default="daily", description="1min/5min/15min/30min/60min/daily/weekly/monthly"),
):
    """OHLCV bars from Public API (replaces alpha intraday)."""
    bars = await fetch_bars_from_public_api(ticker.upper(), interval=interval)
    if bars is None:
        raise HTTPException(status_code=502, detail=f"Public API bars unavailable for {ticker}")
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "interval": interval,
        "bars": bars,
        "n_bars": len(bars),
        "data_source": "public_api",
    }


@router.get("/history/{ticker}")
async def get_public_history(
    ticker: str,
    interval: str = Query(default="daily", description="daily/weekly/monthly"),
):
    """OHLCV history from Public API (replaces alpha historical)."""
    result = await fetch_history_from_public_api(ticker.upper(), interval=interval)
    if result is None:
        raise HTTPException(status_code=502, detail=f"Public API history unavailable for {ticker}")
    return {"ok": True, **result}


@router.get("/technical/{ticker}/{indicator}")
async def get_public_technical(
    ticker: str,
    indicator: str,
    time_period: int = Query(default=14, ge=1, le=200),
    interval: str = Query(default="daily"),
):
    """RSI/SMA/EMA/MACD computed locally from Public API bars (replaces alpha technical)."""
    bars = await fetch_bars_from_public_api(ticker.upper(), interval=interval)
    if bars is None:
        raise HTTPException(status_code=502, detail=f"Public API bars unavailable for {ticker}")
    result = compute_technical_from_bars(ticker.upper(), indicator.upper(), bars, time_period)
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    return {"ok": True, **result}


@router.get("/expirations/{ticker}")
async def get_public_expirations(ticker: str):
    """Listed option expirations from Public API."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail=f"Public API unavailable for {ticker}")
    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail="No trading account available")
    try:
        expiries = await broker.get_option_expirations(ticker.upper(), account.account_id)
    except Exception as exc:
        log.warning("Public API expirations failed for %s: %s", ticker, exc)
        raise HTTPException(status_code=502, detail=f"Public API expirations unavailable for {ticker}") from exc
    return {
        "ok": True,
        "ticker": ticker.upper(),
        "expirations": expiries,
        "data_source": "public_api",
    }
