"""
backend/services/correlation_engine.py

Cross-Asset and Cross-Exchange VPIN CDF Correlation Engine.

Calculates rolling correlation of VPIN CDF values across:
  - Assets: SPX, SPY, QQQ (cross-asset correlation)
  - Exchanges: Simulated multi-exchange data (cross-exchange correlation)

Outputs z-scores that indicate whether toxicity is systemic (high correlation)
or idiosyncratic (low correlation). Used by trading_signals.py to filter
out noise — only trade when toxicity is systemic.

Reference:
    The Open Street (2024). "VPIN_HFT: Volume-Synchronized Probability of
    Informed Trading for High-Frequency Signal Generation."
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np


class CorrelationEngine:
    """Rolling cross-asset and cross-exchange VPIN CDF correlation engine.

    Maintains per-asset and per-exchange VPIN CDF history buffers and
    computes pairwise Pearson correlations over a rolling window.

    Parameters
    ----------
    window : int
        Rolling window size for correlation calculation. Default 60 (minutes).
    assets : list[str]
        Asset symbols to track. Default ["SPX", "SPY", "QQQ"].
    exchanges : list[str]
        Exchange identifiers to track. Default ["NYSE", "NASDAQ", "BATS"].
    """

    def __init__(
        self,
        window: int = 60,
        assets: list[str] | None = None,
        exchanges: list[str] | None = None,
    ) -> None:
        if window < 2:
            raise ValueError("window must be >= 2")

        self.window = window
        self.assets = assets or ["SPX", "SPY", "QQQ"]
        self.exchanges = exchanges or ["NYSE", "NASDAQ", "BATS"]

        # Per-asset VPIN CDF history: {symbol: deque[float]}
        self._asset_history: dict[str, deque] = {
            a: deque(maxlen=window) for a in self.assets
        }
        # Per-exchange VPIN CDF history: {exchange: deque[float]}
        self._exchange_history: dict[str, deque] = {
            e: deque(maxlen=window) for e in self.exchanges
        }

        # Latest correlation z-scores
        self._asset_corr_zscore: float = 0.0
        self._exchange_corr_zscore: float = 0.0

    # ------------------------------------------------------------------
    # Update methods
    # ------------------------------------------------------------------

    def update_asset(self, symbol: str, vpin_cdf: float) -> None:
        """Record a new VPIN CDF observation for an asset.

        Parameters
        ----------
        symbol : str
            Asset symbol (e.g. "SPY").
        vpin_cdf : float
            Current VPIN CDF value in [0, 1].
        """
        if symbol in self._asset_history:
            self._asset_history[symbol].append(float(vpin_cdf))

    def update_exchange(self, exchange: str, vpin_cdf: float) -> None:
        """Record a new VPIN CDF observation for an exchange.

        Parameters
        ----------
        exchange : str
            Exchange identifier (e.g. "NYSE").
        vpin_cdf : float
            Current VPIN CDF value in [0, 1].
        """
        if exchange in self._exchange_history:
            self._exchange_history[exchange].append(float(vpin_cdf))

    def update(
        self,
        asset_vpin_cdfs: dict[str, float],
        exchange_vpin_cdfs: dict[str, float] | None = None,
    ) -> None:
        """Batch update all assets and exchanges for one time step.

        Parameters
        ----------
        asset_vpin_cdfs : dict[str, float]
            {symbol: vpin_cdf} for each asset.
        exchange_vpin_cdfs : dict[str, float], optional
            {exchange: vpin_cdf} for each exchange.
        """
        for symbol, cdf in asset_vpin_cdfs.items():
            self.update_asset(symbol, cdf)
        if exchange_vpin_cdfs:
            for exchange, cdf in exchange_vpin_cdfs.items():
                self.update_exchange(exchange, cdf)

    # ------------------------------------------------------------------
    # Correlation computation
    # ------------------------------------------------------------------

    @staticmethod
    def _pearson_correlation(x: np.ndarray, y: np.ndarray) -> float:
        """Compute Pearson correlation between two arrays.

        Returns 0.0 if either array has zero variance or length < 2.
        """
        if len(x) < 2 or len(y) < 2:
            return 0.0
        std_x = float(np.std(x))
        std_y = float(np.std(y))
        if std_x <= 0 or std_y <= 0:
            return 0.0
        return float(np.corrcoef(x, y)[0, 1])

    @staticmethod
    def _fisher_z_transform(r: float) -> float:
        """Fisher z-transform: z = arctanh(r) = 0.5 * ln((1+r)/(1-r)).

        Clamps r to [-0.999, 0.999] to avoid division by zero.
        """
        r = max(-0.999, min(0.999, r))
        return 0.5 * math.log((1.0 + r) / (1.0 - r))

    def _compute_pairwise_correlations(
        self, history: dict[str, deque]
    ) -> list[float]:
        """Compute all pairwise Pearson correlations from a history dict.

        Returns list of correlation values (one per unique pair).
        """
        symbols = list(history.keys())
        correlations = []
        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                buf_i = history[symbols[i]]
                buf_j = history[symbols[j]]
                min_len = min(len(buf_i), len(buf_j))
                if min_len < 2:
                    continue
                arr_i = np.array(list(buf_i)[-min_len:], dtype=np.float64)
                arr_j = np.array(list(buf_j)[-min_len:], dtype=np.float64)
                r = self._pearson_correlation(arr_i, arr_j)
                if not math.isnan(r):
                    correlations.append(r)
        return correlations

    def _correlations_to_zscore(self, correlations: list[float]) -> float:
        """Convert a list of correlation coefficients to a single z-score.

        Steps:
        1. Apply Fisher z-transform to each correlation.
        2. Average the z-values.
        3. Convert back to correlation scale and normalize by expected
           standard error to produce a z-score.

        High positive z-score = strong systemic correlation.
        Near zero = no correlation (idiosyncratic).
        """
        if not correlations:
            return 0.0

        # Fisher z-transform each correlation
        z_values = [self._fisher_z_transform(r) for r in correlations]
        mean_z = float(np.mean(z_values))

        # Standard error of Fisher z: SE = 1 / sqrt(n - 3)
        # where n is the number of observations used for each correlation
        # We use the minimum history length across all series
        min_history_len = self.window  # default
        for buf in self._asset_history.values():
            min_history_len = min(min_history_len, len(buf))
        for buf in self._exchange_history.values():
            min_history_len = min(min_history_len, len(buf))

        n = max(min_history_len, 4)  # avoid division by zero
        se = 1.0 / math.sqrt(n - 3)

        # Z-score of the mean Fisher z
        z_score = mean_z / se if se > 0 else 0.0
        return z_score

    # ------------------------------------------------------------------
    # Main compute methods
    # ------------------------------------------------------------------

    def compute_asset_correlation(self) -> float:
        """Compute cross-asset VPIN CDF correlation z-score.

        Returns
        -------
        float
            Z-score of average pairwise Fisher-z-transformed correlation.
            High values indicate systemic toxicity across assets.
        """
        correlations = self._compute_pairwise_correlations(self._asset_history)
        self._asset_corr_zscore = self._correlations_to_zscore(correlations)
        return self._asset_corr_zscore

    def compute_exchange_correlation(self) -> float:
        """Compute cross-exchange VPIN CDF correlation z-score.

        Returns
        -------
        float
            Z-score of average pairwise Fisher-z-transformed correlation.
            High values indicate systemic toxicity across exchanges.
        """
        correlations = self._compute_pairwise_correlations(self._exchange_history)
        self._exchange_corr_zscore = self._correlations_to_zscore(correlations)
        return self._exchange_corr_zscore

    def compute(self) -> tuple[float, float]:
        """Compute both correlation z-scores.

        Returns
        -------
        (exchange_corr_zscore, asset_corr_zscore) : tuple[float, float]
        """
        return self.compute_exchange_correlation(), self.compute_asset_correlation()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def asset_corr_zscore(self) -> float:
        return self._asset_corr_zscore

    @property
    def exchange_corr_zscore(self) -> float:
        return self._exchange_corr_zscore

    def get_state(self) -> dict[str, Any]:
        """Return full engine state for API serialization."""
        return {
            "config": {
                "window": self.window,
                "assets": self.assets,
                "exchanges": self.exchanges,
            },
            "zscores": {
                "asset_corr_zscore": self._asset_corr_zscore,
                "exchange_corr_zscore": self._exchange_corr_zscore,
            },
            "history_lengths": {
                **{a: len(buf) for a, buf in self._asset_history.items()},
                **{e: len(buf) for e, buf in self._exchange_history.items()},
            },
        }
