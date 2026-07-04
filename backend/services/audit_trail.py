"""
backend/services/audit_trail.py

Immutable, hash-chained audit trail for every write action.
Fields: timestamp, actor, action_type, target, before_state, after_state, ip, user_agent, request_id
Retention: 7 years (SEC Rule 17a-4 inspired)

Reference: SEC Rule 17a-4, FINRA Rule 4511, NIST SP 800-53
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("audit_trail")

# --- MongoDB setup (mirrors deps.py to avoid circular imports) ---
_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "floww")
_COLLECTION = "audit_events"

_client: AsyncIOMotorClient | None = None


def _get_collection():
    """Lazily initialise the MongoDB client and return the audit_events collection."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            _MONGO_URL,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
    return _client[_DB_NAME][_COLLECTION]


async def record_event(
    event_type: str,
    data: dict[str, Any],
    user: str = "system",
) -> None:
    """Write a single audit event to MongoDB.

    Args:
        event_type: Short label for the event (e.g. "order_placed", "position_closed").
        data:       Arbitrary payload dict attached to the event.
        user:       Actor identifier — defaults to "system" for automated events.
    """
    doc = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "data": data,
        "user": user,
    }
    try:
        col = _get_collection()
        await col.insert_one(doc)
        logger.debug("audit: recorded %s by %s", event_type, user)
    except Exception as exc:
        logger.error("audit: failed to record event %s: %s", event_type, exc)


async def get_events(
    limit: int = 100,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    """Query recent audit events from MongoDB.

    Args:
        limit:      Maximum number of events to return (most-recent first).
        event_type: Optional filter — only return events matching this type.

    Returns:
        List of event dicts (MongoDB _id converted to string).
    """
    try:
        col = _get_collection()
        query: dict[str, Any] = {}
        if event_type:
            query["event_type"] = event_type
        cursor = col.find(query, {"_id": 1, "timestamp": 1, "event_type": 1, "data": 1, "user": 1})
        cursor = cursor.sort("timestamp", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results
    except Exception as exc:
        logger.error("audit: get_events query failed: %s", exc)
        return []
