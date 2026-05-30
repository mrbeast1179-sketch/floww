"""
backend/services/risk/gate.py — Pre-trade risk gate with multi-trigger circuit breakers.

Two APIs:
  1. RiskGate — Original API with before_trade(intent, account) -> RiskResult
  2. PreTradeRiskGate — New API with check(**kwargs) -> RiskDecision

Reference: swarmSPX risk/gate.py, Almgren-Chriss (2001)
"""

from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default constants ─────────────────────────────────────────────────────────

DEFAULT_DAILY_LOSS_PCT = -3.0
DEFAULT_DATA_STALENESS_SEC = 30.0
DEFAULT_IDEMPOTENCY_WINDOW_SEC = 5.0
DEFAULT_KYLE_LAMBDA_THRESHOLD = 1e-6
DEFAULT_MAX_OPEN_POSITIONS = 5
DEFAULT_MAX_POSITION_PCT = 0.01
DEFAULT_MIN_ACCOUNT_EQUITY = 5000.0
DEFAULT_MIN_CONVICTION = 0.7
DEFAULT_MIN_SENTIMENT_Z = -2.0


# ── RiskDecision (new API) ────────────────────────────────────────────────────

@dataclass
class RiskDecision:
    """Result of a PreTradeRiskGate check."""
    action: str  # "PASS" or "REJECT"
    reasons: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.action == "PASS"


# ── PreTradeRiskGate (new API) ────────────────────────────────────────────────

class PreTradeRiskGate:
    """
    Pre-trade risk gate with keyword-argument check() API.

    Usage:
        gate = PreTradeRiskGate()
        decision = gate.check(
            signal_id="sig_001",
            ticker="SPX",
            conviction=0.85,
            position_size=50.0,
            equity=10000.0,
            sentiment_z=-1.0,
            kyle_lambda=1e-7,
            open_positions=2,
            snapshot_age_sec=5.0,
            daily_pnl_pct=-1.0,
            kill_switch_active=False,
        )
        if decision.passed:
            execute_trade()
    """

    def __init__(
        self,
        kyle_lambda_threshold: float = DEFAULT_KYLE_LAMBDA_THRESHOLD,
        min_conviction: float = DEFAULT_MIN_CONVICTION,
        min_account_equity: float = DEFAULT_MIN_ACCOUNT_EQUITY,
        max_position_pct: float = DEFAULT_MAX_POSITION_PCT,
        max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS,
        min_sentiment_z: float = DEFAULT_MIN_SENTIMENT_Z,
        daily_loss_pct: float = DEFAULT_DAILY_LOSS_PCT,
        data_staleness_sec: float = DEFAULT_DATA_STALENESS_SEC,
        idempotency_window_sec: float = DEFAULT_IDEMPOTENCY_WINDOW_SEC,
        kill_switch_path: Optional[str] = None,
    ):
        self.kyle_lambda_threshold = kyle_lambda_threshold
        self.min_conviction = min_conviction
        self.min_account_equity = min_account_equity
        self.max_position_pct = max_position_pct
        self.max_open_positions = max_open_positions
        self.min_sentiment_z = min_sentiment_z
        self.daily_loss_pct = daily_loss_pct
        self.data_staleness_sec = data_staleness_sec
        self.idempotency_window_sec = idempotency_window_sec
        self.kill_switch_path = kill_switch_path
        self._idempotency_cache: dict[str, float] = {}

    def check(
        self,
        signal_id: str,
        ticker: str,
        conviction: float,
        position_size: float,
        equity: float,
        sentiment_z: float,
        kyle_lambda: float,
        open_positions: int,
        snapshot_age_sec: float,
        daily_pnl_pct: float,
        kill_switch_active: bool = False,
    ) -> RiskDecision:
        """Run all risk checks. Returns RiskDecision with all failing reasons."""
        reasons: list[str] = []
        meta: dict = {
            "signal_id": signal_id,
            "ticker": ticker,
            "conviction": conviction,
            "position_size": position_size,
            "equity": equity,
        }

        # Kill switch (short-circuits)
        if kill_switch_active or self._kill_switch_file_exists():
            return RiskDecision(
                action="REJECT",
                reasons=["kill_switch_active"],
                meta=meta,
            )

        # Daily loss band
        if daily_pnl_pct <= self.daily_loss_pct:
            reasons.append("daily_loss_band")
            meta["daily_loss_pct"] = self.daily_loss_pct

        # Max open positions
        if open_positions >= self.max_open_positions:
            reasons.append("max_open_positions")
            meta["max_open_positions"] = self.max_open_positions

        # Position size
        max_size = equity * self.max_position_pct
        if position_size > max_size:
            reasons.append("position_size_exceeded")
            meta["max_position_size"] = max_size

        # Sentiment (NaN always fails)
        if math.isnan(sentiment_z) or sentiment_z < self.min_sentiment_z:
            reasons.append("sentiment_too_negative")
            meta["min_sentiment_z"] = self.min_sentiment_z

        # Liquidity (Kyle's lambda) — NaN always fails
        if math.isnan(kyle_lambda) or kyle_lambda >= self.kyle_lambda_threshold:
            reasons.append("illiquid_market")
            meta["kyle_lambda_threshold"] = self.kyle_lambda_threshold

        # Account equity
        if equity <= self.min_account_equity:
            reasons.append("insufficient_equity")
            meta["min_equity"] = self.min_account_equity

        # Data freshness
        if snapshot_age_sec >= self.data_staleness_sec:
            reasons.append("stale_market_data")
            meta["data_staleness_sec"] = self.data_staleness_sec

        # Conviction (NaN always fails)
        if math.isnan(conviction) or conviction < self.min_conviction:
            reasons.append("conviction_too_low")
            meta["min_conviction"] = self.min_conviction

        # Idempotency
        if self._is_duplicate(signal_id):
            reasons.append("duplicate_signal")

        if reasons:
            return RiskDecision(action="REJECT", reasons=reasons, meta=meta)
        return RiskDecision(action="PASS", meta=meta)

    def clear_idempotency_cache(self):
        """Clear the idempotency cache."""
        self._idempotency_cache.clear()

    def _kill_switch_file_exists(self) -> bool:
        if self.kill_switch_path and os.path.exists(self.kill_switch_path):
            return True
        return False

    def _is_duplicate(self, signal_id: str) -> bool:
        now = time.monotonic()
        if signal_id in self._idempotency_cache:
            ts = self._idempotency_cache[signal_id]
            if now - ts < self.idempotency_window_sec:
                return True
        self._idempotency_cache[signal_id] = now
        # Evict old entries
        cutoff = now - self.idempotency_window_sec * 2
        self._idempotency_cache = {
            k: v for k, v in self._idempotency_cache.items() if v > cutoff
        }
        return False


# ── RiskConfig / TradeIntent / AccountState (original API) ────────────────────

@dataclass
class RiskConfig:
    """Configuration for the RiskGate.

    Conservative defaults — override per-account via RiskConfig(...). Owner decision
    2026-05-30: prior defaults were at broken scales (-3.0 = -300% daily loss never
    triggered; 1e-6 Kyle rejected every trade; 1% concentration rejected normal
    ~1-2% positions). Realigned to a sane, configurable policy.
    """
    max_daily_loss_pct: float = -0.03      # -3% realized daily loss trips the breaker
    max_consecutive_losses: int = 3
    min_account_equity: float = 1000.0
    max_position_pct: float = 0.10         # <=10% of equity per position (relative cap)
    max_position_value: float = 5000.0     # absolute $ cap per position (usual binder)
    max_open_positions: int = 5
    kyle_lambda_threshold: float = 0.05    # liquidity gate (Kyle's lambda)


@dataclass
class TradeIntent:
    """Minimal trade intent for risk checking."""
    ticker: str
    side: str
    qty: int
    limit_price: float
    conviction: float = 0.5
    kyle_lambda: float = 0.0
    signal_id: str = ""


@dataclass
class Position:
    """Current position for a ticker."""
    ticker: str
    qty: int
    avg_cost: float
    unrealized_pnl: float = 0.0


@dataclass
class AccountState:
    """Current account state."""
    equity: float
    cash: float
    daily_pnl_pct: float = 0.0
    open_positions: dict = field(default_factory=dict)
    consecutive_losses: int = 0
    last_trade_pnl: float = 0.0


# ── RiskGate (original API) ───────────────────────────────────────────────────

class RiskGate:
    """
    Pre-trade risk gate with multi-trigger circuit breakers.

    Usage:
        gate = RiskGate(config=RiskConfig())
        result = gate.before_trade(intent, account)
        if result.approved:
            execute_trade(intent)
    """

    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        self._circuit_breaker_tripped = False
        self._circuit_breaker_reason = ""
        self._trade_history: list[dict] = []

    @property
    def circuit_breaker_active(self) -> bool:
        return self._circuit_breaker_tripped

    def reset_circuit_breaker(self):
        """Manual reset after human review."""
        self._circuit_breaker_tripped = False
        self._circuit_breaker_reason = ""
        logger.info("RiskGate: circuit breaker reset")

    def before_trade(self, intent: TradeIntent, account: AccountState) -> "RiskResult":
        """Evaluate a trade intent against all risk rules."""
        if self._circuit_breaker_tripped:
            return RiskResult(
                approved=False,
                reason=f"Circuit breaker active: {self._circuit_breaker_reason}",
                rule="circuit_breaker",
            )

        # Rule 1: Daily loss limit
        if account.daily_pnl_pct <= self.config.max_daily_loss_pct:
            self._trip_circuit_breaker(f"Daily loss limit hit: {account.daily_pnl_pct:.2%}")
            return RiskResult(
                approved=False,
                reason=f"Daily loss limit: {account.daily_pnl_pct:.2%} <= {self.config.max_daily_loss_pct:.2%}",
                rule="daily_loss_limit",
            )

        # Rule 2: Consecutive losses
        if account.consecutive_losses >= self.config.max_consecutive_losses:
            self._trip_circuit_breaker(f"Consecutive losses: {account.consecutive_losses}")
            return RiskResult(
                approved=False,
                reason=f"Consecutive losses: {account.consecutive_losses} >= {self.config.max_consecutive_losses}",
                rule="consecutive_losses",
            )

        # Rule 3: Minimum account equity
        if account.equity < self.config.min_account_equity:
            return RiskResult(
                approved=False,
                reason=f"Account equity ${account.equity:.0f} < minimum ${self.config.min_account_equity:.0f}",
                rule="min_equity",
            )

        # Rule 4: Position concentration
        position_value = intent.qty * intent.limit_price
        if position_value > account.equity * self.config.max_position_pct:
            return RiskResult(
                approved=False,
                reason=f"Position size ${position_value:.0f} > {self.config.max_position_pct:.0%} of equity ${account.equity:.0f}",
                rule="position_concentration",
            )

        # Rule 5: Max position value
        if position_value > self.config.max_position_value:
            return RiskResult(
                approved=False,
                reason=f"Position value ${position_value:.0f} > max ${self.config.max_position_value:.0f}",
                rule="max_position_value",
            )

        # Rule 6: Max open positions
        if len(account.open_positions) >= self.config.max_open_positions:
            if intent.ticker not in account.open_positions:
                return RiskResult(
                    approved=False,
                    reason=f"Max open positions: {len(account.open_positions)} >= {self.config.max_open_positions}",
                    rule="max_open_positions",
                )

        # Rule 7: Liquidity gate
        if intent.kyle_lambda > self.config.kyle_lambda_threshold:
            return RiskResult(
                approved=False,
                reason=f"Kyle's λ {intent.kyle_lambda:.4f} > threshold {self.config.kyle_lambda_threshold}",
                rule="liquidity_gate",
            )

        # Rule 8: Conviction threshold
        if intent.conviction < 0.5:
            return RiskResult(
                approved=False,
                reason=f"Conviction {intent.conviction:.2f} < 0.5",
                rule="conviction_threshold",
            )

        return RiskResult(approved=True, reason="All checks passed", rule="")

    def after_trade(self, intent: TradeIntent, pnl: float):
        """Update internal state after a trade completes."""
        self._trade_history.append({
            "ticker": intent.ticker,
            "side": intent.side,
            "qty": intent.qty,
            "pnl": pnl,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if pnl < 0:
            logger.warning(f"RiskGate: loss trade {intent.ticker} PnL=${pnl:.2f}")
        else:
            logger.info(f"RiskGate: profit trade {intent.ticker} PnL=${pnl:.2f}")

    def _trip_circuit_breaker(self, reason: str):
        self._circuit_breaker_tripped = True
        self._circuit_breaker_reason = reason
        logger.critical(f"RiskGate: CIRCUIT BREAKER TRIPPED — {reason}")

    def get_trade_history(self) -> list[dict]:
        return list(self._trade_history)


@dataclass
class RiskResult:
    """Result of a risk gate check."""
    approved: bool
    reason: str
    rule: str

    def __bool__(self):
        return self.approved
