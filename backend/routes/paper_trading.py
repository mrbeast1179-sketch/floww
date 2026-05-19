"""
backend/routes/paper_trading.py

Paper trading routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/api/paper-trading/execute")
async def paper_trade_execute(request: dict):
    from server import db, execute_paper_trade
    result = await execute_paper_trade(request)
    return result


@router.post("/api/paper-trading/signals")
async def paper_trade_signals(request: dict):
    from server import db, generate_trade_signals
    result = await generate_trade_signals(request)
    return result


@router.get("/api/paper-trading/status")
async def paper_trade_status():
    from server import db
    orders = db.orders_dry_run.find({}, {"_id": 0}).sort("date", -1).limit(50)
    return {"orders": await orders.to_list(length=50)}
