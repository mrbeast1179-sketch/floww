"""
backend/services/rl/trading_env.py

Gym-compatible trading environment for RL policy training.

Observation space (continuous, 20-dim simplified):
  - GEX features (3): zscore_60d, regime_pos, wall_density_pct
  - VPIN ensemble (3): vpin_current, vpin_cdf, vpin_forecast_15min
  - Trinity (1): score
  - Position state (3): qty_held, unrealized_pnl_pct, time_in_trade_minutes
  - Anomaly (2): anomaly_score, anomaly_regime_index
  - Microstructure (3): kyle_lambda, qi_zscore, amihud
  - Underlying (3): return_5min, return_30min, atr_pct
  - Calendar (2): minutes_to_close, day_of_week

Action space (discrete, 5): {-2: strong sell, -1: sell, 0: hold, +1: buy, +2: strong buy}

Reward: r_t = ΔPnL_t - 0.5 * |Δposition_t| * kyle_lambda - 1.0 * adverse_excursion_t

Reference: Brockman et al. (2016) "OpenAI Gym"; Sutton-Barto (2018) Ch. 13
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)

# Environment constants
OBS_DIM = 20
ACTION_SPACE = 5  # {-2, -1, 0, 1, 2}
MAX_STEPS_PER_EPISODE = 390  # one trading day in minutes
MAX_POSITION = 10  # max contracts
TRANSACTION_COST_PCT = 0.001  # 0.1% per trade


class TradingEnv:
    """A simplified trading environment compatible with Gym interface.

    This environment simulates a single-asset (SPY) trading session
    with realistic market microstructure features.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)
        self.step_count = 0
        self.position = 0  # current position in contracts
        self.cash = 10000.0  # starting cash
        self.entry_price = 0.0
        self.time_in_trade = 0
        self.peak_pnl = 0.0
        self.prev_pnl = 0.0
        self.done = False

        # Simulated market state
        self._vpin = 0.3
        self._trinity_score = 50.0
        self._anomaly_score = 0.0
        self._kyle_lambda = 1e-7
        self._qi_zscore = 0.0
        self._gex_zscore = 0.0
        self._spot = 450.0

    def reset(self) -> np.ndarray:
        """Reset the environment to initial state."""
        self.step_count = 0
        self.position = 0
        self.cash = 10000.0
        self.entry_price = 0.0
        self.time_in_trade = 0
        self.peak_pnl = 0.0
        self.prev_pnl = 0.0
        self.done = False

        # Randomize initial market state
        self._vpin = self.rng.uniform(0.1, 0.5)
        self._trinity_score = self.rng.uniform(20.0, 80.0)
        self._anomaly_score = self.rng.uniform(0.0, 0.3)
        self._kyle_lambda = self.rng.uniform(1e-8, 1e-6)
        self._qi_zscore = self.rng.uniform(-1.0, 1.0)
        self._gex_zscore = self.rng.uniform(-2.0, 2.0)
        self._spot = self.rng.uniform(440.0, 460.0)

        return self._get_observation()

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict[str, Any]]:
        """Take a step in the environment.

        Args:
            action: Integer in {0, 1, 2, 3, 4} mapping to {-2, -1, 0, 1, 2}

        Returns:
            (observation, reward, done, info)
        """
        if self.done:
            return self._get_observation(), 0.0, True, {}

        # Map action index to trade signal
        trade_signal = action - 2  # {0,1,2,3,4} -> {-2,-1,0,1,2}

        # Execute trade
        old_position = self.position
        if trade_signal > 0:
            # Buy
            qty = min(trade_signal, MAX_POSITION - self.position)
            if qty > 0:
                cost = qty * self._spot * (1 + TRANSACTION_COST_PCT)
                if cost <= self.cash:
                    self.cash -= cost
                    if self.position == 0:
                        self.entry_price = self._spot
                    else:
                        # Average entry
                        total_cost = self.entry_price * self.position + self._spot * qty
                        self.entry_price = total_cost / (self.position + qty)
                    self.position += qty
                    self.time_in_trade = 0
        elif trade_signal < 0:
            # Sell
            qty = min(abs(trade_signal), self.position)
            if qty > 0:
                revenue = qty * self._spot * (1 - TRANSACTION_COST_PCT)
                self.cash += revenue
                self.position -= qty
                if self.position == 0:
                    self.entry_price = 0.0
                    self.time_in_trade = 0

        # Simulate market evolution
        self._evolve_market()

        # Compute P&L
        unrealized_pnl = self.position * (self._spot - self.entry_price) if self.position > 0 else 0.0
        total_pnl = (self.cash - 10000.0) + unrealized_pnl

        # Adverse excursion
        if total_pnl > self.peak_pnl:
            self.peak_pnl = total_pnl
        adverse_excursion = max(0, self.peak_pnl - total_pnl)

        # Reward: ΔPnL - transaction_cost_penalty - drawdown_penalty
        delta_pnl = total_pnl - self.prev_pnl
        position_change = abs(self.position - old_position)
        reward = (
            delta_pnl
            - 0.5 * position_change * self._kyle_lambda * self._spot
            - 1.0 * adverse_excursion * 0.01
        )

        self.prev_pnl = total_pnl
        self.step_count += 1
        self.time_in_trade += 1

        # Episode ends at end of trading day
        if self.step_count >= MAX_STEPS_PER_EPISODE:
            self.done = True

        info = {
            "position": self.position,
            "cash": self.cash,
            "total_pnl": total_pnl,
            "unrealized_pnl": unrealized_pnl,
            "spot": self._spot,
            "step": self.step_count,
        }

        return self._get_observation(), reward, self.done, info

    def _evolve_market(self):
        """Simulate one step of market evolution."""
        # Random walk for spot
        self._spot += self.rng.normal(0, 0.1)
        self._spot = max(400.0, min(500.0, self._spot))

        # Mean-reverting VPIN
        self._vpin += (0.3 - self._vpin) * 0.01 + self.rng.normal(0, 0.02)
        self._vpin = max(0.0, min(1.0, self._vpin))

        # Random trinity score
        self._trinity_score += self.rng.normal(0, 2.0)
        self._trinity_score = max(0.0, min(100.0, self._trinity_score))

        # Anomaly score (occasional spikes)
        if self.rng.random() < 0.02:
            self._anomaly_score = self.rng.uniform(0.5, 1.0)
        else:
            self._anomaly_score *= 0.95

        # Kyle's lambda
        self._kyle_lambda = max(1e-8, self._kyle_lambda + self.rng.normal(0, 1e-8))

        # QI z-score
        self._qi_zscore += self.rng.normal(0, 0.1)
        self._qi_zscore = max(-3.0, min(3.0, self._qi_zscore))

        # GEX z-score
        self._gex_zscore += self.rng.normal(0, 0.05)
        self._gex_zscore = max(-3.0, min(3.0, self._gex_zscore))

    def _get_observation(self) -> np.ndarray:
        """Build the observation vector (20-dim)."""
        unrealized_pnl_pct = 0.0
        if self.position > 0 and self.entry_price > 0:
            unrealized_pnl_pct = (self._spot - self.entry_price) / self.entry_price

        obs = np.array([
            # GEX features (3)
            self._gex_zscore,
            0.0,  # regime_pos (placeholder)
            0.0,  # wall_density_pct (placeholder)
            # VPIN ensemble (3)
            self._vpin,
            self._vpin,  # vpin_cdf (simplified)
            self._vpin + self.rng.normal(0, 0.01),  # vpin_forecast
            # Trinity (1)
            self._trinity_score / 100.0,
            # Position state (3)
            float(self.position) / MAX_POSITION,
            unrealized_pnl_pct,
            float(self.time_in_trade) / MAX_STEPS_PER_EPISODE,
            # Anomaly (2)
            self._anomaly_score,
            0.0,  # anomaly_regime_index (placeholder)
            # Microstructure (3)
            math.log10(max(self._kyle_lambda, 1e-10)) / 6.0,  # normalized
            self._qi_zscore / 3.0,
            0.0,  # amihud (placeholder)
            # Underlying (3)
            self.rng.normal(0, 0.001),  # return_5min
            self.rng.normal(0, 0.0005),  # return_30min
            0.15,  # atr_pct (placeholder)
            # Calendar (2)
            1.0 - float(self.step_count) / MAX_STEPS_PER_EPISODE,  # minutes_to_close
            0.5,  # day_of_week (placeholder)
        ], dtype=np.float32)

        return obs

    @property
    def observation_dim(self) -> int:
        return OBS_DIM

    @property
    def action_dim(self) -> int:
        return ACTION_SPACE

    def get_state(self) -> Dict[str, Any]:
        return {
            "step": self.step_count,
            "position": self.position,
            "cash": self.cash,
            "spot": self._spot,
            "vpin": self._vpin,
            "trinity_score": self._trinity_score,
            "done": self.done,
        }
