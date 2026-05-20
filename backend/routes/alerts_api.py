"""
backend/routes/alerts_api.py

Alert management API routes.
Exposes alert firing, acknowledgment, and dispatcher status.

Endpoints:
  POST /api/alerts/fire          — Fire an alert (called by Prometheus Alertmanager webhook)
  GET  /api/alerts/status        — Dispatcher status (Twilio config, dedup cache)
  POST /api/alerts/acknowledge   — Acknowledge + resolve an alert (phone callback)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class FireAlertRequest(BaseModel):
    alert_id: str
    severity: str = "CRITICAL"
    title: str = ""
    message: str = ""
    category: str = ""


class AcknowledgeRequest(BaseModel):
    alert_id: str
    resolved: bool = True


@router.post("/fire")
async def fire_alert(req: FireAlertRequest):
    """Fire an alert through the dispatcher. Called by Alertmanager webhook."""
    from services.alert_dispatcher import dispatcher
    result = await dispatcher.dispatch(
        alert_id=req.alert_id,
        severity=req.severity,
        title=req.title,
        message=req.message,
        category=req.category,
    )
    return {"status": "ok", "result": result}


@router.get("/status")
async def dispatcher_status():
    """Return dispatcher configuration status."""
    from services.alert_dispatcher import dispatcher
    return {
        "twilio_configured": dispatcher._twilio_available,
        "from_number": dispatcher._from_number or "not set",
        "to_number": dispatcher._to_number or "not set",
        "dedup_cache_size": len(dispatcher._dedup_cache),
        "dedup_cooldown_sec": 900,
    }


@router.post("/acknowledge")
async def acknowledge_alert(req: AcknowledgeRequest):
    """Acknowledge an alert (e.g., from phone callback URL).
    Clears dedup cache entry so the alert can fire again if it recurs."""
    from services.alert_dispatcher import dispatcher
    if req.alert_id in dispatcher._dedup_cache:
        del dispatcher._dedup_cache[req.alert_id]
    logger.info(f"Alert acknowledged: {req.alert_id} (resolved={req.resolved})")

    # Auto-create incident post-mortem on resolve
    if req.resolved:
        try:
            from scripts.start_incident import create_from_alert
            create_from_alert(req.alert_id)
        except Exception as e:
            logger.warning(f"Auto incident creation failed: {e}")

    return {"status": "acknowledged", "alert_id": req.alert_id}
