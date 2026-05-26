"""
backend/services/request_deduplicator.py

Request deduplication for concurrent API calls.

When multiple callers request the same resource simultaneously, only one
outgoing request is made. Other callers share the in-flight promise.

Usage:
    dedup = RequestDeduplicator()

    # In an async route handler:
    result = await dedup.execute(f"chain:{ticker}", lambda: fetch_chain(ticker))

Thread-safety: This class is designed for asyncio (single-threaded
concurrent) use. It is NOT safe for multi-threaded access.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

logger = logging.getLogger(__name__)


class RequestDeduplicator:
    """Deduplicate concurrent async requests by key.

    If a request with the same key is already in flight, the caller
    awaits the existing future instead of making a duplicate call.

    Exceptions from the wrapped function propagate to ALL waiters.
    The in-flight entry is always cleaned up (even on exception).
    """

    def __init__(self) -> None:
        self._inflight: Dict[str, asyncio.Future] = {}

    @property
    def inflight_count(self) -> int:
        """Number of currently in-flight requests."""
        return len(self._inflight)

    @property
    def inflight_keys(self) -> list:
        """List of keys currently in flight."""
        return list(self._inflight.keys())

    async def execute(
        self, key: str, func: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Execute *func*, deduplicating concurrent calls by *key*.

        If *key* is already in flight, wait for the existing result.
        Otherwise, call *func* and share the result with all waiters.

        Args:
            key: Deduplication key (e.g. ``"chain:SPY"``).
            func: Async callable with no arguments. Called only once
                  per unique in-flight key.

        Returns:
            The result of *func*.

        Raises:
            Any exception raised by *func*, propagated to all waiters.
        """
        # Fast path: already in flight — just wait
        existing = self._inflight.get(key)
        if existing is not None:
            logger.debug("Deduplicating request for key=%s", key)
            return await existing

        # Slow path: create future, execute, resolve
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._inflight[key] = future

        try:
            result = await func()
            future.set_result(result)
            return result
        except Exception as exc:
            future.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
