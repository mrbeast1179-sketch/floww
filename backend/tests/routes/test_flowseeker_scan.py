"""/api/flowseeker/scan: cache, 429 backoff, stale-serve, regimes map."""
import asyncio
import json
import time

import pytest

import routes.flowseeker as fs


class FakeResp:
    def __init__(self, status_code=200, rows=None):
        self.status_code = status_code
        self._rows = rows or [
            ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06",
             50000, 10000, 0.2, 0.5, 744.5],
        ]

    def json(self):
        return {"result": {"content": [
            {"type": "text", "text": json.dumps({"rows": self._rows})},
        ]}}


class FakeClient:
    calls = 0
    status = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        FakeClient.calls += 1
        return FakeResp(FakeClient.status)


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(fs, "CVFORGE_API_KEY", "test-key")
    monkeypatch.setattr(fs.httpx, "AsyncClient", FakeClient)
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})
    FakeClient.calls = 0
    FakeClient.status = 200
    yield
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})


def run(coro):
    return asyncio.run(coro)


def test_success_returns_rows_with_source_and_asof():
    out = run(fs.market_scan(min_volume=1000, limit=300))
    assert out["count"] == 1
    assert out["source"] == "cvserver-screen"
    assert out["stale"] is False
    assert out["asof"]
    assert isinstance(out["regimes"], dict)


def test_second_call_within_ttl_hits_cache():
    run(fs.market_scan(min_volume=1000, limit=300))
    run(fs.market_scan(min_volume=1000, limit=300))
    assert FakeClient.calls == 1


def test_429_with_warm_cache_serves_stale_and_backs_off():
    run(fs.market_scan(min_volume=1000, limit=300))
    fs._scan_cache["1000:300"]["ts"] = time.time() - 999   # expire the entry
    FakeClient.status = 429
    out = run(fs.market_scan(min_volume=1000, limit=300))
    assert out["stale"] is True
    assert out["count"] == 1
    assert fs._scan_backoff["until"] > time.time()
    calls_after_429 = FakeClient.calls
    out2 = run(fs.market_scan(min_volume=1000, limit=300))  # inside backoff window
    assert out2["stale"] is True
    assert FakeClient.calls == calls_after_429               # upstream NOT re-hit


def test_429_with_no_cache_returns_503():
    from fastapi import HTTPException
    FakeClient.status = 429
    with pytest.raises(HTTPException) as e:
        run(fs.market_scan(min_volume=1000, limit=300))
    assert e.value.status_code == 503


def test_backoff_delay_doubles_and_caps():
    FakeClient.status = 429
    from fastapi import HTTPException
    for _ in range(8):
        fs._scan_backoff["until"] = 0.0                      # force upstream attempt
        with pytest.raises(HTTPException):
            run(fs.market_scan(min_volume=1000, limit=300))
    assert fs._scan_backoff["delay"] == 600.0
