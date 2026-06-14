"""
Rolling VPIN CDF Calculator with MongoDB persistence.

Maintains a rolling window of VPIN values and computes the empirical CDF
(percentile rank) of the current VPIN against that window.  Historical CDF
values are stored in MongoDB for backtesting.

Reference: Easley/López de Prado/O'Hara (2012).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import UTC
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class VpinCdfCalculator:
    """Rolling empirical CDF for VPIN values.

    Parameters
    ----------
    window : int
        Number of VPIN values in the rolling window.  Default 50.
    mongo_collection : pymongo collection, optional
        If provided, every CDF update is persisted here for backtesting.
    ticker : str, optional
        Symbol tag for Mongo documents.
    """

    def __init__(
        self,
        window: int = 50,
        mongo_collection: Any = None,
        ticker: str = "",
    ) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self._history: deque[float] = deque(maxlen=window)
        self._current_vpin: float = 0.0
        self._current_cdf: float = 0.0
        self._mongo = mongo_collection
        self._ticker = ticker

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def update(self, vpin_value: float) -> float:
        """Add a new VPIN observation and return its CDF percentile.

        Parameters
        ----------
        vpin_value : float
            The VPIN value for the most-recently-finalized bucket.

        Returns
        -------
        float
            Empirical CDF in [0, 1].  0.5 = median.
        """
        if not (0.0 <= vpin_value <= 1.0):
            raise ValueError(f"VPIN must be in [0,1], got {vpin_value}")

        self._current_vpin = vpin_value
        self._history.append(vpin_value)
        self._current_cdf = self._compute_cdf()

        if self._mongo is not None:
            self._persist()

        return self._current_cdf

    def _compute_cdf(self) -> float:
        """Empirical CDF: fraction of history <= current VPIN.

        The current value is excluded from the denominator to avoid
        self-influence. CDF = count(history < current) / (len(history) - 1).
        """
        if len(self._history) < 2:
            return 0.0
        arr = np.array(self._history, dtype=np.float64)
        # Exclude the last element (current value) from the comparison set
        prior = arr[:-1]
        return float(np.mean(prior <= self._current_vpin))

    def _persist(self) -> None:
        """Write the current CDF snapshot to MongoDB."""
        try:
            import asyncio
            from datetime import datetime

            doc = {
                "ticker": self._ticker,
                "vpin": self._current_vpin,
                "vpin_cdf": self._current_cdf,
                "window": self.window,
                "history_length": len(self._history),
                "ts": datetime.now(UTC),
            }
            # Support both sync and async mongo clients
            if hasattr(self._mongo, "insert_one"):
                # Check if it's async
                import inspect
                if inspect.iscoroutinefunction(self._mongo.insert_one):
                    # Schedule async insert — fire and forget
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._mongo.insert_one(doc))
                    except RuntimeError:
                        pass  # no running loop; skip
                else:
                    self._mongo.insert_one(doc)
        except Exception as exc:
            logger.warning(f"VPIN CDF Mongo persist failed: {exc}")

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def cdf(self) -> float:
        return self._current_cdf

    @property
    def vpin(self) -> float:
        return self._current_vpin

    @property
    def history(self) -> list[float]:
        return list(self._history)

    @property
    def is_high(self) -> bool:
        """True when VPIN is above its historical median (CDF > 0.5)."""
        return self._current_cdf > 0.5

    def get_state(self) -> dict[str, Any]:
        return {
            "vpin": self._current_vpin,
            "vpin_cdf": self._current_cdf,
            "window": self.window,
            "history_length": len(self._history),
            "is_high": self.is_high,
        }

    def reset(self) -> None:
        self._history.clear()
        self._current_vpin = 0.0
        self._current_cdf = 0.0
