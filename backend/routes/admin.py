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
    from server import db, PAID_TICKERS, LIVE_WINDOW, _live_tape_session
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    usage = db.databento_usage.find({"ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", -1).limit(100)
    usage_list = await usage.to_list(length=100)

    # Budget calculation
    BUDGET_USD = 125.0
    est_cost = sum(u.get("cost_usd", 0) for u in usage_list)
    budget_remaining = BUDGET_USD - est_cost
    budget_pct = (est_cost / BUDGET_USD * 100) if BUDGET_USD > 0 else 0

    # Window check
    now_et = datetime.now(timezone.utc) - timedelta(hours=5)  # rough ET
    current_hhmm = now_et.strftime("%H:%M")
    ws = LIVE_WINDOW.get("start_hhmm", "09:00")
    we = LIVE_WINDOW.get("stop_hhmm", "16:00")
    in_window = ws <= current_hhmm <= we

    return {
        "usage": usage_list,
        "paid_tickers": sorted(PAID_TICKERS),
        "live_window_et": {"start_hhmm": ws, "stop_hhmm": we},
        "est_total_cost_usd": round(est_cost, 2),
        "budget_remaining_usd": round(budget_remaining, 2),
        "budget_pct_used": round(budget_pct, 2),
        "in_window_now": in_window,
        "live_tape_state": "active" if _live_tape_session.get("active") else "stopped",
        "budget_usd": BUDGET_USD,
    }
