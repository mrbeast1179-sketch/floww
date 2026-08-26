#!/usr/bin/env python3
"""
backend/tests/services/test_auto_trade_risk.py — Kill-switch wiring tests.

Verifies the GSD risk wiring: the previously-unwired services.risk
KillSwitch now gates the Flowseeker auto-trade pipeline via
services.auto_trade_risk.
"""

from __future__ import annotations

from datetime import date

import pytest

from services import auto_trade_risk


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    """Isolate the singleton per test."""
    monkeypatch.setattr(auto_trade_risk, "_ks", None)
    monkeypatch.setattr(auto_trade_risk, "_ks_date", None)
    yield


class TestKillSwitchWiring:
    def test_allows_fresh_day(self):
        allowed, reason = auto_trade_risk.ensure_trading_allowed(100_000.0)
        assert allowed is True
        assert reason == ""

    def test_blocks_after_daily_loss_tripped(self):
        # -2% daily loss threshold: 100k -> 97.9k trips it
        auto_trade_risk.record_fill(100_000.0)
        tripped = auto_trade_risk.record_fill(97_900.0)
        assert tripped is True
        allowed, reason = auto_trade_risk.ensure_trading_allowed(97_900.0)
        assert allowed is False
        assert "Kill switch" in reason or "kill switch" in reason.lower()

    def test_blocks_on_drawdown_from_peak(self):
        # Establish peak at 110k, then fall -5%+ to 104k
        auto_trade_risk.record_fill(100_000.0)
        auto_trade_risk.record_fill(110_000.0)  # peak
        tripped = auto_trade_risk.record_fill(104_000.0)  # -5.45% from peak
        assert tripped is True

    def test_no_trip_within_thresholds(self):
        auto_trade_risk.record_fill(100_000.0)
        tripped = auto_trade_risk.record_fill(99_500.0)  # -0.5% day, fine
        assert tripped is False
        allowed, _ = auto_trade_risk.ensure_trading_allowed(99_500.0)
        assert allowed is True

    def test_day_rollover_resets(self, monkeypatch):
        auto_trade_risk.record_fill(100_000.0)
        auto_trade_risk.record_fill(97_000.0)  # trip
        allowed, _ = auto_trade_risk.ensure_trading_allowed(97_000.0)
        assert allowed is False
        # Simulate next calendar day
        from datetime import timedelta
        monkeypatch.setattr(auto_trade_risk, "_ks_date", date.today() - timedelta(days=1))
        # get_kill_switch rolls over and start_day resets the switch
        ks = auto_trade_risk.get_kill_switch(equity=97_000.0)
        allowed, _ = ks.can_trade()
        assert allowed is True

    def test_status_shape(self):
        s = auto_trade_risk.status(equity=100_000.0)
        assert {"tripped", "daily_pnl_pct", "peak_equity"} <= set(s)

    def test_manual_reset(self):
        auto_trade_risk.record_fill(100_000.0)
        auto_trade_risk.record_fill(90_000.0)  # deep loss — trips
        out = auto_trade_risk.reset()
        assert out["tripped"] is False
