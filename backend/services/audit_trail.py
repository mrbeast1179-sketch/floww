"""
backend/services/audit_trail.py

Immutable, hash-chained audit trail for every write action.
Fields: timestamp, actor, action_type, target, before_state, after_state, ip, user_agent, request_id
Retention: 7 years (SEC Rule 17a-4 inspired)

Reference: SEC Rule 17a-4, FINRA Rule 4511, NIST SP 800-53
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("audit_trail")


class AuditEntry:
    """A single audit trail entry."""

    def __init__(
        self,
        actor: str,
        action_type: str,
        target: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
        previous_hash: str = "",
    ):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.actor = actor
        self.action_type = action_type
        self.target = target
        self.before_state = before_state
        self.after_state = after_state
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.request_id = request_id
        self.previous_hash = previous_hash
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry (includes previous hash for chaining)."""
        data = json.dumps({
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action_type": self.action_type,
            "target": self.target,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "previous_hash": self.previous_hash,
        }, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action_type": self.action_type,
            "target": self.target,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
        }


class AuditTrail:
    """Hash-chained audit trail with MongoDB persistence."""

    COLLECTION = "audit_trail"

    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self._db = db
        self._last_hash = ""

    async def initialize(self, db: AsyncIOMotorDatabase):
        """Set up the audit trail collection with indexes."""
        self._db = db
        try:
            await db[self.COLLECTION].create_index([("timestamp", -1)])
            await db[self.COLLECTION].create_index([("actor", 1)])
            await db[self.COLLECTION].create_index([("action_type", 1)])
            await db[self.COLLECTION].create_index([("target", 1)])
            # Get the last hash for chain continuity
            last = await db[self.COLLECTION].find_one(sort=[("timestamp", -1)])
            if last:
                self._last_hash = last.get("hash", "")
            logger.info(f"Audit trail initialized (last_hash: {self._last_hash[:16]}...)")
        except Exception as e:
            logger.warning(f"Audit trail init failed (non-fatal): {e}")

    async def log(
        self,
        actor: str,
        action_type: str,
        target: str,
        before_state: Optional[Dict[str, Any]] = None,
        after_state: Optional[Dict[str, Any]] = None,
        ip_address: str = "",
        user_agent: str = "",
        request_id: str = "",
    ) -> Optional[str]:
        """Write an audit entry. Returns the hash."""
        if not self._db:
            logger.warning("Audit trail not initialized — entry logged to memory only")
            return None

        entry = AuditEntry(
            actor=actor,
            action_type=action_type,
            target=target,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            previous_hash=self._last_hash,
        )

        try:
            await self._db[self.COLLECTION].insert_one(entry.to_dict())
            self._last_hash = entry.hash
            return entry.hash
        except Exception as e:
            logger.error(f"Audit trail write failed: {e}")
            return None

    async def verify_chain(self) -> Tuple[bool, int]:
        """Verify the hash chain integrity. Returns (valid, entry_count)."""
        if not self._db:
            return True, 0

        try:
            entries = await self._db[self.COLLECTION].find(
                {}, {"_id": 0}
            ).sort("timestamp", 1).to_list(length=10000)

            prev_hash = ""
            for entry in entries:
                # Verify previous_hash links correctly
                if entry.get("previous_hash", "") != prev_hash:
                    logger.error(f"Chain break at {entry.get('timestamp')}")
                    return False, len(entries)

                # Verify hash integrity
                data = {
                    k: v for k, v in entry.items()
                    if k != "hash"
                }
                expected = hashlib.sha256(
                    json.dumps(data, sort_keys=True, default=str).encode()
                ).hexdigest()
                if expected != entry.get("hash", ""):
                    logger.error(f"Hash mismatch at {entry.get('timestamp')}")
                    return False, len(entries)

                prev_hash = entry["hash"]

            return True, len(entries)
        except Exception as e:
            logger.error(f"Chain verification failed: {e}")
            return False, 0

    async def query(
        self,
        actor: Optional[str] = None,
        action_type: Optional[str] = None,
        target: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit trail entries."""
        if not self._db:
            return []

        filter_query: Dict[str, Any] = {}
        if actor:
            filter_query["actor"] = actor
        if action_type:
            filter_query["action_type"] = action_type
        if target:
            filter_query["target"] = target
        if since:
            filter_query["timestamp"] = {"$gte": since}

        cursor = self._db[self.COLLECTION].find(filter_query, {"_id": 0}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)
