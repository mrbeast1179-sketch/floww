"""
Volume-Synchronized Probability of Informed Trading (VPIN) Engine

Implementation based on:
    Easley, D., Lopez de Prado, M.M., & O'Hara, M. (2012).
    "Flow Toxicity and Liquidity in a High-frequency World."
    Review of Financial Studies, 25(5), 1457-1493.

VPIN measures the probability that a trade is information-based (toxic)
by classifying volume into buy and sell initiated trades using the
Bulk Volume Classification (BVC) method, then computing the imbalance
over a rolling window of volume-time buckets.

Key concepts:
    - Volume Clock: Time is measured in cumulative traded volume rather
      than wall-clock time. Each bucket contains a fixed amount of volume
      (bucket_size), making the measure robust to irregular trading intensity.
    - Bulk Volume Classification: Each trade's volume is split into
      buyer-initiated (V^B) and seller-initiated (V^S) components using
      the standard normal CDF applied to the normalized price change:
          V^B_tau = V * Phi(delta_P / (sigma * sqrt(dt)))
          V^S_tau = V - V^B_tau
    - VPIN: The rolling average absolute imbalance across n buckets:
          VPIN = sum(|V^B - V^S|) / sum(V)
      Values near 1 indicate high toxicity (informed trading); values
      near 0 indicate balanced flow.
    - Quote Imbalance (QI): A complementary signal derived from the
      bid/ask size imbalance at the top of book:
          QI = (bid_size - ask_size) / (bid_size + ask_size)
      Combined with VPIN, it provides a multi-dimensional toxicity signal.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, Tuple

import numpy as np

import services.observability as obs_metrics


class VpinEngine:
    """Volume-Synchronized PIN (VPIN) engine with Bulk Volume Classification
    and Quote Imbalance tracking.

    Parameters
    ----------
    bucket_size : float
        Target volume per bucket (volume clock). Default 50,000 units.
    window : int
        Number of buckets in the rolling VPIN window. Default 50.
    """

    def __init__(self, bucket_size: float = 50000.0, window: int = 50, ticker: str = "") -> None:
        if bucket_size <= 0:
            raise ValueError("bucket_size must be positive")
        if window <= 0:
            raise ValueError("window must be positive")

        self.bucket_size = float(bucket_size)
        self.window = int(window)
        self.ticker = ticker

        # Current bucket accumulators
        self._bucket_buy_volume: float = 0.0
        self._bucket_sell_volume: float = 0.0
        self._bucket_total_volume: float = 0.0

        # Rolling finalized buckets
        self._buy_buckets: deque[float] = deque(maxlen=self.window)
        self._sell_buckets: deque[float] = deque(maxlen=self.window)
        self._total_buckets: deque[float] = deque(maxlen=self.window)

        # VPIN history for empirical CDF (larger window for distribution)
        self._vpin_history: deque[float] = deque(maxlen=500)

        # Quote imbalance history for z-score
        self._qi_history: deque[float] = deque(maxlen=500)

        # Latest values for signal output
        self._current_vpin: float = 0.0
        self._current_vpin_cdf: float = 0.0
        self._current_qi: float = 0.0
        self._current_qi_zscore: float = 0.0

    # ------------------------------------------------------------------
    # Bulk Volume Classification
    # ------------------------------------------------------------------

    @staticmethod
    def _norm_cdf(x: np.ndarray) -> np.ndarray:
        """Standard normal CDF: Phi(x) = 0.5 * (1 + erf(x / sqrt(2)))."""
        return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))

    @classmethod
    def classify_volume(
        cls,
        price_changes: np.ndarray,
        volumes: np.ndarray,
        dt: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Classify a sequence of trades into buy and sell volume using
        the Bulk Volume Classification (BVC) method.

        V^B_tau = V * Phi(delta_P / (sigma * sqrt(dt)))
        V^S_tau = V - V^B_tau

        Parameters
        ----------
        price_changes : np.ndarray
            Array of price changes (delta_P) per trade.
        volumes : np.ndarray
            Array of trade volumes.
        dt : float
            Time interval for the observation period. Default 1.0.

        Returns
        -------
        buy_volumes : np.ndarray
            Estimated buyer-initiated volume per trade.
        sell_volumes : np.ndarray
            Estimated seller-initiated volume per trade.
        """
        price_changes = np.asarray(price_changes, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)

        if price_changes.shape != volumes.shape:
            raise ValueError("price_changes and volumes must have the same shape")

        if dt <= 0:
            raise ValueError("dt must be positive")

        # Estimate sigma from price changes (realized volatility)
        sigma = float(np.std(price_changes))
        if sigma <= 0 or math.isnan(sigma):
            # No price variation: split volume evenly
            return volumes * 0.5, volumes * 0.5

        z = price_changes / (sigma * math.sqrt(dt))
        phi = cls._norm_cdf(z)

        buy_volumes = volumes * phi
        sell_volumes = volumes - buy_volumes

        return buy_volumes, sell_volumes

    # ------------------------------------------------------------------
    # Incremental update (single trade)
    # ------------------------------------------------------------------

    def update(
        self,
        price_change: float,
        volume: float,
        sigma: float,
        dt: float = 1.0,
    ) -> None:
        """Add a single trade to the current bucket. When the bucket's
        accumulated volume reaches bucket_size, the bucket is finalized
        and VPIN is recomputed.

        Parameters
        ----------
        price_change : float
            Price change for this trade.
        volume : float
            Trade volume.
        sigma : float
            Estimated return volatility (sigma) for normalization.
        dt : float
            Time interval. Default 1.0.
        """
        if volume <= 0:
            return
        if sigma <= 0 or math.isnan(sigma) or math.isinf(sigma):
            # No volatility estimate: split evenly
            buy_frac = 0.5
        else:
            z = price_change / (sigma * math.sqrt(dt))
            buy_frac = float(self._norm_cdf(np.array([z]))[0])

        buy_vol = volume * buy_frac
        sell_vol = volume - buy_vol

        self._bucket_buy_volume += buy_vol
        self._bucket_sell_volume += sell_vol
        self._bucket_total_volume += volume

        # Check if bucket is full
        if self._bucket_total_volume >= self.bucket_size:
            self._finalize_bucket()

    def _finalize_bucket(self) -> None:
        """Finalize the current bucket and push it into the rolling window."""
        if self._bucket_total_volume <= 0:
            return

        self._buy_buckets.append(self._bucket_buy_volume)
        self._sell_buckets.append(self._bucket_sell_volume)
        self._total_buckets.append(self._bucket_total_volume)

        # Reset accumulators
        self._bucket_buy_volume = 0.0
        self._bucket_sell_volume = 0.0
        self._bucket_total_volume = 0.0

        # Recompute VPIN
        self._current_vpin = self._compute_vpin_from_buckets()
        self._vpin_history.append(self._current_vpin)
        self._current_vpin_cdf = self._compute_vpin_cdf_from_history()

        # Emit Prometheus metrics
        if self.ticker:
            obs_metrics.vpin_current.labels(ticker=self.ticker).set(self._current_vpin)
            obs_metrics.ingestion_messages_total.labels(
                symbol=self.ticker, kind="vpin_bucket"
            ).inc()

    # ------------------------------------------------------------------
    # VPIN computation
    # ------------------------------------------------------------------

    def _compute_vpin_from_buckets(self) -> float:
        """Compute VPIN from the current rolling bucket window."""
        if len(self._total_buckets) == 0:
            return 0.0

        total_vol = sum(self._total_buckets)
        if total_vol <= 0:
            return 0.0

        imbalance = sum(
            abs(b - s)
            for b, s in zip(self._buy_buckets, self._sell_buckets)
        )
        return imbalance / total_vol

    def compute_vpin(self) -> float:
        """Return the current VPIN value.

        VPIN = sum(|V^B - V^S|) / sum(V) over the rolling window of n buckets.

        Returns
        -------
        float
            Current VPIN value in [0, 1].
        """
        return self._current_vpin

    # ------------------------------------------------------------------
    # VPIN empirical CDF
    # ------------------------------------------------------------------

    def _compute_vpin_cdf_from_history(self) -> float:
        """Compute the empirical CDF of the current VPIN against stored history."""
        if len(self._vpin_history) < 2:
            return 0.0

        history = np.array(self._vpin_history, dtype=np.float64)
        # Empirical CDF: fraction of historical VPINs <= current VPIN
        return float(np.mean(history <= self._current_vpin))

    def compute_vpin_cdf(self) -> float:
        """CDF of the current VPIN value against the historical VPIN
        distribution.

        Returns
        -------
        float
            Empirical CDF value in [0, 1]. Higher values indicate the
            current VPIN is in the upper tail of the historical distribution.
        """
        return self._current_vpin_cdf

    # ------------------------------------------------------------------
    # Quote Imbalance
    # ------------------------------------------------------------------

    def compute_quote_imbalance(self, bid_size: float, ask_size: float) -> float:
        """Compute the Quote Imbalance (QI).

        QI = (bid_size - ask_size) / (bid_size + ask_size)

        Parameters
        ----------
        bid_size : float
            Total size at the best bid.
        ask_size : float
            Total size at the best ask.

        Returns
        -------
        float
            QI in [-1, 1]. Positive values indicate bid-side pressure.
        """
        total = bid_size + ask_size
        if total <= 0:
            self._current_qi = 0.0
        else:
            self._current_qi = (bid_size - ask_size) / total

        self._qi_history.append(self._current_qi)

        # Emit Prometheus metric
        if self.ticker:
            obs_metrics.qi_zscore_current.labels(ticker=self.ticker).set(
                self._current_qi
            )

        return self._current_qi

    def compute_qi_zscore(self) -> float:
        """Z-score of the current QI against the rolling QI history.

        Returns
        -------
        float
            Z-score. Values > 1.5 indicate significant bid-side pressure.
        """
        if len(self._qi_history) < 2:
            self._current_qi_zscore = 0.0
            return 0.0

        arr = np.array(self._qi_history, dtype=np.float64)
        mean = float(np.mean(arr))
        std = float(np.std(arr))

        if std <= 0 or math.isnan(std):
            self._current_qi_zscore = 0.0
        else:
            self._current_qi_zscore = (self._current_qi - mean) / std

        return self._current_qi_zscore

    # ------------------------------------------------------------------
    # Toxicity signal
    # ------------------------------------------------------------------

    def get_toxicity_signal(self) -> Dict[str, Any]:
        """Return the composite toxicity signal.

        A market is considered toxic when:
            - VPIN CDF > 0.5  (VPIN is above its historical median)
            AND
            - QI z-score > 1.5  (significant bid-side pressure)

        Returns
        -------
        dict
            {
                "vpin": float,
                "vpin_cdf": float,
                "qi": float,
                "qi_zscore": float,
                "is_toxic": bool,
            }
        """
        is_toxic = (self._current_vpin_cdf > 0.5) and (self._current_qi_zscore > 1.5)
        return {
            "vpin": self._current_vpin,
            "vpin_cdf": self._current_vpin_cdf,
            "qi": self._current_qi,
            "qi_zscore": self._current_qi_zscore,
            "is_toxic": is_toxic,
        }

    # ------------------------------------------------------------------
    # Full state
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return the full engine state for API serialization.

        Returns
        -------
        dict
            Complete state including configuration, current values,
            bucket counts, and history lengths.
        """
        return {
            "config": {
                "bucket_size": self.bucket_size,
                "window": self.window,
            },
            "current": {
                "vpin": self._current_vpin,
                "vpin_cdf": self._current_vpin_cdf,
                "qi": self._current_qi,
                "qi_zscore": self._current_qi_zscore,
            },
            "toxicity": self.get_toxicity_signal(),
            "buckets": {
                "active": {
                    "buy_volume": self._bucket_buy_volume,
                    "sell_volume": self._bucket_sell_volume,
                    "total_volume": self._bucket_total_volume,
                    "fill_ratio": (
                        self._bucket_total_volume / self.bucket_size
                        if self.bucket_size > 0
                        else 0.0
                    ),
                },
                "finalized_count": len(self._total_buckets),
            },
            "history": {
                "vpin_history_length": len(self._vpin_history),
                "qi_history_length": len(self._qi_history),
            },
        }
