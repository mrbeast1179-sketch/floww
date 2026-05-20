"""Shared test fixtures."""
import asyncio
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from server import app


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def aclient():
    """Async HTTP client for the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def _refresh_motor_client_per_test(monkeypatch):
    """Reset ``server.client`` (motor) and ``server.db`` before each test.

    Why this exists: ``backend/server.py:67`` instantiates a module-level
    ``AsyncIOMotorClient`` that caches a reference to whichever event loop
    handled its first request. ``fastapi.testclient.TestClient`` uses
    ``anyio.from_thread`` internally, which spins up a fresh event loop
    per call. After the first test runs a TestClient request, motor's
    cached loop is closed; the next TestClient call (in another module)
    explodes with ``RuntimeError: Event loop is closed``.

    Fix: monkeypatch ``server.client``/``server.db`` to a fresh motor
    handle at the start of every test. The fresh handle is unbound, so
    the first request inside *this* test binds it to whatever loop runs
    that request — then we discard it at teardown.

    Pre-existing 24 failures in test_portfolio, test_v3_costsave,
    test_heatseeker_v2 all matched this pattern. With this fixture they
    pass in the full suite (not just individually).
    """
    import server
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_confluence_decoder")

    fresh = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    monkeypatch.setattr(server, "client", fresh)
    monkeypatch.setattr(server, "db", fresh[db_name])
    try:
        yield
    finally:
        fresh.close()


@pytest.fixture(autouse=True)
def _reset_event_loop_per_test():
    """Reset the asyncio event loop before each test.

    TestClient uses anyio.from_thread which creates a new event loop
    per request. After a test completes, that loop is closed. The next
    test's TestClient request may try to use asyncio.to_thread which
    references the now-closed loop.

    This fixture ensures each test starts with a fresh event loop.
    """
    # Close any existing loop and create a fresh one
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    yield
    # Clean up: close the loop we created
    try:
        new_loop.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_error_tracking_per_test():
    """Reset error tracking state between tests."""
    from error_tracking import clear_error_log
    clear_error_log()
    yield
    clear_error_log()
