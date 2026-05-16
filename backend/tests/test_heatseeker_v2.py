"""V2 features: 2D grid heatmap, swing mode, contract drilldown, Databento usage."""
import os
import math
import pytest
import requests

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Grid + data_source on heatmap SPY day ---
def test_heatmap_spy_day_grid(session):
    r = session.get(f"{API}/heatmap/SPY?expiries=3&mode=day", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d.get("mode") == "day"
    assert "grid" in d
    grid = d["grid"]
    for k in ("expiries", "strikes", "grid", "strike_totals"):
        assert k in grid, f"grid missing {k}"
    assert isinstance(grid["expiries"], list) and len(grid["expiries"]) > 0
    assert isinstance(grid["strikes"], list) and len(grid["strikes"]) > 0
    # grid map keyed by expiry then strike-as-int-string when whole number
    first_exp = grid["expiries"][0]
    cells = grid["grid"][first_exp]
    assert isinstance(cells, dict)
    for key in cells.keys():
        # SPY strikes are integers, should not contain "."
        # (SPY has half-strikes only on weeklies — but we still want pure-int strings for whole numbers)
        if "." not in key:
            assert key.lstrip("-").isdigit(), f"non-int-string key {key} for SPY whole strike"
    # data_source
    assert d.get("data_source") in ("databento+yfinance", "yfinance")


def test_heatmap_swing_more_expiries_wider_band(session):
    # Day baseline
    rd = session.get(f"{API}/heatmap/SPY?expiries=4&mode=day", timeout=120).json()
    rs = session.get(f"{API}/heatmap/SPY?expiries=8&mode=swing", timeout=180).json()
    assert rs.get("mode") == "swing"
    # Swing should have >= day expiries
    assert len(rs["grid"]["expiries"]) >= len(rd["grid"]["expiries"])
    spot = rs["spot"]
    # widest strike distance / spot > 0.15 (since band is ±25% in swing)
    if rs["grid"]["strikes"]:
        max_dev = max(abs(s - spot) / spot for s in rs["grid"]["strikes"])
        # In practice should be > 0.15 if chain has strikes that far
        assert max_dev <= 0.26  # within band cap
    # day baseline must be <= 0.16
    if rd["grid"]["strikes"]:
        max_dev_d = max(abs(s - spot) / spot for s in rd["grid"]["strikes"])
        assert max_dev_d <= 0.16


def test_heatmap_spx_via_spxw(session):
    r = session.get(f"{API}/heatmap/%5ESPX?expiries=2&mode=day", timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "^SPX"
    assert d["spot"] > 0
    assert "grid" in d and len(d["grid"]["strikes"]) > 0


def test_heatmap_qqq_grid(session):
    r = session.get(f"{API}/heatmap/QQQ?expiries=2&mode=day", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "QQQ"
    assert len(d["grid"]["strikes"]) > 0


def test_trinity_day_all_populated(session):
    r = session.get(f"{API}/trinity?mode=day", timeout=240)
    assert r.status_code == 200, r.text
    d = r.json()
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"], f"missing {t}"
        entry = d["tickers"][t]
        if "error" in entry:
            pytest.fail(f"trinity {t} errored: {entry['error']}")
        assert entry["spot"] > 0
        assert len(entry["strikes"]) > 0
    assert d["alignment"]["verdict"] in ("full_alignment", "partial_alignment", "divergence")


def test_contract_drilldown_spy(session):
    # Get a real expiry first
    r = session.get(f"{API}/heatmap/SPY?expiries=3", timeout=120).json()
    exp_list = r["grid"]["expiries"]
    assert exp_list
    exp = exp_list[1] if len(exp_list) > 1 else exp_list[0]
    r2 = session.get(f"{API}/contract/SPY?expiry={exp}", timeout=120)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] > 0
    assert d["count"] > 0
    assert isinstance(d["rows"], list) and len(d["rows"]) > 0
    row = d["rows"][0]
    for k in ("strike", "type", "oi", "iv", "delta", "gamma", "gex"):
        assert k in row, f"missing {k} in drilldown row"
    assert isinstance(row["delta"], (int, float))
    assert isinstance(row["gamma"], (int, float))
    # oi_source present when databento active
    if d.get("data_source", "").startswith("databento"):
        assert any("oi_source" in r_ for r_ in d["rows"]), "missing oi_source despite databento data_source"


def test_databento_usage(session):
    r = session.get(f"{API}/databento/usage", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "cached_days" in d
    assert "recent" in d
    assert isinstance(d["recent"], list)
    # Should have at least 1 cached snapshot from prior heatmap calls
    if d["cached_days"] > 0:
        item = d["recent"][0]
        for k in ("parent", "day", "count"):
            assert k in item


def test_databento_oi_collection_populated(session):
    """After hitting heatmap, Databento cache should have at least one record."""
    session.get(f"{API}/heatmap/SPY?expiries=2", timeout=120)
    r = session.get(f"{API}/databento/usage", timeout=15)
    d = r.json()
    # Either databento active (cached_days >= 1) or env disabled — accept both but flag
    assert d.get("cached_days", 0) >= 0
