"""
backend/routes/liquidity.py

Market Microstructure Liquidity Metrics API routes.
Exposes Kyle's Lambda, Amihud Illiquidity, and Market Fragility Index.

Endpoints:
  GET  /api/liquidity/{ticker}           — Full liquidity metrics
  POST /api/liquidity/{ticker}/kyle      — Update Kyle's Lambda
  POST /api/liquidity/{ticker}/amihud    — Update Amihud Illiquidity
  GET  /api/liquidity/{ticker}/fragility — Market Fragility Index
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/liquidity", tags=["liquidity"])

# Global registry
_kyle: dict[str, Any] = {}
_amihud: dict[str, Any] = {}
_fragility: dict[str, Any] = {}


def _get_kyle(ticker: str, window: int = 20):
    if ticker not in _kyle:
        from services.liquidity_metrics import KyleLambda
        _kyle[ticker] = KyleLambda(window=window)
    return _kyle[ticker]


def _get_amihud(ticker: str, window: int = 20):
    if ticker not in _amihud:
        from services.liquidity_metrics import AmihudIlliquidity
        _amihud[ticker] = AmihudIlliquidity(window=window)
    return _amihud[ticker]


def _get_fragility(ticker: str):
    if ticker not in _fragility:
        from services.liquidity_metrics import MarketFragilityIndex
        _fragility[ticker] = MarketFragilityIndex()
    return _fragility[ticker]


@router.get("/{ticker}")
async def get_liquidity_metrics(ticker: str):
    """Return all liquidity metrics for a ticker."""
    t = ticker.upper()
    kyle = _get_kyle(t)
    amihud = _get_amihud(t)
    fragility = _get_fragility(t)

    return {
        "ticker": t,
        "kyle_lambda": kyle.get_state(),
        "amihud": amihud.get_state(),
        "fragility": fragility.compute(
            kyle_lambda=kyle.compute(),
            amihud=amihud.compute(),
        ),
    }


@router.post("/{ticker}/kyle")
async def update_kyle(
    ticker: str,
    price: float,
    volume: float,
    sign: int,
):
    """Update Kyle's Lambda with a new trade observation."""
    t = ticker.upper()
    kyle = _get_kyle(t)
    kyle.update(price, volume, sign)
    return kyle.get_state()


@router.post("/{ticker}/amihud")
async def update_amihud(
    ticker: str,
    price: float,
    volume: float,
    dollar_volume: float,
):
    """Update Amihud Illiquidity with a new observation."""
    t = ticker.upper()
    amihud = _get_amihud(t)
    amihud.update(price, volume, dollar_volume)
    return amihud.get_state()


@router.get("/{ticker}/fragility")
async def get_fragility(
    ticker: str,
    vpin_cdf: float = 0.0,
    qi_zscore: float = 0.0,
    spread: float = 0.0,
):
    """Compute Market Fragility Index."""
    t = ticker.upper()
    kyle = _get_kyle(t)
    amihud = _get_amihud(t)
    fragility = _get_fragility(t)

    result = fragility.compute(
        kyle_lambda=kyle.compute(),
        amihud=amihud.compute(),
        vpin_cdf=vpin_cdf,
        qi_zscore=qi_zscore,
        spread=spread,
    )
    return {"ticker": t, **result}
