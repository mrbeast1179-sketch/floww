"""
backend/routes/live_trading.py

Live trading routes.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/live/policy")
async def live_policy():
    from server import get_live_policy
    return get_live_policy()


@router.post("/live/policy")
async def live_policy_update(request: dict):
    from server import update_live_policy
    result = await update_live_policy(request)
    return result


@router.post("/live/tape/stop")
async def live_tape_stop():
    from server import stop_live_tape
    result = await stop_live_tape()
    return result
