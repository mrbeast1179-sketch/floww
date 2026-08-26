"""
backend/services/auto_trade_risk.py — Risk wiring for the Flowseeker
auto-trade pipeline.

Bridges the (previously unwired) services.risk stack — KillSwitch — into
the signal-to-trade path:

  - get_kill_switch(): process-singleton KillSwitch, auto start_day() on
    first use of each calendar day (auto_reset_next_day semantics).
  - ensure_trading_allowed(equity): gate to call before submitting orders.
    Trips on -2% daily loss or -5% drawdown from intraday peak
    (KillSwitchConfig defaults).
  - record_fill(equity): feed post-trade equity back into the switch so a
    losing streak trips it mid-session, not just next day.

Pure sync logic; the route layer owns persistence and the paper engine.
"""

from __future__ import annotations

import logging
from datetime import date

from services.risk.killswitch import KillSwitch

logger = logging.getLogger(__name__)

_ks: KillSwitch | None = None
_ks_date: date | None = None


def get_kill_switch(*, equity: float = 0.0) -> KillSwitch:
    """Return the singleton kill switch, rolled over to a new day if needed.

    equity: current account equity; used to seed start_day() on first call
    of the day (or on first-ever call when nonzero).
    """
    global _ks, _ks_date
    today = date.today()
    if _ks is None:
        _ks = KillSwitch()
        _ks_date = None
    if _ks_date != today:
        _ks.start_day(equity if equity > 0 else _ks._daily_starting_equity)
        _ks_date = today
    return _ks


def ensure_trading_allowed(equity: float) -> tuple[bool, str]:
    """Gate every auto-trade batch. Returns (allowed, reason)."""
    ks = get_kill_switch(equity=equity)
    allowed, reason = ks.can_trade()
    if not allowed:
        logger.warning("auto-trade blocked by kill switch: %s", reason)
    return allowed, reason


def record_fill(equity: float) -> bool:
    """Report equity after an accepted fill. Returns True if this tripped
    the kill switch (caller should stop the remaining batch)."""
    ks = get_kill_switch(equity=equity)
    tripped = ks.update_pnl(equity)
    if tripped:
        logger.critical("auto-trade kill switch TRIPPED at equity $%.2f", equity)
    return tripped


def reset() -> dict:
    """Manual reset (human review required per risk policy)."""
    ks = get_kill_switch()
    ks.reset()
    return ks.get_status()


def status(equity: float = 0.0) -> dict:
    """Current kill-switch state for dashboards/status endpoints."""
    return get_kill_switch(equity=equity).get_status()
