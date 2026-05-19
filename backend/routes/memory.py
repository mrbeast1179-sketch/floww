"""
backend/routes/memory.py

Memory/recall routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/memory/trade")
async def memory_trade(request: dict):
    from server import db
    from datetime import datetime, timezone
    request["ts"] = datetime.now(timezone.utc).isoformat()
    db.memory.insert_one(request)
    return {"status": "ok"}


@router.post("/memory/gex")
async def memory_gex(request: dict):
    from server import db
    from datetime import datetime, timezone
    request["ts"] = datetime.now(timezone.utc).isoformat()
    db.memory.insert_one(request)
    return {"status": "ok"}


@router.get("/memory/recall/{ticker}")
async def memory_recall(ticker: str, limit: int = 50):
    from server import db
    cursor = db.memory.find(
        {"ticker": ticker.upper()}, {"_id": 0}
    ).sort("ts", -1).limit(limit)
    return await cursor.to_list(length=limit)


@router.get("/memory/summary/{ticker}")
async def memory_summary(ticker: str):
    from server import db
    count = db.memory.count_documents({"ticker": ticker.upper()})
    latest = db.memory.find_one(
        {"ticker": ticker.upper()}, {"_id": 0}, sort=[("ts", -1)]
    )
    return {"ticker": ticker.upper(), "count": count, "latest": latest}
