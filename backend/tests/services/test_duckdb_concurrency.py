"""Concurrency safety for the shared DuckDBEngine connection.

DuckDB connections are NOT thread-safe (threadsafety==1): two threads calling
`execute().fetchdf()` on the same connection clobber each other's pending
result — the 2026-07-11 audit reproduced both wrong result sets and a hard
segfault. In production the single global `db = DuckDBEngine()` is read by the
GET /api/vpin/{ticker}/history route (event-loop thread) while the 50ms flush
loop and the ingestion pipeline write on pool threads → simultaneous access.

This test hammers `query()` from many threads and asserts every call returns
the correct result. Without serialization, concurrent reads return [] (the
error is swallowed) or the wrong count.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from services.duckdb_engine import DuckDBEngine

_TICK_COLS = 16  # ticks table column count


def _seed(engine: DuckDBEngine, n: int) -> None:
    rows = [
        (datetime.now(UTC), f"SYM{i % 5}", 1.0, 1.1, 1.05, 10, 5,
         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Yahoo", 0)
        for i in range(n)
    ]
    engine.conn.executemany(
        "INSERT INTO ticks VALUES (" + ",".join(["?"] * _TICK_COLS) + ")", rows
    )


def test_concurrent_queries_return_correct_results():
    engine = DuckDBEngine(":memory:")
    _seed(engine, 50)

    bad: list = []

    def reader():
        for _ in range(100):
            r = engine.query("SELECT COUNT(*) AS c FROM ticks")
            if not r or r[0].get("c") != 50:
                bad.append(r)

    threads = [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not bad, (
        f"{len(bad)}/800 concurrent queries returned wrong/empty results — "
        "shared DuckDB connection accessed without serialization"
    )


def test_concurrent_reads_and_writes_stay_consistent():
    """Readers see a monotonically non-decreasing count while a writer inserts;
    no reader ever gets an empty/garbage result mid-stream."""
    engine = DuckDBEngine(":memory:")
    _seed(engine, 10)

    bad: list = []
    stop = threading.Event()

    def writer():
        for _ in range(200):
            if stop.is_set():
                return
            engine.execute_write(
                "INSERT INTO ticks VALUES (" + ",".join(["?"] * _TICK_COLS) + ")",
                [(datetime.now(UTC), "NEW", 1.0, 1.1, 1.05, 1, 1,
                  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "Yahoo", 0)],
            )

    def reader():
        for _ in range(200):
            r = engine.query("SELECT COUNT(*) AS c FROM ticks")
            if not r or r[0].get("c") is None or r[0]["c"] < 10:
                bad.append(r)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()

    assert not bad, f"{len(bad)} reads returned inconsistent results during concurrent writes"
