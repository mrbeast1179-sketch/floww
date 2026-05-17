"""
Integration tests for Confluence Decoder API endpoints.
Run with: cd backend && source .venv/bin/activate && python -m pytest tests/ -v
"""
import pytest
import httpx
import asyncio

BASE = "http://localhost:8000/api"


@pytest.fixture
def client():
    return httpx.AsyncClient(base_url=BASE, timeout=30)


@pytest.mark.asyncio
async def test_root(client):
    r = await client.get("/")
    assert r.status_code == 200
    d = r.json()
    assert d["app"] == "confluence-decoder"


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("healthy", "degraded")
    assert "dependencies" in d


@pytest.mark.asyncio
async def test_tickers(client):
    r = await client.get("/tickers")
    assert r.status_code == 200
    d = r.json()
    assert "trinity" in d
    assert "SPY" in d["trinity"]


@pytest.mark.asyncio
async def test_heatmap_spy(client):
    r = await client.get("/heatmap/SPY?expiries=4")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert "strikes" in d
    assert "nodes" in d
    assert "market_regime" in d
    assert "implied_pdf" in d
    assert len(d["strikes"]) > 0


@pytest.mark.asyncio
async def test_heatmap_modes(client):
    for mode in ["day", "swing", "scalp"]:
        r = await client.get(f"/heatmap/SPY?expiries=2&mode={mode}")
        assert r.status_code == 200, f"Mode {mode} failed"
        d = r.json()
        assert d["mode"] == mode


@pytest.mark.asyncio
async def test_heatmap_dte_filter(client):
    r = await client.get("/heatmap/SPY?expiries=4&dte=2")
    assert r.status_code == 200
    d = r.json()
    assert "strikes" in d


@pytest.mark.asyncio
async def test_chain_spy(client):
    r = await client.get("/chain/SPY?min_oi=100")
    assert r.status_code == 200
    d = r.json()
    assert "rows" in d
    assert "count" in d
    assert d["count"] > 0
    # Check row structure
    row = d["rows"][0]
    assert "type" in row
    assert "strike" in row
    assert "iv" in row
    assert "gex" in row


@pytest.mark.asyncio
async def test_chain_filter_expiry(client):
    r = await client.get("/chain/SPY?min_oi=100")
    d = r.json()
    if d["count"] > 0 and d.get("expiries"):
        first_exp = d["expiries"][0]
        r2 = await client.get(f"/chain/SPY?min_oi=100&expiry={first_exp}")
        assert r2.status_code == 200


@pytest.mark.asyncio
async def test_advanced_spy(client):
    r = await client.get("/advanced/SPY?expiries=4")
    assert r.status_code == 200
    d = r.json()
    assert "implied_pdf" in d
    assert "regime" in d
    assert "hedge_impulse" in d
    assert "pressure_cloud" in d
    assert "charm_integral" in d


@pytest.mark.asyncio
async def test_regime_spy(client):
    # Try individual endpoint first, fall back to advanced
    r = await client.get("/regime/SPY")
    if r.status_code == 404:
        r = await client.get("/advanced/SPY?expiries=4")
        d = r.json()
        assert "regime" in d
    else:
        d = r.json()
        assert "regime" in d
        assert "atm_iv" in d
        assert "skew" in d


@pytest.mark.asyncio
async def test_implied_pdf_spy(client):
    r = await client.get("/implied-pdf/SPY")
    if r.status_code == 404:
        r = await client.get("/advanced/SPY?expiries=4")
        d = r.json()
        assert "implied_pdf" in d
    else:
        d = r.json()
        assert "strike_probabilities" in d
        assert "most_likely_price" in d
        assert "expected_move" in d


@pytest.mark.asyncio
async def test_hedge_impulse_spy(client):
    r = await client.get("/hedge-impulse/SPY")
    if r.status_code == 404:
        r = await client.get("/advanced/SPY?expiries=4")
        d = r.json()
        assert "hedge_impulse" in d
    else:
        d = r.json()
        assert "curve" in d
        assert "regime" in d
        assert "impulse_at_spot" in d


@pytest.mark.asyncio
async def test_pressure_cloud_spy(client):
    r = await client.get("/pressure-cloud/SPY")
    if r.status_code == 404:
        r = await client.get("/advanced/SPY?expiries=4")
        d = r.json()
        assert "pressure_cloud" in d
    else:
        d = r.json()
        assert "stability_zones" in d
        assert "acceleration_zones" in d


@pytest.mark.asyncio
async def test_charm_integral_spy(client):
    r = await client.get("/charm-integral/SPY")
    if r.status_code == 404:
        r = await client.get("/advanced/SPY?expiries=4")
        d = r.json()
        assert "charm_integral" in d
    else:
        d = r.json()
        assert "total_charm_to_close" in d
        assert "direction" in d
        assert "buckets" in d


@pytest.mark.asyncio
async def test_gex_timeframes_spy(client):
    r = await client.get("/gex-timeframes/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "timeframes" in d
    tf = d["timeframes"]
    for key in ["0DTE", "1DTE", "weekly", "monthly", "all"]:
        assert key in tf, f"Missing timeframe {key}"


@pytest.mark.asyncio
async def test_uoa_spy(client):
    r = await client.get("/uoa/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "unusual" in d
    if d["unusual"]:
        row = d["unusual"][0]
        assert "type" in row
        assert "strike" in row
        assert "signals" in row


@pytest.mark.asyncio
async def test_alerts_crud(client):
    # Create
    r = await client.post("/alerts", json={
        "ticker": "SPY",
        "alert_type": "gex_cross",
        "threshold": 1000000,
        "direction": "above",
        "channel": "ui",
    })
    assert r.status_code == 200
    d = r.json()
    alert_id = d.get("rule", {}).get("id") or d.get("id")
    assert alert_id

    # List
    r = await client.get("/alerts")
    assert r.status_code == 200
    d = r.json()
    # Response is {count: N, rules: [...]}
    alerts = d.get("rules", d) if isinstance(d, dict) else d
    assert isinstance(alerts, list)

    # Delete
    r = await client.delete(f"/alerts/{alert_id}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_trinity(client):
    r = await client.get("/trinity")
    assert r.status_code == 200
    d = r.json()
    # Response has tickers nested under "tickers" key
    tickers = d.get("tickers", d)
    assert "SPY" in tickers or "^SPX" in tickers


@pytest.mark.asyncio
async def test_spot_spy(client):
    r = await client.get("/spot/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "spot" in d
    assert d["spot"] > 0


@pytest.mark.asyncio
async def test_multiple_tickers(client):
    """Test heatmap for all major tickers."""
    for ticker in ["SPY", "QQQ", "IWM", "AAPL", "NVDA"]:
        r = await client.get(f"/heatmap/{ticker}?expiries=2")
        assert r.status_code == 200, f"Ticker {ticker} failed: {r.status_code}"
        d = r.json()
        assert d["ticker"].replace("^", "") == ticker.replace("^", "")


@pytest.mark.asyncio
async def test_404_handling(client):
    r = await client.get("/nonexistent")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_validation_error(client):
    r = await client.get("/heatmap/SPY?mode=invalid")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_gamma_flip_endpoint(client):
    r = await client.get("/gamma-flip/SPY?expiries=2")
    assert r.status_code == 200
    d = r.json()
    assert "gamma_flip" in d
    assert "call_wall" in d
    assert "put_wall" in d
    assert "regime" in d
    assert d["regime"] in ("positive_gamma", "negative_gamma", "unknown")


@pytest.mark.asyncio
async def test_daily_checklist_endpoint(client):
    r = await client.get("/daily-checklist/SPY?expiries=2")
    assert r.status_code == 200
    d = r.json()
    assert "regime" in d
    assert "key_levels" in d
    assert "strategy" in d
    assert "risk_management" in d
    assert "hedging_flow" in d
    assert "recommended_strategies" in d["strategy"]


# ----------------------------- Memory Tests -----------------------------

@pytest.mark.asyncio
async def test_memory_trade_endpoint(client):
    """Test storing a trade in memory."""
    r = await client.post("/memory/trade", json={
        "ticker": "SPY",
        "trade_type": "call",
        "entry_price": 450.0,
        "exit_price": 455.0,
        "pnl": 5.0,
        "notes": "Test trade"
    })
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"


@pytest.mark.asyncio
async def test_memory_gex_endpoint(client):
    """Test storing a GEX observation in memory."""
    r = await client.post("/memory/gex", json={
        "ticker": "SPY",
        "observation": "GEX regime changed from positive to negative",
        "metadata": {"regime": "NEGATIVE", "gamma_flip": 450.0}
    })
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"


@pytest.mark.asyncio
async def test_memory_recall_endpoint(client):
    """Test recalling memories for a ticker."""
    r = await client.get("/memory/recall/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "results" in d


@pytest.mark.asyncio
async def test_memory_summary_endpoint(client):
    """Test getting a trading summary from memory."""
    r = await client.get("/memory/summary/SPY")
    assert r.status_code == 200
    d = r.json()
    assert "summary" in d


# ----------------------------- New Alert Type Tests -----------------------------

@pytest.mark.asyncio
async def test_alert_types_in_response(client):
    """Test that all alert types are present in the alert system."""
    r = await client.get("/alerts/types")
    assert r.status_code == 200
    d = r.json()
    alert_types = [a["type"] for a in d.get("alert_types", [])]
    # Check new alert types are registered
    expected_types = [
        "GAMMA_FLIP", "GAMMA_SQUEEZE", "MOMENTUM_EXTREME",
        "WALL_BREACH", "GEX_MAGNITUDE_SHIFT", "GAMMA_FLIP_PROXIMITY",
        "PIN_RISK", "CHARM_PINNING", "VANNA_REGIME_CHANGE",
        "UNUSUAL_PC_OI_RATIO", "MAX_PAIN_MAGNET"
    ]
    for expected in expected_types:
        assert expected in alert_types, f"Missing alert type: {expected}"
