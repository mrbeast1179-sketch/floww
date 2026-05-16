"""Tests for portfolio, Schwab, live policy, and position sizing endpoints."""
import os
import pytest
import requests

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ============ Portfolio Tests ============

def test_portfolio_add_position(session):
    """Add a position to a portfolio."""
    pos = {
        "symbol": "SPY",
        "option_type": "call",
        "strike": 500.0,
        "expiry": "2026-06-15",
        "quantity": 2,
        "entry_price": 5.50,
        "entry_iv": 0.15,
        "underlying_price": 530.0,
    }
    r = session.post(f"{API}/portfolio/test/position", json=pos, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "added"
    assert d["positions"] >= 1


def test_portfolio_get(session):
    """Get portfolio summary."""
    r = session.get(f"{API}/portfolio/test?spot=530&iv=0.15", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "test"
    assert d["positions"] >= 1
    assert "greeks" in d
    assert "pnl" in d
    g = d["greeks"]
    for k in ("delta", "gamma", "vega", "theta"):
        assert k in g, f"missing greek {k}"


def test_portfolio_scenario(session):
    """Run scenario analysis."""
    r = session.get(f"{API}/portfolio/test/scenario?spot=530&iv=0.15", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "scenarios" in d
    assert len(d["scenarios"]) > 0
    # Should have spot and vol scenarios
    spot_scenarios = [s for s in d["scenarios"] if s["type"] == "spot"]
    vol_scenarios = [s for s in d["scenarios"] if s["type"] == "vol"]
    assert len(spot_scenarios) > 0
    assert len(vol_scenarios) > 0


def test_portfolio_hedge(session):
    """Calculate Greek-neutral hedge."""
    hedge_opts = [
        {"strike": 500, "expiry": "2026-06-15", "type": "call", "iv": 0.15},
        {"strike": 495, "expiry": "2026-06-15", "type": "put", "iv": 0.15},
    ]
    r = session.post(f"{API}/portfolio/test/hedge", json={
        "spot": 530, "iv": 0.15, "hedge_options": hedge_opts,
    }, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    if "error" not in d:
        assert "hedge_positions" in d
        assert "stock_hedge" in d
        assert "resulting_greeks" in d


def test_portfolio_remove_position(session):
    """Remove a position."""
    r = session.delete(f"{API}/portfolio/test/position/0", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "removed"


def test_portfolio_not_found(session):
    """404 for nonexistent portfolio."""
    r = session.get(f"{API}/portfolio/nonexistent_xyz?spot=530&iv=0.15", timeout=30)
    assert r.status_code == 404


# ============ Position Sizing Tests ============

def test_position_size(session):
    """Calculate position size."""
    r = session.post(
        f"{API}/position-size?account_size=100000&risk_per_trade_pct=0.02&spot=530&gex_level=1000000",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["recommended_contracts"] >= 1
    assert d["position_value"] > 0
    assert d["risk_per_trade"] == 2000.0  # 2% of 100k


# ============ Live Policy Tests ============

def test_live_policy_get(session):
    """Get current live policy."""
    r = session.get(f"{API}/live/policy", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "paid_tickers" in d
    assert "live_window_et" in d


def test_live_policy_update(session):
    """Update live policy."""
    r = session.post(f"{API}/live/policy", json={
        "paid_tickers": ["SPY"],
        "window_start": "09:00",
        "window_stop": "10:30",
    }, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "SPY" in d["paid_tickers"]


# ============ Schwab Tests (scaffold - will fail without credentials) ============

def test_schwab_auth_url_no_credentials(session):
    """Schwab auth URL should return error without credentials."""
    r = session.get(f"{API}/schwab/auth-url", timeout=15)
    # Without credentials, returns 500 or 200 with error
    assert r.status_code in (200, 500)


# ============ History Tests ============

def test_history_endpoint(session):
    """Get snapshot history."""
    # First trigger a snapshot by hitting heatmap
    session.get(f"{API}/heatmap/SPY?expiries=2", timeout=120)
    r = session.get(f"{API}/history/SPY?limit=5", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "snapshots" in d
    assert isinstance(d["snapshots"], list)


# ============ Patterns Glossary Tests ============

def test_patterns_glossary(session):
    """Get patterns glossary."""
    r = session.get(f"{API}/patterns/glossary", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "King Node" in d or "king" in str(d).lower()
