"""
backend/services/liquidity_metrics.py

Market microstructure liquidity metrics:
- Kyle's Lambda (Kyle, 1985): price impact per unit of order flow
- Amihud Illiquidity (Amihud, 2002): absolute return per dollar of volume
- Market Fragility Index: composite 0-100 score combining multiple signals

References:
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading." Econometrica.
- Amihud, Y. (2002). "Illiquidity and Stock Returns." Journal of Financial Markets.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional

import numpy as np


class KyleLambda:
    """Kyle's Lambda: measures price impact per unit of order flow.

    Estimated via regression: r_t = lambda * signed_volume_t + epsilon
    Higher lambda = less liquid market.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self._returns: deque = deque(maxlen=window)
        self._signed_volumes: deque = deque(maxlen=window)

    def update(self, price: float, volume: float, sign: int):
        """Add an observation. sign: +1 for buy, -1 for sell."""
        if len(self._returns) > 0:
            prev_price = self._last_price if hasattr(self, '_last_price') else price
            if prev_price > 0:
                ret = math.log(price / prev_price) if price > 0 and prev_price > 0 else 0.0
                self._returns.append(ret)
                self._signed_volumes.append(sign * volume)
        self._last_price = price

    def update_from_prices(self, prices: List[float], volumes: List[float], signs: List[int]):
        """Batch update from price/volume/sign arrays."""
        for i in range(1, len(prices)):
            if prices[i] > 0 and prices[i - 1] > 0:
                ret = math.log(prices[i] / prices[i - 1])
                self._returns.append(ret)
                self._signed_volumes.append(signs[i] * volumes[i])

    def compute(self) -> float:
        """Compute Kyle's Lambda via OLS."""
        if len(self._returns) < 3:
            return 0.0
        y = np.array(self._returns, dtype=np.float64)
        x = np.array(self._signed_volumes, dtype=np.float64)
        var_x = np.var(x)
        if var_x < 1e-15:
            return 0.0
        lambda_val = np.cov(y, x)[0, 1] / var_x
        return float(lambda_val)

    def get_state(self) -> Dict[str, Any]:
        return {
            "lambda": self.compute(),
            "n_obs": len(self._returns),
            "window": self.window,
        }


class AmihudIlliquidity:
    """Amihud (2002) Illiquidity measure.

    Amihud = mean(|r_t| / dollar_volume_t) * 1e6
    Higher = more illiquid.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self._illiquidity_values: deque = deque(maxlen=window)
        self._last_price: Optional[float] = None

    def update(self, price: float, volume: float, dollar_volume: float):
        """Add an observation."""
        if self._last_price is not None and self._last_price > 0 and price > 0:
            abs_ret = abs(math.log(price / self._last_price))
            if dollar_volume > 0:
                self._illiquidity_values.append(abs_ret / dollar_volume)
        self._last_price = price

    def compute(self) -> float:
        """Compute Amihud illiquidity (scaled by 1e6)."""
        if not self._illiquidity_values:
            return 0.0
        return float(np.mean(list(self._illiquidity_values)) * 1e6)

    def get_state(self) -> Dict[str, Any]:
        return {
            "amihud": self.compute(),
            "n_obs": len(self._illiquidity_values),
            "window": self.window,
        }


class MarketFragilityIndex:
    """Composite market fragility score (0-100).

    Combines Kyle's Lambda, Amihud, VPIN CDF, Quote Imbalance z-score,
    and bid-ask spread z-score into a single fragility measure.
    """

    # Weights for each component
    WEIGHTS = {
        "kyle_lambda": 0.25,
        "amihud": 0.20,
        "vpin_cdf": 0.25,
        "qi_zscore": 0.15,
        "spread": 0.15,
    }

    def __init__(self, history_window: int = 200):
        self._history_window = history_window
        self._kyle_history: deque = deque(maxlen=history_window)
        self._amihud_history: deque = deque(maxlen=history_window)
        self._vpin_history: deque = deque(maxlen=history_window)
        self._qi_history: deque = deque(maxlen=history_window)
        self._spread_history: deque = deque(maxlen=history_window)

    def update(self, kyle_lambda: float = 0.0, amihud: float = 0.0,
               vpin_cdf: float = 0.0, qi_zscore: float = 0.0,
               spread: float = 0.0):
        """Update all component histories."""
        self._kyle_history.append(abs(kyle_lambda))
        self._amihud_history.append(amihud)
        self._vpin_history.append(vpin_cdf)
        self._qi_history.append(abs(qi_zscore))
        self._spread_history.append(spread)

    def _zscore(self, value: float, history: deque) -> float:
        """Compute z-score of value against history."""
        if len(history) < 5:
            return 0.0
        arr = np.array(history, dtype=np.float64)
        mean = np.mean(arr)
        std = np.std(arr)
        if std < 1e-12:
            return 0.0
        return float((value - mean) / std)

    def _sigmoid_normalize(self, z: float) -> float:
        """Map z-score to [0, 1] via sigmoid."""
        return 1.0 / (1.0 + math.exp(-z))

    def compute(self, kyle_lambda: float = 0.0, amihud: float = 0.0,
                vpin_cdf: float = 0.0, qi_zscore: float = 0.0,
                spread: float = 0.0) -> Dict[str, Any]:
        """Compute composite fragility score.

        Returns dict with:
          - fragility_score: float (0-100)
          - regime: str ("NORMAL", "ELEVATED", "CRISIS")
          - components: dict of individual z-scores and normalized values
          - raw_values: dict of raw inputs
        """
        # Update histories
        self.update(kyle_lambda, amihud, vpin_cdf, qi_zscore, spread)

        # Compute z-scores
        kyle_z = self._zscore(abs(kyle_lambda), self._kyle_history)
        amihud_z = self._zscore(amihud, self._amihud_history)
        vpin_z = self._zscore(vpin_cdf, self._vpin_history)
        qi_z = self._zscore(abs(qi_zscore), self._qi_history)
        spread_z = self._zscore(spread, self._spread_history)

        # Normalize to [0, 1]
        kyle_n = self._sigmoid_normalize(kyle_z)
        amihud_n = self._sigmoid_normalize(amihud_z)
        vpin_n = self._sigmoid_normalize(vpin_z)
        qi_n = self._sigmoid_normalize(qi_z)
        spread_n = self._sigmoid_normalize(spread_z)

        # Weighted combination
        score = (
            self.WEIGHTS["kyle_lambda"] * kyle_n
            + self.WEIGHTS["amihud"] * amihud_n
            + self.WEIGHTS["vpin_cdf"] * vpin_n
            + self.WEIGHTS["qi_zscore"] * qi_n
            + self.WEIGHTS["spread"] * spread_n
        ) * 100.0

        # Regime classification
        if score < 33:
            regime = "NORMAL"
        elif score < 66:
            regime = "ELEVATED"
        else:
            regime = "CRISIS"

        return {
            "fragility_score": round(score, 2),
            "regime": regime,
            "components": {
                "kyle_lambda": {"zscore": round(kyle_z, 4), "normalized": round(kyle_n, 4)},
                "amihud": {"zscore": round(amihud_z, 4), "normalized": round(amihud_n, 4)},
                "vpin_cdf": {"zscore": round(vpin_z, 4), "normalized": round(vpin_n, 4)},
                "qi_zscore": {"zscore": round(qi_z, 4), "normalized": round(qi_n, 4)},
                "spread": {"zscore": round(spread_z, 4), "normalized": round(spread_n, 4)},
            },
            "raw_values": {
                "kyle_lambda": kyle_lambda,
                "amihud": amihud,
                "vpin_cdf": vpin_cdf,
                "qi_zscore": qi_zscore,
                "spread": spread,
            },
        }
