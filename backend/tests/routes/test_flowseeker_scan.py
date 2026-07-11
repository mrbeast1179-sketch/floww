"""/api/flowseeker/scan: cache, 429 backoff, stale-serve, regimes map."""
import asyncio
import json
import time

import pytest

import routes.flowseeker as fs

# The real functions, captured before the autouse fixture stubs the module attrs.
_REAL_CACHED_REGIMES = fs._cached_regimes
_REAL_RECORD_BASELINE = fs._record_scan_baseline


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
    # Stub the regimes lookup: its deferred `import server` drags the whole app
    # (and its background fetchers, which would hit the patched httpx and
    # pollute FakeClient.calls) into the test process. Tested directly below.
    monkeypatch.setattr(fs, "_cached_regimes", lambda: {})
    monkeypatch.setattr(fs, "_last_force_refresh", 0.0)

    async def _no_baselines():
        return {}

    async def _no_record(rows):
        return None

    async def _no_prev_oi():
        return {}

    # Stubbed for the same reason as _cached_regimes: their deferred
    # `import server` drags the whole app into the test process.
    monkeypatch.setattr(fs, "_volume_baselines", _no_baselines)
    monkeypatch.setattr(fs, "_record_scan_baseline", _no_record)
    monkeypatch.setattr(fs, "_prev_contract_oi", _no_prev_oi)
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})
    FakeClient.calls = 0
    FakeClient.status = 200
    yield
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})


def scan(**kw):
    # force=False must be explicit: in direct (non-HTTP) calls the unresolved
    # Query(False) default object is truthy and would bypass cache + backoff.
    return asyncio.run(fs.market_scan(min_volume=1000, limit=300, force=False, **kw))


def test_success_returns_rows_with_source_and_asof():
    out = scan()
    assert out["count"] == 1
    assert out["source"] == "cvserver-screen"
    assert out["stale"] is False
    assert out["asof"]
    assert isinstance(out["regimes"], dict)
    assert out["prev_oi"] == {}          # stubbed; real path serves a {ckey: oi} map


def test_records_per_contract_oi(monkeypatch):
    """_record_scan_baseline bulk-upserts one prior-day OI doc per contract."""
    captured = {}

    class FakeColl:
        async def update_one(self, *a, **k):
            return None

        async def bulk_write(self, ops, ordered=True):
            captured["ops"] = ops
            return None

    class FakeDB:
        flow_scan_daily = FakeColl()
        flow_scan_contract_oi = FakeColl()

    import sys
    import types
    fake_server = types.ModuleType("server")
    fake_server.db = FakeDB()
    monkeypatch.setitem(sys.modules, "server", fake_server)

    rows = [
        ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06", 50000, 10000, 0.2, 0.5, 744.5],
        ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06", 60000, 10000, 0.2, 0.5, 744.5],  # dup key
        ["QQQ", "QQQ260706P00500000", "put", 500, "2026-07-06", 8000, 2000, 0.3, -0.4, 501.0],
    ]
    asyncio.run(_REAL_RECORD_BASELINE(rows))
    ops = captured["ops"]
    assert len(ops) == 2   # deduped per contract ticker
    keys = {op._filter["ticker"] for op in ops}
    assert keys == {"SPY260706C00745000", "QQQ260706P00500000"}


def test_second_call_within_ttl_hits_cache():
    scan()
    out = scan()
    assert FakeClient.calls == 1
    assert out["source"] == "cvserver-cached"


def test_force_true_bypasses_cache():
    scan()
    asyncio.run(fs.market_scan(min_volume=1000, limit=300, force=True))
    assert FakeClient.calls == 2


def test_429_with_warm_cache_serves_stale_and_backs_off():
    scan()
    fs._scan_cache["1000:300"]["ts"] = time.time() - 999   # expire the entry
    FakeClient.status = 429
    out = scan()
    assert out["stale"] is True
    assert out["source"] == "cvserver-stale"
    assert out["count"] == 1
    assert fs._scan_backoff["until"] > time.time()
    calls_after_429 = FakeClient.calls
    out2 = scan()                                           # inside backoff window
    assert out2["stale"] is True
    assert out2["retry_after_seconds"] is not None
    assert FakeClient.calls == calls_after_429               # upstream NOT re-hit


def test_429_with_no_cache_returns_503():
    from fastapi import HTTPException
    FakeClient.status = 429
    with pytest.raises(HTTPException) as e:
        scan()
    assert e.value.status_code == 503


def test_backoff_delay_doubles_and_caps():
    FakeClient.status = 429
    from fastapi import HTTPException
    for _ in range(8):
        fs._scan_backoff["until"] = 0.0                      # force upstream attempt
        with pytest.raises(HTTPException):
            scan()
    assert fs._scan_backoff["delay"] == 600.0


def test_concurrent_misses_single_flight_upstream():
    async def two():
        return await asyncio.gather(
            fs.market_scan(min_volume=1000, limit=300, force=False),
            fs.market_scan(min_volume=1000, limit=300, force=False),
        )
    a, b = asyncio.run(two())
    assert FakeClient.calls == 1          # second request served by the lock re-check
    assert a["count"] == 1 and b["count"] == 1


def test_force_refresh_429_sets_backoff_and_does_not_clear_it():
    from fastapi import HTTPException
    fs._scan_backoff.update({"until": time.time() + 120, "delay": 60.0})
    FakeClient.status = 429
    with pytest.raises(HTTPException) as e:
        asyncio.run(fs.force_refresh_scan(min_volume=1000, limit=300))
    assert e.value.status_code == 503
    assert fs._scan_backoff["until"] > time.time()   # still backing off
    assert fs._scan_backoff["delay"] == 120.0        # doubled, not reset


def test_force_refresh_success_clears_backoff():
    fs._scan_backoff.update({"until": time.time() + 120, "delay": 240.0})
    out = asyncio.run(fs.force_refresh_scan(min_volume=1000, limit=300))
    assert out["count"] == 1
    assert fs._scan_backoff["until"] == 0.0
    assert fs._scan_backoff["delay"] == 30.0


def test_cached_regimes_reads_heatmap_cache(monkeypatch):
    """_cached_regimes maps ticker → nodes.regime from fresh server cache entries."""
    import sys
    import types

    fake_server = types.ModuleType("server")
    fake_server._BUILD_HEATMAP_CACHE = {
        "SPY:6:day:None:False:80": {"ts": time.time(), "data": {"nodes": {"regime": "negative"}}},
        "QQQ:4:day:None:False:80": {"ts": time.time(), "data": {"nodes": {"regime": "positive"}}},
        "IWM:6:day:None:False:80": {"ts": time.time() - 9999, "data": {"nodes": {"regime": "positive"}}},  # stale
        "TSLA:6:day:None:False:80": {"ts": time.time(), "data": {"error": "no chain"}},                     # no nodes
    }
    monkeypatch.setitem(sys.modules, "server", fake_server)
    out = _REAL_CACHED_REGIMES()
    assert out == {"SPY": "negative", "QQQ": "positive"}
