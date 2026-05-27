"""
backend/services/websocket_streamer.py

WebSocket streaming module for real-time data distribution.
Bridges the data ingestion layer to connected Dash/FastAPI websocket clients.

Manages:
- Client connection registry
- Broadcast loops for ticks, LOB, flow, analytics
- Message serialization
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Set
from datetime import datetime, timezone

from fastapi import WebSocket

import services.observability as obs_metrics

logger = logging.getLogger(__name__)


manager = ConnectionManager()
