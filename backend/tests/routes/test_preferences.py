"""Tests for routes/preferences.py — user preferences API.

Covers: GET defaults, theme validation, arbitrary key setting with
validation filters, and Mongo persistence failure tolerance (the route
must still return 200 when Mongo is down — persistence is best-effort).
"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routes.preferences import _preferences, router

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_prefs():
    _preferences.clear()
    _preferences.update({"theme": "dark", "default_ticker": "SPY", "refresh_ms": 25000})
    yield
    _preferences.clear()
    _preferences.update({"theme": "dark", "default_ticker": "SPY", "refresh_ms": 25000})


@pytest.fixture
async def client():
    """ASGI client on the router only — HTTPException(404/405) from unmatched
    sub-paths must be raised, not swallowed, so tests assert real status codes."""
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_get_defaults(client):
    r = await client.get("/api/preferences/")
    assert r.status_code == 200
    d = r.json()
    assert d["theme"] == "dark"
    assert d["default_ticker"] == "SPY"
    assert d["refresh_ms"] == 25000


async def test_set_theme_valid(client):
    r = await client.post("/api/preferences/theme", json={"theme": "light"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "theme": "light"}
    assert (await client.get("/api/preferences/")).json()["theme"] == "light"


async def test_set_theme_invalid_rejected(client):
    r = await client.post("/api/preferences/theme", json={"theme": "solarized"})
    assert r.status_code == 400
    # unchanged
    assert (await client.get("/api/preferences/")).json()["theme"] == "dark"


async def test_set_arbitrary_preferences(client):
    r = await client.post(
        "/api/preferences/",
        json={"default_ticker": "QQQ", "refresh_ms": 5000},
    )
    assert r.status_code == 200
    d = (await client.get("/api/preferences/")).json()
    assert d["default_ticker"] == "QQQ"
    assert d["refresh_ms"] == 5000


async def test_validation_filters_applied(client):
    """refresh_ms below 1000 and invalid theme keys are silently skipped."""
    r = await client.post(
        "/api/preferences/",
        json={"theme": "blue", "refresh_ms": 100, "custom_key": "kept"},
    )
    assert r.status_code == 200
    d = (await client.get("/api/preferences/")).json()
    assert d["theme"] == "dark"          # invalid theme skipped
    assert d["refresh_ms"] == 25000      # too-low refresh skipped
    assert d["custom_key"] == "kept"     # arbitrary keys allowed


async def test_mongo_failure_still_ok(client, monkeypatch):
    """Persistence is best-effort: a Mongo outage must not fail the request."""
    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("mongo down")

    import server

    monkeypatch.setattr(server, "db", _Boom(), raising=False)
    r = await client.post("/api/preferences/theme", json={"theme": "light"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
