"""
backend/services/staleness_alerts.py

Predictive alerting for polling delays and cache staleness.

Monitors `delay_seconds` in DuckDB `ticks`/`chains` tables.
Alerts:
  - MEDIUM  → cache age > 15 min  ("Stale data mode active")
  - CRITICAL → cache age > 60 min  ("Data pipeline stalled")
Suppress duplicates: 15-min cooldown per alert ID.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import duckdb

log = logging.getLogger(__name__)

MEDIUM = "MEDIUM"
CRITICAL = "CRITICAL"

# Thresholds (seconds)
STALE_MEDIUM_SECONDS = 15 * 60    # 15 minutes
STALE_CRITICAL_SECONDS = 60 * 60  # 60 minutes
COOLDOWN_SECONDS = 15 * 60        # 15-minute dedup cooldown


@dataclass
class StalenessAlertManager:
    """
    Monitors data freshness and fires deduplicated staleness alerts.

    Usage:
        mgr = StalenessAlertManager(db_path=":memory:")
        alerts = mgr.check_staleness()
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        stale_medium_seconds: float = STALE_MEDIUM_SECONDS,
        stale_critical_seconds: float = STALE_CRITICAL_SECONDS,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        on_alert: Optional[Callable[[StalenessAlert], None]] = None,
    ):
        self.db_path = db_path
        self.stale_medium_seconds = stale_medium_seconds
        self.stale_critical_seconds = stale_critical_seconds
        self.cooldown_seconds = cooldown_seconds
        self.on_alert = on_alert
        self._last_fired: Dict[str, float] = {}  # alert_id → timestamp

    def _get_max_delay(self, table: str) -> Optional[float]:
        """Get the maximum delay_seconds from a table."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            result = conn.execute(
                f"SELECT MAX(delay_seconds) FROM {table}"
            ).fetchone()
            conn.close()
            if result and result[0] is not None:
                return float(result[0])
            return None
        except Exception as e:
            log.debug(f"Could not query {table}: {e}")
            return None

    def _get_table_freshness(self, table: str) -> Optional[Dict[str, Any]]:
        """Get freshness stats from a table."""
        try:
            conn = duckdb.connect(self.db_path, read_only=True)
            result = conn.execute(f"""
                SELECT
                    MAX(delay_seconds) as max_delay,
                    AVG(delay_seconds) as avg_delay,
                    COUNT(*) as row_count,
                    MAX(timestamp) as latest_ts
                FROM {table}
            """).fetchone()
            conn.close()
            if result:
                return {
                    "max_delay_seconds": float(result[0]) if result[0] else 0,
                    "avg_delay_seconds": float(result[1]) if result[1] else 0,
                    "row_count": int(result[2]) if result[2] else 0,
                    "latest_timestamp": str(result[3]) if result[3] else None,
                }
            return None
        except Exception as e:
            log.debug(f"Could not query {table} freshness: {e}")
            return None

    def _is_cooldown(self, alert_id: str) -> bool:
        """Check if an alert is in cooldown."""
        last = self._last_fired.get(alert_id, 0)
        return (time.time() - last) < self.cooldown_seconds

    def _fire_alert(self, alert: StalenessAlert):
        """Fire an alert and record it."""
        self._last_fired[alert.alert_id] = time.time()
        log.warning(f"[STALENESS] {alert.message}")
        if self.on_alert:
            self.on_alert(alert)

    def check_staleness(
        self,
        tables: Optional[List[str]] = None,
    ) -> List[StalenessAlert]:
        """
        Check staleness across tables.
        Returns list of new alerts (respecting cooldown).
        """
        if tables is None:
            tables = ["ticks", "chains"]

        alerts = []
        now = time.time()

        for table in tables:
            freshness = self._get_table_freshness(table)
            if not freshness:
                continue

            max_delay = freshness["max_delay_seconds"]

            # CRITICAL: > 60 min
            if max_delay >= self.stale_critical_seconds:
                alert_id = f"stalled_{table}"
                if not self._is_cooldown(alert_id):
                    alert = StalenessAlert(
                        alert_id=alert_id,
                        severity=CRITICAL,
                        cache_age_seconds=max_delay,
                        threshold_seconds=self.stale_critical_seconds,
                        timestamp=now,
                        message=(
                            f"CRITICAL: Data pipeline stalled on {table}. "
                            f"Cache age: {max_delay/60:.0f} min "
                            f"(threshold: {self.stale_critical_seconds/60:.0f} min)"
                        ),
                        table=table,
                        details=freshness,
                    )
                    self._fire_alert(alert)
                    alerts.append(alert)
                continue  # Don't also fire MEDIUM

            # MEDIUM: > 15 min
            if max_delay >= self.stale_medium_seconds:
                alert_id = f"stale_{table}"
                if not self._is_cooldown(alert_id):
                    alert = StalenessAlert(
                        alert_id=alert_id,
                        severity=MEDIUM,
                        cache_age_seconds=max_delay,
                        threshold_seconds=self.stale_medium_seconds,
                        timestamp=now,
                        message=(
                            f"MEDIUM: Stale data mode active on {table}. "
                            f"Cache age: {max_delay/60:.0f} min "
                            f"(threshold: {self.stale_medium_seconds/60:.0f} min)"
                        ),
                        table=table,
                        details=freshness,
                    )
                    self._fire_alert(alert)
                    alerts.append(alert)

        return alerts

    def get_freshness_summary(
        self,
        tables: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get freshness summary for all monitored tables."""
        if tables is None:
            tables = ["ticks", "chains"]

        summary = {}
        for table in tables:
            freshness = self._get_table_freshness(table)
            if freshness:
                summary[table] = {
                    **freshness,
                    "stalled": freshness["max_delay_seconds"] >= self.stale_critical_seconds,
                    "stale": freshness["max_delay_seconds"] >= self.stale_medium_seconds,
                }
        return {
            "tables": summary,
            "thresholds": {
                "stale_medium_seconds": self.stale_medium_seconds,
                "stale_critical_seconds": self.stale_critical_seconds,
                "cooldown_seconds": self.cooldown_seconds,
            },
            "active_alerts": [
                {
                    "alert_id": aid,
                    "last_fired": ts,
                    "cooldown_remaining": max(0, self.cooldown_seconds - (time.time() - ts)),
                }
                for aid, ts in self._last_fired.items()
            ],
        }
