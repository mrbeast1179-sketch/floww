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

from fastapi import WebSocket, WebSocketDisconnect

import services.observability as obs_metrics

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket client connections with topic-based subscriptions."""

    def __init__(self):
        self._active: Dict[str, Set[WebSocket]] = {}  # topic -> set of websockets
        self._all: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, topics: List[str] = None):
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
        for ws in self._all:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


class StreamOrchestrator:
    """Orchestrates real-time data streams from DuckDB to WebSocket clients."""

    def __init__(self, db_engine, connection_manager: ConnectionManager):
        self.db = db_engine
        self.cm = connection_manager
        self._running = False
        self._tasks: List[asyncio.Task] = []

    async def start(self):
        """Start all broadcast loops."""
        self._running = True
        self._tasks = [
            asyncio.create_task(self._tick_broadcast_loop()),
            asyncio.create_task(self._analytics_broadcast_loop()),
            asyncio.create_task(self._toxicity_broadcast_loop()),
        ]
        logger.info("Stream orchestrator started")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()

    async def _tick_broadcast_loop(self):
        """Broadcast latest ticks every 500ms."""
        while self._running:
            try:
                rows = self.db.query(
                    "SELECT * FROM ticks ORDER BY timestamp DESC LIMIT 5"
                )
                await self.cm.broadcast("ticks", {"type": "ticks", "data": rows})
            except Exception as e:
                logger.error(f"Tick broadcast error: {e}")
            await asyncio.sleep(0.5)

    async def _analytics_broadcast_loop(self):
        """Broadcast analytics updates every 2 seconds."""
        while self._running:
            try:
                await self.cm.broadcast("analytics", {"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                logger.error(f"Analytics broadcast error: {e}")
            await asyncio.sleep(2.0)

    async def _toxicity_broadcast_loop(self):
        """Broadcast toxicity updates every 1 second."""
        while self._running:
            try:
                rows = self.db.query(
                    "SELECT * FROM vpin_buckets ORDER BY timestamp DESC LIMIT 10"
                )
                await self.cm.broadcast("toxicity", {"type": "vpin", "data": rows})
            except Exception as e:
                logger.error(f"Toxicity broadcast error: {e}")
            await asyncio.sleep(1.0)


# Global singleton
manager = ConnectionManager()
