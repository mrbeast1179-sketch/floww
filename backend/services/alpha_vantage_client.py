"""
backend/services/alpha_vantage_client.py

Circuit breaker pattern for Alpha Vantage API calls.

Prevents cascading failures when Alpha Vantage is down or rate-limited.
Circuit opens after N consecutive failures, rejects requests for a timeout
period, then enters half-open state to test recovery.

States:
  CLOSED   -> normal operation, failures counted
  OPEN     -> reject requests immediately, wait for recovery timeout
  HALF_OPEN -> allow one request through to test if service recovered

Usage:
    from services.alpha_vantage_client import CircuitBreaker, circuit

    # Use the global instance
    result = await circuit.call(some_async_func, arg1, arg2)

    # Or create a custom instance
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    result = await cb.call(some_async_func, arg1, arg2)
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is OPEN and rejecting requests."""
    def __init__(self, state: CircuitState, retry_after: float):
        self.state = state
        self.retry_after = retry_after
        remaining = max(0, int(retry_after - time.time()))
        super().__init__(
            f"Circuit breaker is OPEN. Retry after {remaining}s."
        )


class CircuitBreaker:
    """Async-compatible circuit breaker for API calls.

    Args:
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before transitioning to HALF_OPEN.
        name: Human-readable name for logging.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "circuit",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._success_count = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def success_count(self) -> int:
        return self._success_count

    def _reset(self):
        """Reset circuit to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        logger.info("[%s] Circuit reset to CLOSED", self.name)

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute func through the circuit breaker.

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN and timeout hasn't expired.
            Exception: Any exception raised by func (after recording failure).
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                if elapsed < self.recovery_timeout:
                    raise CircuitBreakerOpenError(
                        self._state, self._last_failure_time + self.recovery_timeout
                    )
                else:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "[%s] Transition: OPEN -> HALF_OPEN", self.name
                    )

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                if self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count += 1
                    logger.info(
                        "[%s] Transition: HALF_OPEN -> CLOSED (recovery confirmed)",
                        self.name,
                    )
                elif self._state == CircuitState.CLOSED:
                    self._failure_count = 0
                    self._success_count += 1
            return result

        except Exception as e:
            async with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()

                if self._state == CircuitState.HALF_OPEN:
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "[%s] Transition: HALF_OPEN -> OPEN (failure in half-open: %s)",
                        self.name,
                        e,
                    )
                elif (
                    self._state == CircuitState.CLOSED
                    and self._failure_count >= self.failure_threshold
                ):
                    self._state = CircuitState.OPEN
                    logger.warning(
                        "[%s] Transition: CLOSED -> OPEN (%d consecutive failures)",
                        self.name,
                        self._failure_count,
                    )

            raise


# Global circuit breaker instance for Alpha Vantage
circuit = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    name="AlphaVantage",
)
