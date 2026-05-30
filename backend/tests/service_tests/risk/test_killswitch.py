"""
backend/tests/services/risk/test_killswitch.py — Tests for kill switch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from backend.services.risk.killswitch import KillSwitch, KillSwitchConfig


class TestKillSwitchInit:
    def test_default_config(self):
        ks = KillSwitch()
        assert not ks.is_tripped
        assert ks.trip_reason == ""

    def test_custom_config(self):
        ks = KillSwitch(config=KillSwitchConfig(daily_loss_pct_threshold=-0.05))
        assert not ks.is_tripped


class TestDailyLoss:
    def test_trips_on_daily_loss(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        assert ks.update_pnl(9700.0)  # -3%
        assert ks.is_tripped
        assert "Daily loss" in ks.trip_reason

    def test_no_trip_on_small_loss(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        assert not ks.update_pnl(9900.0)  # -1%
        assert not ks.is_tripped

    def test_no_trip_on_profit(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        assert not ks.update_pnl(10500.0)
        assert not ks.is_tripped


class TestMaxDrawdown:
    def test_trips_on_drawdown(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        ks.update_pnl(10500.0)  # new peak
        assert ks.update_pnl(9900.0)  # -5.7% from peak
        assert ks.is_tripped
        assert "drawdown" in ks.trip_reason.lower() or "Max drawdown" in ks.trip_reason


class TestCanTrade:
    def test_allowed_when_not_tripped(self):
        ks = KillSwitch()
        allowed, reason = ks.can_trade()
        assert allowed

    def test_blocked_when_tripped(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        ks.update_pnl(9700.0)
        allowed, reason = ks.can_trade()
        assert not allowed
        assert "Kill switch" in reason


class TestReset:
    def test_manual_reset(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        ks.update_pnl(9700.0)
        assert ks.is_tripped
        ks.reset()
        assert not ks.is_tripped
        allowed, _ = ks.can_trade()
        assert allowed


class TestStartDay:
    def test_resets_daily_tracking(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        ks.record_trade(100.0)
        ks.record_trade(-50.0)
        status = ks.get_status()
        assert status["trade_count_today"] == 2
        assert status["loss_count_today"] == 1


class TestGetStatus:
    def test_status_dict(self):
        ks = KillSwitch()
        ks.start_day(10000.0)
        ks.update_pnl(10200.0)
        status = ks.get_status()
        assert status["tripped"] is False
        assert status["current_equity"] == 10200.0
        assert status["daily_pnl_pct"] == 0.02


class TestRecordTrade:
    def test_trade_counting(self):
        ks = KillSwitch()
        ks.record_trade(100.0)
        ks.record_trade(-50.0)
        ks.record_trade(200.0)
        status = ks.get_status()
        assert status["trade_count_today"] == 3
        assert status["loss_count_today"] == 1
