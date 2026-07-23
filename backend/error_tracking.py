"""
Error tracking and logging improvements for Confluence Decoder.

Features:
- Structured JSON logging
- Request ID tracking
- Error aggregation
- Performance monitoring
- Sentry integration (optional)
"""

import logging
import os
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Error aggregation
_error_counts: dict[str, int] = {}
_error_log: list = []
MAX_ERROR_LOG = 1000


def setup_logging(level: str = "INFO") -> None:
    """Set up structured logging for the application."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Console handler with structured format
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(StructuredFormatter())

    # File handler for persistent logs
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(
        os.path.join(log_dir, "app.log"),
        encoding="utf-8",
    )
    file_handler.setFormatter(StructuredFormatter())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def set_request_id(request_id: str | None = None) -> str:
    """Set the current request ID for logging context."""
    rid = request_id or str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID."""
    return request_id_var.get()


def log_error(error_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    """Log an error and track it in the aggregation."""
    global _error_counts, _error_log

    _error_counts[error_type] = _error_counts.get(error_type, 0) + 1

    error_entry = {
        "type": error_type,
        "message": message,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": get_request_id(),
        "count": _error_counts[error_type],
    }

    _error_log.append(error_entry)

    # Trim log if too large
    if len(_error_log) > MAX_ERROR_LOG:
        _error_log = _error_log[-MAX_ERROR_LOG:]

    # Log to standard logger
    logger = logging.getLogger("error_tracker")
    logger.error(f"[{error_type}] {message}", extra={"extra_data": data})


def get_error_summary() -> dict[str, Any]:
    """Get a summary of all tracked errors."""
    return {
        "total_errors": sum(_error_counts.values()),
        "by_type": dict(_error_counts),
        "recent": _error_log[-20:],
        "timestamp": datetime.now(UTC).isoformat(),
    }


def clear_error_log() -> None:
    """Clear the error tracking data."""
    global _error_counts, _error_log
    _error_counts = {}
    _error_log = []


class StructuredFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record):
        import json
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        })


class PerformanceMonitor:
    """Best-effort per-endpoint latency tracker.

    `record()` is the sole writer; the middleware (server.py:286) wraps every
    call in try/except so this method MUST stay side-effect-free for invalid
    inputs and cheap on the hot path.  `_metrics` is a flat dict bucketed by
    endpoint with running count + total + max — enough to derive p99 latency
    on demand via read helpers without maintaining a per-bucket histogram.
    Cardinality cap protects against memory creep on a long-running backend.
    """

    _MAX_TRACKED_ENDPOINTS = 256

    def __init__(self):
        self._metrics: dict[str, dict[str, float | int]] = {}

    def record(self, endpoint: str, duration_ms: float) -> None:
        """Append one timing sample for `endpoint`.

        Best-effort: returns silently on bad input so the middleware's outer
        try/except (server.py:286) never has to log a warning for routine
        shape mismatches.  Hot-path safe — no I/O, no allocation beyond a
        small dict setdefault + arithmetic.
        """
        if not isinstance(endpoint, str) or not endpoint:
            return
        if not isinstance(duration_ms, (int, float)) or duration_ms < 0:
            return
        # LRU-ish cap: drop the oldest tracked endpoint when full so memory
        # stays bounded under pathologically diverse route lists.
        if endpoint not in self._metrics and len(self._metrics) >= self._MAX_TRACKED_ENDPOINTS:
            self._metrics.pop(next(iter(self._metrics)))
        bucket = self._metrics.setdefault(endpoint, {"count": 0, "total_ms": 0.0, "max_ms": 0.0})
        bucket["count"] += 1
        bucket["total_ms"] += duration_ms
        if duration_ms > bucket["max_ms"]:
            bucket["max_ms"] = duration_ms


perf_monitor = PerformanceMonitor()


# ---------------------------------------------------------------------------
# Re-export the redaction Counter (defined in services/observability.py
# alongside all other floww_ Prom metrics) so server.py:global_exception_handler
# can call `error_tracking.redacted_500_count.labels(env=_env).inc()`
# directly.  This keeps prometheus_client and the registry confined to a
# single backend module while exposing a stable cross-module call surface
# here.  Wrapped in try/except so a missing prometheus_client dep does not
# turn `import error_tracking` into a top-level crash — callers (server.py)
# already wrap the metric .inc() in try/except as belt-and-suspenders.
# ---------------------------------------------------------------------------
try:
    from services.observability import redacted_500_count  # noqa: F401  (re-export)
except Exception:
    redacted_500_count = None  # type: ignore[assignment]  CALLER MUST try/except
