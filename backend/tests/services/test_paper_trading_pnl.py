"""Regression test for the paper-trading round-trip P&L bug (2026-06-15).

Bug: PaperTradingEngine keyed positions by ``f"{symbol}_{side}"``, so a flat
buy->sell round-trip created TWO positions (SPY_buy qty>0 AND SPY_sell qty>0)
and get_portfolio_summary counted both as open longs -> reported ~+$2,000 P&L
and 2 open positions on a trade that actually netted to flat. A round-trip must
net to ~0 P&L and 0 open positions; a single buy must still show 1 open long.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.execution_engine import MarketState  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402


def _market(bid=100.0, ask=100.0, volatility=0.0):
    return MarketState(
        symbol="SPY", bid=bid, ask=ask, last=(bid + ask) / 2,
        bid_size=100, ask_size=100, volume=1_000_000, volatility=volatility,
    )


def _round_trip(engine, qty=10):
    m = _market()
    b = engine.submit_order(symbol="SPY", side="buy", quantity=qty, market=m)
    engine.execute_order(b["order_id"], m)
    s = engine.submit_order(symbol="SPY", side="sell", quantity=qty, market=m)
    engine.execute_order(s["order_id"], m)


class TestRoundTripNetsToFlat:
    def test_flat_round_trip_pnl_near_zero(self):
        eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        _round_trip(eng, qty=10)
        assert eng.get_portfolio_summary()["total_pnl"] == pytest.approx(0.0, abs=1.0)

    def test_flat_round_trip_has_no_open_positions(self):
        eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        _round_trip(eng, qty=10)
        assert eng.get_portfolio_summary()["open_positions"] == 0


class TestOpenLongStillCounts:
    def test_single_buy_is_one_open_long_valued_at_capital(self):
        eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        b = eng.submit_order(symbol="SPY", side="buy", quantity=10, market=m)
        eng.execute_order(b["order_id"], m)
        s = eng.get_portfolio_summary()
        assert s["open_positions"] == 1
        assert s["positions"][0]["symbol"] == "SPY"
        assert s["positions"][0]["quantity"] == pytest.approx(10)
        assert s["total_value"] == pytest.approx(100_000.0, abs=1.0)
