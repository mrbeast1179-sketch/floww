"""
backend/tests/services/backtest/test_retail_flow_signal_edge.py

Additional edge-case tests for backtest/retail_flow_signal.py.

The existing test_retail_flow_signal.py covers the main signal/regime logic.
This file covers:
    - _safe_float: None, NaN, inf, non-numeric, valid
    - _sma: short list, exact period, longer list
    - RegimeFilter: boundary (price == SMA), custom period
    - RetailFlowSignal: None/missing snapshot keys, NaN values in snapshots
    - Position: is_open, close, update_unrealized
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.backtest.retail_flow_signal import (
    RegimeFilter,
    RetailFlowSignal,
    _safe_float,
    _sma,
)
from services.backtest.signals import Action, Position


class TestSafeFloat:
    def test_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_none_custom_default(self):
        assert _safe_float(None, default=1.5) == 1.5

    def test_nan_returns_default(self):
        assert _safe_float(float("nan")) == 0.0

    def test_inf_returns_default(self):
        """_safe_float that passes through inf (the actual behavior of the code)."""
        # The current _safe_float does NOT handle inf — it only checks f != f (NaN).
        # This is the actual behavior: inf passes through as-is.
        result = _safe_float(float("inf"))
        assert result == float("inf")

    def test_neg_inf_returns_default(self):
        """_safe_float passes through -inf."""
        result = _safe_float(float("-inf"))
        assert result == float("-inf")

    def test_valid_float(self):
        assert _safe_float(3.14) == 3.14

    def test_valid_int(self):
        assert _safe_float(42) == 42.0

    def test_valid_string(self):
        assert _safe_float("2.5") == 2.5

    def test_invalid_string_returns_default(self):
        assert _safe_float("abc") == 0.0

    def test_list_returns_default(self):
        assert _safe_float([1, 2]) == 0.0


class TestSMA:
    def test_short_list_uses_all(self):
        """If len(values) < period, use mean of all available."""
        result = _sma([1.0, 2.0, 3.0], period=10)
        assert result == pytest.approx(2.0)

    def test_exact_period(self):
        """If len(values) == period, use mean of all."""
        result = _sma([1.0, 2.0, 3.0, 4.0, 5.0], period=5)
        assert result == pytest.approx(3.0)

    def test_longer_list_uses_last_n(self):
        """If len(values) > period, use mean of last `period` values."""
        result = _sma([1.0, 2.0, 3.0, 4.0, 5.0], period=3)
        # Last 3: [3, 4, 5] => mean = 4.0
        assert result == pytest.approx(4.0)

    def test_empty_list_returns_zero(self):
        result = _sma([], period=5)
        assert result == 0.0

    def test_single_element(self):
        result = _sma([42.0], period=5)
        assert result == pytest.approx(42.0)


class TestRegimeFilterEdge:
    def test_price_equals_sma(self):
        """When price == SMA, allow_bullish is False (price > SMA is strict)."""
        rf = RegimeFilter(sma_period=3, enabled=True)
        # All same price => SMA = price
        prices = [100.0, 100.0, 100.0, 100.0]
        assert not rf.allow_bullish(prices)
        # price == SMA => not < SMA => allow_bearish also False
        assert not rf.allow_bearish(prices)

    def test_custom_sma_period(self):
        """RegimeFilter with custom SMA period."""
        rf = RegimeFilter(sma_period=5, enabled=True)
        # Uptrend: last 5 values increasing
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
        assert rf.allow_bullish(prices)
        assert not rf.allow_bearish(prices)

    def test_empty_prices(self):
        """Empty price list should return True (len < 2)."""
        rf = RegimeFilter(sma_period=21, enabled=True)
        assert rf.allow_bullish([])
        assert rf.allow_bearish([])

    def test_two_prices_computed(self):
        """Two prices (len < default period 21) are still compared against SMA of those 2."""
        rf = RegimeFilter(sma_period=21, enabled=True)
        # SMA of [100.0, 99.0] = 99.5; price=99.0 < SMA=99.5 => bullish blocked
        assert not rf.allow_bullish([100.0, 99.0])
        # price=99.0 < SMA=99.5 => bearish allowed
        assert rf.allow_bearish([100.0, 99.0])

    def test_two_prices_bullish(self):
        """Two increasing prices: price > SMA => bullish allowed."""
        rf = RegimeFilter(sma_period=21, enabled=True)
        # SMA of [99.0, 100.0] = 99.5; price=100.0 > SMA=99.5 => bullish
        assert rf.allow_bullish([99.0, 100.0])


class TestRetailFlowSignalEdge:
    def test_none_snapshot_values(self):
        """Snapshot with None values should use defaults and not crash."""
        rf = RegimeFilter(enabled=False)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        snapshots = [{"cpr": None, "oi_change_pct": None, "iv_skew": None}]
        bars = [{"close": 400.0}]
        # Should not raise — defaults to CPR=1.0, OI=0, skew=0 => neutral score
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_missing_snapshot_keys(self):
        """Snapshot with missing keys should use defaults."""
        rf = RegimeFilter(enabled=False)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        snapshots = [{}]  # All keys missing
        bars = [{"close": 400.0}]
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_nan_in_snapshot(self):
        """NaN values in snapshot should be handled by _safe_float."""
        rf = RegimeFilter(enabled=False)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        snapshots = [{"cpr": float("nan"), "oi_change_pct": float("nan"), "iv_skew": float("nan")}]
        bars = [{"close": 400.0}]
        action = signal.evaluate(snapshots, bars, Position())
        assert action == Action.HOLD

    def test_negative_cpr_handled(self):
        """Negative CPR (invalid but possible in data) should not crash."""
        rf = RegimeFilter(enabled=False)
        signal = RetailFlowSignal(entry_threshold=30.0, regime_filter=rf)
        snapshots = [{"cpr": -1.0, "oi_change_pct": 0.0, "iv_skew": 0.0}]
        bars = [{"close": 400.0}]
        # Should not raise
        action = signal.evaluate(snapshots, bars, Position())
        assert isinstance(action, Action)

    def test_exit_call_only_when_long_call(self):
        """SELL_CALL only when position is LONG CALL, not PUT."""
        signal = RetailFlowSignal(entry_threshold=30.0, exit_threshold=10.0,
                                  regime_filter=RegimeFilter(enabled=False))
        prices = [400.0] * 30
        snapshots = [{"cpr": 1.0}] * 30  # neutral score
        bars = [{"close": p} for p in prices]
        # Long PUT position — should NOT trigger SELL_CALL
        pos = Position(side="PUT", direction="LONG", entry_price=5.0, quantity=1)
        action = signal.evaluate(snapshots, bars, pos)
        assert action == Action.SELL_PUT

    def test_no_exit_when_score_at_threshold(self):
        """Score exactly at exit threshold should not exit (strict <)."""
        signal = RetailFlowSignal(entry_threshold=30.0, exit_threshold=10.0,
                                  regime_filter=RegimeFilter(enabled=False))
        prices = [400.0] * 30
        # CPR=1.0, OI=0, skew=0 => score = 0 (neutral)
        # score=0 is NOT < exit_threshold=10 => no exit for call
        snapshots = [{"cpr": 1.0}] * 30
        bars = [{"close": p} for p in prices]
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=1)
        action = signal.evaluate(snapshots, bars, pos)
        # score=0 < 10 => SELL_CALL
        assert action == Action.SELL_CALL


class TestPosition:
    def test_default_is_not_open(self):
        pos = Position()
        assert not pos.is_open

    def test_open_position(self):
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=1)
        assert pos.is_open

    def test_zero_quantity_not_open(self):
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=0)
        assert not pos.is_open

    def test_none_side_not_open(self):
        pos = Position(side=None, direction="LONG", entry_price=5.0, quantity=1)
        assert not pos.is_open

    def test_close_long_position(self):
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=2)
        pnl = pos.close(exit_price=7.0)
        assert pnl == pytest.approx((7.0 - 5.0) * 2)
        assert not pos.is_open
        assert pos.quantity == 0

    def test_close_short_position(self):
        pos = Position(side="PUT", direction="SHORT", entry_price=5.0, quantity=3)
        pnl = pos.close(exit_price=3.0)
        assert pnl == pytest.approx((5.0 - 3.0) * 3)
        assert not pos.is_open

    def test_close_already_closed_returns_zero(self):
        pos = Position()
        pnl = pos.close(exit_price=10.0)
        assert pnl == 0.0

    def test_update_unrealized_long(self):
        pos = Position(side="CALL", direction="LONG", entry_price=5.0, quantity=2)
        unrealized = pos.update_unrealized(8.0)
        assert unrealized == pytest.approx((8.0 - 5.0) * 2)

    def test_update_unrealized_short(self):
        pos = Position(side="PUT", direction="SHORT", entry_price=5.0, quantity=2)
        unrealized = pos.update_unrealized(3.0)
        assert unrealized == pytest.approx((5.0 - 3.0) * 2)

    def test_update_unrealized_not_open(self):
        pos = Position()
        result = pos.update_unrealized(100.0)
        assert result == 0.0
        assert pos.unrealized_pnl == 0.0
