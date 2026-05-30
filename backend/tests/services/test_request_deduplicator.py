import asyncio
import time

import pytest

from backend.services.request_deduplicator import RequestDeduplicator


@pytest.fixture
def dedup():
    return RequestDeduplicator()


def _run(coro):
    return asyncio.run(coro)


def test_concurrent_same_key(dedup):
    counter = {"n": 0}

    async def slow():
        counter["n"] += 1
        await asyncio.sleep(0.05)
        return 42

    async def main():
        return await asyncio.gather(
            dedup.execute("same", slow),
            dedup.execute("same", slow),
            dedup.execute("same", slow),
        )

    results = _run(main())
    assert results == [42, 42, 42]
    assert counter["n"] == 1


def test_concurrent_different_keys(dedup):
    counter_slow = {"n": 0}

    async def slow(v):
        counter_slow["n"] += 1
        await asyncio.sleep(0.05)
        return v

    async def main():
        return await asyncio.gather(
            dedup.execute("a", lambda: slow(1)),
            dedup.execute("b", lambda: slow(2)),
        )

    results = _run(main())
    assert results == [1, 2]
    assert counter_slow["n"] == 2


def test_exception_propagation(dedup):
    class MyError(Exception):
        pass

    async def boom():
        await asyncio.sleep(0.01)
        raise MyError("boom")

    async def main():
        return await asyncio.gather(
            dedup.execute("k", boom),
            dedup.execute("k", boom),
            return_exceptions=True,
        )

    results = _run(main())
    assert all(isinstance(r, MyError) for r in results)


def test_cleanup_on_complete(dedup):
    async def ok():
        await asyncio.sleep(0.01)
        return 1

    r = _run(dedup.execute("k", ok))
    assert r == 1
    assert dedup.inflight_keys == []
