"""Backend tests for Confluence Decoder (Heatseeker GEX)."""
import os
import math
import pytest
import requests

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
API = f"{BASE_URL}/api"


def _has_nan_or_inf(obj):
    if isinstance(obj, float):
        return math.isnan(obj) or math.isinf(obj)
    if isinstance(obj, dict):
        return any(_has_nan_or_inf(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_nan_or_inf(v) for v in obj)
    return False


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --------- Root + tickers ---------
def test_root(session):
    r = session.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("app") == "confluence-decoder"
    assert "version" in d and "ts" in d


def test_tickers_list(session):
    r = session.get(f"{API}/tickers", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "trinity" in d and "default" in d and "popular" in d
    assert d["trinity"] == ["^SPX", "SPY", "QQQ"]
    assert "SPY" in d["default"] and "QQQ" in d["default"]
    assert isinstance(d["popular"], list) and len(d["popular"]) > 10


# --------- Heatmap SPY ---------
def test_heatmap_spy(session):
    r = session.get(f"{API}/heatmap/SPY?expiries=2", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    # No NaN/Inf
    raw = r.content.decode()
    assert "NaN" not in raw and "Infinity" not in raw
    assert d["ticker"] == "SPY"
    assert isinstance(d["spot"], (int, float)) and d["spot"] > 0
    assert isinstance(d["strikes"], list) and len(d["strikes"]) > 0
    for s in d["strikes"]:
        for k in ("strike", "gex", "call_gex", "put_gex", "lifecycle", "tap_prob", "taps"):
            assert k in s, f"missing {k}"
    nodes = d["nodes"]
    for k in ("king", "floors", "ceilings", "gatekeepers", "air_pockets", "regime"):
        assert k in nodes
    assert nodes["king"] and "strike" in nodes["king"]
    assert isinstance(d["patterns"], list)
    assert isinstance(d["velocity"], dict)
    assert "velocity_score" in d["velocity"]
    assert "tap_counts" in d
    assert "asof" in d
    assert not _has_nan_or_inf(d)


def test_heatmap_qqq(session):
    r = session.get(f"{API}/heatmap/QQQ?expiries=2", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "QQQ"
    assert d["spot"] > 0
    assert len(d["strikes"]) > 0
    assert not _has_nan_or_inf(d)


def test_heatmap_spx(session):
    # URL-encoded ^SPX
    r = session.get(f"{API}/heatmap/%5ESPX?expiries=2", timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "^SPX"
    assert d["spot"] > 0
    assert len(d["strikes"]) > 0


# --------- Trinity ---------
def test_trinity(session):
    r = session.get(f"{API}/trinity", timeout=120)
    assert r.status_code == 200
    d = r.json()
    assert "tickers" in d and "alignment" in d
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"]
    align = d["alignment"]
    assert align["verdict"] in ("full_alignment", "partial_alignment", "divergence")
    assert "confluence" in align and "regime" in align


# --------- Movers ---------
def test_movers(session):
    r = session.get(f"{API}/movers?limit=5", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "results" in d
    assert isinstance(d["results"], list)
    if d["results"]:
        row = d["results"][0]
        for k in ("ticker", "pct", "close"):
            assert k in row


# --------- History ---------
def test_history_spy(session):
    # ensure snapshot exists first
    session.get(f"{API}/heatmap/SPY?expiries=2", timeout=60)
    r = session.get(f"{API}/history/SPY", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert isinstance(d["snapshots"], list)


# --------- Glossary ---------
def test_glossary(session):
    r = session.get(f"{API}/patterns/glossary", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ("Rug", "Reverse Rug", "Pika Cloud", "Beach Ball", "Whipsaw", "Rainbow Road",
              "King Node", "Floor", "Ceiling", "Gatekeeper", "Air Pocket"):
        assert k in d, f"missing glossary entry {k}"
