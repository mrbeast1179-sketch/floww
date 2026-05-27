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
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from fastapi import WebSocket

import services.observability as obs_metrics

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket client connections with topic-based subscriptions."""

    def __init__(self):
        self._active: Dict[str, Set[WebSocket]] = {}  # topic -> set of websockets
        self._all: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, topics: Optional[List[str]] = None):
        await websocket.accept()
        self._all.add(websocket)
        if topics:
            for topic in topics:
                if topic not in self._active:
                    self._active[topic] = set()
                self._active[topic].add(websocket)
                obs_metrics.websocket_connections.labels(topic=topic).inc()
        logger.info(f"Client connected. Total: {len(self._all)}")

    def disconnect(self, websocket: WebSocket):
        self._all.discard(websocket)
        for topic in list(self._active.keys()):
            if websocket in self._active[topic]:
                obs_metrics.websocket_connections.labels(topic=topic).dec()
            self._active[topic].discard(websocket)
            if not self._active[topic]:
                del self._active[topic]

    async def broadcast(self, topic: str, data: Dict[str, Any]):
        """Broadcast message to all clients subscribed to a topic."""
        if topic not in self._active or not self._active[topic]:
            return
        message = json.dumps(data, default=str)
        disconnected = []
        for ws in self._active[topic]:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def broadcast_all(self, data: Dict[str, Any]):
        """Broadcast to all connected clients."""
        if not self._all:
            return
        message = json.dumps(data, default=str)
        disconnected = []
        for ws in list(self._all):
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)

    async def close_all(self, code: int = 1001, reason: str = "Server shutting down"):
        """Close all connected WebSocket clients gracefully."""
        for ws in list(self._all):
            try:
                await ws.close(code=code, reason=reason)
            except Exception:
                pass
        self._all.clear()
        self._active.clear()


manager = ConnectionManager()
