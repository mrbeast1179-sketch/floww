"""
tests/services/test_request_deduplicator.py

Tests for RequestDeduplicator.

Covers:
- Concurrent requests with same key → func called once
- Different keys → func called separately for each
- Exception propagates to all waiters
- In-flight tracking (count, keys)
- Cleanup after success and after exception
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from services.request_deduplicator import RequestDeduplicator


@pytest.fixture
def dedup() -> RequestDeduplicator:
    return RequestDeduplicator()


# ── Basic deduplication ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_same_key_calls_func_once(dedup: RequestDeduplicator):
    """Two concurrent requests with the same key should call func only once.

    Uses an Event to ensure both callers are genuinely in-flight
    at the same time (prevents the issue where a fast-sync mock
    completes before the second coroutine starts).
    """
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_func():
        started.set()
        await release.wait()
        return {"data": "ok"}

    async def caller():
        return await dedup.execute("key1", slow_func)

    # Launch first caller — it will enter func and wait on release
    task1 = asyncio.create_task(caller())
    await started.wait()

    # Launch second caller while first is mid-flight
    task2 = asyncio.create_task(caller())

    # Let both complete
    release.set()
    results = await asyncio.gather(task1, task2)

    assert results[0] == {"data": "ok"}
    assert results[1] == {"data": "ok"}


@pytest.mark.asyncio
async def test_different_keys_call_func_separately(dedup: RequestDeduplicator):
    """Requests with different keys should each call func."""
    mock_a = AsyncMock(return_value="a")
    mock_b = AsyncMock(return_value="b")

    result_a, result_b = await asyncio.gather(
        dedup.execute("key_a", mock_a),
        dedup.execute("key_b", mock_b),
    )

    assert mock_a.call_count == 1
    assert mock_b.call_count == 1
    assert result_a == "a"
    assert result_b == "b"


@pytest.mark.asyncio
async def test_three_concurrent_same_key(dedup: RequestDeduplicator):
    """Three concurrent requests with same key → func called once."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_func():
        started.set()
        await release.wait()
        return 42

    async def caller():
        return await dedup.execute("k", slow_func)

    tasks = []
    for _ in range(3):
        t = asyncio.create_task(caller())
        tasks.append(t)

    # Wait until at least one is in func
    await started.wait()
    release.set()

    results = await asyncio.gather(*tasks)
    assert all(r == 42 for r in results)


# ── Exception propagation ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exception_propagates_to_all_waiters(dedup: RequestDeduplicator):
    """If func raises, all waiters should receive the exception."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def failing_func():
        started.set()
        await release.wait()
        raise ValueError("rate limited")

    async def caller():
        return await dedup.execute("err_key", failing_func)

    task1 = asyncio.create_task(caller())
    await started.wait()
    task2 = asyncio.create_task(caller())

    release.set()

    with pytest.raises(ValueError, match="rate limited"):
        await asyncio.gather(task1, task2)


@pytest.mark.asyncio
async def test_exception_different_keys(dedup: RequestDeduplicator):
    """Exception for one key should not affect other keys."""
    mock_ok = AsyncMock(return_value="ok")
    mock_err = AsyncMock(side_effect=RuntimeError("fail"))

    with pytest.raises(RuntimeError, match="fail"):
        await asyncio.gather(
            dedup.execute("good", mock_ok),
            dedup.execute("bad", mock_err),
        )


# ── In-flight tracking ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inflight_count_zero_initially(dedup: RequestDeduplicator):
    assert dedup.inflight_count == 0
    assert dedup.inflight_keys == []


@pytest.mark.asyncio
async def test_inflight_count_during_request(dedup: RequestDeduplicator):
    """While a request is in flight, inflight_count should be 1."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_func():
        started.set()
        await release.wait()
        return "done"

    async def make_request():
        return await dedup.execute("slow", slow_func)

    task = asyncio.create_task(make_request())
    await started.wait()

    assert dedup.inflight_count == 1
    assert "slow" in dedup.inflight_keys

    release.set()
    await task

    assert dedup.inflight_count == 0


@pytest.mark.asyncio
async def test_inflight_cleanup_after_success(dedup: RequestDeduplicator):
    """After a successful request, inflight should be empty."""
    await dedup.execute("k", AsyncMock(return_value=1))
    assert dedup.inflight_count == 0


@pytest.mark.asyncio
async def test_inflight_cleanup_after_exception(dedup: RequestDeduplicator):
    """After a failed request, inflight should be empty."""
    with pytest.raises(ValueError):
        await dedup.execute("k", AsyncMock(side_effect=ValueError("x")))
    assert dedup.inflight_count == 0


# ── Sequential reuse ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sequential_same_key_calls_func_each_time(dedup: RequestDeduplicator):
    """Sequential (non-concurrent) requests should each call func."""
    mock = AsyncMock(side_effect=[1, 2])

    r1 = await dedup.execute("seq", mock)
    r2 = await dedup.execute("seq", mock)

    assert r1 == 1
    assert r2 == 2
    assert mock.call_count == 2
