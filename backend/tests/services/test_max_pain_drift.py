"""
backend/tests/services/test_max_pain_drift.py

Max-Pain Drift test profile (steal-list #9 deferred completion).
==================================================================

28 hand-verified cases split between three test families:

  PURE-LOGIC (compute_max_pain_drift)
  1.  test_empty_snapshots_returns_graceful_zero_response
  2.  test_single_snapshot_returns_insufficient_data_with_pin_score
  3.  test_two_snapshots_matches_1d_and_Nd_drift
  4.  test_seven_stable_days_returns_zero_drift_and_stable_label
  5.  test_seven_days_migrating_toward_spot_returns_positive_drift_toward_now
  6.  test_seven_days_migrating_away_from_spot_returns_negative_drift_toward_now
  7.  test_long_stable_window_at_spot_returns_high_pin_score
  8.  test_reverse_chronological_input_auto_sorted
  9.  test_nan_spot_returns_drift_toward_now_None_with_warning
  10. test_missing_max_pain_strike_filtered_with_warning
  11. test_future_dated_snapshots_dropped_with_warning
  12. test_compute_returns_documented_dict_keys

  DUCKDB I/O (init_max_pain_daily_table, accumulate_today, read_recent_drift)
  13. test_init_table_idempotent_multiple_calls_no_crash
  14. test_accumulate_today_idempotent_same_date_overwrites
  15. test_accumulate_three_distinct_tickers_does_not_cross_contaminate
  16. test_read_recent_returns_chronological_with_correct_n
  17. test_read_recent_empty_table_returns_empty_list
  18. test_db_query_exception_returns_empty_list_with_warning_logged

  PER-EXPIRY + MIGRATION + SCHEDULER + LOW-POLISH + READ-DRIFT-FILTER (steal-list #9 PARTIAL → DONE)
  19. test_accumulate_today_per_expiry_writes_n_rows_and_updates
  20. test_schema_migration_drops_legacy_table_then_recreates
  21. test_scheduler_has_max_pain_poll_method
  22. test_route_default_days_is_30
  23. test_silently_dropped_non_dict_rows_log_debug
  24. test_read_recent_drift_per_expiry_empty_db_returns_empty_list
  25. test_read_recent_drift_per_expiry_groups_by_expiry_and_skips_overall
  26. test_read_recent_drift_per_expiry_respects_n_days_window
  27. test_read_recent_drift_per_expiry_drops_nan_strike_rows
  28. test_accumulate_today_per_expiry_drops_nan_strike_rows

(Audit: bumped 23 → 28 after the per-expiry drift tile round added
the popular filter / n_days / NaN-drift read-side semantics + the
belt-and-suspenders write-side NaN-filter regression guard.)
"""

from __future__ import annotations

import math
import warnings as _warnings

import pytest

from services.max_pain_drift import (
    accumulate_today,
    accumulate_today_per_expiry,
    compute_max_pain_drift,
    init_max_pain_daily_table,
    read_recent_drift,
    read_recent_drift_per_expiry,
)

# ─────────────────────────────────────────────────────────────────────
# DuckDB test fixture — fresh in-memory engine per test, mirrors
# backend/tests/services/test_duckdb_writes.py + test_replay_engine.py.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe
    engine = dbe.DuckDBEngine(":memory:")
    yield engine
    # :memory: is wiped at close; no teardown needed.


def _row(date_, symbol, strike, spot):
    """Build a snapshot row matching what read_recent_drift returns."""
    return {
        "snapshot_date": date_,
        "symbol": symbol,
        "spot": spot,
        "max_pain_strike": strike,
        "total_loss_at_strike": 0.0,
        "calls_at_strike": 0,
        "puts_at_strike": 0,
        "expiry": None,
    }


# ─────────────────────────────────────────────────────────────────────
# 1. PURE-LOGIC — pure-function tests on compute_max_pain_drift
# ─────────────────────────────────────────────────────────────────────


def test_empty_snapshots_returns_graceful_zero_response():
    out = compute_max_pain_drift([])
    assert out["n_days_covered"] == 0
    assert out["today_strike"] is None
    assert out["drift_strike_1d"] is None
    assert out["drift_strike_Nd"] is None
    assert out["pin_probability_score"] == 0.0
    assert out["direction_label"] == "insufficient_data"
    assert out["warnings"] == ["snapshots must be a list"] \
        if False else isinstance(out["warnings"], list)


def test_single_snapshot_returns_insufficient_data_with_pin_score():
    """A single snapshot can't compute drift, but CAN compute the
    pin-probability score against today's spot — useful signal even
    with one sample."""
    from datetime import date
    row = _row(date(2026, 7, 15), "SPY", 519.0, 520.0)
    out = compute_max_pain_drift([row])
    assert out["n_days_covered"] == 1
    assert out["today_strike"] == 519.0
    assert out["today_spot"] == 520.0
    assert out["yesterday_strike"] is None
    assert out["drift_strike_1d"] is None
    assert out["drift_strike_Nd"] is None
    assert out["direction_label"] == "insufficient_data"
    # Trace: |519-520| / (0.05 × 520) = 1/26 ≈ 0.0385 → pin = 1 - 0.0385 = 0.9615.
    # (Author's mental shortcut “1 - 1/5 = 0.8” conflated the 5%-of-spot
    # decay base with the actual absolute $ delta — those are very
    # different in scale.)
    assert math.isclose(out["pin_probability_score"], 0.9615, rel_tol=1e-2)


def test_two_snapshots_matches_1d_and_Nd_drift():
    """With exactly two snapshots, drift_1d and drift_Nd collapse to the
    same scalar — the most-recent one-step delta."""
    from datetime import date, timedelta
    rows = [
        _row(date(2026, 7, 14), "SPY", 515.0, 518.0),
        _row(date(2026, 7, 15), "SPY", 518.0, 522.0),
    ]
    out = compute_max_pain_drift(rows)
    assert out["n_days_covered"] == 2
    assert out["drift_strike_1d"] == 3.0
    assert out["drift_strike_Nd"] == 3.0
    assert out["yesterday_strike"] == 515.0
    # drift_toward_now = |515-522| - |518-522| = 7 - 4 = 3 (positive = toward)
    assert out["drift_toward_now"] == 3.0
    assert out["direction_label"] == "migrating_toward_spot"


def test_seven_stable_days_returns_zero_drift_and_stable_label():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _row(today - timedelta(days=i), "SPY", 520.0, 520.5)
        for i in range(7)
    ]
    out = compute_max_pain_drift(rows)
    assert out["n_days_covered"] == 7
    assert out["drift_strike_1d"] == 0.0
    assert out["drift_strike_Nd"] == 0.0
    assert out["drift_toward_now"] == 0.0
    assert out["direction_label"] == "stable"


def test_seven_days_migrating_toward_spot_returns_positive_drift_toward_now():
    """Strike migrates from 100 to 110 over 7 days; spot stays at 105.
    d_old = |100-105|=5 ; d_new = |110-105|=5 ; drift = 0 — pin moving
    AROUND then away. Bump the strike trajectory to start FAR (100) and
    end CLOSE (105.5) for a true toward-spot signal."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _row(today - timedelta(days=6 - i), "SPY", 100.0 + i * 1.0, 105.0)
        for i in range(7)   # strikes 100..106
    ]
    out = compute_max_pain_drift(rows)
    assert out["n_days_covered"] == 7
    assert out["drift_strike_1d"] == 1.0
    assert out["drift_strike_Nd"] == 6.0
    # d_old = |100-105|=5 ; d_new = |106-105|=1 ; drift = 4 (toward-spot)
    assert out["drift_toward_now"] == 4.0
    assert out["direction_label"] == "migrating_toward_spot"


def test_seven_days_migrating_away_from_spot_returns_negative_drift_toward_now():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _row(today - timedelta(days=6 - i), "SPY", 105.0 + i * 1.0, 105.0)
        for i in range(7)   # strikes 105..111
    ]
    out = compute_max_pain_drift(rows)
    assert out["drift_strike_1d"] == 1.0
    assert out["drift_strike_Nd"] == 6.0
    # d_old = |105-105|=0 ; d_new = |111-105|=6 ; drift = -6 (away)
    assert out["drift_toward_now"] == -6.0
    assert out["direction_label"] == "migrating_away"


def test_long_stable_window_at_spot_returns_high_pin_score():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _row(today - timedelta(days=29 - i), "SPY", 520.0 + (i % 3) * 0.1,
             520.0)
        for i in range(30)
    ]
    out = compute_max_pain_drift(rows)
    assert out["n_days_covered"] == 30
    # Strike within 0.3 of spot = pin_score > 0.96.
    assert out["pin_probability_score"] > 0.95


def test_reverse_chronological_input_auto_sorted():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    # Input is given in DESCENDING date order (newest first); strikes
    # are configured so that the most-recent date (today) carries the
    # HIGHEST strike. After auto-sort ASC by date, today_strike should
    # equal the highest strike driven by the loop index 0.
    rows_desc = [
        _row(today - timedelta(days=i), "SPY", 130.0 - i * 5.0, 100.0)
        for i in range(7)   # dates DESC, strikes 130 down to 100
    ]
    out = compute_max_pain_drift(rows_desc)
    # After auto-sort ASC by date: today has strike 130 (i=0), oldest
    # date (today-6) has strike 100 (i=6).
    assert out["n_days_covered"] == 7
    assert out["today_strike"] == 130.0
    assert out["drift_strike_Nd"] == 30.0


def test_nan_spot_returns_drift_toward_now_None_with_warning():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        {"snapshot_date": today - timedelta(days=2),
         "max_pain_strike": 515.0, "spot": float("nan")},
        {"snapshot_date": today - timedelta(days=1),
         "max_pain_strike": 517.0, "spot": 520.0},
        {"snapshot_date": today, "max_pain_strike": 519.0, "spot": 520.0},
    ]
    out = compute_max_pain_drift(rows)
    # NaN is not isfinite → coerce to None → drift_toward_now falls
    # back with a warning surfaced.
    assert out["drift_toward_now"] is None
    assert any("spot" in w and "not finite" in w for w in out["warnings"])


def test_missing_max_pain_strike_filtered_with_warning():
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        {"snapshot_date": today - timedelta(days=1),
         "max_pain_strike": None, "spot": 520.0},
        {"snapshot_date": today,
         "max_pain_strike": 519.0, "spot": 520.0},
    ]
    out = compute_max_pain_drift(rows)
    # The None-strike row is dropped; only one survives.
    assert out["n_days_covered"] == 1
    assert out["today_strike"] == 519.0
    assert any("max_pain_strike missing" in w or "NaN" in w
               for w in out["warnings"])


def test_future_dated_snapshots_dropped_with_warning():
    from datetime import date, timedelta
    today = date.today()
    rows = [
        _row(today - timedelta(days=1), "SPY", 519.0, 520.0),
        _row(today + timedelta(days=1), "SPY", 521.0, 522.0),    # future!
        _row(today, "SPY", 520.0, 520.5),
    ]
    out = compute_max_pain_drift(rows)
    assert out["n_days_covered"] == 2
    assert any("future-dated" in w for w in out["warnings"])


def test_compute_returns_documented_dict_keys():
    out = compute_max_pain_drift([])
    expected = {
        "today_strike", "today_spot", "yesterday_strike",
        "drift_strike_1d", "drift_strike_Nd", "drift_toward_now",
        "drift_velocity_per_day", "pin_probability_score",
        "direction_label", "n_days_covered", "warnings",
    }
    assert set(out.keys()) == expected


# ─────────────────────────────────────────────────────────────────────
# 2. DuckDB I/O — init + accumulate + read_recent (in-memory engine)
# ─────────────────────────────────────────────────────────────────────


def test_init_table_idempotent_multiple_calls_no_crash(fresh_engine):
    init_max_pain_daily_table(fresh_engine)
    # Second call MUST NOT raise.
    init_max_pain_daily_table(fresh_engine)
    init_max_pain_daily_table(fresh_engine)
    # And it should still expose exactly one max_pain_daily row count = 0.
    rows = fresh_engine.query(
        "SELECT count(*) AS n FROM max_pain_daily"
    )
    assert rows[0]["n"] == 0


def test_accumulate_today_idempotent_same_date_overwrites(fresh_engine):
    """Two accumulate calls on the same (date, symbol) MUST yield exactly
    one row with the SECOND call's values (UPSERT behavior)."""
    from datetime import date
    init_max_pain_daily_table(fresh_engine)
    fixed_date = date(2026, 7, 15)
    accumulate_today(
        fresh_engine, "SPY", 520.0,
        {"max_pain_strike": 510.0, "total_loss_at_strike": 100.0,
         "calls_at_strike": 0, "puts_at_strike": 0},
        snapshot_date=fixed_date,
    )
    accumulate_today(
        fresh_engine, "SPY", 521.0,
        {"max_pain_strike": 511.0, "total_loss_at_strike": 200.0,
         "calls_at_strike": 5, "puts_at_strike": 7},
        snapshot_date=fixed_date,
    )
    rows = read_recent_drift(fresh_engine, "SPY", n_days=30)
    assert len(rows) == 1
    assert rows[0]["max_pain_strike"] == 511.0
    assert rows[0]["spot"] == 521.0
    assert rows[0]["calls_at_strike"] == 5
    assert rows[0]["puts_at_strike"] == 7


def test_accumulate_three_distinct_tickers_does_not_cross_contaminate(fresh_engine):
    """Same date, three tickers — three rows, no overwrite."""
    from datetime import date
    init_max_pain_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    for sym, strike in [("SPY", 510.0), ("QQQ", 460.0), ("IWM", 215.0)]:
        accumulate_today(
            fresh_engine, sym, 500.0,
            {"max_pain_strike": strike,
             "total_loss_at_strike": 100.0, "calls_at_strike": 1,
             "puts_at_strike": 2},
            snapshot_date=today,
        )
    rows = fresh_engine.query(
        "SELECT symbol, max_pain_strike FROM max_pain_daily "
        "ORDER BY symbol"
    )
    assert len(rows) == 3
    sym_to_strike = {r["symbol"]: r["max_pain_strike"] for r in rows}
    assert sym_to_strike == {"SPY": 510.0, "QQQ": 460.0, "IWM": 215.0}


def test_read_recent_returns_chronological_with_correct_n(fresh_engine):
    """Insert 7 days of SPY snapshots; read n_days=3 returns the LAST 3
    in chronological order (oldest first)."""
    from datetime import date, timedelta
    init_max_pain_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    for i in range(7):
        accumulate_today(
            fresh_engine, "SPY", 500.0 + i,
            {"max_pain_strike": 510.0 + i,
             "total_loss_at_strike": 100.0, "calls_at_strike": 0,
             "puts_at_strike": 0},
            snapshot_date=today - timedelta(days=6 - i),
        )
    rows = read_recent_drift(fresh_engine, "SPY", n_days=3)
    assert len(rows) == 3
    # Rows should be sorted ASCENDING by date — the last 3 days.
    dates = [r["snapshot_date"] for r in rows]
    assert dates == sorted(dates)
    # The newest one is today, with the highest strike.
    assert rows[-1]["snapshot_date"] == today
    assert rows[-1]["max_pain_strike"] == 516.0  # 510 + 6


def test_read_recent_empty_table_returns_empty_list(fresh_engine):
    init_max_pain_daily_table(fresh_engine)
    rows = read_recent_drift(fresh_engine, "ZZZZ", n_days=14)
    assert rows == []


def test_db_query_exception_returns_empty_list_with_warning_logged(fresh_engine, caplog=None):
    """If the SQL execution fails (e.g. column mismatch), read_recent_drift
    MUST swallow the exception and return [] rather than crashing the route.
    The bad SQL forces a DuckDB BinderError."""
    init_max_pain_daily_table(fresh_engine)
    # Monkeypatch engine.query to raise.
    fresh_engine.query = lambda *_a, **_kw: (_ for _ in ()).throw(
        RuntimeError("simulated binder error")
    )
    with _warnings.catch_warnings():
        rows = read_recent_drift(fresh_engine, "SPY", n_days=7)
    assert rows == []


# ─────────────────────────────────────────────────────────────────────
# 3. PER-EXPIRY + MIGRATION + SCHEDULER (steal-list #9 PARTIAL → DONE)
# ─────────────────────────────────────────────────────────────────────


def test_accumulate_today_per_expiry_writes_n_rows_and_updates(fresh_engine):
    """``accumulate_today_per_expiry`` writes ONE row per expiry for the
    same (date, ticker) — the new PK ``(snapshot_date, symbol, expiry)``
    permits multiple rows per day. Re-running with a subset UPSERTs
    (no duplicates) and updates existing fields.
    """
    from datetime import date
    init_max_pain_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    rows = [
        {"expiry": "2026-07-16", "max_pain_strike": 510.0,
         "total_loss_at_strike": 100.0, "calls_at_strike": 5,
         "puts_at_strike": 5},
        {"expiry": "2026-07-17", "max_pain_strike": 515.0,
         "total_loss_at_strike": 150.0, "calls_at_strike": 7,
         "puts_at_strike": 3},
        {"expiry": "2026-07-22", "max_pain_strike": 520.0,
         "total_loss_at_strike": 200.0, "calls_at_strike": 10,
         "puts_at_strike": 10},
    ]
    written = accumulate_today_per_expiry(
        fresh_engine, "TEST", 500.0, rows, snapshot_date=today,
    )
    assert written == 3

    db_rows = fresh_engine.query(
        "SELECT expiry, max_pain_strike, calls_at_strike "
        "FROM max_pain_daily ORDER BY expiry"
    )
    assert len(db_rows) == 3
    assert db_rows[0]["expiry"] == "2026-07-16"
    assert db_rows[0]["max_pain_strike"] == 510.0
    assert db_rows[2]["max_pain_strike"] == 520.0

    # Re-running with a SUBSET of the same expiries UPSERTs the matching
    # rows (one per (date, ticker, expiry)) AND leaves untouched rows
    # alone — no duplicate insert, no row loss.
    rows_update = [
        {"expiry": "2026-07-16", "max_pain_strike": 511.0,
         "total_loss_at_strike": 100.0, "calls_at_strike": 50,
         "puts_at_strike": 50},
    ]
    accumulate_today_per_expiry(
        fresh_engine, "TEST", 500.0, rows_update, snapshot_date=today,
    )
    db_rows_updated = fresh_engine.query(
        "SELECT expiry, max_pain_strike, calls_at_strike "
        "FROM max_pain_daily ORDER BY expiry"
    )
    assert len(db_rows_updated) == 3   # subset updated, NOT duplicated
    assert db_rows_updated[0]["max_pain_strike"] == 511.0
    assert db_rows_updated[0]["calls_at_strike"] == 50
    assert db_rows_updated[2]["max_pain_strike"] == 520.0  # untouched


def test_schema_migration_drops_legacy_table_then_recreates(fresh_engine):
    """If a legacy ``max_pain_daily`` table exists with PK on (date, symbol)
    only (no ``expiry`` in PK), the migration drops + recreates so the
    new PK ``(snapshot_date, symbol, expiry)`` is in force.
    """
    # Seed the legacy schema manually.
    fresh_engine.execute_write(
        "CREATE TABLE max_pain_daily ("
        "snapshot_date DATE, symbol VARCHAR, spot DOUBLE, "
        "max_pain_strike DOUBLE, total_loss_at_strike DOUBLE, "
        "calls_at_strike BIGINT, puts_at_strike BIGINT, "
        "expiry VARCHAR, "
        "PRIMARY KEY (snapshot_date, symbol)"
        ")"
    )
    # Should detect legacy PK and DROP+recreate.
    init_max_pain_daily_table(fresh_engine)
    # New PK has expiry. Use information_schema (DuckDB-portable) to
    # check membership — pragma_table_info column names differ
    # between SQLite (`name`/`pk`) and DuckDB (`column_name`/...).
    rows = fresh_engine.query(
        "SELECT kcu.column_name "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON tc.constraint_name = kcu.constraint_name "
        "WHERE tc.table_name = 'max_pain_daily' "
        "AND tc.constraint_type = 'PRIMARY KEY' "
        "AND kcu.column_name = 'expiry'"
    )
    assert rows, "expiry should be in PRIMARY KEY after migration"


def test_scheduler_has_max_pain_poll_method():
    """Smoke check: ``PollingScheduler`` exposes the new daily cron."""
    from services.scheduler import PollingScheduler
    sched = PollingScheduler()
    assert hasattr(sched, "_poll_max_pain_for_universe")
    assert callable(sched._poll_max_pain_for_universe)


def test_route_default_days_is_30():
    """The ``/api/max_pain_drift/{ticker}`` route default is now ``days=30``
    (was 14 at PARTIAL; user spec bumped to 30).
    """
    import inspect

    from routes.steal_three import max_pain_drift_endpoint
    sig = inspect.signature(max_pain_drift_endpoint)
    assert sig.parameters["days"].default == 30


def test_silently_dropped_non_dict_rows_log_debug(fresh_engine, caplog):
    """``accumulate_today_per_expiry`` defensively drops non-dict rows from
    ``per_expiry_rows``. A debug-time caller chasing a missing write
    could not previously see this happen — the LOW-priority polish
    in this commit adds a ``logging.debug`` emission that names the
    ticker, drop count, and filtered types. This test pins that
    contract so future refactors can't silently regress it back to
    the warn-only-on-coercion-failure behavior.

    The emission sits at DEBUG (not WARNING) on the root logger —
    caplog captures it via ``with caplog.at_level(logging.DEBUG)``.
    Production callers won't get spammed when a single malformed row
    passes by; the log only emerges under ``PYTHONLOGLEVEL=debug`` or
    a logger filter targeting ``services.max_pain_drift``.
    """
    import logging
    from datetime import date
    init_max_pain_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    per_expiry_rows = [
        # 1 valid dict that survives the filter.
        {"expiry": "2026-07-16", "max_pain_strike": 510.0,
         "total_loss_at_strike": 100.0, "calls_at_strike": 5,
         "puts_at_strike": 5},
        # 3 non-dict rows that the defensive filter silently drops.
        "not a dict",
        None,
        [1, 2, 3],
    ]
    with caplog.at_level(logging.DEBUG):
        written = accumulate_today_per_expiry(
            fresh_engine, "TEST", 500.0, per_expiry_rows, snapshot_date=today,
        )
    # Only 1 of the 4 rows survived — the 1 valid dict.
    assert written == 1
    db_rows = fresh_engine.query(
        "SELECT expiry, max_pain_strike FROM max_pain_daily "
        "WHERE symbol = 'TEST' ORDER BY expiry"
    )
    assert len(db_rows) == 1
    assert db_rows[0]["expiry"] == "2026-07-16"
    # The drop-count debug log MUST have fired, named the ticker,
    # and reported the dropped count. This is the contract the
    # user-requested polish establishes.
    matching = [
        r for r in caplog.records
        if r.levelno == logging.DEBUG
        and "non-dict row(s)" in r.getMessage()
        and "TEST" in r.getMessage()
    ]
    assert len(matching) == 1, (
        f"expected exactly one DROP-COUNT debug log naming ticker=TEST; "
        f"got: {[r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]}"
    )
    msg = matching[0].getMessage()
    assert "3" in msg, (
        f"expected drop count '3' in debug log message; msg={msg!r}"
    )
    # Type names of dropped rows must be present so a debug-time
    # operator can tell str from NoneType from list at a glance.
    assert "str" in msg or "NoneType" in msg or "list" in msg, (
        f"expected the filtered row type names in the debug message; "
        f"msg={msg!r}"
    )


def _seed_per_expiry_history(fresh_engine, ticker: str, days: int = 6,
                              n_expiries: int = 3) -> list[str]:
    """Helper: accumulate_today_per_expiry N days of history N expiries.
    Returns the sorted list of expiry ISO dates in insertion order."""
    from datetime import date, timedelta
    init_max_pain_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    expiries = [
        "2026-07-17",  # 1DTE (today + 2)
        "2026-07-22",  # 1-week
        "2026-08-21",  # 1-month
    ][:n_expiries]
    base_strikes = (745.0, 750.0, 760.0)
    for offset in range(days):
        snap_date = today - timedelta(days=offset)
        per_expiry_rows = [
            {
                "expiry": exp,
                "max_pain_strike": base_strikes[i] + offset * 0.5,
                "total_loss_at_strike": 100.0 + offset,
                "calls_at_strike": 5 + offset,
                "puts_at_strike": 5 + offset,
            }
            for i, exp in enumerate(expiries)
        ]
        accumulate_today_per_expiry(
            fresh_engine, ticker, 750.0, per_expiry_rows,
            snapshot_date=snap_date,
        )
    # Also seed one OVERALL row so the per-expiry filter has to skip it.
    accumulate_today(
        fresh_engine, ticker, 750.0,
        {"max_pain_strike": 745.0, "total_loss_at_strike": 100.0,
         "calls_at_strike": 5, "puts_at_strike": 5},
        snapshot_date=today,
    )
    return expiries


def test_read_recent_drift_per_expiry_empty_db_returns_empty_list(fresh_engine):
    """No rows in max_pain_daily → empty list. No warnings."""
    from services.max_pain_drift import read_recent_drift_per_expiry
    init_max_pain_daily_table(fresh_engine)
    out = read_recent_drift_per_expiry(fresh_engine, "SPY", n_days=30)
    assert out == []


def test_read_recent_drift_per_expiry_groups_by_expiry_and_skips_overall(fresh_engine):
    """The OVERALL row (``expiry == ''``) is filtered out so the chart
    only sees the per-expiry trajectories. Expiries with rows are
    returned sorted ASC by ISO date string."""
    from datetime import date as _date
    expected_expiries = _seed_per_expiry_history(
        fresh_engine, "TEST", days=6, n_expiries=3,
    )
    out = read_recent_drift_per_expiry(
        fresh_engine, "TEST", n_days=30, today=_date(2026, 7, 15))
    # One entry per listed expiry, none for the OVERALL row.
    assert [g["expiry"] for g in out] == expected_expiries
    # Each expiry group has 6 history points (6 days seeded).
    for g in out:
        assert g["n_points"] == 6
        assert len(g["history"]) == 6
        # History sorted ASC by date.
        dates = [pt["date"] for pt in g["history"]]
        assert dates == sorted(dates)
        # first_strike/last_strike/drift_strike_Nd agree with the
        # endpoints of the seeded array (note strikes drift
        # +0.5 per day from the base).
        assert g["first_strike"] is not None
        assert g["last_strike"] is not None
        assert g["drift_strike_Nd"] is not None


def test_read_recent_drift_per_expiry_respects_n_days_window(fresh_engine):
    """n_days trims the per-group history to the trailing N days.

    The window uses *inclusive* boundaries:
        cutoff = date.today() - n_days
        kept_dates = [d for d in history if d >= cutoff]
    For n_days=4 + a 10-day seed anchored to date.today(): cutoff =
    today-4, keeps offsets 0..4 = 5 points (today, today-1, ..., today-4).
    The anchor is ``date.today()`` (not a hardcoded 2026-07-15) so the
    test is portable across machines with different system clocks.
    """
    from datetime import date, timedelta
    init_max_pain_daily_table(fresh_engine)
    today = date.today()    # anchor to current date (portable)
    # Seed 10 days of history for ONE expiry.
    for offset in range(10):
        snap_date = today - timedelta(days=offset)
        accumulate_today_per_expiry(
            fresh_engine, "TEST", 750.0,
            [{"expiry": "2026-08-21",
              "max_pain_strike": 750.0 + offset,
              "total_loss_at_strike": 100.0, "calls_at_strike": 1,
              "puts_at_strike": 1}],
            snapshot_date=snap_date,
        )
    # n_days=4 keeps offsets 0..4 (inclusive boundary) = 5 points.
    out = read_recent_drift_per_expiry(fresh_engine, "TEST", n_days=4)
    assert len(out) == 1
    assert out[0]["expiry"] == "2026-08-21"
    assert out[0]["n_points"] == 5
    # Drift uses the truncated window's endpoints (latest - oldest
    # within the 4-day window).
    assert out[0]["first_strike"] is not None
    assert out[0]["last_strike"] is not None
    # n_days=999 still bounded by the natural cutoff (returns all 10).
    out_full = read_recent_drift_per_expiry(fresh_engine, "TEST", n_days=999)
    assert out_full[0]["n_points"] == 10


def test_read_recent_drift_per_expiry_drops_nan_strike_rows(fresh_engine):
    """NaN strike rows are silently dropped by the **read-side** filter
    (the per-expiry group keeps the finite-strike rows only).

    Test approach: write 2 finite rows on distinct dates via
    ``accumulate_today`` (already-validated path) and then inject
    1 NaN row via direct SQL INSERT — bypassing ``_safe_float`` so
    the NaN reaches the table. The read filter
    ``not (strike_f == strike_f)`` is then responsible for dropping
    the NaN row, yielding ``n_points == 2``.

    This eliminates the prior entangled WRITE+READ NaN semantics by
    isolating the read filter as the only NaN-drop mechanism.
    """
    from datetime import date, timedelta
    init_max_pain_daily_table(fresh_engine)
    today = date.today()
    # 2 finite rows on distinct dates via accumulate_today.
    for offset, strike in [(0, 750.0), (5, 752.0)]:
        accumulate_today(
            fresh_engine, "TEST", 750.0,
            {"max_pain_strike": strike,
             "total_loss_at_strike": 100.0, "calls_at_strike": 1,
             "puts_at_strike": 1},
            snapshot_date=today - timedelta(days=offset),
            expiry="2026-08-21",
        )
    # Inject 1 NaN row via direct SQL — bypass _safe_float.
    fresh_engine.execute_write(
        "INSERT INTO max_pain_daily "
        "(snapshot_date, symbol, spot, max_pain_strike, "
        " total_loss_at_strike, calls_at_strike, puts_at_strike, "
        " expiry) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(today - timedelta(days=2), "TEST", 750.0,
          float("nan"), 100.0, 1, 1, "2026-08-21")],
    )
    out = read_recent_drift_per_expiry(fresh_engine, "TEST", n_days=30)
    assert len(out) == 1
    assert out[0]["expiry"] == "2026-08-21"
    # NaN row dropped by read-side filter; only 750.0 + 752.0 survive.
    assert out[0]["n_points"] == 2


def test_accumulate_today_per_expiry_drops_nan_strike_rows(fresh_engine):
    """Write side: a NaN-strike row in ``per_expiry_rows`` MUST NOT reach
    ``engine.execute_write`` — ``_safe_float`` returns ``None`` for
    NaN and the row is ``continue``-skipped BEFORE tuple construction.

    Belt-and-suspenders for the read-side NaN filter in
    test_read_recent_drift_per_expiry_drops_nan_strike_rows above.
    Without this test, a future refactor that accidentally removes
    the ``_safe_float`` upstream of the tuple-build loop would let
    NaN tuples reach the UPSERT, and the read filter would silently
    hide them — undetectable without an explicit write-side assertion.

    3 rows on the SAME snapshot_date with DISTINCT expiry strings so
    UPSERT-by-PK does NOT collapse the 3 rows into 1 — the test can
    independently observe the NaN-drop at the tuple-build stage.
    """
    from datetime import date
    init_max_pain_daily_table(fresh_engine)
    today = date.today()
    rows = [
        {"expiry": "2026-07-16", "max_pain_strike": 510.0,
         "total_loss_at_strike": 100.0, "calls_at_strike": 5,
         "puts_at_strike": 5},
        # NaN-strike row drops at the _safe_float → continue path.
        {"expiry": "2026-07-22", "max_pain_strike": float("nan"),
         "total_loss_at_strike": 200.0, "calls_at_strike": 10,
         "puts_at_strike": 10},
        {"expiry": "2026-07-29", "max_pain_strike": 520.0,
         "total_loss_at_strike": 300.0, "calls_at_strike": 15,
         "puts_at_strike": 15},
    ]
    written = accumulate_today_per_expiry(
        fresh_engine, "TEST", 500.0, rows, snapshot_date=today,
    )
    # NaN row filtered before tuple-build → written = 2 finite rows.
    assert written == 2
    # Belt-and-suspenders: read-back check pins BOTH the write-side
    # return AND the storage-side observation. Reading back lets a
    # regression where _safe_float returns the wrong thing be
    # caught even if the return-value assertion alone would mask it.
    db_rows = fresh_engine.query(
        "SELECT expiry, max_pain_strike FROM max_pain_daily "
        "WHERE symbol = 'TEST' ORDER BY expiry"
    )
    assert len(db_rows) == 2
    assert db_rows[0]["expiry"] == "2026-07-16"
    assert db_rows[1]["expiry"] == "2026-07-29"
    # Per-row NaN check — NaN != NaN means a NaN row would fail
    # this assertion. Catches a regression where _safe_float is
    # bypassed AND DuckDB stores NaN as a valid DOUBLE.
    for r in db_rows:
        strike = r["max_pain_strike"]
        assert strike == strike, (
            f"row {r['expiry']} has NaN strike in DB — write filter regressed"
        )
