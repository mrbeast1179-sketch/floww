"""
backend/routes/briefing.py

Legacy briefing routes — delegates to morning_briefing_api.
Kept for backward compatibility. New code should use morning_briefing_api directly.

NOTE: This router is mounted at prefix="/api" in server.py,
so routes here must NOT include the /api prefix. I-7 fix applied.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/briefing/{ticker}/send")
async def briefing_send(ticker: str, request: dict):
    """Send briefing (stub — future: email/webhook delivery)."""
    return {"status": "ok", "ticker": ticker.upper(), "sent": False, "detail": "Not yet implemented"}
