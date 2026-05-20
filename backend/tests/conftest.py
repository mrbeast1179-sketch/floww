"""Shared test fixtures."""
import asyncio
import os

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from server import app

# Configure pytest-asyncio to auto-detect async tests
pytest_plugins = ["pytest_asyncio"]


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


@pytest_asyncio.fixture(autouse=True)
async def _reset_event_loop_and_motor(aclient, monkeypatch):
    """Reset event loop AND motor client before each test.

    This fixes the 'Event loop is closed' RuntimeError that occurs when:
    1. TestClient uses anyio.from_thread which creates a new event loop per request
    2. After a test, that loop is closed
    3. The next test's motor client still references the closed loop
    4. Async iteration over motor cursors fails with 'Event loop is closed'

    Fix: Close old loop, create fresh one, AND create fresh motor client bound to new loop.
    """
    import server
    from motor.motor_asyncio import AsyncIOMotorClient

    # Step 1: Close old event loop
    try:
        old_loop = asyncio.get_event_loop()
        if not old_loop.is_closed():
            old_loop.close()
    except RuntimeError:
        pass

    # Step 2: Create fresh event loop
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)

    # Step 3: Create fresh motor client bound to the new loop
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_confluence_decoder")

    fresh = AsyncIOMotorClient(
        mongo_url,
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    monkeypatch.setattr(server, "client", fresh)
    monkeypatch.setattr(server, "db", fresh[db_name])

    # Step 4: Reset error tracking
    try:
        from error_tracking import clear_error_log
        clear_error_log()
    except Exception:
        pass

    try:
        yield
    finally:
        fresh.close()
        try:
            new_loop.close()
        except Exception:
            pass
