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
    """Track API call rates and enforce limits.

    Sliding window rate limiter that tracks per-minute and per-day call counts.
    """

    def __init__(self, per_minute: int = 5, per_day: int = 500):
        self.per_minute = per_minute
        self.per_day = per_day
        self._minute_window: deque = deque()
        self._day_window: deque = deque()

    def _prune(self, now: datetime | None = None):
        if now is None:
            now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        day_ago = now - timedelta(days=1)
        while self._minute_window and self._minute_window[0] <= minute_ago:
            self._minute_window.popleft()
        while self._day_window and self._day_window[0] <= day_ago:
            self._day_window.popleft()

    def can_call(self) -> bool:
        self._prune()
        return (len(self._minute_window) < self.per_minute and
                len(self._day_window) < self.per_day)

    def record_call(self):
        now = datetime.utcnow()
        self._minute_window.append(now)
        self._day_window.append(now)

    @property
    def remaining_minute(self) -> int:
        self._prune()
        return max(0, self.per_minute - len(self._minute_window))

    @property
    def remaining_day(self) -> int:
        self._prune()
        return max(0, self.per_day - len(self._day_window))


av_rate_tracker = RateLimitTracker(per_minute=5, per_day=500)
