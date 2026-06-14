"""
backend/services/risk/sizer.py — Kelly criterion position sizer with daily lock.

Computes optimal position size using Kelly criterion:
  f* = (p * b - q) / b
  where p = win rate, b = avg win / avg loss, q = 1 - p

Uses half-Kelly for safety (f* / 2).
Enforces daily lock: if daily loss exceeds threshold, no new positions.

Reference: swarmSPX risk/sizer.py, Kelly (1956)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SizerConfig:
    """Position sizer configuration."""
    max_position_pct: float = 0.10  # max 10% of equity per position
    max_position_value: float = 5000.0  # max $ per position
    kelly_fraction: float = 0.5  # half-Kelly for safety
    min_trades_for_kelly: int = 20  # min trades before using Kelly
    default_win_rate: float = 0.55  # assumed win rate with no history
    default_payoff_ratio: float = 1.5  # assumed avg_win / avg_loss
    daily_loss_lock_pct: float = -0.015  # -1.5% daily loss locks sizing


@dataclass
class TradeRecord:
    """Record of a completed trade."""
    ticker: str
    pnl: float
    entry_price: float
    exit_price: float
    qty: int


class KellySizer:
    """
    Kelly criterion position sizer with daily lock.

    Usage:
        sizer = KellySizer(config=SizerConfig())
        size = sizer.compute_size(intent, account, trade_history)
        if size > :
            execute_with_size(size)
    """

    def __init__(self, config: SizerConfig | None = None):
        self.config = config or SizerConfig()
        self._trade_history: list[TradeRecord] = []

    def compute_size(
        self,
        ticker: str,
        current_price: float,
        account_equity: float,
        daily_pnl_pct: float = 0.0,
        trade_history: list[TradeRecord] | None = None,
    ) -> int:
        """
        Compute optimal position size in shares.
        Returns 0 if sizing is locked or no valid size.
        """
        # Daily loss lock
        if daily_pnl_pct <= self.config.daily_loss_lock_pct:
            logger.warning(f"Sizer: daily loss lock active ({daily_pnl_pct:.2%})")
            return 0

        # Compute Kelly fraction
        history = trade_history or self._trade_history
        kelly_pct = self._compute_kelly_fraction(history)

        # Apply Kelly to equity
        target_value = account_equity * kelly_pct * self.config.kelly_fraction

        # Cap at max position value
        target_value = min(target_value, self.config.max_position_value)

        # Cap at max position pct of equity
        max_value = account_equity * self.config.max_position_pct
        target_value = min(target_value, max_value)

        # Convert to shares
        if current_price <= 0:
            return 0
        shares = int(target_value / current_price)

        logger.info(
            f"Sizer: kelly={kelly_pct:.4f}, target=${target_value:.2f}, shares={shares}"
        )
        return max(shares, 0)

    def _compute_kelly_fraction(self, history: list[TradeRecord]) -> float:
        """
        Compute Kelly fraction from trade history.
        f* = (p * b - q) / b
        """
        if len(history) < self.config.min_trades_for_kelly:
            # Use defaults
            p = self.config.default_win_rate
            b = self.config.default_payoff_ratio
            q = 1 - p
            return max((p * b - q) / b, 0.0)

        # Compute from history
        wins = [t for t in history if t.pnl > 0]
        losses = [t for t in history if t.pnl <= 0]

        if not wins:
            return 0.0  # no winning trades = no edge
        if not losses:
            return 0.05  # conservative default when no losses

        p = len(wins) / len(history)
        avg_win = sum(t.pnl for t in wins) / len(wins)
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses))

        if avg_loss == 0:
            return 0.05

        b = avg_win / avg_loss  # payoff ratio
        q = 1 - p

        kelly = (p * b - q) / b
        return max(kelly, 0.0)  # never negative

    def add_trade(self, trade: TradeRecord):
        """Record a completed trade for future sizing."""
        self._trade_history.append(trade)

    def get_stats(self) -> dict:
        """Get sizing statistics."""
        history = self._trade_history
        wins = [t for t in history if t.pnl > 0]
        losses = [t for t in history if t.pnl <= 0]

        total_pnl = sum(t.pnl for t in history)
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

        return {
            "total_trades": len(history),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": len(wins) / len(history) if history else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "kelly_fraction": round(self._compute_kelly_fraction(history), 4),
        }
