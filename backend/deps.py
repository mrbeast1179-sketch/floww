"""
backend/deps.py

Shared dependencies for route modules.
Extracts common DB connections, auth, and utility functions.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")


def get_db():
    """Get MongoDB database connection."""
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


def get_current_user(request: Request) -> Optional[str]:
    """Get current user from request (placeholder for auth)."""
    return request.headers.get("X-User-Id", "anonymous")


def verify_admin(user: str = Depends(get_current_user)) -> str:
    """Verify user is admin (placeholder)."""
    # TODO: Implement proper admin verification
    return user


class RateLimiter:
    """Simple in-memory rate limiter."""
    from collections import defaultdict, deque
    import time

    _limits: dict = defaultdict(deque)
    RATE_LIMIT: int = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

    @classmethod
    def check(cls, client_ip: str) -> bool:
        now = cls.time.time()
        window = 60.0
        dq = cls._limits[client_ip]
        while dq and now - dq[0] >= window:
            dq.popleft()
        if len(dq) >= cls.RATE_LIMIT:
            return False
        dq.append(now)
        return True
