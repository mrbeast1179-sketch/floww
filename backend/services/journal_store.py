"""
backend/services/journal_store.py

Server-side persistence for auto-seeded trade-journal entries — the backend
half of the Flowseeker signal-to-trade pipeline. Seeds are written to DuckDB
at execute-time so they survive browser localStorage clears and sync across
devices. The frontend keeps its floww_trades_v2 localStorage store as the
offline cache and merges server rows on load (server wins on conflicts by
updated_at).

Schema mirrors the frontend's floww_trades_v2 entry shape exactly
(ticker, type, action, strike, expiry, quantity, entry_price, exit_price,
entry_date, exit_date, notes, gex_regime, setup, tags) plus provenance:
ckey (alert contract key), source, created_at, updated_at.

Dedupe key = ticker|type|action|strike|expiry|entry_date — identical to
frontend/src/components/flowseeker/autoTrade.js journalSeedKey().
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Dedicated FILE-BACKED store. The shared duckdb_engine.db is :memory:
# (rebuilt each process start) — fine for scan-derived data, wrong for a
# trade journal, which must survive restarts. Same file-per-concern pattern
# as graph_trade_service.research_kg.duckdb.
_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "journal.duckdb"
_engine = None
_lock = threading.Lock()


def get_engine():
    """Lazily-created singleton DuckDBEngine at data/journal.duckdb."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                from services.duckdb_engine import DuckDBEngine
                _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                _engine = DuckDBEngine(str(_DB_PATH))
                logger.info("Journal store opened at %s", _DB_PATH)
    return _engine

_JOURNAL_DDL = """
    CREATE TABLE IF NOT EXISTS flow_journal_trades (
        ckey TEXT,
        ticker TEXT NOT NULL,
        type TEXT,
        action TEXT,
        strike DOUBLE,
        expiry TEXT,
        quantity TEXT,
        entry_price DOUBLE,
        exit_price DOUBLE,
        entry_date TEXT,
        exit_date TEXT,
        notes TEXT,
        gex_regime TEXT,
        setup TEXT,
        tags TEXT,
        source TEXT DEFAULT 'flowseeker-auto',
        created_at TIMESTAMP DEFAULT current_timestamp,
        updated_at TIMESTAMP DEFAULT current_timestamp,
        PRIMARY KEY (ticker, type, action, strike, expiry, entry_date)
    )
"""


def init_journal_tables(engine) -> None:
    """Create the journal table if absent; migrate older shapes in place."""
    engine.execute_write(_JOURNAL_DDL)


def journal_seed_key(seed: dict) -> str:
    """Same composite key as the frontend's journalSeedKey()."""
    return "|".join(str(seed.get(k) or "") for k in
                    ("ticker", "type", "action", "strike", "expiry", "entry_date"))


def _to_db_row(seed: dict) -> dict[str, Any]:
    """floww_trades_v2-shaped seed → column map. Numeric coercion is
    defensive: alerts always carry numeric strike/est_entry but a corrupted
    payload must not 500 the execute route."""
    def _num(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return {
        "ckey": seed.get("ckey"),
        "ticker": str(seed.get("ticker") or "").upper(),
        "type": str(seed.get("type") or "call").lower(),
        "action": str(seed.get("action") or "buy").lower(),
        "strike": _num(seed.get("strike")),
        "expiry": str(seed.get("expiry") or ""),
        "quantity": str(seed.get("quantity") or "1"),
        "entry_price": _num(seed.get("entry_price")),
        "exit_price": _num(seed.get("exit_price")) if seed.get("exit_price") not in ("", None) else None,
        "entry_date": str(seed.get("entry_date") or ""),
        "exit_date": str(seed.get("exit_date") or ""),
        "notes": str(seed.get("notes") or ""),
        "gex_regime": str(seed.get("gex_regime") or ""),
        "setup": str(seed.get("setup") or ""),
        "tags": str(seed.get("tags") or ""),
        "source": str(seed.get("source") or "flowseeker-auto"),
    }


def save_seeds(engine, seeds: list[dict]) -> int:
    """Insert seeds, skipping contracts already journaled. Returns count added."""
    added = 0
    for seed in seeds or []:
        row = _to_db_row(seed)
        if not row["ticker"]:
            continue
        try:
            engine.execute_write(
                """
                INSERT INTO flow_journal_trades (
                    ckey, ticker, type, action, strike, expiry, quantity,
                    entry_price, exit_price, entry_date, exit_date, notes,
                    gex_regime, setup, tags, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [[row["ckey"], row["ticker"], row["type"], row["action"],
                 row["strike"], row["expiry"], row["quantity"],
                 row["entry_price"], row["exit_price"], row["entry_date"],
                 row["exit_date"], row["notes"], row["gex_regime"],
                 row["setup"], row["tags"], row["source"]]],
            )
            added += 1
        except Exception as e:
            # PK conflict = already journaled (expected on re-execute);
            # anything else gets logged but never breaks the trade path.
            if "Constraint" not in type(e).__name__ and "constraint" not in str(e).lower():
                logger.warning("journal seed insert failed for %s: %s",
                               journal_seed_key(row), e)
    return added


_COLS = ("ckey, ticker, type, action, strike, expiry, quantity, entry_price, "
         "exit_price, entry_date, exit_date, notes, gex_regime, setup, tags, "
         "source, created_at, updated_at")


def read_trades(engine, *, status: str = "all", days: int = 365) -> list[dict]:
    """Read journal rows as floww_trades_v2-shaped dicts (+ provenance).
    status: all | open | closed. Closed = has exit_date OR any exit price."""
    cutoff = f"current_timestamp - INTERVAL '{int(days)}' DAY"
    where = ""
    if status == "open":
        where = (f"WHERE COALESCE(exit_date, '') = '' AND exit_price IS NULL "
                 f"AND created_at > {cutoff}")
    elif status == "closed":
        where = "WHERE NOT (COALESCE(exit_date, '') = '' AND exit_price IS NULL)"
    rows = engine.query(
        f"SELECT {_COLS} FROM flow_journal_trades {where} "
        f"ORDER BY created_at DESC LIMIT 2000"
    )
    out: list[dict] = []
    for r in rows:
        out.append({
            **{k: r.get(k) for k in
               ("ticker", "type", "action", "expiry", "quantity", "notes",
                "gex_regime", "setup", "tags", "ckey", "source")},
            "strike": r.get("strike"),
            "entry_price": r.get("entry_price"),
            # frontend treats "" as no-exit
            "exit_price": r["exit_price"] if r.get("exit_price") is not None else "",
            "exit_date": r.get("exit_date") or "",
            "entry_date": r.get("entry_date") or "",
            "created_at": str(r.get("created_at") or ""),
            "updated_at": str(r.get("updated_at") or ""),
        })
    return out


def close_trade(engine, key: str, *, exit_price: float, exit_date: str) -> bool:
    """Set exit fields on the trade matching a journalSeedKey() key."""
    parts = str(key).split("|")
    if len(parts) != 6:
        return False
    ticker, ctype, action, strike, expiry, entry_date = parts
    try:
        strike_f = float(strike) if strike else None
    except ValueError:
        return False

    existing = engine.query(
        "SELECT ticker FROM flow_journal_trades WHERE ticker = ? AND type = ? "
        "AND action = ? AND strike IS NOT DISTINCT FROM ? AND expiry = ? AND entry_date = ?",
        [ticker.upper(), ctype.lower(), action.lower(), strike_f, expiry, entry_date],
    )
    if not existing:
        return False
    engine.execute_write(
        """
        UPDATE flow_journal_trades
        SET exit_price = ?, exit_date = ?, updated_at = current_timestamp
        WHERE ticker = ? AND type = ? AND action = ?
          AND strike IS NOT DISTINCT FROM ? AND expiry = ? AND entry_date = ?
        """,
        [(float(exit_price), exit_date, ticker.upper(), ctype.lower(),
         action.lower(), strike_f, expiry, entry_date)],
    )
    return True
