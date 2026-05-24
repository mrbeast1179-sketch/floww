"""
backend/services/fill_monitor.py

Fill-quality monitor — tracks slippage and execution quality per ticker.

After each fill, computes slippage_bps = (fill_price - limit_price) / limit_price * 10000.
Tracks p50/p95/p99 slippage rolling 24h per ticker.
Emits Prometheus metric floww_fill_slippage_bps_p95.

Reference: Hasbrouck (2007) "Empirical Market Microstructure" — slippage modeling.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

import services.observability as obs_metrics

log = logging.getLogger(__name__)

# Rolling window for slippage data (seconds)
SLIPPAGE_WINDOW = 86400  # 24 hours

# Alert threshold for p95 slippage (bps)
P95_SLIPPAGE_ALERT_BPS = 5.0


@dataclass
class FillRecord:
    """A single fill record for slippage tracking."""
    ticker: str
    fill_price: float
    limit_price: float
    slippage_bps: float
    timestamp: float
    side: str  # "buy" or "sell"


class FillMonitor:
    """Monitors fill quality and tracks slippage per ticker."""

    def __init__(self, window_seconds: int = SLIPPAGE_WINDOW):
        self._window = window_seconds
        self._fills: Dict[str, deque] = {}  # ticker -> deque of FillRecord

    def record_fill(
        self,
        ticker: str,
        fill_price: float,
        limit_price: float,
        side: str = "buy",
    ) -> float:
        """Record a fill and compute slippage in basis points.

        Returns:
            slippage_bps: positive means adverse (paid more than limit).
        """
        if limit_price <= 0:
            slippage_bps = 0.0
        else:
            slippage_bps = (fill_price - limit_price) / limit_price * 10000.0

        record = FillRecord(
            ticker=ticker,
            fill_price=fill_price,
            limit_price=limit_price,
            slippage_bps=slippage_bps,
            timestamp=time.time(),
            side=side,
        )

        if ticker not in self._fills:
            self._fills[ticker] = deque()
        self._fills[ticker].append(record)
        self._cleanup(ticker)

        # Emit Prometheus metric for slippage
        try:
            obs_metrics.fill_slippage_bps.labels(ticker=ticker, side=side).observe(abs(slippage_bps))
            obs_metrics.fills_total.labels(ticker=ticker, side=side).inc()
        except Exception:
            pass  # Metrics should never break fill recording

        log.debug(
            f"Fill recorded: {ticker} {side} @ {fill_price:.2f} "
            f"(limit={limit_price:.2f}, slippage={slippage_bps:.1f}bps)"
        )
        return slippage_bps

    def _cleanup(self, ticker: str):
        """Remove fills outside the rolling window."""
        cutoff = time.time() - self._window
        dq = self._fills.get(ticker)
        if dq:
            while dq and dq[0].timestamp < cutoff:
                dq.popleft()

    def get_slippage_stats(self, ticker: str) -> Dict[str, float]:
        """Get slippage statistics for a ticker.

        Returns dict with p50, p95, p99, mean, count.
        """
        dq = self._fills.get(ticker, deque())
        if not dq:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "count": 0}

        slippages = [abs(f.slippage_bps) for f in dq]
        arr = np.array(slippages)

        return {
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "mean": round(float(np.mean(arr)), 2),
            "count": len(slippages),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Get slippage stats for all tickers."""
        return {ticker: self.get_slippage_stats(ticker) for ticker in self._fills}

    def is_p95_alert(self, ticker: str) -> bool:
        """Check if p95 slippage exceeds alert threshold."""
        stats = self.get_slippage_stats(ticker)
        return stats["p95"] > P95_SLIPPAGE_ALERT_BPS and stats["count"] >= 10

    def get_state(self) -> Dict[str, Any]:
        return {
            "tickers_tracked": list(self._fills.keys()),
            "total_fills": sum(len(dq) for dq in self._fills.values()),
            "stats": self.get_all_stats(),
        }


# Global singleton
monitor = FillMonitor()
