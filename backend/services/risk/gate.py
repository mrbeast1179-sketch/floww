"""
backend/services/risk/gate.py

Pre-trade risk gate: synchronous, blocking, fast (~50ms budget).

Sits between signal generation and order dispatch. Every trade decision passes
through this gate. If any check rejects, the trade is killed before it leaves
the box.

Checks performed (all rejections collected, not short-circuited):
    1. Kill switch (any active circuit breaker → reject)
    2. Daily loss band (default -3% of bankroll → reject)
    3. Max open positions (default 5 concurrent → reject new)
    4. Position size (position_size <= max_position_pct * equity)
    5. Sentiment (sentiment_z >= min_sentiment_z)
    6. Liquidity / Kyle's lambda (kyle_lambda < threshold)
    7. Account equity floor (equity > min_equity)
    8. Data freshness (snapshot age < 30s → reject stale)
    9. Idempotency (duplicate signal_id within 5min → reject)

References:
    - Kyle, A.S. (1985). "Continuous Auctions and Insider Trading." Econometrica.
    - Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
      Journal of Risk.
    - Jarrow, R. & Protter, P. (2012). "A Dysfunctional Role of High Frequency Trading
      in Electronic Markets." International Journal of Theoretical and Applied Finance.
    - Cartea, Á., Jaimungal, S., & Penalva, J. (2015). "Algorithmic and High-Frequency
      Trading." Cambridge University Press.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Default thresholds ────────────────────────────────────────────────────────

DEFAULT_KYLE_LAMBDA_THRESHOLD = 1e-6
DEFAULT_MIN_CONVICTION = 0.7
DEFAULT_MIN_ACCOUNT_EQUITY = 5000.0
DEFAULT_MAX_POSITION_PCT = 0.01
DEFAULT_MAX_OPEN_POSITIONS = 5
DEFAULT_MIN_SENTIMENT_Z = -2.0
DEFAULT_DAILY_LOSS_PCT = 3.0
DEFAULT_DATA_STALENESS_SEC = 30
DEFAULT_IDEMPOTENCY_WINDOW_SEC = 300  # 5 minutes
DEFAULT_KILL_SWITCH_PATH = "/tmp/floww_kill_switch"


@dataclass
class RiskDecision:
    """Outcome of a pre-trade risk check.

    Attributes:
        action: 'PASS' if all checks passed, 'REJECT' otherwise.
        reasons: List of structured rejection codes (empty on PASS).
        meta: Optional details for audit logging (e.g. computed values).
    """

    action: str  # "PASS" | "REJECT"
    reasons: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return True if the decision is PASS."""
        return self.action == "PASS"


class PreTradeRiskGate:
    """Synchronous pre-trade risk evaluator.

    Stateful for idempotency (recent signal_ids cached in memory).
    All checks run on every call; rejection reasons are collected
    (not short-circuited) so callers get full diagnostics.

    Example::

        gate = PreTradeRiskGate()
        decision = gate.check(
            signal_id="abc123",
            ticker="SPX",
            conviction=0.85,
            position_size=100.0,
            equity=10000.0,
            sentiment_z=-1.0,
            kyle_lambda=1e-7,
            open_positions=2,
            snapshot_age_sec=5.0,
            daily_pnl_pct=-1.0,
        )
        if not decision.passed:
            logger.warning("Rejected: %s", decision.reasons)
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
        kill_switch_path: str = DEFAULT_KILL_SWITCH_PATH,
    ):
        self.kyle_lambda_threshold = float(kyle_lambda_threshold)
        self.min_conviction = float(min_conviction)
        self.min_account_equity = float(min_account_equity)
        self.max_position_pct = float(max_position_pct)
        self.max_open_positions = int(max_open_positions)
        self.min_sentiment_z = float(min_sentiment_z)
        self.daily_loss_pct = float(daily_loss_pct)
        self.data_staleness_sec = float(data_staleness_sec)
        self.idempotency_window_sec = float(idempotency_window_sec)
        self.kill_switch_path = kill_switch_path

        # In-memory idempotency cache: signal_id -> timestamp (seconds since epoch)
        self._recent_signals: Dict[str, float] = {}

    # ── Public entry point ───────────────────────────────────────────────────

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
        """Run all pre-trade checks. Returns PASS or REJECT with all reasons.

        All checks are evaluated (no short-circuiting) so the caller receives
        the complete set of rejection reasons for diagnostics and audit.

        Args:
            signal_id: Unique identifier for this trade signal.
            ticker: Ticker symbol (e.g. "SPX").
            conviction: Computed conviction score [0, 1].
            position_size: Dollar size of the proposed position.
            equity: Current account equity in dollars.
            sentiment_z: FlashAlpha sentiment z-score.
            kyle_lambda: Kyle's lambda liquidity estimate.
            open_positions: Number of currently open positions.
            snapshot_age_sec: Age of the market data snapshot in seconds.
            daily_pnl_pct: Current day's P&L as a percentage of bankroll.
            kill_switch_active: If True, immediately reject (circuit breaker).

        Returns:
            RiskDecision with action, reasons list, and meta dict.
        """
        reasons: List[str] = []
        meta: Dict[str, Any] = {
            "signal_id": signal_id,
            "ticker": ticker,
            "conviction": conviction,
            "position_size": position_size,
            "equity": equity,
            "sentiment_z": sentiment_z,
            "kyle_lambda": kyle_lambda,
            "open_positions": open_positions,
            "snapshot_age_sec": snapshot_age_sec,
            "daily_pnl_pct": daily_pnl_pct,
        }

        # 1. Kill switch (highest priority — short-circuit for safety)
        if self._check_kill_switch(kill_switch_active):
            return RiskDecision(
                action="REJECT",
                reasons=["kill_switch_active"],
                meta=meta,
            )

        # 2. Daily loss band
        if not self._check_daily_loss_band(daily_pnl_pct):
            reasons.append("daily_loss_band")
            meta["daily_loss_limit"] = -self.daily_loss_pct

        # 3. Max open positions
        if not self._check_max_open_positions(open_positions):
            reasons.append("max_open_positions")
            meta["max_open_positions_limit"] = self.max_open_positions

        # 4. Position size
        if not self._check_position_size(position_size, equity):
            reasons.append("position_size_exceeded")
            meta["max_position_size"] = self.max_position_pct * equity

        # 5. Sentiment
        if not self._check_sentiment(sentiment_z):
            reasons.append("sentiment_too_negative")
            meta["min_sentiment_z"] = self.min_sentiment_z

        # 6. Liquidity (Kyle's lambda)
        if not self._check_liquidity(kyle_lambda):
            reasons.append("illiquid_market")
            meta["kyle_lambda_threshold"] = self.kyle_lambda_threshold

        # 7. Account equity floor
        if not self._check_account_equity(equity):
            reasons.append("insufficient_equity")
            meta["min_equity"] = self.min_account_equity

        # 8. Data freshness
        if not self._check_data_freshness(snapshot_age_sec):
            reasons.append("stale_market_data")
            meta["data_staleness_limit"] = self.data_staleness_sec

        # 9. Conviction floor
        if not self._check_conviction(conviction):
            reasons.append("conviction_too_low")
            meta["min_conviction"] = self.min_conviction

        # 10. Idempotency
        if not self._check_idempotency(signal_id):
            reasons.append("duplicate_signal")
            meta["idempotency_window_sec"] = self.idempotency_window_sec
        else:
            self._record_signal(signal_id)

        if reasons:
            logger.warning(
                "PRE_TRADE_REJECT signal_id=%s ticker=%s reasons=%s",
                signal_id,
                ticker,
                reasons,
            )
            return RiskDecision(action="REJECT", reasons=reasons, meta=meta)

        return RiskDecision(action="PASS", reasons=[], meta=meta)

    # ── Individual checks (each independently testable) ──────────────────────

    def _check_kill_switch(self, kill_switch_active: bool) -> bool:
        """Return True if kill switch is engaged.

        Checks both the in-memory flag and the kill-switch file on disk.
        The file-based check allows external circuit breakers (e.g. ops scripts)
        to halt trading without modifying process state.

        Reference:
            - Aldridge, I. (2013). "High-Frequency Trading: A Practical Guide."
              Wiley. (Chapter on risk controls and kill switches)
        """
        if kill_switch_active:
            return True
        return os.path.exists(self.kill_switch_path)

    def _check_daily_loss_band(self, daily_pnl_pct: float) -> bool:
        """Return True if daily P&L is within the allowed loss band.

        Rejects when daily_pnl_pct <= -daily_loss_pct (i.e. loss exceeds threshold).

        Reference:
            - Taleb, N.N. (2012). "Antifragile: Things That Gain from Disorder."
              Random House. (Discussion of stop-loss mechanisms)
        """
        return daily_pnl_pct > -self.daily_loss_pct

    def _check_max_open_positions(self, open_positions: int) -> bool:
        """Return True if opening another position would not exceed the cap.

        Reference:
            - Grinold, R. & Kahn, R. (2000). "Active Portfolio Management."
              McGraw-Hill. (Risk budgeting and position limits)
        """
        return open_positions < self.max_open_positions

    def _check_position_size(self, position_size: float, equity: float) -> bool:
        """Return True if position size is within the max_position_pct of equity.

        The 1% rule limits single-trade exposure to a small fraction of total
        capital, consistent with fractional Kelly sizing principles.

        Reference:
            - Kelly, J.L. (1956). "A New Interpretation of Information Rate."
              Bell System Technical Journal.
            - Thorp, E.O. (2006). "The Kelly Criterion in Blackjack, Sports Betting,
              and the Stock Market." Handbook of Asset and Liability Management.
        """
        max_size = self.max_position_pct * equity
        return position_size <= max_size

    def _check_sentiment(self, sentiment_z: float) -> bool:
        """Return True if sentiment z-score is above the minimum threshold.

        Extremely negative sentiment (z < -2) suggests the market regime
        may be adverse; we avoid initiating new positions in such conditions.

        Reference:
            - Baker, M. & Wurgler, J. (2007). "Investor Sentiment in the Stock Market."
              Journal of Economic Perspectives.
        """
        return sentiment_z >= self.min_sentiment_z

    def _check_liquidity(self, kyle_lambda: float) -> bool:
        """Return True if Kyle's lambda indicates sufficient liquidity.

        Kyle's lambda measures the price impact per unit of order flow.
        A lambda above the threshold indicates an illiquid market where
        execution costs would be prohibitive.

        Reference:
            - Kyle, A.S. (1985). "Continuous Auctions and Insider Trading."
              Econometrica, 53(6), 1315-1335.
        """
        return kyle_lambda < self.kyle_lambda_threshold

    def _check_account_equity(self, equity: float) -> bool:
        """Return True if account equity exceeds the minimum floor.

        Trading with insufficient capital increases the risk of ruin
        and may violate broker minimums.

        Reference:
            - Browne, S. (2000). "Can You Do Better Than Kelly in the Short Run?"
              Proceedings of the IEEE/IAFE/INFORMS Conference.
        """
        return equity > self.min_account_equity

    def _check_data_freshness(self, snapshot_age_sec: float) -> bool:
        """Return True if market data snapshot is fresh enough.

        Stale data leads to decisions based on outdated prices, which can
        result in adverse selection and poor fills.

        Reference:
            - Easley, D., López de Prado, M., & O'Hara, M. (2012).
              "Flow Toxicity and Liquidity in a High-frequency World."
              Review of Financial Studies.
        """
        return snapshot_age_sec < self.data_staleness_sec

    def _check_conviction(self, conviction: float) -> bool:
        """Return True if conviction score meets the minimum threshold.

        Low-conviction signals have insufficient edge to justify transaction costs.

        Reference:
            - Black, F. & Litterman, R. (1992). "Global Portfolio Optimization."
              Financial Analysts Journal. (Views and confidence framework)
        """
        return conviction >= self.min_conviction

    def _check_idempotency(self, signal_id: str) -> bool:
        """Return True if signal_id has not been seen within the idempotency window.

        Prevents duplicate order submission from retries or race conditions.

        Reference:
            - Helland, P. & Taber, D. (2018). "Idempotency is a Myth."
              ACM Queue. (Discussion of idempotency keys in distributed systems)
        """
        self._prune_expired_signals()
        return signal_id not in self._recent_signals

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _record_signal(self, signal_id: str) -> None:
        """Record a signal_id in the idempotency cache."""
        self._recent_signals[signal_id] = time.monotonic()

    def _prune_expired_signals(self) -> None:
        """Remove entries older than the idempotency window."""
        cutoff = time.monotonic() - self.idempotency_window_sec
        expired = [sid for sid, ts in self._recent_signals.items() if ts < cutoff]
        for sid in expired:
            del self._recent_signals[sid]

    def clear_idempotency_cache(self) -> None:
        """Clear the entire idempotency cache. Useful for testing."""
        self._recent_signals.clear()
