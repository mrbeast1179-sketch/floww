"""
Standalone test for health.py router — tests the router directly without
importing the full server (which may have transient breakages from other agents).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Add backend dir to path so we can import routes.health directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from routes.health import router

# Create a minimal FastAPI app with just the health router
app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestHealthEndpoint:
    """Test /api/health returns correct structure and status."""

    def test_health_returns_200(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_structure(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data

    def test_health_checks_contain_all_deps(self):
        resp = client.get("/api/health")
        checks = resp.json()["checks"]
        assert "duckdb" in checks
        assert "alpha_vantage" in checks
        assert "websocket" in checks

    def test_health_duckdb_healthy(self):
        resp = client.get("/api/health")
        assert resp.json()["checks"]["duckdb"]["status"] == "healthy"

    def test_health_websocket_shows_connections(self):
        ws = client.get("/api/health").json()["checks"]["websocket"]
        assert ws["status"] == "healthy"
        assert isinstance(ws["active_connections"], int)

    def test_health_overall_healthy_when_all_up(self):
        resp = client.get("/api/health")
        assert resp.json()["status"] in ("healthy", "degraded")

    def test_health_degraded_when_duckdb_fails(self):
        with patch("routes.health.duckdb_engine") as mock_engine:
            mock_engine._conn.execute.side_effect = Exception("DuckDB down")
            resp = client.get("/api/health")
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["checks"]["duckdb"]["status"] == "unhealthy"
            assert "DuckDB down" in data["checks"]["duckdb"]["error"]

    def test_health_degraded_when_av_times_out(self):
        with patch("routes.health.get_alpha_vantage_key", return_value="test-key"):
            with patch("routes.health.httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
                mock_client.get.side_effect = Exception("Connection timeout")
                resp = client.get("/api/health")
                data = resp.json()
                assert data["status"] == "degraded"
                assert data["checks"]["alpha_vantage"]["status"] == "unhealthy"
                assert "Connection timeout" in data["checks"]["alpha_vantage"]["error"]

    def test_health_av_unhealthy_on_missing_key(self):
        with patch("routes.health.get_alpha_vantage_key", return_value=""):
            resp = client.get("/api/health")
            av = resp.json()["checks"]["alpha_vantage"]
            assert av["status"] == "unhealthy"
            assert "ALPHA_VANTAGE_KEY not configured" in av["error"]

    def test_health_av_healthy_on_200(self):
        with patch("routes.health.get_alpha_vantage_key", return_value="test-key"):
            with patch("routes.health.httpx") as mock_httpx:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_client.get = AsyncMock(return_value=mock_resp)
                mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
                resp = client.get("/api/health")
                assert resp.json()["checks"]["alpha_vantage"]["status"] == "healthy"
