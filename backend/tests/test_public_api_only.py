"""
backend/tests/test_public_api_only.py

Public-API-only policy tests (2026-09-03, architect directive):
no Schwab, no Alpha Vantage — every live market-data path is Public.com.

All tests are offline (mocked broker/provider). No live key required.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import server
from server import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bars(n: int = 30, start: float = 100.0) -> list[dict]:
    """Deterministic rising OHLCV bars for technical-indicator tests."""
    return [
        {"t": i, "o": start + i, "h": start + i + 1, "l": start + i - 1,
         "c": start + i, "v": 1000}
        for i in range(n)
    ]


def _fake_broker(**kwargs) -> MagicMock:
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")
    for key, val in kwargs.items():
        setattr(broker, key, val)
    return broker


# ---------------------------------------------------------------------------
# 1. AlphaVantageProvider is a disabled stub
# ---------------------------------------------------------------------------

class TestAlphaVantageRetired:
    def test_disabled_by_default(self):
        from data_providers import AlphaVantageProvider
        with patch.dict(os.environ, {"ALPHA_VANTAGE_KEY": "some-key"}):
            p = AlphaVantageProvider()
        assert p.enabled is False

    @pytest.mark.asyncio
    async def test_quote_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_quote("SPY") is None

    @pytest.mark.asyncio
    async def test_technical_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_technical_indicator("SPY", "RSI") is None

    @pytest.mark.asyncio
    async def test_forex_returns_none(self):
        from data_providers import AlphaVantageProvider
        p = AlphaVantageProvider()
        assert await p.get_forex_rate("USD", "EUR") is None

    def test_status_reports_disabled(self):
        from data_providers import DataAggregator
        status = DataAggregator().get_status()
        assert status["public_api"]["enabled"] is True
        assert status["alphavantage"]["enabled"] is False


# ---------------------------------------------------------------------------
# 2. DataAggregator tries Public API first
# ---------------------------------------------------------------------------

class TestAggregatorPublicFirst:
    @pytest.mark.asyncio
    async def test_public_api_first(self):
        from data_providers import DataAggregator
        agg = DataAggregator()
        import services.public_api_adapter as adapter
        with patch.object(adapter, "fetch_spot_from_public_api",
                          new=AsyncMock(return_value=450.0)):
            result = await agg.get_spot_price("SPY")
        assert result is not None
        assert result["source"] == "public_api"
        assert result["price"] == 450.0

    @pytest.mark.asyncio
    async def test_falls_through_when_public_unavailable(self):
        from data_providers import DataAggregator
        agg = DataAggregator()
        agg.finnhub.get_quote = AsyncMock(return_value={"price": 451.0, "source": "finnhub"})
        import services.public_api_adapter as adapter
        with patch.object(adapter, "fetch_spot_from_public_api",
                          new=AsyncMock(return_value=None)):
            result = await agg.get_spot_price("SPY")
        assert result is not None
        assert result["source"] == "finnhub"


# ---------------------------------------------------------------------------
# 3. Schwab routes are 410 Gone
# ---------------------------------------------------------------------------

class TestSchwabRetired:
    def test_auth_url_gone(self):
        r = client.get("/api/schwab/auth-url")
        assert r.status_code == 410
        assert r.json()["error"] == "schwab_retired"
        assert "/api/public/brokerage/" in r.json()["replacement"]

    def test_accounts_gone(self):
        r = client.get("/api/schwab/accounts")
        assert r.status_code == 410

    def test_positions_gone(self):
        r = client.get("/api/schwab/positions/abc123")
        assert r.status_code == 410
        assert r.json()["replacement"] == "/api/public/brokerage/portfolio"

    def test_sweeps_gone(self):
        r = client.get("/api/schwab/sweeps/abc123")
        assert r.status_code == 410

    def test_import_gone(self):
        # POST routes sit behind the API-key middleware → send the test key.
        r = client.post("/api/schwab/import-to-portfolio/x/abc123",
                        headers={"X-API-Key": "test-secret-key"})
        assert r.status_code == 410

    def test_client_construction_raises(self):
        from schwab import SchwabClient, SchwabRetiredError
        with pytest.raises(SchwabRetiredError):
            SchwabClient()


# ---------------------------------------------------------------------------
# 4. Alpha routes: live shims on Public API, 410 elsewhere
# ---------------------------------------------------------------------------

class TestAlphaShims:
    def test_quote_from_public(self):
        with patch("services.public_api_adapter.fetch_spot_from_public_api",
                   new=AsyncMock(return_value=450.0)):
            r = client.get("/api/alpha/quote/SPY")
        assert r.status_code == 200
        d = r.json()
        assert d["price"] == 450.0
        assert d["data_source"] == "public_api"

    def test_options_from_public(self):
        fake_chain = {"spot": 450.0, "expiries": ["2026-09-04"],
                      "contracts": [{"expiry": "2026-09-04", "strike": 450}]}
        with patch("services.public_api_adapter.fetch_chain_from_public_api",
                   new=AsyncMock(return_value=fake_chain)):
            r = client.get("/api/alpha/options/SPY")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_technical_from_public_bars(self):
        with patch("services.public_api_adapter.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars())):
            r = client.get("/api/alpha/technical/SPY/RSI")
        assert r.status_code == 200
        d = r.json()
        assert d["indicator"] == "RSI"
        assert d["data_source"] == "public_api"
        assert d["value"] == 100.0  # monotonically rising → RSI 100

    def test_historical_from_public(self):
        payload = {"ticker": "SPY", "interval": "daily", "bars": _bars(5),
                   "n_bars": 5, "data_source": "public_api"}
        with patch("services.public_api_adapter.fetch_history_from_public_api",
                   new=AsyncMock(return_value=payload)):
            r = client.get("/api/alpha/historical/SPY")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_intraday_from_public(self):
        with patch("services.public_api_adapter.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(5))):
            r = client.get("/api/alpha/intraday/SPY?interval=5min")
        assert r.status_code == 200
        assert r.json()["data_source"] == "public_api"

    def test_overview_gone(self):
        r = client.get("/api/alpha/overview/SPY")
        assert r.status_code == 410
        assert r.json()["error"] == "alpha_vantage_retired"

    def test_market_status_gone(self):
        r = client.get("/api/alpha/market-status")
        assert r.status_code == 410

    def test_no_alphavantage_co_calls(self):
        # The vendor request helpers are deleted; no route may reference
        # the vendor host anymore.
        import inspect

        import routes.alpha_advantage as mod
        src = inspect.getsource(mod)
        assert "alphavantage.co" not in src
        assert not hasattr(mod, "_av_request")
        assert not hasattr(mod, "_av_request_circuit")
        # The quote path is served live from Public API.
        with patch("services.public_api_adapter.fetch_spot_from_public_api",
                   new=AsyncMock(return_value=1.0)):
            r = client.get("/api/alpha/quote/SPY")
            assert r.status_code == 200
            assert r.json()["data_source"] == "public_api"


# ---------------------------------------------------------------------------
# 5. New /api/public/* endpoints (mocked broker)
# ---------------------------------------------------------------------------

class TestPublicBarsHistoryTechnical:
    def test_bars(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(5))):
            r = client.get("/api/public/bars/SPY?interval=daily")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["n_bars"] == 5
        assert d["data_source"] == "public_api"

    def test_bars_502_when_unavailable(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=None)):
            r = client.get("/api/public/bars/SPY")
        assert r.status_code == 502

    def test_history(self):
        payload = {"ticker": "SPY", "interval": "daily", "bars": _bars(5),
                   "n_bars": 5, "data_source": "public_api"}
        with patch("routes.public_api.fetch_history_from_public_api",
                   new=AsyncMock(return_value=payload)):
            r = client.get("/api/public/history/SPY")
        assert r.status_code == 200
        assert r.json()["n_bars"] == 5

    def test_technical_sma(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(30))):
            r = client.get("/api/public/technical/SPY/SMA?time_period=10")
        assert r.status_code == 200
        d = r.json()
        assert d["indicator"] == "SMA"
        # closes 100..129 → SMA(10) of last 10 = mean(120..129) = 124.5
        assert d["value"] == pytest.approx(124.5)

    def test_technical_bad_indicator_400(self):
        with patch("routes.public_api.fetch_bars_from_public_api",
                   new=AsyncMock(return_value=_bars(30))):
            r = client.get("/api/public/technical/SPY/NOPE")
        assert r.status_code == 400

    def test_expirations(self):
        broker = _fake_broker()
        broker.get_option_expirations = AsyncMock(return_value=["2026-09-04"])
        with patch("routes.public_api._get_broker", new=AsyncMock(return_value=broker)):
            r = client.get("/api/public/expirations/SPY")
        assert r.status_code == 200
        assert r.json()["expirations"] == ["2026-09-04"]


# ---------------------------------------------------------------------------
# 6. Local technical math
# ---------------------------------------------------------------------------

class TestTechnicalMath:
    def test_rsi_rising_is_100(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "RSI", _bars(30), 14)
        assert out["value"] == 100.0

    def test_rsi_flat_is_100(self):
        from services.public_api_adapter import compute_technical_from_bars
        flat = [{"t": i, "o": 100, "h": 100, "l": 100, "c": 100, "v": 1} for i in range(30)]
        out = compute_technical_from_bars("SPY", "RSI", flat, 14)
        assert out["value"] == 100.0

    def test_sma_value(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "SMA", _bars(30), 10)
        assert out["value"] == pytest.approx(124.5)

    def test_macd_positive_on_rise(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "MACD", _bars(60), 14)
        assert out["value"] > 0

    def test_unsupported_indicator(self):
        from services.public_api_adapter import compute_technical_from_bars
        out = compute_technical_from_bars("SPY", "NOPE", _bars(30), 14)
        assert "error" in out


# ---------------------------------------------------------------------------
# 7. Health reports public_api, retired stub stays disabled
# ---------------------------------------------------------------------------

class TestHealthPublicApi:
    def test_public_api_healthy_with_key(self):
        with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
            r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["checks"]["public_api"]["status"] == "healthy"

    def test_alpha_stub_disabled_never_degrades(self):
        with patch.dict(os.environ, {"PUBLIC_API_KEY": "test-key"}):
            r = client.get("/api/health")
        body = r.json()
        assert body["checks"]["alpha_vantage"]["status"] == "disabled"
        assert body["status"] == "healthy"

    def test_data_status_reports_policy(self):
        r = client.get("/api/data/status")
        assert r.status_code == 200
        d = r.json()
        assert d["primary"] == "public_api"
        assert "alphavantage" in d["retired"]
        assert "schwab" in d["retired"]
        assert d["providers"]["alphavantage"]["enabled"] is False
