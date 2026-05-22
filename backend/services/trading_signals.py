"""
backend/services/trading_signals.py

VPIN_HFT Strategy Signal Generator.

Implements the exact trading logic from the VPIN_HFT paper:
  IF vpin_cdf_zscore > 0.5 AND (exchange_corr_zscore + asset_corr_zscore) > 4:
    IF qi_zscore > 1.5:
      SIGNAL = BUY (Cover shorts, Add longs, Reset long death count to 10)
    ELIF qi_zscore < -1.5:
      SIGNAL = SELL (Cover longs, Add shorts, Reset short death count to 10)
  ELSE:
    SIGNAL = HOLD

"Death Count" mechanism: Each period, decrement the death counter for the
active side. When it reaches 0, exit the position. This implements a
variable holding period — positions are held until the death count expires
or a new signal resets it.

Reference:
    The Open Street (2024). "VPIN_HFT: Volume-Synchronized Probability of
    Informed Trading for High-Frequency Signal Generation."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Signal(Enum):
    """Trading signal enumeration."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class SignalState:
    """Mutable state for the signal generator.

    Tracks death counters, current position side, and signal history.
    """
    long_death_count: int = 0
    short_death_count: int = 0
    current_position: Optional[str] = None  # "LONG", "SHORT", or None
    last_signal: Signal = Signal.HOLD
    signal_history: list = field(default_factory=list)

    # Thresholds (configurable)
    vpin_cdf_zscore_threshold: float = 0.5
    corr_zscore_sum_threshold: float = 4.0
    qi_zscore_buy_threshold: float = 1.5
    qi_zscore_sell_threshold: float = -1.5
    death_count_max: int = 10


class TradingSignalGenerator:
    """Generates BUY/SELL/HOLD signals from VPIN CDF z-score, correlation
    z-scores, and quote imbalance z-score per the VPIN_HFT paper.

    Parameters
    ----------
    state : SignalState, optional
        Initial state. If None, uses defaults.
    """

    def __init__(self, state: Optional[SignalState] = None) -> None:
        self.state = state or SignalState()

    # ------------------------------------------------------------------
    # Core signal logic
    # ------------------------------------------------------------------

    def evaluate(
        self,
        vpin_cdf_zscore: float,
        exchange_corr_zscore: float,
        asset_corr_zscore: float,
        qi_zscore: float,
    ) -> Signal:
        """Evaluate the strategy logic and return a BUY/SELL/HOLD signal.

        Parameters
        ----------
        vpin_cdf_zscore : float
            Z-score of the current VPIN CDF against its history.
        exchange_corr_zscore : float
            Cross-exchange VPIN CDF correlation z-score.
        asset_corr_zscore : float
            Cross-asset VPIN CDF correlation z-score.
        qi_zscore : float
            Quote Imbalance z-score.

        Returns
        -------
        Signal
            BUY, SELL, or HOLD.
        """
        # Step 1: Decrement death counts
        self._tick_death_counts()

        # Step 2: Check toxicity condition
        corr_sum = exchange_corr_zscore + asset_corr_zscore
        is_toxic = (
            vpin_cdf_zscore > self.state.vpin_cdf_zscore_threshold
            and corr_sum > self.state.corr_zscore_sum_threshold
        )

        if not is_toxic:
            signal = Signal.HOLD
        else:
            # Step 3: Check quote imbalance direction
            if qi_zscore > self.state.qi_zscore_buy_threshold:
                signal = Signal.BUY
                self._on_buy_signal()
            elif qi_zscore < self.state.qi_zscore_sell_threshold:
                signal = Signal.SELL
                self._on_sell_signal()
            else:
                signal = Signal.HOLD

        # Step 4: Check death count exits
        signal = self._check_death_count_exit(signal)

        # Record
        self.state.last_signal = signal
        self.state.signal_history.append({
            "signal": signal.value,
            "vpin_cdf_zscore": vpin_cdf_zscore,
            "exchange_corr_zscore": exchange_corr_zscore,
            "asset_corr_zscore": asset_corr_zscore,
            "qi_zscore": qi_zscore,
            "long_death_count": self.state.long_death_count,
            "short_death_count": self.state.short_death_count,
        })

        return signal

    # ------------------------------------------------------------------
    # Signal actions
    # ------------------------------------------------------------------

    def _on_buy_signal(self) -> None:
        """Handle BUY signal: cover shorts, add longs, reset long death count."""
        self.state.long_death_count = self.state.death_count_max
        self.state.short_death_count = 0
        self.state.current_position = "LONG"
        logger.debug("BUY signal: long_death_count reset to %d", self.state.death_count_max)

    def _on_sell_signal(self) -> None:
        """Handle SELL signal: cover longs, add shorts, reset short death count."""
        self.state.short_death_count = self.state.death_count_max
        self.state.long_death_count = 0
        self.state.current_position = "SHORT"
        logger.debug("SELL signal: short_death_count reset to %d", self.state.death_count_max)

    # ------------------------------------------------------------------
    # Death count management
    # ------------------------------------------------------------------

    def _tick_death_counts(self) -> None:
        """Decrement both death counts by 1 each period (floor at 0)."""
        if self.state.long_death_count > 0:
            self.state.long_death_count -= 1
        if self.state.short_death_count > 0:
            self.state.short_death_count -= 1

    def _check_death_count_exit(self, signal: Signal) -> Signal:
        """If death count reached 0, force exit (HOLD)."""
        if (
            self.state.current_position == "LONG"
            and self.state.long_death_count <= 0
        ):
            self.state.current_position = None
            if signal == Signal.BUY:
                pass  # New buy signal already reset the counter
            else:
                signal = Signal.HOLD
            logger.debug("Long position expired (death count = 0)")

        if (
            self.state.current_position == "SHORT"
            and self.state.short_death_count <= 0
        ):
            self.state.current_position = None
            if signal == Signal.SELL:
                pass
            else:
                signal = Signal.HOLD
            logger.debug("Short position expired (death count = 0)")

        return signal

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return full state for serialization."""
        return {
            "long_death_count": self.state.long_death_count,
            "short_death_count": self.state.short_death_count,
            "current_position": self.state.current_position,
            "last_signal": self.state.last_signal.value,
            "thresholds": {
                "vpin_cdf_zscore": self.state.vpin_cdf_zscore_threshold,
                "corr_zscore_sum": self.state.corr_zscore_sum_threshold,
                "qi_zscore_buy": self.state.qi_zscore_buy_threshold,
                "qi_zscore_sell": self.state.qi_zscore_sell_threshold,
                "death_count_max": self.state.death_count_max,
            },
            "signal_count": len(self.state.signal_history),
        }
