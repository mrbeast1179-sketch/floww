"""
backend/services/schwab_streamer.py

Production WebSocket client for Schwab Streamer API.
Connects to Schwab's streaming endpoint, subscribes to Level 1 options
and equities data, auto-refreshes OAuth tokens, reconnects with backoff.

Reference: tylerebowers/Schwabdev (https://github.com/tylerebowers/Schwabdev)
Schwab Streamer API docs: https://developer.schwab.com/products/trader-api--individual

Message types handled:
  - LEVELONE_OPTIONS: bid, ask, last, volume, openInterest, greeks (delta, gamma, theta, vega)
  - LEVELONE_EQUITIES: bid, ask, last, volume
  - HEARTBEAT: connection keepalive
  - ERROR: stream errors

Output: parsed dicts matching the DuckDB schema in services/duckdb_engine.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set
from datetime import datetime, timezone

import websockets
from websockets.exceptions import ConnectionClosed

from schwab import SchwabTokenManager

logger = logging.getLogger(__name__)

SCHWAB_WS_URL = "wss://streamerapi.schwab.com/ws/v1/stream"


class SchwabStreamer:
    """WebSocket client for Schwab streaming data.

    Usage:
        streamer = SchwabStreamer()
        streamer.on_tick(handle_tick)
        streamer.on_chain(handle_chain)
        await streamer.start()
    """

    def __init__(
        self,
        token_manager: Optional[SchwabTokenManager] = None,
        max_reconnect_delay: float = 60.0,
        initial_reconnect_delay: float = 1.0,
    ):
        self.tokens = token_manager or SchwabTokenManager()
        self.max_reconnect_delay = max_reconnect_delay
        self.initial_reconnect_delay = initial_reconnect_delay

        self._ws: Optional[Any] = None
        self._running = False
        self._reconnect_delay = initial_reconnect_delay
        self._tick_handlers: List[Callable] = []
        self._chain_handlers: List[Callable] = []
        self._error_handlers: List[Callable] = []
        self._subscribed_symbols: Set[str] = set()
        self._metrics = {
            "messages_received": 0,
            "messages_parsed": 0,
            "reconnects": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def on_tick(self, handler: Callable[[Dict[str, Any]], Any]):
        """Register a handler for equity/underlying tick data.

        Handler receives: {timestamp, symbol, bid, ask, last, volume, ...}
        """
        self._tick_handlers.append(handler)

    def on_chain(self, handler: Callable[[Dict[str, Any]], Any]):
        """Register a handler for options chain data.

        Handler receives: {timestamp, symbol, expiry, strike, type, bid, ask,
        last, volume, oi, delta, gamma, theta, vega, ...}
        """
        self._chain_handlers.append(handler)

    def on_error(self, handler: Callable[[str], Any]):
        """Register a handler for stream errors."""
        self._error_handlers.append(handler)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the WebSocket client with auto-reconnect."""
        self._running = True
        logger.info("Schwab streamer starting")
        while self._running:
            try:
                await self._connect_and_stream()
            except Exception as e:
                if not self._running:
                    break
                self._metrics["reconnects"] += 1
                logger.warning(
                    f"Schwab streamer disconnected: {e}. "
                    f"Reconnecting in {self._reconnect_delay:.1f}s "
                    f"(attempt {self._metrics['reconnects']})"
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self.max_reconnect_delay
                )

    async def stop(self):
        """Gracefully stop the streamer."""
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        logger.info("Schwab streamer stopped")

    # ------------------------------------------------------------------
    # WebSocket connection
    # ------------------------------------------------------------------

    async def _connect_and_stream(self):
        """Connect to Schwab WebSocket and start streaming."""
        # Get valid access token
        access_token = await self._get_valid_token()
        if not access_token:
            raise ConnectionError("No valid Schwab access token available")

        headers = {"Authorization": f"Bearer {access_token}"}

        logger.info(f"Connecting to {SCHWAB_WS_URL}")
        async with websockets.connect(
            SCHWAB_WS_URL,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self._reconnect_delay = self.initial_reconnect_delay  # reset on success
            logger.info("Schwab WebSocket connected")

            # Subscribe to default symbols
            await self._subscribe_default()

            # Message loop
            async for raw_msg in ws:
                if not self._running:
                    break
                self._metrics["messages_received"] += 1
                await self._handle_message(raw_msg)

    async def _get_valid_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if needed."""
        token = self.tokens.get_access_token()
        if token and not self.tokens.is_expired():
            return token
        # Try refresh
        token = await self.tokens.refresh_token()
        if token:
            return token
        logger.error("No valid Schwab token — OAuth flow required")
        return None

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    async def _subscribe_default(self):
        """Subscribe to default Level 1 options and equities."""
        # Subscribe to underlyings
        await self._subscribe_equities(["SPY", "QQQ", "DIA", "IWM"])
        # Subscribe to options chains (top strikes near ATM)
        await self._subscribe_options("SPY", num_strikes=20)
        await self._subscribe_options("QQQ", num_strikes=20)

    async def _subscribe_equities(self, symbols: List[str]):
        """Subscribe to Level 1 equities."""
        request = {
            "service": "LEVELONE_EQUITIES",
            "requestid": "1",
            "command": "SUBS",
            "SchwabClientCustomerId": "",
            "SchwabClientCorrelId": "",
            "parameters": {
                "keys": ",".join(symbols),
                "fields": "0,1,2,3,4,5,6,7,8",
                # symbol, bid, ask, last, bidSize, askSize, volume, lastSize, time
            },
        }
        await self._send(request)
        for s in symbols:
            self._subscribed_symbols.add(s)
        logger.info(f"Subscribed to equities: {symbols}")

    async def _subscribe_options(self, underlying: str, num_strikes: int = 20):
        """Subscribe to Level 1 options for an underlying.

        Note: Schwab streamer uses option symbols in format: UNDERLYING YYMMDD C/P STRIKE
        We subscribe to the full chain via the underlying symbol.
        """
        request = {
            "service": "LEVELONE_OPTIONS",
            "requestid": "2",
            "command": "SUBS",
            "SchwabClientCustomerId": "",
            "SchwabClientCorrelId": "",
            "parameters": {
                "keys": underlying,
                "fields": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14",
                # symbol, bid, ask, last, volume, openInterest, delta, gamma,
                # theta, vega, strikePrice, expirationDate, contractType, underlying
            },
        }
        await self._send(request)
        self._subscribed_symbols.add(f"OPTIONS_{underlying}")
        logger.info(f"Subscribed to options: {underlying} ({num_strikes} strikes)")

    async def _send(self, data: Dict[str, Any]):
        """Send a JSON message over the WebSocket."""
        if self._ws:
            await self._ws.send(json.dumps(data))

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------

    async def _handle_message(self, raw: str):
        """Parse and dispatch a WebSocket message."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            self._metrics["errors"] += 1
            return

        # Handle different message shapes
        service = msg.get("service", "")

        if service == "LEVELONE_EQUITIES":
            await self._parse_equity(msg)
        elif service == "LEVELONE_OPTIONS":
            await self._parse_option(msg)
        elif msg.get("responseid") == "0" or msg.get("command") == "LOGIN":
            logger.info(f"Schwab streamer login response: {msg.get('content', {}).get('code', '?')}")
        elif "heartbeat" in str(msg).lower():
            pass  # heartbeat, ignore
        elif "error" in msg:
            error_msg = msg.get("error", "unknown error")
            self._metrics["errors"] += 1
            logger.error(f"Schwab streamer error: {error_msg}")
            for h in self._error_handlers:
                try:
                    await h(error_msg) if asyncio.iscoroutinefunction(h) else h(error_msg)
                except Exception:
                    pass

    async def _parse_equity(self, msg: Dict[str, Any]):
        """Parse a Level 1 equity message into a tick dict."""
        content = msg.get("content", [])
        for item in content:
            try:
                tick = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": item.get("key", ""),
                    "bid": float(item.get("1", 0)),
                    "ask": float(item.get("2", 0)),
                    "last": float(item.get("3", 0)),
                    "volume": int(item.get("6", 0)),
                    "bid_size": int(item.get("4", 0)),
                    "ask_size": int(item.get("5", 0)),
                    "source": "schwab",
                }
                self._metrics["messages_parsed"] += 1
                for h in self._tick_handlers:
                    try:
                        await h(tick) if asyncio.iscoroutinefunction(h) else h(tick)
                    except Exception as e:
                        logger.error(f"Tick handler error: {e}")
            except (ValueError, TypeError) as e:
                logger.debug(f"Equity parse error: {e}")

    async def _parse_option(self, msg: Dict[str, Any]):
        """Parse a Level 1 option message into a chain dict."""
        content = msg.get("content", [])
        for item in content:
            try:
                symbol = item.get("key", "")
                # Parse option symbol: "SPY 240516C00500000"
                parts = symbol.split()
                underlying = parts[0] if parts else ""
                chain = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": underlying,
                    "option_symbol": symbol,
                    "expiry": item.get("12", ""),  # expiration date
                    "strike": float(item.get("10", 0)),
                    "type": "call" if "C" in symbol.split()[-1][:7] else "put",
                    "bid": float(item.get("1", 0)),
                    "ask": float(item.get("2", 0)),
                    "last": float(item.get("3", 0)),
                    "volume": int(item.get("4", 0)),
                    "oi": int(item.get("5", 0)),
                    "delta": float(item.get("6", 0)),
                    "gamma": float(item.get("7", 0)),
                    "theta": float(item.get("8", 0)),
                    "vega": float(item.get("9", 0)),
                    "source": "schwab",
                }
                self._metrics["messages_parsed"] += 1
                for h in self._chain_handlers:
                    try:
                        await h(chain) if asyncio.iscoroutinefunction(h) else h(chain)
                    except Exception as e:
                        logger.error(f"Chain handler error: {e}")
            except (ValueError, TypeError, IndexError) as e:
                logger.debug(f"Option parse error: {e}")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "subscribed_symbols": list(self._subscribed_symbols),
            "connected": self._ws is not None and not self._ws.closed,
            "reconnect_delay": self._reconnect_delay,
        }
