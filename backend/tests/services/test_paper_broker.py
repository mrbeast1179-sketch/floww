#!/usr/bin/env python3
"""
backend/tests/services/test_paper_broker.py — Tests for paper broker.
"""

from __future__ import annotations

import pytest
from services.paper_broker import PaperBroker, PaperBrokerConfig


class TestPaperBrokerConfig:
    def test_defaults(self):
        cfg = PaperBrokerConfig()
        assert cfg.initial_capital == 25000.0
        assert cfg.slippage_per_contract == 0.01
        assert cfg.market_impact_pct == 0.001

    def test_custom_config(self):
        cfg = PaperBrokerConfig(initial_capital=50000.0, slippage_per_contract=0.02)
        assert cfg.initial_capital == 50000.0
        assert cfg.slippage_per_contract == 0.02


class TestPaperBrokerInit:
    def test_default_init(self):
        broker = PaperBroker()
        assert broker.cash == 25000.0
        assert len(broker.positions) == 0
        assert len(broker.fills) == 0

    def test_custom_init(self):
        cfg = PaperBrokerConfig(initial_capital=10000.0)
        broker = PaperBroker(config=cfg)
        assert broker.cash == 10000.0


class TestSubmitOrder:
    def test_submit_returns_order_id(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 5)
        assert order_id is not None
        assert order_id in broker.orders

    def test_submit_records_order(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 5, "limit", 500.0)
        order = broker.orders[order_id]
        assert order["symbol"] == "SPY"
        assert order["side"] == "buy"
        assert order["quantity"] == 5
        assert order["order_type"] == "limit"
        assert order["limit_price"] == 500.0
        assert order["status"] == "submitted"


class TestGetFillPrice:
    def test_buy_has_positive_slippage(self):
        broker = PaperBroker()
        fill_price, slippage, impact = broker.get_fill_price("SPY", "buy", 1, 500.0)
        assert fill_price > 500.0  # Buy at higher price
        assert slippage > 0
        assert impact > 0

    def test_sell_has_negative_slippage(self):
        broker = PaperBroker()
        fill_price, slippage, impact = broker.get_fill_price("SPY", "sell", 1, 500.0)
        assert fill_price < 500.0  # Sell at lower price
        assert slippage > 0
        assert impact > 0

    def test_larger_quantity_more_slippage(self):
        broker = PaperBroker()
        _, slippage1, _ = broker.get_fill_price("SPY", "buy", 1, 500.0)
        _, slippage10, _ = broker.get_fill_price("SPY", "buy", 10, 500.0)
        assert slippage10 > slippage1


class TestExecuteFill:
    def test_fill_updates_cash(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 1)
        initial_cash = broker.cash
        fill = broker.execute_fill(order_id, 500.0)
        assert fill is not None
        assert broker.cash < initial_cash

    def test_fill_creates_position(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(order_id, 500.0)
        pos = broker.get_position("SPY")
        assert pos is not None
        assert pos.quantity == 5

    def test_fill_records_history(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 1)
        broker.execute_fill(order_id, 500.0)
        history = broker.get_trade_history()
        assert len(history) == 1
        assert history[0]["symbol"] == "SPY"

    def test_fill_updates_order_status(self):
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 1)
        broker.execute_fill(order_id, 500.0)
        assert broker.orders[order_id]["status"] == "filled"


class TestPositionTracking:
    def test_long_position(self):
        broker = PaperBroker()
        oid = broker.submit_order("SPY", "buy", 10)
        broker.execute_fill(oid, 500.0)
        pos = broker.get_position("SPY")
        assert pos.quantity == 10
        # avg_cost includes slippage (fill_price > market_price for buys)
        assert pos.avg_cost > 500.0

    def test_short_position(self):
        broker = PaperBroker()
        oid = broker.submit_order("SPY", "sell", 10)
        broker.execute_fill(oid, 500.0)
        pos = broker.get_position("SPY")
        assert pos.quantity == -10

    def test_add_to_position(self):
        broker = PaperBroker()
        oid1 = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(oid1, 500.0)
        oid2 = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(oid2, 510.0)
        pos = broker.get_position("SPY")
        assert pos.quantity == 10
        # Weighted average of fill prices (which include slippage)
        assert pos.avg_cost > 505.0

    def test_close_position(self):
        broker = PaperBroker()
        oid = broker.submit_order("SPY", "buy", 10)
        broker.execute_fill(oid, 500.0)
        fill = broker.close_position("SPY", 510.0)
        assert fill is not None
        pos = broker.get_position("SPY")
        assert pos.quantity == 0

    def test_close_nonexistent_position(self):
        broker = PaperBroker()
        fill = broker.close_position("SPY", 500.0)
        assert fill is None

    def test_get_all_positions(self):
        broker = PaperBroker()
        oid1 = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(oid1, 500.0)
        oid2 = broker.submit_order("QQQ", "sell", 3)
        broker.execute_fill(oid2, 400.0)
        positions = broker.get_all_positions()
        assert len(positions) == 2


class TestPnL:
    def test_initial_pnl(self):
        broker = PaperBroker()
        pnl = broker.get_pnl()
        assert pnl["realized_pnl"] == 0
        assert pnl["total_pnl"] == 0
        assert pnl["cash"] == 25000.0

    def test_realized_pnl_on_close(self):
        broker = PaperBroker()
        oid = broker.submit_order("SPY", "buy", 10)
        broker.execute_fill(oid, 500.0)
        broker.close_position("SPY", 510.0)
        pnl = broker.get_pnl()
        assert pnl["realized_pnl"] > 0  # Profitable trade

    def test_daily_pnl_tracking(self):
        broker = PaperBroker()
        oid = broker.submit_order("SPY", "buy", 10)
        broker.execute_fill(oid, 500.0)
        broker.close_position("SPY", 510.0)
        assert broker.daily_pnl > 0

    def test_reset_daily_pnl(self):
        broker = PaperBroker()
        broker.daily_pnl = 100.0
        broker.reset_daily_pnl()
        assert broker.daily_pnl == 0


class TestEdgeCases:
    def test_fill_nonexistent_order(self):
        broker = PaperBroker()
        fill = broker.execute_fill("fake-id", 500.0)
        assert fill is None

    def test_zero_quantity(self):
        """Zero quantity should not cause division by zero."""
        broker = PaperBroker()
        order_id = broker.submit_order("SPY", "buy", 0)
        # Zero quantity fills should be handled gracefully
        fill = broker.execute_fill(order_id, 500.0)
        # Either None or a fill with quantity 0
        if fill is not None:
            assert fill.quantity == 0

    def test_reverse_position(self):
        """Going from long to short."""
        broker = PaperBroker()
        oid1 = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(oid1, 500.0)
        oid2 = broker.submit_order("SPY", "sell", 10)
        broker.execute_fill(oid2, 510.0)
        pos = broker.get_position("SPY")
        assert pos.quantity == -5  # Net short

    def test_random_slippage(self):
        cfg = PaperBrokerConfig(random_slippage=True, random_seed=42)
        broker = PaperBroker(config=cfg)
        fill_price, _, _ = broker.get_fill_price("SPY", "buy", 1, 500.0)
        assert fill_price > 500.0
