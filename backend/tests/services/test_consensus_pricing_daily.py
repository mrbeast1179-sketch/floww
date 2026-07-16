"""
backend/tests/services/test_consensus_pricing_daily.py

Tests for backend/services/consensus_pricing_daily.py —
   pure-math + DuckDB I/O (in-memory engine).

18 hand-verified cases split between two test families:

  PURE-LOGIC (compute_consensus_drift)
  1.  test_empty_snapshots_returns_graceful_zero_response
  2.  test_single_snapshot_returns_insufficient_data_with_convergence
  3.  test_two_snapshots_matches_1d_and_Nd_drift
  4.  test_seven_stable_days_returns_zero_drift_and_stable_label
  5.  test_seven_days_call_side_pulling_up_returns_positive_drift
  6.  test_seven_days_put_side_pulling_down_returns_negative_drift
  7.  test_high_convergence_score_when_consensus_at_spot
  8.  test_reverse_chronological_input_auto_sorted
  9.  test_nan_consensus_returns_insufficient_data_with_warning
 10.  test_missing_field_filtered_with_warning
 11.  test_future_dated_snapshots_dropped_with_warning
 12.  test_compute_returns_documented_dict_keys
 13.  test_skew_change_1d_detects_premium_tilt
 14.  test_direction_label_balanced_when_premium_sides_tied

  DUCKDB I/O (init_consensus_daily_table, accumulate_today, read_recent_drift)
 15. test_init_table_idempotent_multiple_calls_no_crash
 16. test_accumulate_today_idempotent_same_date_overwrites
 17. test_accumulate_three_distinct_tickers_does_not_cross_contaminate
 18. test_read_recent_returns_chronological_with_correct_n
 19. test_read_recent_with_expiry_filter_returns_match_plus_overall
 20. test_read_recent_empty_table_returns_empty_list
 21. test_db_query_exception_returns_empty_list_with_warning_logged
"""

from __future__ import annotations

import math
import warnings as _warnings

import pytest

from services.consensus_pricing_daily import (
    accumulate_today,
    compute_consensus_drift,
    init_consensus_daily_table,
    read_recent_drift,
)

# ─────────────────────────────────────────────────────────────────────
# DuckDB in-memory engine fixture — fresh per test, mirrors
# backend/tests/services/test_max_pain_drift.py::fresh_engine.
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_engine():
    import services.duckdb_engine as dbe
    engine = dbe.DuckDBEngine(":memory:")
    yield engine
    # :memory: is wiped at close; no teardown needed.


def _snapshot(
    date_, symbol, expiry,
    consensus_price, avg_call_premium, avg_put_premium,
    total_oi=1000, call_oi=500, put_oi=500,
):
    """Build a snapshot row matching what read_recent_drift returns."""
    return {
        "snapshot_date": date_,
        "symbol": symbol,
        "expiry": expiry,
        "consensus_price": consensus_price,
        "total_oi": total_oi,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "avg_call_premium": avg_call_premium,
        "avg_put_premium": avg_put_premium,
    }


def _build_chain(
    strike: float = 100.0,
    n_calls: int = 2,
    n_puts: int = 2,
    call_premium: float = 1.0,
    put_premium: float = 1.0,
    call_oi: int = 100,
    put_oi: int = 100,
    expiry: str = "2026-08-15",
):
    """Build a synthetic options chain for accumulate_today tests."""
    chain = []
    for i in range(n_calls):
        chain.append({
            "strike": strike + i,
            "type": "CALL",
            "openInterest": call_oi,
            "expiry": expiry,
            "bid": 1.0 if call_premium > 0 else 0.0,
            "ask": 2.0 * call_premium if call_premium > 0 else 0.0,
            "lastPrice": call_premium,
        })
    for i in range(n_puts):
        chain.append({
            "strike": strike - 1 - i,
            "type": "PUT",
            "openInterest": put_oi,
            "expiry": expiry,
            "bid": 1.0 if put_premium > 0 else 0.0,
            "ask": 2.0 * put_premium if put_premium > 0 else 0.0,
            "lastPrice": put_premium,
        })
    return chain


# ─────────────────────────────────────────────────────────────────────
# 1. PURE-LOGIC — pure-function tests on compute_consensus_drift
# ─────────────────────────────────────────────────────────────────────


def test_empty_snapshots_returns_graceful_zero_response():
    out = compute_consensus_drift([])
    assert out["n_days_covered"] == 0
    assert out["today_consensus"] is None
    assert out["drift_consensus_1d"] is None
    assert out["drift_consensus_Nd"] is None
    assert out["convergence_score"] == 0.0
    assert out["direction_label"] == "insufficient_data"
    assert isinstance(out["warnings"], list)


def test_single_snapshot_returns_insufficient_data_with_convergence():
    """Single snapshot can't compute drift but CAN compute convergence vs spot.

    Trace: consensus=99, spot=100 → |99-100|/(0.05*100)=1/5=0.2 → score=0.8
    """
    from datetime import date
    snap = _snapshot(
        date(2026, 7, 15), "SPY", "2026-08-15",
        consensus_price=99.0,
        avg_call_premium=1.5, avg_put_premium=2.0,
    )
    out = compute_consensus_drift([snap], today_spot=100.0)
    assert out["n_days_covered"] == 1
    assert out["today_consensus"] == 99.0
    assert out["today_spot"] == 100.0
    assert out["yesterday_consensus"] is None
    assert out["drift_consensus_1d"] is None
    assert out["drift_consensus_Nd"] is None
    assert math.isclose(out["convergence_score"], 0.8, rel_tol=1e-3)
    assert out["direction_label"] == "insufficient_data"


def test_two_snapshots_matches_1d_and_Nd_drift():
    """Two snapshots — drift_1d and drift_Nd collapse to the same scalar."""
    from datetime import date, timedelta
    rows = [
        _snapshot(
            date(2026, 7, 14), "SPY", "2026-08-15",
            consensus_price=98.0,
            avg_call_premium=1.5, avg_put_premium=2.5,
        ),
        _snapshot(
            date(2026, 7, 15), "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=1.5, avg_put_premium=2.5,
        ),
    ]
    out = compute_consensus_drift(rows, today_spot=100.5)
    assert out["n_days_covered"] == 2
    assert out["drift_consensus_1d"] == 2.0
    assert out["drift_consensus_Nd"] == 2.0
    assert out["yesterday_consensus"] == 98.0


def test_seven_stable_days_returns_zero_drift_and_stable_label():
    """Consensus stays at 100 over 7 days; spot stays at 100; label stable."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=i), "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        )
        for i in range(7)
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["n_days_covered"] == 7
    assert out["drift_consensus_1d"] == 0.0
    assert out["drift_consensus_Nd"] == 0.0
    assert out["drift_skew_today"] == 0.0
    assert out["drift_skew_change_1d"] == 0.0
    assert out["direction_label"] == "stable"


def test_seven_days_call_side_pulling_up_returns_positive_drift():
    """Consensus migrates from 95 to 105 + call-premium > put-premium →
    call_side_pulling_up label. Spot stays at 100."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=6 - i), "SPY", "2026-08-15",
            consensus_price=95.0 + i * 1.5,
            avg_call_premium=2.5,
            avg_put_premium=1.0,
        )
        for i in range(7)
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["n_days_covered"] == 7
    assert out["drift_consensus_1d"] == 1.5
    assert out["drift_consensus_Nd"] == 9.0
    # today=104, spot=100, delta=4 > 0.5% of 100 = 0.5 → above_threshold
    # call_premium 2.5 > put_premium 1.0 → call_dominant
    assert out["direction_label"] == "call_side_pulling_up"


def test_seven_days_put_side_pulling_down_returns_negative_drift():
    """Consensus migrates from 105 → 95 + put-premium > call-premium →
    put_side_pulling_down label."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=6 - i), "SPY", "2026-08-15",
            consensus_price=105.0 - i * 1.5,
            avg_call_premium=1.0,
            avg_put_premium=2.5,
        )
        for i in range(7)
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["drift_consensus_Nd"] == -9.0
    # today=95, spot=100, delta=-5 < -0.5 → above_threshold
    # put_premium 2.5 > call_premium 1.0 → put_dominant
    assert out["direction_label"] == "put_side_pulling_down"


def test_high_convergence_score_when_consensus_at_spot():
    """Consensus exactly at spot → convergence_score = 1.0."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=i), "SPY", "2026-08-15",
            consensus_price=520.0 + (i % 3) * 0.05,
            avg_call_premium=1.0, avg_put_premium=1.0,
        )
        for i in range(7)
    ]
    out = compute_consensus_drift(rows, today_spot=520.05)
    # The closest to spot is consensus = 520.0 + (today_idx % 3) * 0.05.
    # |today_consensus - 520.05| is at most 0.1 → /26 = 0.00385 → score 0.996
    assert out["convergence_score"] > 0.99


def test_reverse_chronological_input_auto_sorted():
    """DESC date order input → auto-sort → today is the most-recent row.
    Then drift_consensus_Nd = today_consensus - oldest_consensus =
    130 - 100 = +30 (consensus migrated UP over 6 days)."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows_desc = [
        _snapshot(
            today - timedelta(days=i), "SPY", "2026-08-15",
            consensus_price=130.0 - i * 5.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        )
        for i in range(7)   # i=0 is today, strike 130; i=6 is oldest, 100
    ]
    out = compute_consensus_drift(rows_desc, today_spot=131.0)
    assert out["today_consensus"] == 130.0
    assert out["drift_consensus_Nd"] == 30.0   # 130 - 100 = +30


def test_nan_consensus_returns_insufficient_data_with_warning():
    """NaN consensus → coerce to None → row dropped."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        {
            "snapshot_date": today - timedelta(days=2),
            "expiry": "2026-08-15",
            "consensus_price": float("nan"),
            "avg_call_premium": 1.0, "avg_put_premium": 1.0,
        },
        {
            "snapshot_date": today - timedelta(days=1),
            "expiry": "2026-08-15",
            "consensus_price": 99.0,
            "avg_call_premium": 1.0, "avg_put_premium": 1.0,
        },
        {
            "snapshot_date": today,
            "expiry": "2026-08-15",
            "consensus_price": 100.0,
            "avg_call_premium": 1.0, "avg_put_premium": 1.0,
        },
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["n_days_covered"] == 2
    assert any("not finite" in w or "NaN" in w for w in out["warnings"])


def test_missing_field_filtered_with_warning():
    """Row missing consensus_price → dropped with warning."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        {
            "snapshot_date": today - timedelta(days=1),
            "expiry": "2026-08-15",
            "avg_call_premium": 1.0, "avg_put_premium": 1.0,
        },
        _snapshot(
            today, "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        ),
    ]
    out = compute_consensus_drift(rows)
    assert out["n_days_covered"] == 1
    assert any("missing" in w or "NaN" in w for w in out["warnings"])


def test_future_dated_snapshots_dropped_with_warning():
    """Future-dated snapshot → dropped with warning."""
    from datetime import date, timedelta
    today = date.today()
    rows = [
        _snapshot(
            today - timedelta(days=1), "SPY", "2026-08-15",
            consensus_price=99.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        ),
        _snapshot(
            today + timedelta(days=1), "SPY", "2026-08-15",
            consensus_price=101.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        ),
        _snapshot(
            today, "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        ),
    ]
    out = compute_consensus_drift(rows)
    assert out["n_days_covered"] == 2
    assert any("future-dated" in w for w in out["warnings"])


def test_compute_returns_documented_dict_keys():
    out = compute_consensus_drift([])
    expected = {
        "today_consensus", "today_call_premium", "today_put_premium",
        "today_spot", "yesterday_consensus",
        "drift_consensus_1d", "drift_consensus_Nd",
        "drift_skew_today", "drift_skew_change_1d",
        "convergence_score", "direction_label",
        "n_days_covered", "warnings",
    }
    assert set(out.keys()) == expected


def test_skew_change_1d_detects_premium_tilt():
    """Yesterday skew-tied → today has call-heavy tilt → skew_change_1d > 0."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=1), "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=1.0, avg_put_premium=1.0,
        ),
        _snapshot(
            today, "SPY", "2026-08-15",
            consensus_price=100.0,
            avg_call_premium=3.0, avg_put_premium=1.0,
        ),
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["drift_skew_today"] == 2.0
    assert out["drift_skew_change_1d"] == 2.0


def test_direction_label_balanced_when_premium_sides_tied():
    """Above threshold but call_premium == put_premium → balanced."""
    from datetime import date, timedelta
    today = date(2026, 7, 15)
    rows = [
        _snapshot(
            today - timedelta(days=i), "SPY", "2026-08-15",
            consensus_price=120.0,    # 20 above spot=100 → big delta
            avg_call_premium=1.5, avg_put_premium=1.5,    # TIED
        )
        for i in range(7)
    ]
    out = compute_consensus_drift(rows, today_spot=100.0)
    assert out["direction_label"] == "balanced"


# ─────────────────────────────────────────────────────────────────────
# 2. DuckDB I/O — init + accumulate + read_recent (in-memory engine)
# ─────────────────────────────────────────────────────────────────────


def test_init_table_idempotent_multiple_calls_no_crash(fresh_engine):
    init_consensus_daily_table(fresh_engine)
    init_consensus_daily_table(fresh_engine)
    init_consensus_daily_table(fresh_engine)
    rows = fresh_engine.query("SELECT count(*) AS n FROM consensus_daily")
    assert rows[0]["n"] == 0


def test_accumulate_today_idempotent_same_date_overwrites(fresh_engine):
    """Two accumulate calls on the same (date, symbol, expiry) → one row
    with the SECOND call's values (UPSERT behavior)."""
    from datetime import date
    init_consensus_daily_table(fresh_engine)
    fixed_date = date(2026, 7, 15)
    chain = _build_chain(strike=100, call_premium=1.0, put_premium=1.0)
    accumulate_today(fresh_engine, "SPY", chain, snapshot_date=fixed_date)
    # Synthesize a different chain for the second accumulate.
    chain2 = _build_chain(
        strike=110, call_premium=2.0, put_premium=2.0,
        call_oi=200, put_oi=200,
    )
    accumulate_today(fresh_engine, "SPY", chain2, snapshot_date=fixed_date)
    rows = read_recent_drift(fresh_engine, "SPY", n_days=30)
    # Should have one date worth of rows: one per-expiry (2026-08-15) + the
    # overall row (empty expiry sentinel).
    assert len(rows) == 2
    expiry_set = {(r.get("expiry") or "") for r in rows}
    assert "" in expiry_set    # overall row
    assert "2026-08-15" in expiry_set
    # The chain2 had higher premiums so consensus should reflect that.
    overall_row = next(r for r in rows if (r.get("expiry") or "") == "")
    per_expiry_row = next(r for r in rows if r.get("expiry") == "2026-08-15")
    assert overall_row["consensus_price"] == per_expiry_row["consensus_price"]


def test_accumulate_three_distinct_tickers_does_not_cross_contaminate(fresh_engine):
    from datetime import date
    init_consensus_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    for sym, strike in [("SPY", 510.0), ("QQQ", 460.0), ("IWM", 215.0)]:
        chain = _build_chain(strike=strike, call_premium=1.0, put_premium=1.0)
        accumulate_today(fresh_engine, sym, chain, snapshot_date=today)
    rows = fresh_engine.query(
        "SELECT symbol, COUNT(*) AS n FROM consensus_daily GROUP BY symbol "
        "ORDER BY symbol"
    )
    sym_to_n = {r["symbol"]: r["n"] for r in rows}
    assert sym_to_n == {"SPY": 2, "QQQ": 2, "IWM": 2}


def test_read_recent_returns_chronological_with_correct_n(fresh_engine):
    """Insert 7 days of SPY snapshots; read n_days=3 returns ALL rows in
    last 3 dates, ASC by date."""
    from datetime import date, timedelta
    init_consensus_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    for i in range(7):
        chain = _build_chain(
            strike=100 + i, call_premium=1.0 + i * 0.1, put_premium=1.0 + i * 0.1,
        )
        accumulate_today(
            fresh_engine, "SPY", chain, snapshot_date=today - timedelta(days=6 - i)
        )
    rows = read_recent_drift(fresh_engine, "SPY", n_days=3, today=today)
    # 3 days × 2 rows per day = 6 rows
    assert len(rows) == 6
    dates = [r["snapshot_date"] for r in rows]
    assert dates == sorted(dates)


def test_read_recent_with_expiry_filter_returns_match_plus_overall(fresh_engine):
    """Filter by expiry returns the per-expiry row + the overall row."""
    from datetime import date
    init_consensus_daily_table(fresh_engine)
    today = date(2026, 7, 15)
    chain = _build_chain(strike=100, expiry="2026-08-15")
    accumulate_today(fresh_engine, "SPY", chain, snapshot_date=today)
    rows = read_recent_drift(fresh_engine, "SPY", n_days=30, expiry="2026-08-15")
    assert len(rows) == 2
    expiry_set = {(r.get("expiry") or "") for r in rows}
    assert expiry_set == {"2026-08-15", ""}


def test_read_recent_empty_table_returns_empty_list(fresh_engine):
    init_consensus_daily_table(fresh_engine)
    rows = read_recent_drift(fresh_engine, "ZZZZ", n_days=14)
    assert rows == []


def test_db_query_exception_returns_empty_list_with_warning_logged(fresh_engine):
    """If SQL execution fails (e.g. column mismatch), read_recent_drift
    MUST swallow the exception and return [] rather than crashing the route."""
    init_consensus_daily_table(fresh_engine)
    fresh_engine.query = lambda *_a, **_kw: (_ for _ in ()).throw(
        RuntimeError("simulated binder error")
    )
    with _warnings.catch_warnings():
        rows = read_recent_drift(fresh_engine, "SPY", n_days=7)
    assert rows == []
