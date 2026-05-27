"""Regression: H4 hardening — heatseeker routes degrade gracefully."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


def _broken_fetch(*a, **kw):
    raise RuntimeError("simulated chain fetch failure")


def test_flip_zones_returns_degraded_on_chain_failure(client):
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/heatseeker/flip-zones?ticker=SPY")
        assert r.status_code == 200, f"expected 200 degraded, got {r.status_code}"
        body = r.json()
        assert body.get("status") == "degraded", body
        assert body.get("zones") == [], body


def test_node_lifecycle_returns_degraded_on_failure(client):
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/heatseeker/node-lifecycle?ticker=SPY")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "degraded", body
        assert body.get("nodes") == [], body


def test_air_pockets_returns_degraded_on_failure(client):
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(side_effect=_broken_fetch)):
        r = client.get("/heatseeker/air-pockets?ticker=SPY")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "degraded", body


def test_routes_still_propagate_404_for_missing_data(client):
    """HTTPException 404 must still propagate (not get swallowed by the catch-all)."""
    with patch("routes.heatseeker._fetch_chain", new=AsyncMock(return_value={"spot": None, "contracts": []})):
        r = client.get("/heatseeker/flip-zones?ticker=ZZZ")
        assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"
