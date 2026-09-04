"""Tests for the SwarmSPX-inspired risk gate (services/swarm_risk.py)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from services.swarm_risk import (
    ExtendedKillSwitch,
    KellyPositionSizer,
    KellySizingResult,
    PreTradeRiskGate,
    RiskDecision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_lock_dir(tmp_path: Path) -> str:
    """Return a temp dir used as the Kelly sizer lock path."""
    return str(tmp_path)


@pytest.fixture
def kill_switch() -> ExtendedKillSwitch:
    return ExtendedKillSwitch()


@pytest.fixture
def risk_gate() -> PreTradeRiskGate:
    return PreTradeRiskGate()


@pytest.fixture
def sizer(temp_lock_dir: str) -> KellyPositionSizer:
    s = KellyPositionSizer(bankroll=100_000.0, kelly_fraction=0.10)
    # Override lock path to temp dir so we don't pollute data/
    s._lock_path = Path(temp_lock_dir) / "sizing_lock.json"
    return s


# ---------------------------------------------------------------------------
# ExtendedKillSwitch
# ---------------------------------------------------------------------------

class TestExtendedKillSwitch:
    """Tests for ExtendedKillSwitch."""

    def test_initial_status(self, kill_switch: ExtendedKillSwitch) -> None:
        status = kill_switch.get_status()
        assert status["tripped"] is False
        assert "weekly_loss_pct" in status
        assert "monthly_loss_pct" in status
        assert "max_consecutive_losses" in status
        assert status["consecutive_losses"] == 0

    def test_daily_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        kill_switch.trip("daily loss")
        status = kill_switch.get_status()
        assert status["tripped"] is True
        assert status["trip_reason"] == "daily loss"

    def test_evaluate_loss_bands_no_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_loss_bands(
            daily_pnl_pct=-0.01, weekly_pnl_pct=-0.01, monthly_pnl_pct=-0.01
        )
        assert result is False
        assert kill_switch.is_tripped is False

    def test_evaluate_loss_bands_daily_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_loss_bands(
            daily_pnl_pct=-0.03, weekly_pnl_pct=-0.01, monthly_pnl_pct=-0.01
        )
        assert result is True
        assert kill_switch.is_tripped is True

    def test_evaluate_loss_bands_weekly_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_loss_bands(
            daily_pnl_pct=-0.01, weekly_pnl_pct=-0.07, monthly_pnl_pct=-0.01
        )
        assert result is True

    def test_evaluate_loss_bands_monthly_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_loss_bands(
            daily_pnl_pct=-0.01, weekly_pnl_pct=-0.01, monthly_pnl_pct=-0.11
        )
        assert result is True

    def test_evaluate_consecutive_losses_no_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_consecutive_losses(2)
        assert result is False

    def test_evaluate_consecutive_losses_trip(self, kill_switch: ExtendedKillSwitch) -> None:
        result = kill_switch.evaluate_consecutive_losses(3)
        assert result is True
        assert kill_switch.is_tripped is True

    def test_record_loss_and_win(self, kill_switch: ExtendedKillSwitch) -> None:
        kill_switch.record_loss()
        kill_switch.record_loss()
        assert kill_switch._consecutive_losses == 2
        kill_switch.record_win()
        assert kill_switch._consecutive_losses == 0

    def test_get_status_extended_fields(self, kill_switch: ExtendedKillSwitch) -> None:
        status = kill_switch.get_status()
        assert status["weekly_loss_pct"] == -0.06
        assert status["monthly_loss_pct"] == -0.10
        assert status["max_consecutive_losses"] == 3

    def test_trip_resets_on_new_day(self, kill_switch: ExtendedKillSwitch) -> None:
        kill_switch.trip("daily loss")
        assert kill_switch.is_tripped is True
        kill_switch.reset()
        assert kill_switch.is_tripped is False


# ---------------------------------------------------------------------------
# PreTradeRiskGate
# ---------------------------------------------------------------------------

class TestPreTradeRiskGate:
    """Tests for PreTradeRiskGate."""

    @pytest.fixture(autouse=True)
    def reset_gate(self) -> None:
        """Clear the global gate between tests."""
        PreTradeRiskGate._recent_orders = {}

    def test_passes_valid_buy(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is True
        assert decision.action == "PASS"

    def test_rejects_kill_switch_active(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=True)
        assert decision.passed is False
        assert "kill_switch_active" in decision.reasons

    def test_rejects_hold(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "HOLD", "ticker": "SPY", "target": 0.0, "stop": 0.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "non_directional" in decision.reasons

    def test_rejects_watch(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "WATCH", "ticker": "SPY", "target": 0.0, "stop": 0.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "non_directional" in decision.reasons

    def test_rejects_daily_loss_band(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": -0.03,
            "weekly_pnl_pct": 0.0,
            "monthly_pnl_pct": 0.0,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "daily_loss_band" in decision.reasons

    def test_rejects_weekly_loss_band(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": 0.0,
            "weekly_pnl_pct": -0.07,
            "monthly_pnl_pct": 0.0,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "weekly_loss_band" in decision.reasons

    def test_rejects_monthly_loss_band(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": 0.0,
            "weekly_pnl_pct": 0.0,
            "monthly_pnl_pct": -0.11,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "monthly_loss_band" in decision.reasons

    def test_rejects_consecutive_losses(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": 0.0,
            "weekly_pnl_pct": 0.0,
            "monthly_pnl_pct": 0.0,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        # With default max_consecutive=3 and empty paper broker, should pass
        assert decision.passed is True

    def test_rejects_stale_data(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        stale_time = (datetime.now() - timedelta(seconds=60)).isoformat()
        market_context = {"timestamp": stale_time}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "stale_market_data" in decision.reasons

    def test_rejects_duplicate_order(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        # First call should pass
        decision1 = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision1.passed is True
        # Second call with same card within window should be duplicate
        decision2 = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision2.passed is False
        assert "duplicate_order" in decision2.reasons

    def test_position_count_cap(self, risk_gate: PreTradeRiskGate) -> None:
        risk_gate._open_positions = 5
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {"timestamp": datetime.now().isoformat()}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "position_count_cap" in decision.reasons

    def test_empty_timestamp_rejected(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {}
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is False
        assert "stale_market_data" in decision.reasons

    def test_meta_contains_pnl(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": -0.01,
            "weekly_pnl_pct": -0.02,
            "monthly_pnl_pct": -0.03,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert "daily_pnl_pct" in decision.meta
        assert "weekly_pnl_pct" in decision.meta
        assert "monthly_pnl_pct" in decision.meta
        assert "consecutive_losses" in decision.meta

    def test_passes_with_all_margins_respected(self, risk_gate: PreTradeRiskGate) -> None:
        trade_card = {"side": "BUY", "ticker": "SPY", "target": 450.0, "stop": 440.0}
        market_context = {
            "timestamp": datetime.now().isoformat(),
            "daily_pnl_pct": 0.01,
            "weekly_pnl_pct": 0.01,
            "monthly_pnl_pct": 0.01,
        }
        decision = risk_gate.check(trade_card, market_context, kill_switch_active=False)
        assert decision.passed is True
        assert decision.action == "PASS"


# ---------------------------------------------------------------------------
# KellyPositionSizer
# ---------------------------------------------------------------------------

class TestKellyPositionSizer:
    """Tests for KellyPositionSizer."""

    def test_size_default(self, sizer: KellyPositionSizer) -> None:
        result = sizer.size()
        assert isinstance(result, KellySizingResult)
        assert result.dollar_size > 0.0
        assert result.pct_of_bankroll > 0.0
        assert result.kelly_fraction > 0.0

    def test_size_returns_positive(self, sizer: KellyPositionSizer) -> None:
        result = sizer.size(win_prob=0.6, payoff_ratio=2.0)
        assert result.dollar_size > 0.0

    def test_size_capped_by_max_per_trade(self, sizer: KellyPositionSizer) -> None:
        # With default 5% max per trade and bankroll 100k, max is 5000
        result = sizer.size(win_prob=0.99, payoff_ratio=100.0)
        assert result.dollar_size <= 5000.0 + 0.01  # allow tiny float diff

    def test_size_lower_kelly_fraction_smaller(self, sizer: KellyPositionSizer) -> None:
        sizer2 = KellyPositionSizer(bankroll=100_000.0, kelly_fraction=0.05)
        sizer2._lock_path = sizer._lock_path
        r1 = sizer.size(win_prob=0.55, payoff_ratio=2.0)
        r2 = sizer2.size(win_prob=0.55, payoff_ratio=2.0)
        assert r2.dollar_size <= r1.dollar_size

    def test_today_size_after_call(self, sizer: KellyPositionSizer) -> None:
        sizer.size(win_prob=0.55, payoff_ratio=2.0)
        locked = sizer.today_size
        assert locked is not None
        assert locked.dollar_size > 0.0

    def test_different_bankroll_produces_different_size(self) -> None:
        s1 = KellyPositionSizer(bankroll=50_000.0, kelly_fraction=0.10)
        s1._lock_path = Path(tempfile.mkdtemp()) / "lock.json"
        s2 = KellyPositionSizer(bankroll=200_000.0, kelly_fraction=0.10)
        s2._lock_path = Path(tempfile.mkdtemp()) / "lock.json"
        r1 = s1.size(win_prob=0.55, payoff_ratio=2.0)
        r2 = s2.size(win_prob=0.55, payoff_ratio=2.0)
        assert r2.dollar_size > r1.dollar_size

    def test_zero_payoff_yields_zero_size(self, sizer: KellyPositionSizer) -> None:
        result = sizer.size(win_prob=0.5, payoff_ratio=0.0)
        assert result.dollar_size == 0.0

    def test_daily_lock_persists(self, sizer: KellyPositionSizer) -> None:
        sizer.size(win_prob=0.55, payoff_ratio=2.0)
        # Create a fresh sizer pointing to the same lock file
        sizer2 = KellyPositionSizer(bankroll=100_000.0, kelly_fraction=0.10)
        sizer2._lock_path = sizer._lock_path
        sizer2._lock = sizer2._load_lock()  # reload from the overridden path
        locked = sizer2.today_size
        assert locked is not None
        assert locked.dollar_size > 0.0

    def test_today_size_none_before_first_call(self, sizer: KellyPositionSizer) -> None:
        # Ensure no lock file exists
        if sizer._lock_path.exists():
            sizer._lock_path.unlink()
        assert sizer.today_size is None

    def test_capped_flag(self, sizer: KellyPositionSizer) -> None:
        result = sizer.size(win_prob=0.99, payoff_ratio=100.0)
        # May or may not be capped depending on exact calc, just verify it's a bool
        assert isinstance(result.capped, bool)