"""
backend/tests/services/test_databento_snapshot.py

Tests for DatabentoCache.snapshot_circuits() — the shape contract behind
GET /api/databento/breaker/status. Pins:

- Empty state → empty list (parents never seen by engine are not surfaced)
- All closed → state='closed', opened_at=None, ttl_remaining=0
- One open → ttl_remaining counts down, opened_at is ISO format
- One half_open → state='half_open', opened_at=<timestamp>, ttl_remaining=0
- Sort order: OPENs first (by ttl_remaining ascending), then half_open, then closed
- Per-parent shape keys: parent, state, consecutive_failures, close_attempts, opened_at, ttl_remaining_s
- Mixed-state stack pins the canonical sort behavior (manual _CircuitState construction,
  no timing-flaky `monkeypatch(CIRCUIT_OPEN_TTL_SEC)`).
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from unittest import mock

import pytest

from databento_provider import (
    CIRCUIT_MAX_FAILURES,
    CIRCUIT_OPEN_TTL_SEC,
    DatabentoCache,
    _CircuitState,
)


# ── In-memory Mongo stand-in ─────────────────────────────
class _FakeCollection:
    async def find_one(self, q, projection=None):
        return None

    async def update_one(self, *args, **kwargs):
        pass

    async def create_index(self, *args, **kwargs):
        pass


class _FakeMongoDB:
    def __init__(self):
        self.databento_oi = _FakeCollection()


def _auth_locked_error() -> RuntimeError:
    return RuntimeError(
        "Your account has been locked for security reasons. (auth_account_locked)"
    )


@pytest.fixture
def today() -> date:
    return date(2026, 7, 21)


@pytest.fixture
def cache() -> DatabentoCache:
    return DatabentoCache(_FakeMongoDB())


# ── Tests ───────────────────────────────────────────────

def test_snapshot_empty_returns_empty_list(cache):
    """No parents in cache._circuit → empty snapshot. The route's closed_count
    is sum of providers, so empty list = no per-parent state ever recorded.
    Parents never seen by the engine are intentionally omitted."""
    assert cache.snapshot_circuits() == []
    assert cache.is_circuit_open("SPY.OPT") is False  # accessor still works


def test_snapshot_all_closed_reports_zero_state(cache):
    """Parents registered in cache._circuit but with opened_at=None → closed,
    opened_at=None, ttl_remaining=0, consecutive_failures tracked."""
    cache._circuit["SPY.OPT"] = _CircuitState(parent="SPY.OPT")
    cache._circuit["QQQ.OPT"] = _CircuitState(
        parent="QQQ.OPT", consecutive_failures=1
    )
    snap = cache.snapshot_circuits()
    assert len(snap) == 2
    by_parent = {e["parent"]: e for e in snap}
    spy = by_parent["SPY.OPT"]
    qqq = by_parent["QQQ.OPT"]
    assert spy["state"] == "closed"
    assert spy["opened_at"] is None
    assert spy["ttl_remaining_s"] == 0.0
    assert spy["consecutive_failures"] == 0
    assert spy["close_attempts"] == 0
    assert qqq["state"] == "closed"
    assert qqq["consecutive_failures"] == 1
    # Sort order: closed-by-parent-alphabetical in the closed tier
    assert [e["parent"] for e in snap] == ["QQQ.OPT", "SPY.OPT"]


async def test_snapshot_one_open_after_three_failures(cache, today, monkeypatch):
    """3 consecutive failures trip open; snapshot reports state='open',
    ttl_remaining_s > 0 (within CIRCUIT_OPEN_TTL_SEC window),
    opened_at is ISO string."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)
    snap = cache.snapshot_circuits()
    assert len(snap) == 1
    entry = snap[0]
    assert entry["parent"] == "SPY.OPT"
    assert entry["state"] == "open"
    assert entry["consecutive_failures"] >= CIRCUIT_MAX_FAILURES
    assert 0.0 < entry["ttl_remaining_s"] <= CIRCUIT_OPEN_TTL_SEC
    assert entry["opened_at"] is not None
    # opened_at must be valid ISO
    parsed = datetime.fromisoformat(entry["opened_at"])
    assert parsed.tzinfo is not None  # timezone-aware


def test_snapshot_half_open_state_after_ttl_elapses(cache):
    """TTL elapsed but no successful probe yet → HALF-OPEN state.
    opened_at still set, timestamp, but ttl_remaining=0.

    Constructed manually (no monkeypatch + asyncio.sleep) so the test is
    not timing-fragile — the position of `opened_at` is exact, not
    inferred from clock skew between the trip point and the snapshot call."""
    # opened_at is older than CIRCUIT_OPEN_TTL_SEC — TTL has elapsed, no probe fired.
    cache._circuit["SPY.OPT"] = _CircuitState(
        parent="SPY.OPT",
        consecutive_failures=CIRCUIT_MAX_FAILURES,
        opened_at=datetime.now(UTC) - timedelta(seconds=CIRCUIT_OPEN_TTL_SEC + 1),
        close_attempts=0,
    )
    snap = cache.snapshot_circuits()
    entry = snap[0]
    assert entry["state"] == "half_open"
    assert entry["opened_at"] is not None  # timestamp preserved
    assert entry["ttl_remaining_s"] == 0.0


def test_snapshot_sort_order_open_first_by_ttl_asc(cache):
    """Sort priority: OPENs earliest-to-recover first (smallest ttl_remaining),
    then HALF-OPEN, then CLOSED alphabetically. Pins the dashboard's "what
    will clear next" visual logic.

    Constructed manually — no trip-via-mock + asyncio.sleep — so the test
    isolates the sort behavior from clock skew between consecutive circuit
    trips and the snapshot call. Both parents are OPEN with calculated
    ttl_remaining, parent_a is older (smaller ttl) so it sorts first."""
    # A opened 595s ago → ttl_remaining ≈ 5s (smaller, sorts first)
    cache._circuit["AAPL.OPT"] = _CircuitState(
        parent="AAPL.OPT",
        consecutive_failures=CIRCUIT_MAX_FAILURES,
        opened_at=datetime.now(UTC) - timedelta(seconds=595),
        close_attempts=0,
    )
    # B opened 5s ago → ttl_remaining ≈ 595s (larger, sorts second)
    cache._circuit["MSFT.OPT"] = _CircuitState(
        parent="MSFT.OPT",
        consecutive_failures=CIRCUIT_MAX_FAILURES,
        opened_at=datetime.now(UTC) - timedelta(seconds=5),
        close_attempts=0,
    )
    snap = cache.snapshot_circuits()
    assert len(snap) == 2
    # Both OPEN — A (older) has smaller ttl_remaining, sorts first.
    assert [e["parent"] for e in snap] == ["AAPL.OPT", "MSFT.OPT"]
    assert snap[0]["ttl_remaining_s"] < snap[1]["ttl_remaining_s"]
    assert snap[0]["state"] == "open" and snap[1]["state"] == "open"


def test_snapshot_mixed_states_full_stack(cache):
    """One OPEN + one HALF-OPEN + one CLOSED → sort: open-by-ttl ascending,
    then half_open, then closed. Constructed manually so the test isn't
    timing-fragile (monkeypatching CIRCUIT_OPEN_TTL_SEC mid-test affects
    ALL already-open states, not just the new one — manual construction
    isolates the sort logic from clock-skew flakiness)."""
    # SPY.OPT: opened 10s ago, full TTL window → still OPEN
    cache._circuit["SPY.OPT"] = _CircuitState(
        parent="SPY.OPT",
        consecutive_failures=3,
        opened_at=datetime.now(UTC) - timedelta(seconds=10),
        close_attempts=0,
    )
    # QQQ.OPT: opened past TTL → HALF-OPEN
    cache._circuit["QQQ.OPT"] = _CircuitState(
        parent="QQQ.OPT",
        consecutive_failures=4,
        opened_at=datetime.now(UTC) - timedelta(seconds=CIRCUIT_OPEN_TTL_SEC + 1),
        close_attempts=0,
    )
    # IWM.OPT: never tripped, registered only as a closed parent
    cache._circuit["IWM.OPT"] = _CircuitState(parent="IWM.OPT", consecutive_failures=1)

    snap = cache.snapshot_circuits()
    assert [e["parent"] for e in snap] == ["SPY.OPT", "QQQ.OPT", "IWM.OPT"]
    assert snap[0]["state"] == "open"
    assert snap[1]["state"] == "half_open"
    assert snap[2]["state"] == "closed"
    assert sum(1 for e in snap if e["state"] == "open") == 1
    assert sum(1 for e in snap if e["state"] == "half_open") == 1
    assert sum(1 for e in snap if e["state"] == "closed") == 1
    # Defense-in-depth: ttl_remaining_s is non-negative (the max(0.0, ...) clamp
    # catches negative cases that would arise from time-skew in tests).
    assert all(e["ttl_remaining_s"] >= 0.0 for e in snap)
