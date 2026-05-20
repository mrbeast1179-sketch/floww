"""
backend/routes/vpin.py

VPIN (Volume-Synchronized Probability of Informed Trading) API routes.
Exposes the VPIN engine, Quote Imbalance, and composite toxicity signal.

Endpoints:
  GET  /api/vpin/{ticker}           — Current VPIN state for a ticker
  GET  /api/vpin/{ticker}/history   — VPIN bucket history from DuckDB
  POST /api/vpin/{ticker}/ingest    — Ingest a trade tick (for live feed)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vpin", tags=["vpin"])

# Global VPIN engine registry (ticker -> VpinEngine)
_vpin_engines: Dict[str, Any] = {}


def _get_engine(ticker: str, bucket_size: float = 50000.0, window: int = 50):
    """Get or create a VPIN engine for the given ticker."""
    if ticker not in _vpin_engines:
        from services.vpin_engine import VpinEngine
        _vpin_engines[ticker] = VpinEngine(bucket_size=bucket_size, window=window)
    return _vpin_engines[ticker]


@router.get("/{ticker}")
async def get_vpin_state(ticker: str):
    """Return the current VPIN engine state for a ticker."""
    t = ticker.upper()
    engine = _get_engine(t)
    return engine.get_state()


@router.get("/{ticker}/history")
async def get_vpin_history(ticker: str, limit: int = Query(50, ge=1, le=500)):
    """Return VPIN bucket history from DuckDB."""
    try:
        from services.duckdb_engine import db as duck
        rows = duck.query(
            "SELECT * FROM vpin_buckets WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
            [ticker.upper(), limit],
        )
        return {"ticker": ticker.upper(), "buckets": rows}
    except Exception as e:
        logger.error(f"VPIN history error: {e}")
        return {"ticker": ticker.upper(), "buckets": []}


@router.post("/{ticker}/ingest")
async def ingest_trade(
    ticker: str,
    price_change: float,
    volume: float,
    sigma: float,
    dt: float = 1.0,
    bid_size: float = 0.0,
    ask_size: float = 0.0,
):
    """Ingest a trade tick and update VPIN + QI engines."""
    t = ticker.upper()
    engine = _get_engine(t)
    engine.update(price_change, volume, sigma, dt)

    if bid_size > 0 or ask_size > 0:
        engine.compute_quote_imbalance(bid_size, ask_size)

    return engine.get_toxicity_signal()


@router.get("/{ticker}/toxicity")
async def get_toxicity(ticker: str):
    """Return the composite toxicity signal (VPIN CDF + QI z-score)."""
    t = ticker.upper()
    engine = _get_engine(t)
    return engine.get_toxicity_signal()
