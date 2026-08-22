"""
backend/tests/services/test_journal_store.py

RED-first tests for services/journal_store.py — server-side persistence of
auto-seeded trade-journal entries (the backend half of the Flowseeker
signal-to-trade pipeline). Seeds written at execute-time survive browser
clears and sync to every device; the frontend localStorage store remains
the offline cache.
"""
import pytest

from services.journal_store import (
    init_journal_tables,
    save_seeds,
    read_trades,
    close_trade,
    journal_seed_key,
)


@pytest.fixture
def engine():
    from services.duckdb_engine import DuckDBEngine
    # in-memory engine per test
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
        "notes": "auto", "gex_regime": "", "setup": "score gold",
        "tags": "flowseeker,auto", "ckey": "SPY|call|500|2026-09-18",
    }
    base.update(over)
    return base


def test_save_and_read_roundtrip(engine):
    n = save_seeds(engine, [_seed()])
    assert n == 1
    rows = read_trades(engine)
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "SPY"
    assert float(r["strike"]) == 500.0
    assert r["ckey"] == "SPY|call|500|2026-09-18"


def test_dedupe_same_contract_twice(engine):
    save_seeds(engine, [_seed()])
    n = save_seeds(engine, [_seed()])          # identical re-execute
    assert n == 0
    assert len(read_trades(engine)) == 1


def test_different_contracts_both_saved(engine):
    n = save_seeds(engine, [_seed(), _seed(ticker="QQQ", strike=380.0,
                                          ckey="QQQ|call|380|2026-09-18")])
    assert n == 2


def test_close_trade_sets_exit(engine):
    save_seeds(engine, [_seed()])
    key = journal_seed_key(_seed())
    ok = close_trade(engine, key, exit_price=2.50, exit_date="2026-08-25")
    assert ok is True
    r = read_trades(engine)[0]
    assert float(r["exit_price"]) == 2.50
    assert r["exit_date"] == "2026-08-25"


def test_close_missing_returns_false(engine):
    ok = close_trade(engine, "NOPE|x|1|2026-01-01", exit_price=1.0,
                     exit_date="2026-01-02")
    assert ok is False


def test_open_only_filter(engine):
    save_seeds(engine, [_seed(), _seed(ticker="QQQ", strike=380.0,
                                       ckey="QQQ|call|380|2026-09-18")])
    key = journal_seed_key(_seed())
    close_trade(engine, key, exit_price=3.0, exit_date="2026-08-26")
    open_rows = read_trades(engine, status="open")
    assert len(open_rows) == 1
    assert open_rows[0]["ticker"] == "QQQ"
