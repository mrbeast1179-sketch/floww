"""
Quote Imbalance (QI) Z-Score Calculator.

Quote Imbalance measures the relative size of the best bid vs best ask:

    QI = (bid_size - ask_size) / (bid_size + ask_size)

A rolling z-score of QI flags unusual order-book pressure.  Combined with
VPIN CDF this forms the composite "toxic flow" signal.

Reference: Easley/López de Prado/O'Hara (2012); Hasbrouck (2007).
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, Optional

import numpy as np


class QuoteImbalanceTracker:
    """Rolling Quote Imbalance with z-score.

    Parameters
    ----------
    window : int
        Rolling window size in *minutes*.  Since LOB snapshots arrive
        irregularly we keep the last ``window`` *observations* (each
        observation = one LOB snapshot).  Default 100.
    """

    def __init__(self, window: int = 100) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        self.window = window
        self._history: deque[float] = deque(maxlen=window)
        self._current_qi: float = 0.0
        self._current_zscore: float = 0.0

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def update(self, bid_size: float, ask_size: float) -> float:
        """Ingest a new LOB snapshot and return the raw QI.

        Parameters
        ----------
        bid_size : float
            Total size at the best bid.
        ask_size : float
            Total size at the best ask.

        Returns
        -------
        float
            QI in [-1, 1].
        """
        total = bid_size + ask_size
        if total <= 0:
            qi = 0.0
        else:
            qi = (bid_size - ask_size) / total

        self._current_qi = qi
        self._history.append(qi)
        self._current_zscore = self._compute_zscore()
        return qi

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @property
    def qi(self) -> float:
        return self._current_qi

    @property
    def zscore(self) -> float:
        return self._current_zscore

    def _compute_zscore(self) -> float:
        if len(self._history) < 2:
            return 0.0
        arr = np.array(self._history, dtype=np.float64)
        mean = float(np.mean(arr))
        std = float(np.std(arr, ddof=0))
        if std <= 0 or math.isnan(std):
            return 0.0
        return (self._current_qi - mean) / std

    @property
    def is_bid_dominant(self) -> bool:
        """True when bid_size > ask_size (QI > 0)."""
        return self._current_qi > 0.0

    @property
    def is_significant(self, threshold: float = 1.5) -> bool:
        """True when |z-score| exceeds ``threshold``."""
        return abs(self._current_zscore) > threshold

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        return {
            "qi": self._current_qi,
            "zscore": self._current_zscore,
            "window": self.window,
            "history_length": len(self._history),
            "is_bid_dominant": self.is_bid_dominant,
        }

    def reset(self) -> None:
        self._history.clear()
        self._current_qi = 0.0
        self._current_zscore = 0.0
