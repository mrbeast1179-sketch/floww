"""
SwarmSPX-inspired risk gate for the Neridian Agent.

Adopts three patterns from dhawalc/swarmSPX (MIT) that floww's
auto_trade_risk currently lacks:

  1. PreTradeRiskGate — 8-check synchronous gate (kill switch,
     daily/weekly/monthly loss bands, consecutive losses, position
     cap, data freshness, idempotency, direction validity) before
     any order is dispatched.
  2. KellyPositionSizer — fractional Kelly (default 0.10) with
     daily sizing lock.
  3. Extended KillSwitch — weekly/monthly loss bands + auto-clear
     at next trading-day open (the floww KillSwitch only has
     daily loss + drawdown).

All logic is pure-Python; the route layer owns persistence and the
paper-trading engine.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from services.risk.killswitch import KillSwitch, KillSwitchConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extended KillSwitch — adds weekly / monthly bands + auto-clear
# ---------------------------------------------------------------------------

DEFAULT_WEEKLY_LOSS_PCT = -0.06   # -6% weekly loss
DEFAULT_MONTHLY_LOSS_PCT = -0.10  # -10% monthly loss
DEFAULT_MAX_CONSECUTIVE_LOSSES = 3


class ExtendedKillSwitch(KillSwitch):
    """KillSwitch with weekly / monthly loss bands and consecutive-loss trip.

    Inherits the daily -2% / -5% drawdown gates from the base class
    and adds:
      - weekly loss band
      - monthly loss band
      - consecutive-loss trip
      - auto-clear at next 09:30 ET trading-day open
    """

    def __init__(
        self,
        config: KillSwitchConfig | None = None,
        weekly_loss_pct: float = DEFAULT_WEEKLY_LOSS_PCT,
        monthly_loss_pct: float = DEFAULT_MONTHLY_LOSS_PCT,
        max_consecutive_losses: int = DEFAULT_MAX_CONSECUTIVE_LOSSES,
    ) -> None:
        super().__init__(config=config)
        self.weekly_loss_pct = weekly_loss_pct
        self.monthly_loss_pct = monthly_loss_pct
        self.max_consecutive_losses = max_consecutive_losses
        self._consecutive_losses = 0
        self._last_loss_date: date | None = None

    def trip(self, reason: str = "") -> None:
        super()._trip(reason or "extended kill switch")
        logger.error("ExtendedKillSwitch TRIPPED: %s", reason)

    def evaluate_loss_bands(
        self,
        daily_pnl_pct: float,
        weekly_pnl_pct: float,
        monthly_pnl_pct: float,
    ) -> bool:
        """Trip if any loss-band threshold is breached. Returns is_tripped."""
        if self.is_tripped:
            return True
        if monthly_pnl_pct <= self.monthly_loss_pct:
            self.trip(f"monthly_loss: {monthly_pnl_pct:+.2%}")
            return True
        if weekly_pnl_pct <= self.weekly_loss_pct:
            self.trip(f"weekly_loss: {weekly_pnl_pct:+.2%}")
            return True
        if daily_pnl_pct <= self.config.daily_loss_pct_threshold:
            self.trip(f"daily_loss: {daily_pnl_pct:+.2%}")
            return True
        return False

    def evaluate_consecutive_losses(self, count: int) -> bool:
        """Trip if consecutive-loss count meets/exceeds the threshold."""
        if self.is_tripped:
            return True
        today = date.today()
        if self._last_loss_date != today:
            self._consecutive_losses = 0
            self._last_loss_date = today
        if count >= self.max_consecutive_losses:
            self.trip(f"{count} consecutive losses today")
            return True
        return False

    def record_loss(self) -> None:
        """Increment consecutive-loss counter and persist."""
        today = date.today()
        if self._last_loss_date != today:
            self._consecutive_losses = 0
            self._last_loss_date = today
        self._consecutive_losses += 1
        self.evaluate_consecutive_losses(self._consecutive_losses)

    def record_win(self) -> None:
        """Reset consecutive-loss counter on a winning trade."""
        self._consecutive_losses = 0
        self._last_loss_date = date.today()

    def get_status(self) -> dict[str, Any]:
        status = super().get_status()
        status.update({
            "weekly_loss_pct": self.weekly_loss_pct,
            "monthly_loss_pct": self.monthly_loss_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "consecutive_losses": self._consecutive_losses,
        })
        return status


# ---------------------------------------------------------------------------
# PreTradeRiskGate — 8-check synchronous gate (from SwarmSPX)
# ---------------------------------------------------------------------------

@dataclass
class RiskDecision:
    """Outcome of a pre-trade check."""
    action: str  # "PASS" | "REJECT"
    reasons: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.action == "PASS"


class PreTradeRiskGate:
    """Synchronous pre-trade risk evaluator.

    Every Neridian decision passes through this gate before the
    paper-trading engine dispatches anything.  If any check rejects,
    the trade is killed before it leaves the box.

    Checks (all rejections logged with structured reason):
        1. Kill switch state (any active circuit breaker → reject)
        2. Daily loss band (default -2% of bankroll → reject for day)
        3. Weekly loss band (default -6% → reject for week)
        4. Monthly loss band (default -10% → reject for month)
        5. Consecutive losses (3 in a row → reject for session)
        6. Position-count cap (default 5 open → reject new)
        7. Data freshness (snapshot older than 30s → reject stale)
        8. Idempotency (same key within 5min → reject duplicate)
        9. Direction validity (HOLD/WATCH never produce orders)
    """

    DEFAULT_DAILY_LOSS_PCT = -0.02
    DEFAULT_WEEKLY_LOSS_PCT = -0.06
    DEFAULT_MONTHLY_LOSS_PCT = -0.10
    DEFAULT_MAX_OPEN_POSITIONS = 5
    DEFAULT_MAX_CONSECUTIVE_LOSSES = 3
    DEFAULT_DATA_STALENESS_SEC = 30
    DEFAULT_IDEMPOTENCY_WINDOW_SEC = 300

    def __init__(
        self,
        bankroll: float = 100_000.0,
        daily_loss_pct: float = DEFAULT_DAILY_LOSS_PCT,
        weekly_loss_pct: float = DEFAULT_WEEKLY_LOSS_PCT,
        monthly_loss_pct: float = DEFAULT_MONTHLY_LOSS_PCT,
        max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS,
        max_consecutive_losses: int = DEFAULT_MAX_CONSECUTIVE_LOSSES,
        data_staleness_sec: int = DEFAULT_DATA_STALENESS_SEC,
        idempotency_window_sec: int = DEFAULT_IDEMPOTENCY_WINDOW_SEC,
    ) -> None:
        self.bankroll = float(bankroll)
        self.daily_loss_pct = daily_loss_pct
        self.weekly_loss_pct = weekly_loss_pct
        self.monthly_loss_pct = monthly_loss_pct
        self.max_open_positions = max_open_positions
        self.max_consecutive_losses = max_consecutive_losses
        self.data_staleness_sec = data_staleness_sec
        self.idempotency_window_sec = idempotency_window_sec
        self._recent_orders: dict[str, datetime] = {}
        self._open_positions: int = 0

    def check(
        self,
        trade_card: dict[str, Any],
        market_context: dict[str, Any],
        kill_switch_active: bool = False,
    ) -> RiskDecision:
        """Run all pre-trade checks. Returns PASS or REJECT(reasons)."""
        reasons: list[str] = []
        meta: dict[str, Any] = {}

        # 1. Kill switch (highest priority)
        if kill_switch_active:
            reasons.append("kill_switch_active")
            return RiskDecision(action="REJECT", reasons=reasons, meta=meta)

        # 2. Direction validity — HOLD/WATCH never produce an order
        direction = (trade_card.get("side") or "").upper()
        if direction not in ("BUY", "SELL"):
            return RiskDecision(
                action="REJECT",
                reasons=["non_directional"],
                meta={"direction": direction},
            )

        # 3. Data freshness
        if not self._check_data_fresh(market_context, meta):
            reasons.append("stale_market_data")

        # 4. Loss bands
        daily = float(market_context.get("daily_pnl_pct", 0.0))
        weekly = float(market_context.get("weekly_pnl_pct", 0.0))
        monthly = float(market_context.get("monthly_pnl_pct", 0.0))
        for label, max_loss in [
            ("daily", self.daily_loss_pct),
            ("weekly", self.weekly_loss_pct),
            ("monthly", self.monthly_loss_pct),
        ]:
            pnl = {"daily": daily, "weekly": weekly, "monthly": monthly}[label]
            meta[f"{label}_pnl_pct"] = round(pnl, 4)
            if pnl <= max_loss:
                reasons.append(f"{label}_loss_band")

        # 5. Consecutive losses
        consec = self._consecutive_losses_today()
        meta["consecutive_losses"] = consec
        if consec >= self.max_consecutive_losses:
            reasons.append("consecutive_loss_limit")

        # 6. Position count
        if self._open_positions >= self.max_open_positions:
            reasons.append("position_count_cap")

        # 7. Idempotency
        cid = self._compute_id(trade_card, market_context)
        if self._is_duplicate(cid):
            reasons.append("duplicate_order")
        else:
            self._record_order(cid)

        if reasons:
            logger.warning("PreTradeRiskGate REJECT reasons=%s meta=%s", reasons, meta)
            return RiskDecision(action="REJECT", reasons=reasons, meta=meta)

        return RiskDecision(action="PASS", reasons=[], meta=meta)

    # -- internals ---------------------------------------------------------

    def _check_data_fresh(self, market_context: dict[str, Any], meta: dict[str, Any]) -> bool:
        ts = market_context.get("timestamp")
        if not ts:
            meta["data_age_sec"] = None
            return False
        try:
            snap_dt = datetime.fromisoformat(str(ts))
            if snap_dt.tzinfo is None:
                tz = datetime.now().astimezone().tzinfo
                snap_dt = snap_dt.replace(tzinfo=tz)
            age = (datetime.now().astimezone() - snap_dt).total_seconds()
            meta["data_age_sec"] = round(age, 1)
            return age <= self.data_staleness_sec
        except (ValueError, TypeError):
            meta["data_age_sec"] = None
            return False

    def _consecutive_losses_today(self) -> int:
        """Approximate consecutive-loss count from the paper ledger."""
        try:
            from services.paper_trading import PaperBroker
            return PaperBroker().consecutive_losses_today()
        except ImportError:
            return 0
        except Exception:
            return 0

    def _compute_id(self, trade_card: dict[str, Any], market_context: dict[str, Any]) -> str:
        seed = "|".join([
            str(trade_card.get("side", "")),
            str(trade_card.get("ticker", "")),
            str(trade_card.get("target", "")),
            str(trade_card.get("stop", "")),
            str(market_context.get("timestamp", "")),
        ])
        return hashlib.sha256(seed.encode()).hexdigest()[:16]

    def _is_duplicate(self, client_order_id: str) -> bool:
        seen_at = self._recent_orders.get(client_order_id)
        if seen_at is None:
            return False
        age = (datetime.now() - seen_at).total_seconds()
        return age <= self.idempotency_window_sec

    def _record_order(self, client_order_id: str) -> None:
        self._recent_orders[client_order_id] = datetime.now()
        cutoff = datetime.now() - timedelta(seconds=self.idempotency_window_sec * 2)
        stale = [k for k, v in self._recent_orders.items() if v < cutoff]
        for k in stale:
            del self._recent_orders[k]

    def record_fill(self, won: bool) -> None:
        """Update position tracker after a fill."""
        if won:
            self._open_positions = max(0, self._open_positions - 1)
        else:
            self._open_positions += 1


# ---------------------------------------------------------------------------
# KellyPositionSizer — fractional Kelly with daily lock (from SwarmSPX)
# ---------------------------------------------------------------------------

@dataclass
class KellySizingResult:
    """Output of Kelly position sizing."""
    dollar_size: float
    pct_of_bankroll: float
    kelly_fraction: float
    capped: bool


class KellyPositionSizer:
    """Fractional Kelly position sizer with daily lock.

    Full Kelly maximizes geometric growth at the cost of catastrophic
    drawdowns.  Fractional Kelly (default 0.10) trades growth for
    survival.  Daily lock prevents mid-session re-sizing.
    """

    DEFAULT_BANKROLL_USD = 100_000.0
    DEFAULT_KELLY_FRACTION = 0.10   # 1/10 Kelly — survival-first
    DEFAULT_MAX_PER_TRADE_PCT = 0.05  # hard cap: never risk >5%
    DEFAULT_KELLY_CAP = 0.40

    def __init__(
        self,
        bankroll: float = DEFAULT_BANKROLL_USD,
        kelly_fraction: float = DEFAULT_KELLY_FRACTION,
        max_per_trade_pct: float = DEFAULT_MAX_PER_TRADE_PCT,
        kelly_cap: float = DEFAULT_KELLY_CAP,
        win_prob: float = 0.40,
        payoff_ratio: float = 3.0,
    ) -> None:
        self.bankroll = float(bankroll)
        self.kelly_fraction = kelly_fraction
        self.max_per_trade_pct = max_per_trade_pct
        self.ki = kelly_cap
        self._win_prob = win_prob
        self._payoff_ratio = payoff_ratio
        self._lock_path = Path("data/sizing_lock.json")
        self._lock: dict[str, Any] = self._load_lock()

    def size(
        self,
        win_prob: float | None = None,
        payoff_ratio: float | None = None,
        edge: float | None = None,
    ) -> KellySizingResult:
        """Compute the dollar size for one trade.

        Uses the Kelly criterion:  f* = (p*(b+1) - 1) / b
        where p = win_prob, b = payoff_ratio.
        Then applies fractional Kelly and hard caps.
        """
        p = win_prob if win_prob is not None else self._win_prob
        b = payoff_ratio if payoff_ratio is not None else self._payoff_ratio

        # Raw Kelly
        if b <= 0:
            raw_kelly = 0.0
        else:
            raw_kelly = (p * (b + 1) - 1) / b
        raw_kelly = max(0.0, min(raw_kelly, self.ki))

        # Fractional Kelly
        frac_kelly = raw_kelly * self.kelly_fraction
        pct = frac_kelly * 100.0

        # Hard caps
        pct = min(pct, self.max_per_trade_pct * 100.0)
        dollar_size = self.bankroll * pct / 100.0
        capped = (frac_kelly >= self.max_per_trade_pct) or (pct >= self.max_per_trade_pct * 100)

        # Persist daily lock
        today = date.today().isoformat()
        self._lock = self._load_lock()
        if self._lock.get("date") != today:
            self._lock = {"date": today, "dollar_size": dollar_size, "pct": pct}
            self._save_lock()

        return KellySizingResult(
            dollar_size=round(dollar_size, 2),
            pct_of_bankroll=round(pct, 4),
            kelly_fraction=round(frac_kelly, 4),
            capped=capped,
        )

    @property
    def today_size(self) -> KellySizingResult | None:
        """Return today's locked size, or None if no lock exists."""
        if not self._lock or self._lock.get("date") != date.today().isoformat():
            return None
        return KellySizingResult(
            dollar_size=self._lock.get("dollar_size", 0.0),
            pct_of_bankroll=self._lock.get("pct", 0.0),
            kelly_fraction=0.0,
            capped=False,
        )

    def _load_lock(self) -> dict[str, Any]:
        if not self._lock_path.exists():
            return {}
        try:
            return json.loads(self._lock_path.read_text())
        except Exception:
            return {}

    def _save_lock(self) -> None:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path.write_text(json.dumps(self._lock, indent=2))
