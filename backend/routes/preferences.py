"""
backend/routes/preferences.py

User preferences API routes.
Persists theme, default ticker, refresh rate, etc. to MongoDB for cross-device sync.

Endpoints:
  GET  /api/preferences       — Get all preferences for current session
  POST /api/preferences/theme — Set theme preference
  POST /api/preferences       — Set arbitrary preferences
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

# In-memory store for preferences (session-scoped)
# In production, this would use user authentication
_preferences: Dict[str, Any] = {
    "theme": "dark",
    "default_ticker": "SPY",
    "refresh_ms": 25000,
}


@router.get("/")
async def get_preferences():
    """Get all user preferences."""
    return dict(_preferences)


@router.post("/theme")
async def set_theme(pref: Dict[str, str]):
    """Set theme preference."""
    theme = pref.get("theme", "dark")
    if theme not in ("dark", "light"):
        raise HTTPException(status_code=400, detail="Theme must be 'dark' or 'light'")
    _preferences["theme"] = theme

    # Persist to MongoDB if available
    try:
        from server import db
        await db.preferences.update_one(
            {"_id": "default"},
            {"$set": {"theme": theme, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"MongoDB preference save failed (non-critical): {e}")

    return {"status": "ok", "theme": theme}


@router.post("/")
async def set_preferences(prefs: Dict[str, Any]):
    """Set arbitrary preferences."""
    for key, value in prefs.items():
        if key == "theme" and value not in ("dark", "light"):
            continue
        if key == "refresh_ms" and (not isinstance(value, int) or value < 1000):
            continue
        _preferences[key] = value

    # Persist to MongoDB if available
    try:
        from server import db
        await db.preferences.update_one(
            {"_id": "default"},
            {"$set": {**_preferences, "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"MongoDB preference save failed (non-critical): {e}")

    return {"status": "ok", "preferences": dict(_preferences)}


def get_preference(key: str, default: Any = None) -> Any:
    """Get a preference value."""
    return _preferences.get(key, default)
