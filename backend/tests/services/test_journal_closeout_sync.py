"""
backend/tests/services/test_journal_closeout_sync.py

RED-first tests: when the paper engine nets a symbol to flat (round-trip
closed) and that symbol has an OPEN server-journal card seeded by the
Flowseeker bridge, the journal card must be closed automatically with
the realized exit price — no manual step, no frontend round-trip.

Design: PaperTradingEngine gains an optional ``on_position_closed`` hook
(callable(symbol, exit_price)). The route layer (flowseeker.execute)
registers a hook that calls journal_store.close_open_by_symbol().
Keeping the engine dependency-injected avoids a services→services hard
coupling and keeps the engine unit-testable in isolation.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.execution_engine import MarketState  # noqa: E402
from services.journal_store import (  # noqa: E402
    close_open_by_symbol,
    get_engine,
    init_journal_tables,
    read_trades,
    save_seeds,
)


def _market(symbol="SPY", bid=100.0, ask=100.0):
    return MarketState(
        symbol=symbol, bid=bid, ask=ask, last=(bid + ask) / 2,
        bid_size=100, ask_size=100, volume=1_000_000, volatility=0.0,
    )


@pytest.fixture
def jeng():
    # In-memory engine — the live data/journal.duckdb is DuckDB-locked by
    # the running server process; tests must never contend with it.
    from services.duckdb_engine import DuckDBEngine
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    yield eng
    try:
        eng._conn.close()
    except Exception:
        pass


def _seed(**over):
    base = {
        "ticker": "SPY", "type": "call", "action": "buy", "strike": 500.0,
        "expiry": "2026-09-18", "quantity": "2", "entry_price": 1.25,
        "exit_price": "", "entry_date": "2026-08-22", "exit_date": "",
        "notes": "", "gex_regime": "", "setup": "score gold",
        "tags": "flowseeker,auto", "ckey": "SPY|call|500|2026-09-18",
    }
    base.update(over)
    return base


class TestHookFires:
    def test_engine_accepts_hook_and_fires_on_flat(self):
        from services.paper_trading import PaperTradingEngine
        fired = []
        eng = PaperTradingEngine(initial_capital=100_000,
                                 commission_per_contract=0.0,
                                 on_position_closed=lambda sym, px: fired.append((sym, px)))
        m = _market()
        b = eng.submit_order(symbol="SPY", side="buy", quantity=10, market=m)
        eng.execute_order(b["order_id"], m)
        s = eng.submit_order(symbol="SPY", side="sell", quantity=10, market=m)
        eng.execute_order(s["order_id"], m)
        assert len(fired) == 1
        assert fired[0][0] == "SPY"
        assert isinstance(fired[0][1], float)

    def test_no_hook_no_crash(self):
        from services.paper_trading import PaperTradingEngine
        eng = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.0)
        m = _market()
        b = eng.submit_order(symbol="QQQ", side="buy", quantity=5, market=m)
        eng.execute_order(b["order_id"], m)
        s = eng.submit_order(symbol="QQQ", side="sell", quantity=5, market=m)
        r = eng.execute_order(s["order_id"], m)
        assert r.symbol == "QQQ"

    def test_partial_close_does_not_fire(self):
        from services.paper_trading import PaperTradingEngine
        fired = []
        eng = PaperTradingEngine(initial_capital=100_000,
                                 commission_per_contract=0.0,
                                 on_position_closed=lambda sym, px: fired.append((sym, px)))
        m = _market()
        b = eng.submit_order(symbol="SPY", side="buy", quantity=10, market=m)
        eng.execute_order(b["order_id"], m)
        s = eng.submit_order(symbol="SPY", side="sell", quantity=4, market=m)
        eng.execute_order(s["order_id"], m)
        assert fired == []          # still holding 6 — not flat


class TestJournalSync:
    def test_close_open_by_symbol_closes_matching_cards(self, jeng):
        save_seeds(jeng, [_seed(), _seed(ticker="QQQ", strike=380.0,
                                         ckey="QQQ|call|380|2026-09-18")])
        n = close_open_by_symbol(jeng, "SPY", exit_price=2.75,
                                 exit_date="2026-08-25")
        assert n == 1
        rows = read_trades(jeng)
        by_ticker = {r["ticker"]: r for r in rows}
        assert float(by_ticker["SPY"]["exit_price"]) == 2.75
        assert by_ticker["QQQ"]["exit_price"] == ""      # untouched

    def test_already_closed_card_not_reclosed(self, jeng):
        save_seeds(jeng, [_seed()])
        n1 = close_open_by_symbol(jeng, "SPY", exit_price=2.75,
                                  exit_date="2026-08-25")
        n2 = close_open_by_symbol(jeng, "SPY", exit_price=3.00,
                                  exit_date="2026-08-26")
        assert n1 == 1 and n2 == 0
        row = read_trades(jeng)[0]
        assert float(row["exit_price"]) == 2.75           # first close wins
        assert row["exit_date"] == "2026-08-25"

    def test_no_open_cards_returns_zero(self, jeng):
        assert close_open_by_symbol(jeng, "TLT", exit_price=1.0,
                                    exit_date="2026-08-25") == 0
