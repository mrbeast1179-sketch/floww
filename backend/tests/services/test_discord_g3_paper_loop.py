"""G3 paper-loop pins (GATE-2 OFFLINE half).

Proves the Discord approve path works through the REAL OrderRouter +
a broker stub — today's code sends market orders the router rejects by
default (ALLOW_MARKET_ORDERS=False), so the whole paper loop is dead
before any network or Discord transport is involved.

Paper-only: broker is an in-memory stub; asserts paper venue constant.
No POST/DELETE, no keys, no Discord connection.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _alert(key="score|SPY|call|745|2099-01-08"):
    return {
        "key": key, "rule": "SCORE", "tier": "GOLD", "under": "SPY",
        "type": "call", "strike": 745, "exp": "2099-01-08", "score": 90,
        "premium": 120.0, "bias": "BULLISH", "side": "BUY",
        "under_price": 750.0, "why": "test flow",
        "key_levels": {"entry": 1.2, "invalidation": 0.8, "target": 2.0},
    }


def _accepting_broker():
    broker = MagicMock()
    broker.place_stock_order = AsyncMock(
        return_value={"id": "alpaca-1", "status": "accepted"})
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_order = AsyncMock(
        return_value={"id": "alpaca-1", "status": "filled",
                      "filled_avg_price": "751.0", "filled_qty": "1"})
    return broker


def _mem_engine():
    from services.duckdb_engine import DuckDBEngine
    from services.journal_store import init_journal_tables
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    return eng


class TestApproveThroughRealRouter:
    @pytest.mark.asyncio
    async def test_approve_market_submits_paper(self, monkeypatch):
        """Approve must submit through the real router (market opt-in)."""
        from services import discord_ops as ops
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = OrderRouter("paper", broker=_accepting_broker())
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert res["status"] == "submitted", res
        assert res["order"]["venue"] == "alpaca-paper"

    @pytest.mark.asyncio
    async def test_duplicate_approve_suppressed(self, monkeypatch):
        """Second identical approve must not place a second broker order."""
        from services import discord_ops as ops
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        broker = _accepting_broker()
        router = OrderRouter("paper", broker=broker)
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            first = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
            second = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        assert first["status"] == "submitted"
        assert second["status"] == "duplicate", second
        assert broker.place_stock_order.call_count == 1

    @pytest.mark.asyncio
    async def test_journal_marks_submission_not_fill(self, monkeypatch):
        """Journal seed must not read as a confirmed fill."""
        from services import discord_ops as ops
        from services.journal_store import read_trades
        from services.order_router import OrderRouter

        eng = _mem_engine()
        monkeypatch.setattr("services.journal_store.get_engine", lambda: eng)
        router = OrderRouter("paper", broker=_accepting_broker())
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert()]):
            await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 1, MagicMock(), router)
        notes = read_trades(eng)[0]["notes"]
        assert "not a confirmed fill" in notes


class TestPaperTransportPins:
    def test_paper_venue_hardcoded(self):
        import alpaca_client
        assert alpaca_client.ALPACA_BASE_URL == \
            "https://paper-api.alpaca.markets"

    @pytest.mark.asyncio
    async def test_get_order_read_path(self):
        from alpaca_client import AlpacaClient
        c = AlpacaClient.__new__(AlpacaClient)
        c._api_key = "K"
        c._secret_key = "S"
        with patch.object(AlpacaClient, "_get",
                          new=AsyncMock(return_value={"id": "a1"})) as g:
            assert (await c.get_order("a1"))["id"] == "a1"
        assert "a1" in g.call_args.args[0]
