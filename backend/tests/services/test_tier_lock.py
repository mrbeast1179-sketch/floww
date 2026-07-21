"""
backend/tests/services/test_tier_lock.py

Unit tests for tier_lock state machine.

Coverage:
    - Pure helpers (wilson_lower_bound, monotone predicates)
    - State machine predicates (engage, release, hysteresis dead-zone)
    - 14-day synthetic tier history integration walk
    - DuckDB-persisted lock state round-trip via engine mock

TDD spec from thread A design: engage on rising + strong bounds (z=1.645
90% on 7d AND 30d both ≥ tier_target); release on falling + weak bounds
(z=1.96 95% on 7d AND 30d both < tier_target - flat_band); the 5pp flat
band hysteresis dead-zone sustains a lock through single-day sample noise.

Key convention for the daily_rows fixtures:
  - Each tuple is `(date_iso, hit_rate)`. Sorted DESC by date the rows
    become `[most_recent_date, second, third]` = `[today, yesterday, daybefore]`.
  - "Rising" therefore reads [today > yesterday > daybefore] in helper's
    index semantics, which means the LATEST date has the HIGHEST value.
  - _is_falling reads [today < yesterday < daybefore], which means the
    LATEST date has the LOWEST value.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ── Pure helper tests ──────────────────────────────────────────────


def test_wilson_lower_bound_basic():
    from services.tier_lock import wilson_lower_bound

    lo = wilson_lower_bound(11, 20, z=1.645)
    assert 0.30 < lo < 0.55, f"expected lo in (0.30, 0.55); got {lo}"
    lo_95 = wilson_lower_bound(11, 20, z=1.96)
    assert lo_95 < lo, f"expected 95% lo < 90% lo: 95={lo_95} 90={lo}"


def test_wilson_lower_bound_zero_and_full():
    from services.tier_lock import wilson_lower_bound

    assert wilson_lower_bound(0, 20, z=1.645) == 0.0
    lo_full = wilson_lower_bound(20, 20, z=1.645)
    assert 0.80 < lo_full < 1.0, f"expected lo_full in (0.80, 1.0); got {lo_full}"


def test_monotone_strict_form():
    """Convention: helper receives recurring values in [today, yesterday,
    day-before] (most-recent first). Rising = today > yesterday > daybefore.
    Falling = today < yesterday < daybefore. The STRICT form means equal
    consecutive days disqualify (avoids flat-day noise locking a tier)."""
    from services.tier_lock import _is_rising, _is_falling

    # Rising: [0.8, 0.7, 0.6] — today highest
    assert _is_rising([0.8, 0.7, 0.6]) is True
    assert _is_rising([0.7, 0.7, 0.7]) is False
    assert _is_rising([0.7, 0.7, 0.6]) is False
    # Falling: [0.4, 0.7, 0.8] — today lowest
    assert _is_falling([0.4, 0.7, 0.8]) is True
    assert _is_falling([0.8, 0.7, 0.6]) is False
    assert _is_falling([0.6, 0.7, 0.7]) is False


# ── State machine tests (the actual feature) ──────────────────────


def _quality_row(tier: str, n_measured: int, wins: int):
    return {
        "tier": tier, "rule": "SCORE",
        "n": n_measured + 5, "n_measured": n_measured,
        "wins": wins, "hit_rate": wins / n_measured if n_measured else None,
        "avg_move_pct": 1.0, "sigma_median": 4.0, "is_best_rule": False,
    }


def _day(date_iso: str, tier: str, hit_rate: float):
    return {"date": date_iso, "tier": tier, "n": 4, "n_measured": 4,
            "wins": int(round(hit_rate * 4)), "hit_rate": hit_rate, "avg_move_pct": 1.0}


def test_lock_engages_on_rising_and_strong_bounds():
    """Engage requires: rising last-3-days + 7d Wilson lo (z=1.645) ≥ 0.60
    AND 30d Wilson lo (z=1.645) ≥ 0.60. q7=(10,9) at 90% gives lo~0.65; q30=
    (40,32) at 80% gives lo~0.68. Both ≥ GOLD 0.60 target. Daily fixture
    oriented as RISING (today=0.80 > yesterday=0.70 > daybefore=0.60)."""
    from services.tier_lock import evaluate_lock

    q7 = [_quality_row("GOLD", 10, 9)]
    q30 = [_quality_row("GOLD", 40, 32)]
    daily = [
        _day("2026-07-19", "GOLD", 0.80),  # today — highest
        _day("2026-07-18", "GOLD", 0.70),
        _day("2026-07-17", "GOLD", 0.60),  # day-before — lowest
    ]
    out = evaluate_lock(q7, q30, daily)
    assert out["GOLD"] is True, (
        f"expected GOLD engaged; got {out}. 7d/30d Wilson-90 lo's both "
        "should clear the GOLD 0.60 target with rising last-3 days.")
    assert "_GOLD_locked_rate" in out
    assert 0.6 <= out["_GOLD_locked_rate"] <= 0.95


def test_lock_fails_when_7d_bound_misses_target():
    """Engage BLOCKED if 7d Wilson lo drops below the GOLD 0.60 target even
    though 30d clears. Hot 30d backstop is not enough. q7=(10,6) at 60%
    gives 7d Wilson lo ~ 0.35 → below target. Daily fixture oriented as
    RISING so the only blocker is the bounds check."""
    from services.tier_lock import evaluate_lock

    q7 = [_quality_row("GOLD", 10, 6)]    # 60% point, lo ~0.35
    q30 = [_quality_row("GOLD", 100, 90)]  # 90% point, lo ~0.84 — clears
    daily = [
        _day("2026-07-19", "GOLD", 0.80),
        _day("2026-07-18", "GOLD", 0.70),
        _day("2026-07-17", "GOLD", 0.60),
    ]
    out = evaluate_lock(q7, q30, daily)
    assert out["GOLD"] is False, (
        f"expected GOLD NOT engaged (7d lo blocked); got {out}")


def test_lock_releases_on_falling_and_weak_bounds():
    """Release requires: falling last-3-days + 7d Wilson lo (z=1.96) <
    target - flat_band (= 0.55 for GOLD) AND 30d Wilson lo (z=1.96) <
    0.55. Daily fixture oriented as FALLING (today=0.40 < 0.55 < 0.70)."""
    from services.tier_lock import evaluate_lock

    q7 = [_quality_row("GOLD", 20, 8)]    # 40% point, lo ~0.22
    q30 = [_quality_row("GOLD", 80, 32)]  # 40% point, lo ~0.30
    daily = [
        _day("2026-07-19", "GOLD", 0.40),  # today — lowest
        _day("2026-07-18", "GOLD", 0.55),
        _day("2026-07-17", "GOLD", 0.70),
    ]
    out = evaluate_lock(q7, q30, daily, prev_locked={"GOLD": True})
    assert out["GOLD"] is False, f"expected release; got {out}"


def test_lock_sustains_when_one_bound_within_flat_band():
    """Hysteresis dead-zone: ONE bound inside the band keeps the lock
    engaged. q30 stays confidently above 0.55 even though q7 has decayed;
    the BOTH-AND release predicate stays False, so the tier remains
    locked."""
    from services.tier_lock import evaluate_lock

    q7 = [_quality_row("GOLD", 12, 9)]     # 75% point, lo ~0.47 (below 0.55)
    q30 = [_quality_row("GOLD", 60, 50)]   # 83% point, lo ~0.72 (above 0.55)
    daily = [
        _day("2026-07-19", "GOLD", 0.55),
        _day("2026-07-18", "GOLD", 0.65),
        _day("2026-07-17", "GOLD", 0.75),
    ]
    out = evaluate_lock(q7, q30, daily, prev_locked={"GOLD": True})
    assert out["GOLD"] is True, (
        f"expected SUSTAIN (one bound inside band, one outside); got {out}. "
        "The hysteresis dead-zone only releases when BOTH bounds drop below 0.55.")


# ── Integration walk — 14-day synthetic tier history ──────────────


def test_integration_14d_history_walks_through_engage_and_release():
    """Walk a 14-day synthetic GOLD history through three lifecycle phases:
       Phase 1 (days 1-5): rising + hot field       → ENGAGE
       Phase 2 (days 6-11): plateau / drift          → SUSTAIN
       Phase 3 (days 12-13): falling + cold field   → RELEASE

    A real retuner reads fresh 7d/30d quality windows each night, so
    per-phase quality snapshots reflect the field's CURRENT quality at
    each phase — that's what makes the lock engage (hot field) and later
    release (cold field) with the same daily fixture, the way a real
    pipeline does over time.
    """
    from services.tier_lock import evaluate_lock

    # 13-day daily fixture: rising (7), plateau (3), falling (3)
    data = [
        ("2026-07-07", 0.40), ("2026-07-08", 0.50), ("2026-07-09", 0.60),
        ("2026-07-10", 0.65), ("2026-07-11", 0.70), ("2026-07-12", 0.75),
        ("2026-07-13", 0.80), ("2026-07-14", 0.80), ("2026-07-15", 0.80),
        ("2026-07-16", 0.80), ("2026-07-17", 0.70), ("2026-07-18", 0.60),
        ("2026-07-19", 0.50),
    ]
    daily_full = [_day(d, "GOLD", h) for d, h in data]

    # ── Phase 1 (days 1-5): rising last-3 + HOT 7d/30d wins
    # Last-3 sorted DESC by date: (07-10 0.65), (07-09 0.60), (07-08 0.50)
    # = [0.65, 0.60, 0.50] = RISING (0.65 > 0.60 > 0.50).
    q7_p1 = [_quality_row("GOLD", 30, 24)]    # 80% point, lo ~0.66 ≥ 0.60 ✓
    q30_p1 = [_quality_row("GOLD", 100, 80)]  # 80% point, lo ~0.72 ≥ 0.60 ✓
    out_p1 = evaluate_lock(q7_p1, q30_p1, daily_full[:5])
    assert out_p1["GOLD"] is True, f"phase 1 (engage): expected True; got {out_p1}"

    # ── Phase 2 (days 6-11): plateau keeps engagement
    # Last-3 sorted DESC: (07-16 0.80), (07-15 0.80), (07-14 0.80) = [0.80...] flat.
    # Neither rising nor falling → sustain (prev=engaged stays engaged).
    q7_p2 = [_quality_row("GOLD", 30, 24)]
    q30_p2 = [_quality_row("GOLD", 100, 80)]
    out_p2 = evaluate_lock(q7_p2, q30_p2, daily_full[:11], prev_locked={"GOLD": True})
    assert out_p2["GOLD"] is True, f"phase 2 (sustain plateau): expected True; got {out_p2}"

    # ── Phase 3 (days 12-13): falling + COLD 7d/30d wins
    # Last-3 sorted DESC: (07-19 0.50), (07-18 0.60), (07-17 0.70) = [0.50...] FALLING.
    q7_p3 = [_quality_row("GOLD", 6, 2)]     # 33% point, 7d lo ~0.10 < 0.55
    q30_p3 = [_quality_row("GOLD", 30, 12)]  # 40% point, 30d lo ~0.25 < 0.55
    out_p3 = evaluate_lock(q7_p3, q30_p3, daily_full[:13], prev_locked={"GOLD": True})
    assert out_p3["GOLD"] is False, f"phase 3 (release): expected False; got {out_p3}"


# ── DuckDB-persisted lock state round-trip ────────────────────────


class _FakeExecWrite:
    """Captures (tier, is_engaged, locked_hit_rate, locked_at) writes."""
    def __init__(self):
        self.rows: list[tuple] = []

    def __call__(self, sql, params=None):
        if "ON CONFLICT" in sql and params:
            self.rows.append(params[0])


class _FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows or []

    def __call__(self, sql, params=None):
        return list(self.rows)


class _FakeEngine:
    """Minimal engine — only the methods tier_lock.update_locks uses.
    Distinguishes the prev-state read (``SELECT tier, is_engaged``) from
    the committed-state read (``SELECT tier, is_engaged, locked_hit_rate,
    locked_at``) so a future test that verifies a state-transition mid-
    update can assert "INSERT then SELECT shows the new row" rather than
    collapsing both reads via a single ``tier_locks`` substring match.
    Call-count is captured so tests can verify the two reads actually
    happened separately.
    """
    def __init__(self, *, current_rows=None, init_fail=False):
        self.exec_write = _FakeExecWrite()
        self._rows = current_rows or []
        self.init_table_seen = False
        self.init_fail = init_fail
        # Exposed for test introspection: tests can assert
        # `len(eng.query_calls) == 2` to pin the production request count
        # of update_locks (1 prev read + 1 committed read + N writes).
        self.query_calls: list[str] = []

    def execute_write(self, sql, params=None):
        if "CREATE TABLE IF NOT EXISTS tier_locks" in sql:
            if self.init_fail:
                raise Exception("table init fail")
            self.init_table_seen = True
            return
        self.exec_write(sql, params=params)

    def query(self, sql, params=None):
        self.query_calls.append(sql)
        # Committed-state read queries the full column set (returned to
        # the /alerts/quality path). Prev-state read picks only `tier`
        # and `is_engaged` for the lock-predicate lookup. Tests that
        # construct their own _rows can supply them; existing rows pass
        # through the column projection unchanged.
        if "locked_hit_rate" in sql and "locked_at" in sql:
            return list(self._rows)
        if "tier_locks" in sql:
            return [{"tier": r["tier"], "is_engaged": r["is_engaged"]}
                    for r in self._rows]
        return []


def test_update_locks_persists_engaged_state():
    """GOLD rising + strong bounds → INSERT locked row → committed.GOLD.engaged = True."""
    from services.tier_lock import update_locks

    eng = _FakeEngine()
    q7 = [_quality_row("GOLD", 10, 9)]
    q30 = [_quality_row("GOLD", 40, 32)]
    daily = [
        _day("2026-07-19", "GOLD", 0.80),
        _day("2026-07-18", "GOLD", 0.70),
        _day("2026-07-17", "GOLD", 0.60),
    ]
    committed = update_locks(eng, q7, q30, daily)
    assert committed["GOLD"]["engaged"] is True
    assert len(eng.exec_write.rows) == 1
    row = eng.exec_write.rows[0]
    assert row[0] == "GOLD"
    assert row[1] is True
    assert row[2] is not None  # locked_hit_rate


def test_update_locks_no_transition_no_write():
    """prev=engaged and re-eval = engaged → no INSERT/UPDATE fires."""
    from services.tier_lock import update_locks

    eng = _FakeEngine(current_rows=[
        {"tier": "GOLD", "is_engaged": True, "locked_hit_rate": 0.74,
         "locked_at": "2026-07-15T09:00:00"},
    ])
    q7 = [_quality_row("GOLD", 10, 9)]
    q30 = [_quality_row("GOLD", 40, 32)]
    daily = [
        _day("2026-07-19", "GOLD", 0.80),
        _day("2026-07-18", "GOLD", 0.70),
        _day("2026-07-17", "GOLD", 0.60),
    ]
    update_locks(eng, q7, q30, daily)
    assert eng.exec_write.rows == []


def test_get_all_locks_returns_default_for_empty_table():
    from services.tier_lock import get_all_locks

    eng = _FakeEngine(current_rows=[])
    out = get_all_locks(eng)
    assert out == {
        "GOLD": {"engaged": False, "locked_hit_rate": None, "locked_at": None},
        "SILVER": {"engaged": False, "locked_hit_rate": None, "locked_at": None},
        "BRONZE": {"engaged": False, "locked_hit_rate": None, "locked_at": None},
    }


def test_fake_engine_distinguishes_prev_state_from_committed_state():
    """Pin test isolation: ``_FakeEngine.query`` collapses prior substrings
    that would conflate prev-state (``SELECT tier, is_engaged FROM``) and
    committed-state (``SELECT tier, is_engaged, locked_hit_rate, locked_at
    FROM``) reads. After the refactor, the committed read returns the
    FULL row (with locked_hit_rate / locked_at) and the prev-state read
    returns ONLY ``{tier, is_engaged}`` — a future regression that drops
    one of the reads or merges them will fail this pin immediately.
    """
    row = {"tier": "GOLD", "is_engaged": True, "locked_hit_rate": 0.74,
           "locked_at": "2026-07-21T09:30:00"}
    eng = _FakeEngine(current_rows=[row])

    # Committed-state read — full row
    committed = eng.query("SELECT tier, is_engaged, locked_hit_rate, locked_at FROM tier_locks")
    assert committed == [row], f"committed read should return full row; got {committed}"

    # Prev-state read — `{tier, is_engaged}` only (column projection)
    prev = eng.query("SELECT tier, is_engaged FROM tier_locks")
    assert prev == [{"tier": "GOLD", "is_engaged": True}], (
        f"prev-state read should project to 2 columns; got {prev}")

    # Both reads captured to query_calls
    assert len(eng.query_calls) == 2
    assert "locked_hit_rate" in eng.query_calls[0]  # committed first
    assert "locked_hit_rate" not in eng.query_calls[1]  # prev second
