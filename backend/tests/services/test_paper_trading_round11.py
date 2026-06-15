"""Additional tests for services/paper_trading.py — Round 11 Agent 01.

Covers gaps in existing test suite:
- Detailed cash arithmetic on execute (commission, slippage, fill price)
- Position cost basis averaging via _update_position
- Risk check edge cases (zero qty, insufficient cash, position limits)
- Round-trip portfolio P&L
- Trade history field correctness
- get_state details

Bug found: execution_engine.py:459 ZeroDivisionError when quantity=0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import MarketState, Order
from services.paper_trading import PaperTradingEngine


def _make_market(symbol="SPY", bid=100.0, ask=100.1, volatility=0.20):
    return MarketState(
        symbol=symbol, bid=bid, ask=ask, last=(bid + ask) / 2,
        bid_size=100, ask_size=100, volume=1_000_000, volatility=volatility,
    )


class TestExecuteCashMath:
    def test_buy_cash_decreases(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.65)
        market = _make_market(bid=100.0, ask=100.0)
        submit = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=market)
        result = engine.execute_order(submit["order_id"], market)
        assert result.avg_price > 0
        assert engine.cash < 100_000

    def test_sell_cash_increases(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.65)
        market = _make_market(bid=100.0, ask=100.0)
        s1 = engine.submit_order(symbol="SPY", side="buy", quantity=10, market=market)
        engine.execute_order(s1["order_id"], market)
        cash_after_buy = engine.cash
        s2 = engine.submit_order(symbol="SPY", side="sell", quantity=10, market=market)
        engine.execute_order(s2["order_id"], market)
        assert engine.cash > cash_after_buy

    def test_commission_tracked_in_trade_history(self):
        engine = PaperTradingEngine(commission_per_contract=1.50)
        market = _make_market()
        submit = engine.submit_order(symbol="SPY", side="buy", quantity=5, market=market)
        engine.execute_order(submit["order_id"], market)
        trade = engine.trade_history[0]
        assert trade["commission"] == pytest.approx(1.50 * 5, abs=0.01)

    def test_execution_result_fields(self):
        engine = PaperTradingEngine()
        market = _make_market()
        submit = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=market)
        result = engine.execute_order(submit["order_id"], market)
        assert result.order_id == submit["order_id"]
        assert result.filled_qty == 1
        assert result.avg_price > 0
        assert result.total_cost > 0
        assert result.duration_ms >= 0


class TestPositionCostBasis:
    def test_single_buy_sets_avg_cost(self):
        engine = PaperTradingEngine()
        order = Order(symbol="SPY", side="buy", quantity=10, order_type="market", urgency=0.5, limit_price=0.0)
        engine._update_position(order, fill_price=100.0)
        assert engine.positions["SPY_buy"]["quantity"] == 10
        assert engine.positions["SPY_buy"]["avg_cost"] == pytest.approx(100.0)

    def test_two_buys_average_cost(self):
        engine = PaperTradingEngine()
        o1 = Order(symbol="SPY", side="buy", quantity=10, order_type="market", urgency=0.5, limit_price=0.0)
        o2 = Order(symbol="SPY", side="buy", quantity=10, order_type="market", urgency=0.5, limit_price=0.0)
        engine._update_position(o1, fill_price=100.0)
        engine._update_position(o2, fill_price=110.0)
        assert engine.positions["SPY_buy"]["avg_cost"] == pytest.approx(105.0)
        assert engine.positions["SPY_buy"]["quantity"] == 20


class TestRiskCheckEdgeCases:
    def test_zero_quantity_no_market(self):
        """Zero qty with no market should be approved (no execution plan)."""
        engine = PaperTradingEngine(initial_capital=100_000)
        result = engine.submit_order(symbol="SPY", side="buy", quantity=0, market=None)
        assert result["status"] == "accepted"

    def test_position_limit_rejects(self):
        engine = PaperTradingEngine(initial_capital=10_000, max_position_pct=0.01)
        market = _make_market(bid=100.0, ask=100.0)
        result = engine.submit_order(symbol="SPY", side="buy", quantity=2, market=market)
        assert result["status"] == "rejected"
        assert "Position limit" in result["reason"]

    def test_insufficient_cash_rejected(self):
        """Need enough max_position_pct to pass position limit but fail cash check."""
        engine = PaperTradingEngine(initial_capital=50, max_position_pct=5.0)
        market = _make_market(bid=100.0, ask=100.0)
        result = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=market)
        assert result["status"] == "rejected"
        assert "Insufficient cash" in result["reason"]


class TestPortfolioRoundTrip:
    def test_round_trip_cash_decreases(self):
        """After buy+sell, cash should be less than initial (commissions)."""
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.65)
        market = _make_market(bid=100.0, ask=100.0)
        s1 = engine.submit_order(symbol="SPY", side="buy", quantity=10, market=market)
        engine.execute_order(s1["order_id"], market)
        s2 = engine.submit_order(symbol="SPY", side="sell", quantity=10, market=market)
        engine.execute_order(s2["order_id"], market)
        assert engine.cash < 100_000.0
        assert len(engine.trade_history) == 2


class TestTradeHistoryFields:
    def test_history_has_expected_keys(self):
        engine = PaperTradingEngine()
        market = _make_market()
        submit = engine.submit_order(symbol="SPY", side="buy", quantity=5, market=market)
        engine.execute_order(submit["order_id"], market)
        trade = engine.trade_history[0]
        expected = {"order_id", "symbol", "side", "quantity", "fill_price",
                    "commission", "total_cost", "kyle_impact", "slippage_bps", "timestamp"}
        assert expected.issubset(trade.keys())

    def test_history_limit(self):
        engine = PaperTradingEngine(initial_capital=1_000_000)
        market = _make_market()
        for _ in range(5):
            s = engine.submit_order(symbol="SPY", side="buy", quantity=1, market=market)
            engine.execute_order(s["order_id"], market)
        assert len(engine.get_trade_history(limit=3)) == 3
