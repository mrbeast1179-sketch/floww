"""
backend/tests/services/test_journal_lifecycle.py

RED-first: journal cards seeded from Blademap alerts currently sit open
forever with a static entry price. The lifecycle pass closes them
against their own key levels using the same per-scan spot stamps that
feed update_moves:

  - spot <= invalidation on a BULLISH card  → closed as a stop (exit =
    invalidation, exit_date = today)
  - spot >= target on a BULLISH card        → closed as a win
  - mirrored for BEARISH cards
  - cards with no key_levels are never touched
  - already-closed cards are never re-touched
  - the pass returns how many cards it closed, and NEVER raises into
    the scan loop
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.duckdb_engine import DuckDBEngine  # noqa: E402
from services.journal_store import (  # noqa: E402
    init_journal_tables,
    read_trades,
    save_seeds,
)


@pytest.fixture
def engine():
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    yield eng
    try:
        eng._conn.close()
    except Exception:
        pass


def _seed(under="SPY", bias="bull", entry_spot=100.0, key=None, **over):
    bull = bias == "bull"
    kl = {
        "entry": entry_spot,
        "invalidation": round(entry_spot * (0.975 if bull else 1.025), 2),
        "target": round(entry_spot * (1.055 if bull else 0.945), 2),
    }
    base = {
        "ticker": under, "type": "call" if bull else "put", "action": "buy",
        "strike": 100.0, "expiry": "2026-09-18", "quantity": "1",
        "entry_price": 1.25, "exit_price": "", "entry_date": "2026-08-22",
        "exit_date": "", "notes": "", "gex_regime": "", "setup": "score gold",
        "tags": "flowseeker,auto", "ckey": f"{under}|call|100|2026-09-18",
        "key_levels": kl, "bias_hint": bias,
    }
    base.update(over)
    if key is None:
        key = "|".join(str(base.get(k) or "") for k in
                       ("ticker", "type", "action", "strike", "expiry", "entry_date"))
    base["_key"] = key
    return base


class TestLifecyclePass:
    def test_stop_hit_closes_bullish_card_as_loss(self, engine):
        save_seeds(engine, [_seed(entry_spot=100.0)])          # stop 97.5
        n = journal_lifecycle(engine, {"SPY": 96.0})           # spot below stop
        assert n == 1
        row = read_trades(engine)[0]
        assert float(row["exit_price"]) == 97.5                # stopped AT the level
        assert row["exit_date"] != ""

    def test_target_hit_closes_bullish_card_as_win(self, engine):
        save_seeds(engine, [_seed(entry_spot=100.0)])          # target 105.5
        n = journal_lifecycle(engine, {"SPY": 106.0})
        assert n == 1
        row = read_trades(engine)[0]
        assert float(row["exit_price"]) == 105.5

    def test_bearish_card_mirrors(self, engine):
        save_seeds(engine, [_seed(under="QQQ", bias="bear", entry_spot=100.0)])
        n = journal_lifecycle(engine, {"QQQ": 94.0})           # target 94.5 hit
        assert n == 1
        assert float(read_trades(engine)[0]["exit_price"]) == 94.5

    def test_between_levels_card_stays_open(self, engine):
        save_seeds(engine, [_seed(entry_spot=100.0)])          # between 97.5 and 105.5
        n = journal_lifecycle(engine, {"SPY": 101.0})
        assert n == 0
        assert read_trades(engine)[0]["exit_price"] == ""

    def test_no_key_levels_untouched(self, engine):
        s = _seed()
        s["key_levels"] = None
        save_seeds(engine, [s])
        n = journal_lifecycle(engine, {"SPY": 50.0})           # way through any level
        assert n == 0

    def test_closed_cards_never_retouched(self, engine):
        s = _seed()
        s["exit_price"] = 9.99
        s["exit_date"] = "2026-08-20"
        save_seeds(engine, [s])
        n = journal_lifecycle(engine, {"SPY": 50.0})
        assert n == 0
        assert float(read_trades(engine)[0]["exit_price"]) == 9.99

    def test_multiple_tickers_one_pass(self, engine):
        save_seeds(engine, [
            _seed(under="SPY"),                                 # stop hit at 96
            _seed(under="QQQ", bias="bear", entry_spot=200.0),  # target hit at 188
            _seed(under="IWM"),                                 # between levels at 101
        ])
        n = journal_lifecycle(engine, {"SPY": 96.0, "QQQ": 188.0, "IWM": 101.0})
        assert n == 2


# imported late so the fixture module path stays stable
from services.journal_store import journal_lifecycle  # noqa: E402
