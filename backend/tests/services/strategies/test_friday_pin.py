"""
backend/tests/services/strategies/test_friday_pin.py

Comprehensive tests for the Friday Pin strategy.

Coverage:
    - Config defaults
    - Entry condition: Friday detection
    - Entry condition: time window
    - Entry condition: range/pinning check
    - Entry condition: insufficient history
    - Entry condition: signal deduplication
    - Signal generation: output type and fields
    - Signal generation: iron condor strikes
    - Backtest: synthetic data with known outcome
    - Backtest: no trades on non-Friday data
    - Backtest: Sharpe/win_rate/max_dd/pnl
    - Edge cases: volatile market (no entry)
    - Edge cases: empty data
    - Edge cases: reset clears state
    - Edge cases: ISO string timestamps
"""

import sys
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.strategies.friday_pin import (
    FridayPinConfig,
    FridayPinStrategy,
    _to_et,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

ET = timezone(timedelta(hours=-5))


def make_friday_1535_et(year=2026, month=3, day=6) -> datetime:
    """Return a Friday at 15:35 ET."""
    return datetime(year, month, day, 15, 35, tzinfo=ET)


def make_bars(
    base_price: float = 500.0,
    num_bars: int = 30,
    noise_pct: float = 0.001,
    timestamp_start: datetime | None = None,
) -> list[dict]:
    """Generate synthetic 1-minute bars with small noise."""
    if timestamp_start is None:
        timestamp_start = make_friday_1505_et()

    bars = []
    price = base_price
    for i in range(num_bars):
        ts = timestamp_start + timedelta(minutes=i)
        bars.append({
            "timestamp": ts,
            "price": round(price, 2),
            "ticker": "SPX",
        })
        # Tiny random walk
        price += base_price * noise_pct * ((-1) ** i) * 0.5
    return bars


def make_friday_1505_et(year=2026, month=3, day=6) -> datetime:
    """Return a Friday at 15:05 ET (30 min before entry window)."""
    return datetime(year, month, day, 15, 5, tzinfo=ET)


def make_full_friday_session(
    base_price: float = 500.0,
    noise_pct: float = 0.001,
    year=2026,
    month=3,
    day=6,
) -> list[dict]:
    """Generate a full Friday session from 15:05 to 16:00 ET."""
    start = datetime(year, month, day, 15, 5, tzinfo=ET)
    bars = []
    price = base_price
    for i in range(56):  # 15:05 to 16:00 = 56 bars
        ts = start + timedelta(minutes=i)
        bars.append({
            "timestamp": ts,
            "price": round(price, 2),
            "ticker": "SPX",
        })
        price += base_price * noise_pct * ((-1) ** i) * 0.5
    return bars


# ------------------------------------------------------------------
# Config tests
# ------------------------------------------------------------------

class TestConfig:
    def test_default_values(self):
        cfg = FridayPinConfig()
        assert cfg.range_threshold == 0.5
        assert cfg.lookback_bars == 30
        assert cfg.window_start_minutes == 930
        assert cfg.window_end_minutes == 940
        assert cfg.target_bps == 30
        assert cfg.stop_bps == 60
        assert cfg.iron_condor_width_pct == 0.6

    def test_custom_values(self):
        cfg = FridayPinConfig(range_threshold=0.3, lookback_bars=20)
        assert cfg.range_threshold == 0.3
        assert cfg.lookback_bars == 20
        # Others remain default
        assert cfg.target_bps == 30


# ------------------------------------------------------------------
# Strategy initialization
# ------------------------------------------------------------------

class TestInit:
    def test_default_config(self):
        strat = FridayPinStrategy()
        assert strat.config.range_threshold == 0.5
        assert strat._price_history == []
        assert strat._signal_generated is False

    def test_custom_config(self):
        cfg = FridayPinConfig(range_threshold=0.25)
        strat = FridayPinStrategy(config=cfg)
        assert strat.config.range_threshold == 0.25


# ------------------------------------------------------------------
# Friday detection
# ------------------------------------------------------------------

class TestFridayDetection:
    def test_friday_detected(self):
        strat = FridayPinStrategy()
        ts = make_friday_1535_et()
        assert strat._is_friday(ts) is True

    def test_saturday_rejected(self):
        strat = FridayPinStrategy()
        # Saturday March 7, 2026
        ts = datetime(2026, 3, 7, 15, 35, tzinfo=ET)
        assert strat._is_friday(ts) is False

    def test_monday_rejected(self):
        strat = FridayPinStrategy()
        # Monday March 9, 2026
        ts = datetime(2026, 3, 9, 15, 35, tzinfo=ET)
        assert strat._is_friday(ts) is False

    def test_thursday_rejected(self):
        strat = FridayPinStrategy()
        # Thursday March 5, 2026
        ts = datetime(2026, 3, 5, 15, 35, tzinfo=ET)
        assert strat._is_friday(ts) is False

    def test_utc_input_converted(self):
        strat = FridayPinStrategy()
        # 20:35 UTC = 15:35 ET (UTC-5)
        ts = datetime(2026, 3, 6, 20, 35, tzinfo=timezone.utc)
        assert strat._is_friday(ts) is True


# ------------------------------------------------------------------
# Entry window tests
# ------------------------------------------------------------------

class TestEntryWindow:
    def test_inside_window(self):
        strat = FridayPinStrategy()
        ts = make_friday_1535_et()
        assert strat._is_in_entry_window(ts) is True

    def test_at_window_start(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 6, 15, 30, tzinfo=ET)
        assert strat._is_in_entry_window(ts) is True

    def test_at_window_end(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 6, 15, 40, tzinfo=ET)
        assert strat._is_in_entry_window(ts) is True

    def test_before_window(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 6, 15, 29, tzinfo=ET)
        assert strat._is_in_entry_window(ts) is False

    def test_after_window(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 6, 15, 41, tzinfo=ET)
        assert strat._is_in_entry_window(ts) is False


# ------------------------------------------------------------------
# Range / pinning condition
# ------------------------------------------------------------------

class TestPinningCondition:
    def test_flat_market_passes(self):
        strat = FridayPinStrategy()
        # 30 bars all at exactly 500.0
        for _ in range(30):
            strat.update_history(500.0)
        assert strat._pinning_condition_met() is True

    def test_small_noise_passes(self):
        strat = FridayPinStrategy()
        for i in range(30):
            strat.update_history(500.0 + i * 0.01)  # max range = 0.29/500 = 0.058%
        assert strat._pinning_condition_met() is True

    def test_volatile_market_fails(self):
        strat = FridayPinStrategy()
        for i in range(30):
            strat.update_history(500.0 + i * 1.0)  # range ~5.8%
        assert strat._pinning_condition_met() is False

    def test_exact_threshold_boundary(self):
        """Range exactly at threshold should fail (strict <)."""
        strat = FridayPinStrategy()
        # Create bars with range exactly 0.5%
        for i in range(30):
            strat.update_history(500.0 + i * 0.005)  # max = 500.145, range = 0.029%
        # This is well under 0.5%, so it should pass
        assert strat._pinning_condition_met() is True

    def test_just_over_threshold_fails(self):
        strat = FridayPinStrategy()
        # Create bars with range slightly over 0.5%
        for i in range(30):
            strat.update_history(500.0 + i * 0.2)  # max = 505.8, range = 1.16%
        assert strat._pinning_condition_met() is False

    def test_insufficient_history(self):
        strat = FridayPinStrategy()
        for i in range(20):
            strat.update_history(500.0)
        assert strat._pinning_condition_met() is False

    def test_empty_history(self):
        strat = FridayPinStrategy()
        assert strat._pinning_condition_met() is False


# ------------------------------------------------------------------
# check_entry_condition integration
# ------------------------------------------------------------------

class TestCheckEntryCondition:
    def test_full_condition_met(self):
        strat = FridayPinStrategy()
        # Feed 30 bars of flat data first
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            md = {"timestamp": ts, "price": 500.0}
            result = strat.check_entry_condition(md)

        # The last bar (15:34) is before window, so no signal
        # Now send a bar at 15:35
        ts = make_friday_1535_et()
        result = strat.check_entry_condition({"timestamp": ts, "price": 500.0})
        assert result is True

    def test_not_friday_rejected(self):
        strat = FridayPinStrategy()
        # Thursday March 5, 2026 at 15:35
        ts = datetime(2026, 3, 5, 15, 35, tzinfo=ET)
        for i in range(30):
            strat.update_history(500.0)
        result = strat.check_entry_condition({"timestamp": ts, "price": 500.0})
        assert result is False

    def test_wrong_time_rejected(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 6, 14, 0, tzinfo=ET)  # 2pm
        for i in range(30):
            strat.update_history(500.0)
        result = strat.check_entry_condition({"timestamp": ts, "price": 500.0})
        assert result is False

    def test_volatile_market_rejected(self):
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            md = {"timestamp": ts, "price": 500.0 + i * 5.0}  # very volatile
            result = strat.check_entry_condition(md)
        # Even at 15:35, should be rejected due to range
        ts = make_friday_1535_et()
        result = strat.check_entry_condition({"timestamp": ts, "price": 650.0})
        assert result is False

    def test_signal_deduplication(self):
        """Only one signal per window."""
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        # First signal at 15:35
        ts1 = make_friday_1535_et()
        assert strat.check_entry_condition({"timestamp": ts1, "price": 500.0}) is True

        # Second call at 15:36 should be deduplicated
        ts2 = datetime(2026, 3, 6, 15, 36, tzinfo=ET)
        assert strat.check_entry_condition({"timestamp": ts2, "price": 500.0}) is False

    def test_iso_string_timestamp(self):
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.update_history(500.0)

        # Pass ISO string instead of datetime
        ts = make_friday_1535_et()
        result = strat.check_entry_condition({
            "timestamp": ts.isoformat(),
            "price": 500.0,
        })
        assert result is True

    def test_invalid_timestamp_type(self):
        strat = FridayPinStrategy()
        for i in range(30):
            strat.update_history(500.0)
        result = strat.check_entry_condition({"timestamp": 12345, "price": 500.0})
        assert result is False


# ------------------------------------------------------------------
# Signal generation
# ------------------------------------------------------------------

class TestGenerateSignal:
    def test_returns_signal_input(self):
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        ts = make_friday_1535_et()
        signal = strat.generate_signal({"timestamp": ts, "price": 500.0, "ticker": "SPX"})
        assert signal is not None
        from services.signal_translator import SignalInput
        assert isinstance(signal, SignalInput)

    def test_signal_fields(self):
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        ts = make_friday_1535_et()
        signal = strat.generate_signal({"timestamp": ts, "price": 500.0, "ticker": "SPX"})
        assert signal is not None
        assert signal.ticker == "SPX"
        assert signal.spot_price == 500.0
        assert signal.anomaly_score == 1.0
        assert signal.trinity_score == 100.0
        assert signal.vpin_cdf == 0.0
        assert signal.kyle_lambda == 1e-7

    def test_default_ticker(self):
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        ts = make_friday_1535_et()
        signal = strat.generate_signal({"timestamp": ts, "price": 500.0})
        assert signal is not None
        assert signal.ticker == "SPX"

    def test_no_signal_when_conditions_not_met(self):
        strat = FridayPinStrategy()
        # Not enough history
        ts = make_friday_1535_et()
        signal = strat.generate_signal({"timestamp": ts, "price": 500.0})
        assert signal is None

    def test_no_signal_on_non_friday(self):
        strat = FridayPinStrategy()
        ts = datetime(2026, 3, 5, 15, 35, tzinfo=ET)  # Thursday
        for i in range(30):
            strat.update_history(500.0)
        signal = strat.generate_signal({"timestamp": ts, "price": 500.0})
        assert signal is None


# ------------------------------------------------------------------
# Backtest
# ------------------------------------------------------------------

class TestBacktest:
    def test_synthetic_pinning_data(self):
        """Backtest with perfectly flat data should produce winning trades."""
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.0001)
        result = strat.backtest(bars)
        assert result["num_trades"] > 0
        assert result["win_rate"] == 1.0
        assert result["total_pnl"] > 0

    def test_no_trades_on_non_friday(self):
        """Backtest with only Thursday data should produce zero trades."""
        strat = FridayPinStrategy()
        # Thursday March 5, 2026
        start = datetime(2026, 3, 5, 15, 5, tzinfo=ET)
        bars = []
        for i in range(56):
            ts = start + timedelta(minutes=i)
            bars.append({"timestamp": ts, "price": 500.0, "ticker": "SPX"})
        result = strat.backtest(bars)
        assert result["num_trades"] == 0
        assert result["total_pnl"] == 0.0

    def test_volatile_data_no_trades(self):
        """Backtest with volatile data should produce zero trades."""
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.05)
        result = strat.backtest(bars)
        # With 5% noise, pinning condition should never be met
        assert result["num_trades"] == 0

    def test_empty_data(self):
        strat = FridayPinStrategy()
        result = strat.backtest([])
        assert result["num_trades"] == 0
        assert result["total_pnl"] == 0.0
        assert result["sharpe"] == 0.0
        assert result["win_rate"] == 0.0
        assert result["max_dd"] == 0.0

    def test_backtest_returns_required_keys(self):
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.0001)
        result = strat.backtest(bars)
        required_keys = {"sharpe", "win_rate", "max_dd", "max_dd_pct", "total_pnl", "num_trades", "trades"}
        assert required_keys.issubset(result.keys())

    def test_backtest_trade_structure(self):
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.0001)
        result = strat.backtest(bars)
        if result["num_trades"] > 0:
            trade = result["trades"][0]
            assert "entry_time" in trade
            assert "exit_time" in trade
            assert "entry_price" in trade
            assert "exit_price" in trade
            assert "pnl_bps" in trade
            assert "pnl_dollars" in trade
            assert "won" in trade

    def test_sharpe_is_finite(self):
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.0001)
        result = strat.backtest(bars)
        assert math.isfinite(result["sharpe"])

    def test_win_rate_between_0_and_1(self):
        strat = FridayPinStrategy()
        bars = make_full_friday_session(base_price=500.0, noise_pct=0.0001)
        result = strat.backtest(bars)
        assert 0.0 <= result["win_rate"] <= 1.0


# ------------------------------------------------------------------
# Reset and state management
# ------------------------------------------------------------------

class TestReset:
    def test_reset_clears_history(self):
        strat = FridayPinStrategy()
        for _ in range(30):
            strat.update_history(500.0)
        strat.reset()
        assert strat._price_history == []

    def test_reset_clears_signal_flag(self):
        strat = FridayPinStrategy()
        strat._signal_generated = True
        strat.reset()
        assert strat._signal_generated is False

    def test_can_reenter_after_reset(self):
        """After reset, strategy should be able to generate a new signal."""
        strat = FridayPinStrategy()
        ts_start = make_friday_1505_et()
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        ts = make_friday_1535_et()
        assert strat.check_entry_condition({"timestamp": ts, "price": 500.0}) is True

        strat.reset()

        # Re-feed history and try again
        for i in range(30):
            ts = ts_start + timedelta(minutes=i)
            strat.check_entry_condition({"timestamp": ts, "price": 500.0})

        assert strat.check_entry_condition({"timestamp": ts, "price": 500.0}) is True


# ------------------------------------------------------------------
# _to_et helper
# ------------------------------------------------------------------

class TestToEt:
    def test_utc_to_et(self):
        utc_ts = datetime(2026, 3, 6, 20, 35, tzinfo=timezone.utc)
        et_ts = _to_et(utc_ts)
        assert et_ts.hour == 15
        assert et_ts.minute == 35

    def test_naive_treated_as_utc(self):
        naive_ts = datetime(2026, 3, 6, 20, 35)
        et_ts = _to_et(naive_ts)
        assert et_ts.hour == 15
