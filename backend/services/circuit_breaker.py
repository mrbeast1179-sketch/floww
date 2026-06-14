"""
backend/services/circuit_breaker.py

Circuit breaker pattern for trading protection.
Monitors error rates, latency, and P&L drawdown.
When thresholds are breached, trips the circuit breaker:
  - Stops all trading activity
  - Sends alert to Nav
  - Requires manual reset to resume

States: CLOSED (normal) -> OPEN (tripped) -> HALF_OPEN (testing recovery)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("circuit_breaker")


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Tripped — trading halted
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class Measurement:
    """A single request measurement for circuit breaker monitoring."""
    timestamp: float
    is_error: bool
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TripRecord:
    """Record of a circuit breaker trip event."""
    timestamp: str
    reason: str
    details: str = ""
    actor: str = "system"
    error_rate: float = 0.0
    latency_p99: float = 0.0
    state_before: str = ""
    measurements_at_trip: int = 0
    error_rate_at_trip: float = 0.0
    latency_p99_at_trip: float = 0.0


@dataclass
class BreakerThresholds:
    """Configurable thresholds for circuit breaker triggers."""
    # Error rate: if error_count / total_count > this, trip
    error_rate_pct: float = 10.0
    # Minimum measurements before error_rate check kicks in
    min_measurements: int = 20
    # Latency: if p99 latency > this (ms), trip
    latency_p99_ms: float = 5000.0
    # P&L drawdown: if daily P&L < this (%), trip
    daily_pnl_drawdown_pct: float = -2.0
    # Rejected fills: if rejected_count_1h > this, trip
    rejected_fills_1h: int = 5
    # Window size for measurements (seconds)
    window_seconds: int = 300  # 5 minutes
    # Cooldown after trip (seconds) — must elapse before HALF_OPEN
    cooldown_seconds: int = 3600  # 1 hour
    # Successes needed in HALF_OPEN to close
    half_open_successes_needed: int = 10


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for trading protection.

    Usage:
        breaker = CircuitBreaker("main", thresholds=BreakerThresholds())

        # Record measurements
        breaker.record_request(latency_ms=120, is_error=False)

        # Check if trading is allowed
        if breaker.is_trading_allowed():
            execute_trade()

        # Check P&L
        breaker.check_pnl(daily_pnl_pct=-3.0, equity=5000.0)

        # Get status
        status = breaker.get_status()
    """

    def __init__(
        self,
        name: str = "main",
        thresholds: BreakerThresholds | None = None,
        on_trip: Callable[[str, str], None] | None = None,
    ):
        self.name = name
        self.thresholds = thresholds or BreakerThresholds()
        self._on_trip = on_trip

        self._state = CircuitState.CLOSED
        self._measurements: list[Measurement] = []
        self._trip_log: list[TripRecord] = []
        self._last_trip_time: float | None = None
        self._half_open_successes: int = 0
        self._created_at = datetime.now(UTC)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_tripped(self) -> bool:
        return self._state == CircuitState.OPEN

    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed."""
        if self._state == CircuitState.CLOSED:
            return True
        if self._state == CircuitState.OPEN:
            # Check if cooldown has elapsed -> transition to HALF_OPEN
            if self._last_trip_time and (
                time.time() - self._last_trip_time > self.thresholds.cooldown_seconds
            ):
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False
        return self._state == CircuitState.HALF_OPEN  # Allow limited trading in half-open

    def record_request(
        self,
        latency_ms: float = 0.0,
        is_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a request measurement."""
        now = time.time()
        m = Measurement(
            timestamp=now,
            is_error=is_error,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
        self._measurements.append(m)
        self._cleanup_old_measurements(now)

        # In HALF_OPEN, count successes
        if self._state == CircuitState.HALF_OPEN and not is_error:
            self._half_open_successes += 1
            if self._half_open_successes >= self.thresholds.half_open_successes_needed:
                self._transition_to(CircuitState.CLOSED)
                logger.info(f"Circuit breaker '{self.name}' CLOSED (recovered)")

        # Check thresholds if we have enough data
        if self._state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
            self._check_thresholds()

    def check_pnl(self, daily_pnl_pct: float, equity: float) -> bool:
        """Check P&L drawdown. Returns True if tripped."""
        if daily_pnl_pct < self.thresholds.daily_pnl_drawdown_pct:
            self._trip(
                reason="daily_pnl_drawdown",
                details=f"Daily P&L {daily_pnl_pct:.2f}% < {self.thresholds.daily_pnl_drawdown_pct}% threshold (equity: ${equity:.2f})",
            )
            return True
        return False

    def check_rejected_fills(self, rejected_count_1h: int) -> bool:
        """Check rejected fill count. Returns True if tripped."""
        if rejected_count_1h > self.thresholds.rejected_fills_1h:
            self._trip(
                reason="rejected_fills",
                details=f"{rejected_count_1h} rejected fills in 1h > {self.thresholds.rejected_fills_1h} threshold",
            )
            return True
        return False

    def manual_reset(self, actor: str = "nav") -> None:
        """Manually reset the circuit breaker to CLOSED."""
        old_state = self._state
        self._state = CircuitState.CLOSED
        self._half_open_successes = 0
        self._measurements.clear()
        logger.info(f"Circuit breaker '{self.name}' manually reset to CLOSED by {actor} (was {old_state.value})")

    def manual_trip(self, reason: str = "manual", actor: str = "nav") -> None:
        """Manually trip the circuit breaker."""
        self._trip(reason=reason, details=f"Manually tripped by {actor}", actor=actor)

    def get_status(self) -> dict[str, Any]:
        """Get full circuit breaker status."""
        now = time.time()
        self._cleanup_old_measurements(now)
        error_rate, latency_p99 = self._compute_metrics()

        cooldown_remaining = 0.0
        if self._state == CircuitState.OPEN and self._last_trip_time:
            elapsed = now - self._last_trip_time
            cooldown_remaining = max(0, self.thresholds.cooldown_seconds - elapsed)

        return {
            "name": self.name,
            "state": self._state.value,
            "is_tripped": self.is_tripped,
            "trading_allowed": self.is_trading_allowed(),
            "measurements_in_window": len(self._measurements),
            "error_rate_pct": round(error_rate, 2),
            "latency_p99_ms": round(latency_p99, 2),
            "trip_count": len(self._trip_log),
            "last_trip": self._trip_log[-1].timestamp if self._trip_log else None,
            "cooldown_remaining_seconds": round(cooldown_remaining, 0),
            "half_open_successes": self._half_open_successes,
            "half_open_successes_needed": self.thresholds.half_open_successes_needed,
            "created_at": self._created_at.isoformat(),
        }

    def get_trip_log(self) -> list[dict[str, Any]]:
        """Get trip history."""
        return [
            {
                "timestamp": r.timestamp,
                "reason": r.reason,
                "details": r.details,
                "state_before": r.state_before,
                "measurements_at_trip": r.measurements_at_trip,
                "error_rate_at_trip": r.error_rate_at_trip,
                "latency_p99_at_trip": r.latency_p99_at_trip,
            }
            for r in self._trip_log
        ]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _cleanup_old_measurements(self, now: float) -> None:
        cutoff = now - self.thresholds.window_seconds
        self._measurements = [m for m in self._measurements if m.timestamp >= cutoff]

    def _compute_metrics(self) -> tuple[float, float]:
        """Returns (error_rate_pct, latency_p99_ms)."""
        if not self._measurements:
            return 0.0, 0.0

        total = len(self._measurements)
        errors = sum(1 for m in self._measurements if m.is_error)
        error_rate = (errors / total) * 100 if total > 0 else 0.0

        latencies = sorted(m.latency_ms for m in self._measurements if m.latency_ms > 0)
        if latencies:
            p99_idx = min(int(len(latencies) * 0.99), len(latencies) - 1)
            latency_p99 = latencies[p99_idx]
        else:
            latency_p99 = 0.0

        return error_rate, latency_p99

    def _check_thresholds(self) -> None:
        """Check if any threshold is breached."""
        if len(self._measurements) < self.thresholds.min_measurements:
            return

        error_rate, latency_p99 = self._compute_metrics()

        if error_rate > self.thresholds.error_rate_pct:
            self._trip(
                reason="error_rate",
                details=f"Error rate {error_rate:.1f}% > {self.thresholds.error_rate_pct}% threshold",
            )
            return

        if latency_p99 > self.thresholds.latency_p99_ms:
            self._trip(
                reason="latency_p99",
                details=f"P99 latency {latency_p99:.0f}ms > {self.thresholds.latency_p99_ms}ms threshold",
            )
            return

    def _trip(self, reason: str, details: str, actor: str = "system") -> None:
        """Trip the circuit breaker."""
        old_state = self._state
        self._state = CircuitState.OPEN
        self._last_trip_time = time.time()
        self._half_open_successes = 0

        error_rate, latency_p99 = self._compute_metrics()

        record = TripRecord(
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
            details=details,
            state_before=old_state.value,
            measurements_at_trip=len(self._measurements),
            error_rate_at_trip=round(error_rate, 2),
            latency_p99_at_trip=round(latency_p99, 2),
        )
        self._trip_log.append(record)

        logger.critical(
            f"CIRCUIT BREAKER TRIPPED: '{self.name}' {old_state.value} -> open "
            f"(reason: {reason}, details: {details})"
        )

        # Callback
        if self._on_trip:
            try:
                self._on_trip(reason, details)
            except Exception as e:
                logger.error(f"Circuit breaker on_trip callback failed: {e}")

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        logger.info(
            f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}"
        )


# ── Global singleton ──────────────────────────────────────────────────────────

main_breaker = CircuitBreaker("main")
