"""Shared retry helpers — GSD Phase 3.3.

Exponential backoff with jitter, for both sync and async callables.
Jitter prevents thundering-herd retries when many tickers fail at once
(the classic yfinance rate-limit pattern).

Usage:
    from services.retry import retry_sync, retry_async

    df = retry_sync(lambda: yf.Ticker(t).history(...), attempts=3, base_delay=0.5)
    data = await retry_async(fetch_chain, ticker, attempts=2)
"""
from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from typing import Any

log = logging.getLogger("services.retry")


RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (Exception,)


def _jittered_delay(attempt: int, base_delay: float, cap: float = 10.0) -> float:
    """Full-jitter exponential backoff: min(cap, base * 2**attempt) * U(0, 1]."""
    raw = min(cap, base_delay * (2 ** attempt))
    return random.uniform(raw * 0.5, raw)


def retry_sync[T](
    fn: Callable[..., T],
    *args: Any,
    attempts: int = 3,
    base_delay: float = 0.5,
    retry_on: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
    **kwargs: Any,
) -> T:
    """Call fn(*args, **kwargs), retrying on failure with jittered backoff.

    Re-raises the last exception after exhausting attempts.
    """
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except retry_on as e:
            last_exc = e
            if attempt < attempts - 1:
                delay = _jittered_delay(attempt, base_delay)
                log.warning(
                    "%s failed (attempt %d/%d), retrying in %.2fs: %s",
                    getattr(fn, "__name__", "callable"), attempt + 1, attempts, delay, e,
                )
                import time as _time
                _time.sleep(delay)
    log.error("%s failed after %d attempts", getattr(fn, "__name__", "callable"), attempts)
    assert last_exc is not None
    raise last_exc


async def retry_async(
    fn: Callable[..., Any],
    *args: Any,
    attempts: int = 3,
    base_delay: float = 0.5,
    retry_on: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
    **kwargs: Any,
) -> Any:
    """Async variant of retry_sync."""
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await fn(*args, **kwargs)
        except retry_on as e:
            last_exc = e
            if attempt < attempts - 1:
                delay = _jittered_delay(attempt, base_delay)
                log.warning(
                    "%s failed (attempt %d/%d), retrying in %.2fs: %s",
                    getattr(fn, "__name__", "callable"), attempt + 1, attempts, delay, e,
                )
                await asyncio.sleep(delay)
    log.error("%s failed after %d attempts", getattr(fn, "__name__", "callable"), attempts)
    assert last_exc is not None
    raise last_exc
