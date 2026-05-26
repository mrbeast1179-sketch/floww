"""
backend/services/rate_limit_tracker.py

Alpha Vantage API rate limit tracker.
Free tier: 5 calls/min, 500 calls/day.
"""

from __future__ import annotations
import logging
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RateLimitTracker:
    def __init__(self, per_minute: int = 5, per_day: int = 500) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.calls: deque[datetime] = deque()

    def record_call(self) -> None:
        now = datetime.utcnow()
        self.calls.append(now)
        cutoff = now - timedelta(days=1)
        while self.calls and self.calls[0] <= cutoff:
            self.calls.popleft()

    def get_status(self) -> dict:
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        calls_minute = sum(1 for c in self.calls if c > minute_ago)
        calls_day = len(self.calls)
        rem_minute = max(0, self.per_minute - calls_minute)
        rem_day = max(0, self.per_day - calls_day)
        return {
            "per_minute": {
                "used": calls_minute, "limit": self.per_minute,
                "remaining": rem_minute,
                "pct_used": round(calls_minute / self.per_minute * 100, 1),
            },
            "per_day": {
                "used": calls_day, "limit": self.per_day,
                "remaining": rem_day,
                "pct_used": round(calls_day / self.per_day * 100, 1),
            },
        }


av_rate_tracker = RateLimitTracker(per_minute=5, per_day=500)
