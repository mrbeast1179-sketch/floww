"""
backend/tests/services/test_databento_circuit.py

Circuit-breaker semantics for the databento SDK auth_account_locked spam.

DRIVES a 50-line WARN-log reduction per cvforge scan cycle: per-parent state
trips OPEN after 3 consecutive upstream failures, stays open for
CIRCUIT_OPEN_TTL_SEC (default 10 min), and half-opens one probe per TTL
window. Per-call WARN logs are silenced while OPEN; the OPEN / HALF-OPEN /
CLOSE / REOPEN transitions log once each. Mongo stale-cache stays available
when the breaker is OPEN so fetch_oi_for_ticker's backwalk still serves
older days.
"""

import asyncio
import logging
from datetime import date, timedelta
from unittest import mock

import pytest

from databento_provider import (
    CIRCUIT_MAX_FAILURES,
    CIRCUIT_OPEN_TTL_SEC,
    DatabentoCache,
    _CircuitState,
)


# ── In-memory stand-ins for the Motor collection ─────────────────────

class _FakeCollection:
    """Just enough Motor surface for DatabentoCache.find_one / update_one."""
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, q, projection=None):
        for d in self.docs:
            if d.get("parent") == q.get("parent") and d.get("day") == q.get("day"):
                return d
        return None

    async def update_one(self, q, u, upsert=False):
        for d in self.docs:
            if d.get("parent") == q.get("parent") and d.get("day") == q.get("day"):
                d.update(u.get("$set", {}))
                return
        if upsert:
            self.docs.append({
                "parent": q.get("parent"),
                "day": q.get("day"),
                **u.get("$set", {}),
            })

    async def create_index(self, *args, **kwargs):
        pass


class _FakeMongoDB:
    def __init__(self, docs=None):
        self.databento_oi = _FakeCollection(docs=docs)


def _auth_locked_error():
    return RuntimeError(
        "Your account has been locked for security reasons. (auth_account_locked)"
    )


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def today() -> date:
    return date(2026, 7, 21)


@pytest.fixture
def cache() -> DatabentoCache:
    return DatabentoCache(_FakeMongoDB())


# ── Tests ───────────────────────────────────────────────────────────

async def test_closed_to_open_after_three_consecutive_failures(cache, today, monkeypatch):
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    # 2 failures should keep the breaker CLOSED
    for _ in range(2):
        await cache.get(parent, today)
    state = cache._circuit.get(parent)
    assert state is not None
    assert state.opened_at is None, "2 failures must not open the breaker yet"
    assert state.consecutive_failures == 2

    # 3rd failure trips OPEN
    await cache.get(parent, today)
    state = cache._circuit.get(parent)
    assert state.opened_at is not None
    assert state.consecutive_failures >= CIRCUIT_MAX_FAILURES
    assert cache.is_circuit_open(parent) is True


async def test_stale_mongo_doc_served_for_separate_day_when_circuit_open(
    cache, today, monkeypatch,
):
    """Older Mongo doc for the SAME parent on a DIFFERENT day is still served —
    fetch_oi_for_ticker's backwalk relies on this."""
    parent = "SPY.OPT"
    yesterday = today - timedelta(days=1)
    stale = {
        "parent": parent,
        "day": yesterday.isoformat(),
        "contracts": {
            "SPY   260720C00500000": {"strike": 500.0, "expiry": "2026-07-20", "type": "call", "oi": 99},
        },
    }
    cache.col.docs.append(stale)

    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)

    # Ask for the older day — must return the stale Mongo doc, NOT touch upstream
    out = await cache.get(parent, yesterday)
    assert out == stale["contracts"]


async def test_no_per_call_warn_logs_while_open(cache, today, monkeypatch, caplog):
    """While OPEN, repeated cache.get calls produce ZERO additional WARNs."""
    caplog.set_level(logging.WARNING, logger="databento")

    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )

    # Trip — produces exactly one OPEN WARN
    for _ in range(3):
        await cache.get(parent, today)
    opens = [r for r in caplog.records if r.levelname == "WARNING" and "OPENED" in r.getMessage()]
    assert len(opens) == 1, f"trip should produce 1 OPEN WARN; got {opens}"

    caplog.clear()

    # 50 more calls while OPEN — no further WARN
    for _ in range(50):
        await cache.get(parent, today)
    new_warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert new_warns == [], (
        f"OPEN state must not produce per-call WARN; got {[r.getMessage() for r in new_warns]}"
    )


async def test_half_open_after_ttl_allows_one_upstream_attempt(
    cache, today, monkeypatch,
):
    """After CIRCUIT_OPEN_TTL_SEC elapses, is_circuit_open returns False once
    (allowing one probe); the next call hits upstream."""
    parent = "SPY.OPT"
    upstream = mock.Mock(side_effect=_auth_locked_error())
    monkeypatch.setattr("databento_provider._fetch_oi_sync", upstream)
    monkeypatch.setattr("databento_provider.CIRCUIT_OPEN_TTL_SEC", 0.05)

    for _ in range(3):
        await cache.get(parent, today)
    assert cache.is_circuit_open(parent) is True

    await asyncio.sleep(0.07)  # > TTL

    upstream.reset_mock()
    upstream.side_effect = None
    upstream.return_value = {"SPY   260721C00500000": {"oi": 50}}

    # First call after TTL should fire the half-open probe (upstream called once)
    await cache.get(parent, today)
    assert upstream.call_count == 1


async def test_half_open_success_closes_circuit(cache, today, monkeypatch):
    """A successful probe closes the breaker and resets consecutive_failures."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    monkeypatch.setattr("databento_provider.CIRCUIT_OPEN_TTL_SEC", 0.05)

    for _ in range(3):
        await cache.get(parent, today)
    await asyncio.sleep(0.07)

    upstream_success = mock.Mock(
        return_value={"SPY   260721C00500000": {"oi": 50}}
    )
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync", upstream_success
    )

    await cache.get(parent, today)
    state = cache._circuit.get(parent)
    assert state is not None
    assert state.opened_at is None
    assert state.consecutive_failures == 0
    assert cache.is_circuit_open(parent) is False


async def test_half_open_failure_reopens_with_fresh_ttl(
    cache, today, monkeypatch,
):
    """A failed half-open probe re-opens the breaker; close_attempts >= 1."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    monkeypatch.setattr("databento_provider.CIRCUIT_OPEN_TTL_SEC", 0.05)

    for _ in range(3):
        await cache.get(parent, today)
    opened_at_first = cache._circuit[parent].opened_at

    await asyncio.sleep(0.07)
    await cache.get(parent, today)  # half-open probe also fails

    state = cache._circuit[parent]
    assert state.opened_at is not None
    assert state.opened_at >= opened_at_first
    assert state.close_attempts >= 1


async def test_per_key_isolation_spy_open_does_not_block_qqq(
    cache, today, monkeypatch,
):
    spy = "SPY.OPT"
    qqq = "QQQ.OPT"
    upstream = mock.Mock(side_effect=_auth_locked_error())
    monkeypatch.setattr("databento_provider._fetch_oi_sync", upstream)

    for _ in range(3):
        await cache.get(spy, today)
    assert cache.is_circuit_open(spy) is True
    assert cache.is_circuit_open(qqq) is False

    upstream.reset_mock()
    upstream.side_effect = None
    upstream.return_value = {"QQQ   260721C00350000": {"oi": 30}}
    out = await cache.get(qqq, today)
    assert out == {"QQQ   260721C00350000": {"oi": 30}}
    assert upstream.call_count == 1, "QQQ must hit upstream despite SPY's OPEN state"


async def test_success_before_threshold_resets_counter(
    cache, today, monkeypatch,
):
    """A single success after 2 failures resets the counter; circuit never opens."""
    parent = "SPY.OPT"
    upstream = mock.Mock(side_effect=_auth_locked_error())
    monkeypatch.setattr("databento_provider._fetch_oi_sync", upstream)

    for _ in range(2):
        await cache.get(parent, today)
    assert cache._circuit[parent].consecutive_failures == 2
    assert cache._circuit[parent].opened_at is None

    upstream.side_effect = None
    upstream.return_value = {"SPY   260721C00500000": {"oi": 50}}
    await cache.get(parent, today)

    state = cache._circuit[parent]
    assert state.consecutive_failures == 0
    assert state.opened_at is None, "circuit must NOT open — recovery at 2-of-3 saves it"


async def test_mongo_doc_with_no_contracts_returns_empty(
    cache, today, monkeypatch,
):
    """When breaker is OPEN and Mongo doc lacks a `contracts` field, return {}."""
    parent = "SPY.OPT"
    cache.col.docs.append({"parent": parent, "day": today.isoformat(), "_id": "x"})

    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)

    out = await cache.get(parent, today)
    assert out == {}


async def test_is_circuit_open_accessor_value_reflects_state(
    cache, today, monkeypatch,
):
    parent = "SPY.OPT"
    assert cache.is_circuit_open(parent) is False
    assert cache.is_circuit_open("QQQ.OPT") is False

    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)

    assert cache.is_circuit_open(parent) is True
    assert cache.is_circuit_open("QQQ.OPT") is False


async def test_circuit_does_not_cache_empty_on_open_skip(
    cache, today, monkeypatch,
):
    """When the breaker is OPEN and get() short-circuits, _mem is NOT populated
    with {}. This is what lets the half-open probe fire on the next call after
    CIRCUIT_OPEN_TTL_SEC elapses — a future refactor that caches None/{} on the
    skip path would silently break recovery."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)  # trip → OPEN
    assert cache.is_circuit_open(parent) is True

    # Several downstream consumers
    for _ in range(5):
        key = f"{parent}:{today.isoformat()}"
        assert key not in cache._mem, "_mem must NOT short-circuit the breaker"
        await cache.get(parent, today)
        assert key not in cache._mem, "_mem must remain empty while breaker is OPEN"


async def test_missing_databento_key_trips_circuit_identically(
    cache, today, monkeypatch,
):
    """The `_fetch_oi_sync` missing-key RuntimeError must trip the breaker the
    same way as auth_account_locked — deploys without DATABENTO_API_KEY set
    shouldn't spam logs until the circuit opens, then go quiet for 10 min."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=RuntimeError("databento client not initialized — missing DATABENTO_API_KEY")),
    )
    for _ in range(2):
        await cache.get(parent, today)
    state = cache._circuit.get(parent)
    assert state is not None
    assert state.consecutive_failures == 2
    assert state.opened_at is None

    await cache.get(parent, today)  # 3rd failure
    state = cache._circuit.get(parent)
    assert state.opened_at is not None
    assert cache.is_circuit_open(parent) is True


async def test_on_failure_short_circuits_when_already_open_within_ttl(
    cache, today, monkeypatch,
):
    """Direct _on_failure calls while fully OPEN (TTL still in window) must NOT
    bump consecutive_failures or fire any log. Future callers who bypass get()'s
    upstream-skip must not silently over-accumulate state."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)
    state = cache._circuit.get(parent)
    prior_failures = state.consecutive_failures
    prior_opened_at = state.opened_at

    # Direct call (bypassing get()) — must be a no-op while fully OPEN
    cache._on_failure(parent)
    assert state.consecutive_failures == prior_failures
    assert state.opened_at == prior_opened_at  # unchanged (still fresh OPEN timestamp)
    assert cache.is_circuit_open(parent) is True   # still OPEN, still in TTL


async def test_on_success_short_circuits_when_already_open_within_ttl(
    cache, today, monkeypatch,
):
    """Symmetric to test_on_failure_short_circuits_*: direct _on_success calls
    while fully OPEN (TTL still in window) must NOT prematurely close the
    breaker. Pins the parity guard added in the second review pass — if a
    future refactor removes it while OPEN-with-TTL, opened_at would silently
    flip to None and the breaker would close without a probe ever firing."""
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    for _ in range(3):
        await cache.get(parent, today)  # trip → OPEN, TTL in window
    state = cache._circuit[parent]
    assert state.opened_at is not None
    prior_opened_at = state.opened_at
    prior_attempts = state.close_attempts

    # Direct call (bypassing get()) — must be a no-op while fully OPEN
    cache._on_success(parent)
    assert state.opened_at == prior_opened_at, (
        "_on_success must NOT clear opened_at while fully OPEN — premature "
        "close would cause silent opens without a probe and lose close_attempts"
    )
    assert state.close_attempts == prior_attempts
    assert cache.is_circuit_open(parent) is True   # still OPEN


async def test_half_open_success_still_closes_circuit(
    cache, today, monkeypatch, caplog,
):
    """Regression guard: the _on_success short-circuit must NOT prevent the
    CLOSED→HALF-OPEN→CLOSED recovery path. Once TTL elapses (is_open() returns
    False), the next successful probe must clear opened_at and log 'circuit
    CLOSED'. Pins the order: short-circuit guard runs before the close logic,
    not instead of it."""
    caplog.set_level(logging.INFO, logger="databento")
    parent = "SPY.OPT"
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(side_effect=_auth_locked_error()),
    )
    monkeypatch.setattr("databento_provider.CIRCUIT_OPEN_TTL_SEC", 0.05)
    for _ in range(3):
        await cache.get(parent, today)
    await asyncio.sleep(0.07)  # TTL elapsed → HALF-OPEN

    # Successful half-open probe
    monkeypatch.setattr(
        "databento_provider._fetch_oi_sync",
        mock.Mock(return_value={"SPY   260721C00500000": {"oi": 50}}),
    )
    out = await cache.get(parent, today)
    assert out == {"SPY   260721C00500000": {"oi": 50}}
    state = cache._circuit[parent]
    assert state.opened_at is None, "HALF-OPEN success must clear opened_at"
    assert state.consecutive_failures == 0
    assert cache.is_circuit_open(parent) is False
    closed_logs = [r for r in caplog.records if "CLOSED" in r.getMessage()]
    assert closed_logs, "CLOSED transition must log at INFO level"
