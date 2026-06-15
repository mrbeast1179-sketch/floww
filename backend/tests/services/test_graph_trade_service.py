"""Tests for services/graph_trade_service.py — Knowledge Graph Trade Service."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.graph_trade_service import GraphTradeService


@pytest.fixture
def svc():
    """Create an in-memory GraphTradeService for testing."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=True) as f:
        db_path = f.name
    service = GraphTradeService(db_path=db_path)
    service.ensure_schema()
    yield service
    service.close()


def _make_trade(**overrides):
    trade = {
        "id": "T-001", "symbol": "SPY", "side": "BUY", "quantity": 10,
        "entry_price": 100.0, "exit_price": 105.0, "pnl": 50.0,
        "pnl_pct": 5.0, "trade_type": "paper", "strategy": "test",
    }
    trade.update(overrides)
    return trade


def _make_signal(**overrides):
    signal = {
        "id": "S-001", "signal_type": "VPIN", "value": 0.8,
        "z_score": 2.5, "threshold": 0.7, "direction": "BUY",
        "timestamp": "2026-01-01T00:00:00",
    }
    signal.update(overrides)
    return signal


# ── Schema ───────────────────────────────────────────────────────────────


class TestSchema:
    def test_ensure_schema_creates_tables(self, svc):
        # Should not raise
        svc.ensure_schema()
        assert svc.get_trade_count() == 0
        assert svc.get_signal_count() == 0


# ── Trade CRUD ───────────────────────────────────────────────────────────


class TestTradeCRUD:
    def test_upsert_trade(self, svc):
        svc.upsert_trade(_make_trade())
        assert svc.get_trade_count() == 1

    def test_upsert_trade_updates(self, svc):
        svc.upsert_trade(_make_trade())
        svc.upsert_trade(_make_trade(pnl=100.0))
        assert svc.get_trade_count() == 1  # upsert, not insert

    def test_upsert_trades_batch(self, svc):
        trades = [_make_trade(id=f"T-{i}") for i in range(5)]
        count = svc.upsert_trades_batch(trades)
        assert count == 5
        assert svc.get_trade_count() == 5

    def test_get_trades_by_symbol(self, svc):
        svc.upsert_trade(_make_trade(id="T-1", symbol="SPY"))
        svc.upsert_trade(_make_trade(id="T-2", symbol="QQQ"))
        svc.upsert_trade(_make_trade(id="T-3", symbol="SPY"))
        spy_trades = svc.get_trades_by_symbol("SPY")
        assert len(spy_trades) == 2

    def test_trade_metadata_stored(self, svc):
        svc.upsert_trade(_make_trade(custom_field="hello"))
        trades = svc.get_trades_by_symbol("SPY")
        import json
        meta = json.loads(trades[0]["metadata"])
        assert meta["custom_field"] == "hello"


# ── Signal CRUD ──────────────────────────────────────────────────────────


class TestSignalCRUD:
    def test_upsert_signal(self, svc):
        svc.upsert_signal(_make_signal())
        assert svc.get_signal_count() == 1

    def test_upsert_signals_batch(self, svc):
        signals = [_make_signal(id=f"S-{i}") for i in range(3)]
        count = svc.upsert_signals_batch(signals)
        assert count == 3
        assert svc.get_signal_count() == 3


# ── Market Condition CRUD ────────────────────────────────────────────────


class TestMarketConditionCRUD:
    def test_upsert_market_condition(self, svc):
        svc.upsert_market_condition({
            "id": "MC-001", "regime": "high_vol", "volatility": 0.35,
        })
        assert svc.get_market_condition_count() == 1


# ── Symbol CRUD ──────────────────────────────────────────────────────────


class TestSymbolCRUD:
    def test_upsert_symbol(self, svc):
        svc.upsert_symbol({"id": "SYM-SPY", "name": "SPY", "asset_class": "equity"})
        stats = svc.get_graph_stats()
        assert stats["symbols"] == 1


# ── Edge Operations ──────────────────────────────────────────────────────


class TestEdges:
    def test_trade_signal_edge(self, svc):
        svc.upsert_trade(_make_trade())
        svc.upsert_signal(_make_signal())
        svc.add_trade_signal_edge("T-001", "S-001", confidence=0.9)
        stats = svc.get_graph_stats()
        assert stats["trade_signal_edges"] == 1

    def test_trade_condition_edge(self, svc):
        svc.upsert_trade(_make_trade())
        svc.upsert_market_condition({"id": "MC-001", "regime": "trending"})
        svc.add_trade_condition_edge("T-001", "MC-001")
        stats = svc.get_graph_stats()
        assert stats["trade_condition_edges"] == 1

    def test_trade_symbol_edge(self, svc):
        svc.upsert_trade(_make_trade())
        svc.upsert_symbol({"id": "SYM-SPY", "name": "SPY"})
        svc.add_trade_symbol_edge("T-001", "SYM-SPY")
        stats = svc.get_graph_stats()
        assert stats["trade_symbol_edges"] == 1


# ── Retail Flow CRUD ─────────────────────────────────────────────────────


class TestRetailFlow:
    def test_upsert_retail_flow_score(self, svc):
        svc.upsert_retail_flow_score({
            "id": "RF-001", "symbol": "SPY", "sweep_ratio": 0.3,
            "retail_flow_score": 0.5,
        })
        assert svc.get_retail_flow_count() == 1

    def test_get_retail_flow_scores_by_symbol(self, svc):
        svc.upsert_retail_flow_score({"id": "RF-1", "symbol": "SPY", "retail_flow_score": 0.5})
        svc.upsert_retail_flow_score({"id": "RF-2", "symbol": "QQQ", "retail_flow_score": -0.3})
        scores = svc.get_retail_flow_scores_by_symbol("SPY")
        assert len(scores) == 1

    def test_get_retail_flow_stats(self, svc):
        svc.upsert_retail_flow_score({"id": "RF-1", "symbol": "SPY", "retail_flow_score": 0.5, "sweep_ratio": 0.3})
        svc.upsert_retail_flow_score({"id": "RF-2", "symbol": "SPY", "retail_flow_score": -0.5, "sweep_ratio": 0.1})
        stats = svc.get_retail_flow_stats()
        assert stats["total_flow_scores"] == 2
        assert stats["bullish_count"] == 1
        assert stats["bearish_count"] == 1


# ── Price Movement CRUD ─────────────────────────────────────────────────


class TestPriceMovement:
    def test_upsert_price_movement(self, svc):
        svc.upsert_price_movement({
            "id": "PM-001", "symbol": "SPY", "start_price": 100.0,
            "end_price": 102.0, "price_change": 2.0, "price_change_pct": 2.0,
            "direction": "UP", "timeframe": "5m",
        })
        assert svc.get_price_movement_count() == 1

    def test_get_price_movements_by_symbol(self, svc):
        svc.upsert_price_movement({"id": "PM-1", "symbol": "SPY", "direction": "UP"})
        svc.upsert_price_movement({"id": "PM-2", "symbol": "SPY", "direction": "DOWN"})
        svc.upsert_price_movement({"id": "PM-3", "symbol": "QQQ", "direction": "UP"})
        all_spy = svc.get_price_movements_by_symbol("SPY")
        assert len(all_spy) == 2
        up_spy = svc.get_price_movements_by_symbol("SPY", direction="UP")
        assert len(up_spy) == 1


# ── Graph Queries ────────────────────────────────────────────────────────


class TestGraphQueries:
    def test_get_trade_stats_empty(self, svc):
        stats = svc.get_trade_stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_get_trade_stats_with_trades(self, svc):
        svc.upsert_trade(_make_trade(id="T-1", pnl=100.0))
        svc.upsert_trade(_make_trade(id="T-2", pnl=-50.0))
        stats = svc.get_trade_stats()
        assert stats["total_trades"] == 2
        assert stats["profitable"] == 1
        assert stats["losing"] == 1
        assert stats["total_pnl"] == 50.0

    def test_get_graph_stats(self, svc):
        svc.upsert_trade(_make_trade())
        svc.upsert_signal(_make_signal())
        stats = svc.get_graph_stats()
        assert stats["trades"] == 1
        assert stats["signals"] == 1
        assert "retail_flow_scores" in stats
        assert "price_movements" in stats
