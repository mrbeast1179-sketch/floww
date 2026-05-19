"""
backend/routes/memory.py

Memory/recall routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/memory/trade")
async def memory_trade(request: dict):
    from server import remember_trade
    await remember_trade(request)
    return {"status": "ok"}


@router.post("/memory/gex")
async def memory_gex(request: dict):
    from server import remember_gex_observation
    await remember_gex_observation(request)
    return {"status": "ok"}


@router.get("/memory/recall/{ticker}")
async def memory_recall(ticker: str, limit: int = 50):
    from server import recall_trading_context
    results = await recall_trading_context(ticker, limit)
    return {"results": results}


@router.get("/memory/summary/{ticker}")
async def memory_summary(ticker: str):
    from server import get_trading_summary
    summary = await get_trading_summary(ticker)
    return {"summary": summary}
