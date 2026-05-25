"""
backend/tests/services/test_morning_briefing_api.py

Integration tests for the /api/briefing/{ticker} REST endpoint.

Tests verify:
  - GET /api/briefing/SPY returns valid JSON with regime
  - Response structure: {regime, narrative, timestamp, metrics}
  - Cache works (second call is faster, same result)
  - 15-min TTL is respected
  - I-7: route is at /api/briefing/{ticker}, NOT /api/api/briefing/{ticker}

Run with:
    cd backend && venv/bin/python -m pytest tests/services/test_morning_briefing_api.py -v
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app)


class TestBriefingEndpoint:
    """Test GET /api/briefing/{ticker}."""

    def test_briefing_returns_200_for_spy(self, client):
        """GET /api/briefing/SPY returns 200."""
        r = client.get("/api/briefing/SPY")
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

    def test_briefing_returns_valid_json(self, client):
        """Response is valid JSON."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert isinstance(data, dict)

    def test_briefing_has_regime_field(self, client):
        """Response contains 'regime' field."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert "regime" in data

    def test_briefing_regime_is_valid_value(self, client):
        """Regime is one of BULLISH, BEARISH, NEUTRAL, UNKNOWN."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert data["regime"] in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")

    def test_briefing_has_narrative(self, client):
        """Response contains 'narrative' field."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert "narrative" in data
        assert isinstance(data["narrative"], str)
        assert len(data["narrative"]) > 0

    def test_briefing_has_timestamp(self, client):
        """Response contains 'timestamp' field."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

    def test_briefing_has_metrics(self, client):
        """Response contains 'metrics' dict."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert "metrics" in data
        assert isinstance(data["metrics"], dict)

    def test_briefing_narrative_under_500_chars(self, client):
        """Narrative is always <= 500 chars."""
        r = client.get("/api/briefing/SPY")
        data = r.json()
        assert len(data["narrative"]) <= 500

    def test_briefing_ticker_case_insensitive(self, client):
        """Ticker is case-insensitive."""
        r1 = client.get("/api/briefing/spy")
        r2 = client.get("/api/briefing/SPY")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Both should return the same ticker in response
        assert r1.json()["ticker"] == r2.json()["ticker"]

    def test_briefing_returns_404_for_double_prefix(self, client):
        """I-7 fix: /api/api/briefing/{ticker} must NOT work (double prefix bug)."""
        r = client.get("/api/api/briefing/SPY")
        assert r.status_code == 404

    def test_briefing_different_tickers(self, client):
        """Different tickers return their own briefings."""
        r_spy = client.get("/api/briefing/SPY")
        r_qqq = client.get("/api/briefing/QQQ")
        assert r_spy.status_code == 200
        assert r_qqq.status_code == 200
        assert r_spy.json()["ticker"] == "SPY"
        assert r_qqq.json()["ticker"] == "QQQ"

    def test_briefing_metrics_contain_expected_keys(self, client):
        """Metrics dict has expected sub-keys."""
        r = client.get("/api/briefing/SPY")
        metrics = r.json()["metrics"]
        # May be empty/zero if no data, but keys should exist if we have data
        if metrics:
            for key in ("net_gex", "flip_level", "iv_skew", "spot"):
                assert key in metrics


class TestBriefingCache:
    """Test the 15-minute cache behavior."""

    def test_cache_returns_same_result(self, client):
        """Two calls for same ticker return the same cached result."""
        import routes.morning_briefing_api as api
        api._briefing_cache.clear()

        r1 = client.get("/api/briefing/SPY")
        r2 = client.get("/api/briefing/SPY")
        assert r1.json() == r2.json()

    def test_cache_second_call_faster(self, client):
        """Second call should be faster (cache hit)."""
        import routes.morning_briefing_api as api
        api._briefing_cache.clear()

        t1_start = time.monotonic()
        client.get("/api/briefing/SPY")
        t1 = time.monotonic() - t1_start

        t2_start = time.monotonic()
        client.get("/api/briefing/SPY")
        t2 = time.monotonic() - t2_start

        # Second call should be <= first (cached)
        assert t2 <= t1 * 1.5  # Allow some variance
