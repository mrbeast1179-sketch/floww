"""
backend/routes/admin.py

Admin/utility routes: errors, performance, databento usage.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/errors/summary")
async def errors_summary():
    from server import db
    cutoff = __import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").timedelta(hours=24)
    errors = db.errors.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    return {"errors": await errors.to_list(length=100)}


@router.get("/api/performance/stats")
async def performance_stats():
    from server import db
    from server import _rate_limits
    return {
        "rate_limit_tracked_ips": len(_rate_limits),
        "uptime_seconds": __import__("time").time() - __import__("server")._start_time if hasattr(__import__("server"), "_start_time") else 0,
    }


@router.post("/api/errors/clear")
async def errors_clear():
    from server import db
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    result = db.errors.delete_many({"ts": {"$lt": cutoff}})
    return {"deleted": result.deleted_count}


@router.get("/databento/usage")
async def databento_usage():
    from server import db
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    usage = db.databento_usage.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    return {"usage": await usage.to_list(length=100)}
