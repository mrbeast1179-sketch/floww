"""
backend/tests/services/test_credit_monitor.py

Unit tests for the API Credit & Rate Limit Monitor.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class MagicMonitor:
    def __init__(self):
        self.call_count = 0
        self.call_args = None
    def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.call_args = (args, kwargs)


@pytest.fixture
def monitor():
    from services.credit_monitor import CreditMonitor
    return CreditMonitor(budget=1000, warning_pct=0.80, critical_pct=0.95)


@pytest.fixture
def low_budget_monitor():
    from services.credit_monitor import CreditMonitor
    return CreditMonitor(budget=100, warning_pct=0.80, critical_pct=0.95)


class TestCreditState:
    def test_initial_state(self):
        from services.credit_monitor import CreditState
        state = CreditState(budget=1000)
        assert state.burn_pct == 0.0
        assert state.remaining == 1000

    def test_burn_calculation(self):
        from services.credit_monitor import CreditState
        state = CreditState(budget=1000, consumed=800)
        assert state.burn_pct == 0.8
        assert state.remaining == 200

    def test_burn_over_100(self):
        from services.credit_monitor import CreditState
        state = CreditState(budget=1000, consumed=1500)
        assert state.burn_pct == 1.5
        assert state.remaining == 0

    def test_zero_budget(self):
        from services.credit_monitor import CreditMonitor
        monitor = CreditMonitor(budget=0)
        assert monitor.state.burn_pct == 0.0


class TestCreditAlerts:
    def test_burn_80_warning(self, low_budget_monitor):
        low_budget_monitor.record_credits("marketdata", 80)
        alerts = low_budget_monitor.check_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "MEDIUM"
        assert alerts[0]["alert_type"] == "credit_burn_80"
        assert alerts[0]["burn_pct"] == 80.0

    def test_burn_95_critical(self, low_budget_monitor):
        low_budget_monitor.record_credits("marketdata", 95)
        alerts = low_budget_monitor.check_alerts()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "CRITICAL"
        assert alerts[0]["alert_type"] == "credit_burn_95"

    def test_burn_jumps_straight_to_critical(self, low_budget_monitor):
        low_budget_monitor.record_credits("marketdata", 100)
        alerts = low_budget_monitor.check_alerts()
        critical = [a for a in alerts if a["alert_type"] == "credit_burn_95"]
        warning = [a for a in alerts if a["alert_type"] == "credit_burn_80"]
        assert len(critical) == 1
        assert len(warning) == 0

    def test_no_alert_below_threshold(self, low_budget_monitor):
        low_budget_monitor.record_credits("marketdata", 50)
        alerts = low_budget_monitor.check_alerts()
        assert len(alerts) == 0

    def test_alert_clears_on_recovery(self, low_budget_monitor):
        low_budget_monitor.record_credits("marketdata", 85)
        low_budget_monitor.check_alerts()
        low_budget_monitor.state.consumed = 50
        alerts = low_budget_monitor.check_alerts()
        assert len(alerts) == 0

    def test_alert_callback_fired(self):
        from services.credit_monitor import CreditMonitor
        callback = MagicMonitor()
        mon = CreditMonitor(budget=100, on_alert=callback)
        mon.record_credits("test", 85)
        mon.check_alerts()
        assert callback.call_count >= 1
        args = callback.call_args[0]
        assert args[1] == "credit_burn_80"


class TestRateLimitAlerts:
    def test_429_warning_threshold(self, monitor):
        for _ in range(3):
            monitor.record_call("yfinance", is_429=True)
        alerts = monitor.check_alerts()
        rl_alerts = [a for a in alerts if "rate_limit_warning" in a.get("alert_type", "")]
        assert len(rl_alerts) == 1
        assert rl_alerts[0]["provider"] == "yfinance"
        assert rl_alerts[0]["count_429"] == 3

    def test_429_critical_threshold(self, monitor):
        for _ in range(10):
            monitor.record_call("yfinance", is_429=True)
        alerts = monitor.check_alerts()
        crit = [a for a in alerts if a.get("alert_type") == "rate_limit_critical"]
        assert len(crit) == 1
        assert crit[0]["provider"] == "yfinance"

    def test_429_no_false_positive(self, monitor):
        monitor.record_call("yfinance", is_429=False)
        alerts = monitor.check_alerts()
        rl_alerts = [a for a in alerts if "rate_limit" in a.get("alert_type", "")]
        assert len(rl_alerts) == 0

    def test_429_rolling_window_prune(self, monitor):
        old_time = time.time() - 600
        monitor.state.provider_429s["yfinance"] = [old_time] * 5
        alerts = monitor.check_alerts()
        rl_alerts = [a for a in alerts if "rate_limit" in a.get("alert_type", "")]
        assert len(rl_alerts) == 0

    def test_429_dedup(self, low_budget_monitor):
        for _ in range(3):
            low_budget_monitor.record_call("yfinance", is_429=True)
        alerts1 = low_budget_monitor.check_alerts()
        alerts2 = low_budget_monitor.check_alerts()
        types1 = {(a["provider"], a["alert_type"]) for a in alerts1}
        types2 = {(a["provider"], a["alert_type"]) for a in alerts2}
        assert len(types1) > 0
        assert len(types2) == 0


class TestStatusReport:
    def test_status_structure(self, monitor):
        monitor.record_credits("marketdata", 100)
        status = monitor.get_status()
        assert "budget" in status
        assert "consumed" in status
        assert "remaining" in status
        assert "burn_pct" in status
        assert "providers" in status
        assert "thresholds" in status
        assert "active_alerts" in status

    def test_status_provider_info(self, monitor):
        monitor.record_call("yfinance", is_429=False)
        monitor.record_call("yfinance", is_429=True)
        status = monitor.get_status()
        assert "yfinance" in status["providers"]

    def test_resolve_budget_from_env(self):
        from services.credit_monitor import _resolve_budget
        with patch.dict("os.environ", {"MARKETDATA_CREDIT_BUDGET": "5000"}):
            assert _resolve_budget() == 5000

    def test_resolve_budget_missing_env(self):
        from services.credit_monitor import _resolve_budget
        with patch.dict("os.environ", {}, clear=True):
            budget = _resolve_budget()
            assert budget == 0
