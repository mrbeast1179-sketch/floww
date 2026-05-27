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


av_rate_tracker = RateLimitTracker(per_minute=5, per_day=500)
