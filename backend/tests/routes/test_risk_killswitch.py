#!/usr/bin/env python3
"""
backend/tests/routes/test_risk_killswitch.py — Tests for the
/api/risk/killswitch endpoint family (GET status, POST reset,
POST trip).

Uses FastAPI TestClient against the flowseeker router.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest
from fastapi.testclient import TestClient

from routes.flowseeker import router


@pytest.fixture
def client():
    from fastapi import FastAPI
    app = FastAPI()
    # router already has prefix="/api/flowseeker" — don't double-prefix
    app.include_router(router)
    return TestClient(app)


class TestKillSwitchStatus:
    def test_default_status(self, client):
        r = client.get("/api/flowseeker/risk/killswitch?equity=100000")
        assert r.status_code == 200
        data = r.json()
        assert data["tripped"] is False
        assert data["daily_pnl_pct"] == 0.0
        # start_day(equity=100000) seeds peak_equity = equity
        assert data["peak_equity"] == 100000.0
        assert data["current_equity"] == 100000.0

    def test_status_with_equity(self, client):
        r = client.get("/api/flowseeker/risk/killswitch?equity=100000")
        data = r.json()
        # First call seeds start_day(100000)
        assert data["daily_starting_equity"] == 100000.0
        assert data["peak_equity"] == 100000.0
        assert data["current_equity"] == 100000.0


class TestKillSwitchReset:
    def test_reset_clears_tripped(self, client):
        # Trip first via the trip endpoint
        client.post("/api/flowseeker/risk/killswitch/trip?equity=100000")
        r = client.get("/api/flowseeker/risk/killswitch?equity=100000")
        assert r.json()["tripped"] is True
        # Reset
        r2 = client.post("/api/flowseeker/risk/killswitch/reset")
        assert r2.status_code == 200
        assert r2.json()["reset"] is True
        assert r2.json()["kill_switch"]["tripped"] is False

    def test_reset_response_shape(self, client):
        r = client.post("/api/flowseeker/risk/killswitch/reset")
        assert r.status_code == 200
        data = r.json()
        assert "reset" in data
        assert "kill_switch" in data


class TestKillSwitchTrip:
    def test_trip_marks_tripped(self, client):
        r = client.post("/api/flowseeker/risk/killswitch/trip?equity=100000")
        assert r.status_code == 200
        data = r.json()
        assert data["tripped"] is True
        assert data["trip_reason"] == "manual_trip_via_api"

    def test_trip_returns_full_status(self, client):
        r = client.post("/api/flowseeker/risk/killswitch/trip?equity=90000")
        data = r.json()
        assert "current_equity" in data
        assert "daily_pnl_pct" in data
        assert "peak_equity" in data
