"""
backend/services/alert_dispatcher.py

Phone alerting via Twilio — SMS + voice calls for CRITICAL alerts.

Features:
- Severity taxonomy: CRITICAL fires SMS + voice; MEDIUM fires SMS only; LOW is dashboard-only
- Quiet hours: 22:00–06:00 ET, overridden during market hours (09:30–16:00 ET, DST-aware)
- Emergency override: live-trading risk events always fire regardless of quiet hours
- Deduplication: 15-minute cooldown per unique alert ID
- All sends are logged to DuckDB for audit trail

Environment variables required:
    TWILIO_ACCOUNT_SID   — Twilio account SID
    TWILIO_AUTH_TOKEN    — Twilio auth token
    TWILIO_FROM_NUMBER   — Twilio phone number (e.g. +15551234567)
    NAV_PHONE_NUMBER     — Nav's phone number (e.g. +15559876543)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

log = logging.getLogger(__name__)

# Severity levels
SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# Quiet hours (ET)
QUIET_START_HOUR = 22  # 10pm
QUIET_END_HOUR = 6     # 6am

# Market hours (ET) — DST-aware via ZoneInfo
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MIN = 0

# Deduplication cooldown (seconds)
DEDUP_COOLDOWN = 900  # 15 minutes

# Alert categories that are always emergencies (bypass quiet hours)
EMERGENCY_CATEGORIES = {
    "AnomalyDetected",
    "QueueBackpressure",
    "APIErrorRateHigh",
}


dispatcher = AlertDispatcher()
