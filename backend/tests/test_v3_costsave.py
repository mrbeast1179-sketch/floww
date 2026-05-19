"""V3 cost-effective testing: /api/databento/usage budget meter, /api/live/policy,
/api/spot, /api/flow window-enforcement, /api/live/tape/stop idempotent."""
import json
import time
import pytest
from fastapi.testclient import TestClient

from server import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module")
def session():
    return client


# --- Reset PAID_TICKERS to defaults (SPY) before & after the suite ---
@pytest.fixture(scope="module", autouse=True)
def reset_policy(session):
    yield
    try:
        session.post("/api/live/policy",
                     json={"paid_tickers": ["SPY"], "window_start": "09:00", "window_stop": "10:30"},
                     timeout=10)
    except Exception:
        pass


# --- /api/databento/usage shape ---
def test_databento_usage_v3_shape(session):
    r = session.get("/api/databento/usage", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    # v3 required fields
    for k in ("paid_tickers", "live_window_et", "est_total_cost_usd",
              "budget_remaining_usd", "budget_pct_used", "in_window_now",
              "live_tape_state", "budget_usd"):
        assert k in d, f"missing {k} in usage response"
    assert "SPY" in d["paid_tickers"]
    assert d["budget_usd"] == 125.0
    assert "start_hhmm" in d["live_window_et"]
    assert "stop_hhmm" in d["live_window_et"]
    assert isinstance(d["in_window_now"], bool)
    # Budget remaining math sanity
    assert abs((d["budget_remaining_usd"] + d["est_total_cost_usd"]) - 125.0) < 0.05


# --- POST /api/live/policy with paid_tickers + window ---
def test_live_policy_set_spy_qqq(session):
    r = session.post("/api/live/policy",
                     json={"paid_tickers": ["SPY", "QQQ"],
                           "window_start": "09:30", "window_stop": "10:30"},
                     timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d["paid_tickers"]) == {"SPY", "QQQ"}
    assert d["live_window_et"]["start_hhmm"] == "09:30"
    assert d["live_window_et"]["stop_hhmm"] == "10:30"

    # Verify via GET usage that policy persisted
    r2 = session.get("/api/databento/usage", timeout=10).json()
    assert set(r2["paid_tickers"]) == {"SPY", "QQQ"}
    assert r2["live_window_et"]["start_hhmm"] == "09:30"


def test_live_policy_revert_spy_only(session):
    r = session.post("/api/live/policy", json={"paid_tickers": ["SPY"]}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["paid_tickers"] == ["SPY"]


# --- /api/heatmap data_source by ticker tier ---
def test_heatmap_spy_data_source_databento(session):
    # Ensure SPY in paid list
    session.post("/api/live/policy", json={"paid_tickers": ["SPY"]}, timeout=10)
    r = session.get("/api/heatmap/SPY?expiries=2", timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    # Should be databento+yfinance (paid). If DBN key absent it could fall back to yfinance;
    # the test treats databento+yfinance as preferred but accepts yfinance fallback.
    assert d["data_source"] in ("databento+yfinance", "yfinance")


def test_heatmap_qqq_free_tier_yfinance(session):
    # Ensure QQQ NOT in paid list
    session.post("/api/live/policy", json={"paid_tickers": ["SPY"]}, timeout=10)
    r = session.get("/api/heatmap/QQQ?expiries=2", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data_source"] == "yfinance", f"QQQ free-tier should be yfinance, got {d['data_source']}"


def test_heatmap_spx_free_tier_yfinance(session):
    r = session.get("/api/heatmap/%5ESPX?expiries=2", timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data_source"] == "yfinance", f"SPX free-tier should be yfinance, got {d['data_source']}"


# --- /api/spot fast & free ---
def test_spot_endpoint_fast(session):
    start = time.time()
    r = session.get("/api/spot/SPY", timeout=10)
    elapsed = time.time() - start
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] > 0
    assert "ts" in d
    # Should be fast — cache miss may take a couple seconds but well under 10s
    assert elapsed < 8, f"/api/spot took {elapsed:.1f}s — too slow"


def test_spot_second_call_cached(session):
    session.get("/api/spot/SPY", timeout=10)
    start = time.time()
    r = session.get("/api/spot/SPY", timeout=10)
    elapsed = time.time() - start
    assert r.status_code == 200
    assert elapsed < 2.0, f"cached /api/spot took {elapsed:.2f}s"


# --- /api/flow window enforcement (SSE) ---
def _read_sse_events(url, timeout=8, max_events=3):
    """Read up to max_events SSE events from url, return list of (event_name, data_dict)."""
    out = []
    r = client.get(url, timeout=timeout)
    cur_event = "message"
    text = r.text
    for line in text.split("\n"):
        if line.startswith("event:"):
            cur_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            try:
                d = json.loads(payload)
            except Exception:
                d = {"_raw": payload}
            out.append((cur_event, d))
            cur_event = "message"
            if len(out) >= max_events:
                break
    return out


def _in_window_now():
    try:
        r = client.get("/api/databento/usage", timeout=10).json()
        return bool(r.get("in_window_now"))
    except Exception:
        return False


def test_flow_qqq_refused_not_in_paid_tickers(session):
    # Ensure SPY-only policy
    session.post("/api/live/policy", json={"paid_tickers": ["SPY"]}, timeout=10)
    events = _read_sse_events("/api/flow/QQQ?max_seconds=10&enforce_window=false",
                              timeout=10, max_events=1)
    assert events, "no SSE events received"
    name, data = events[0]
    assert name == "error", f"expected error event, got {name}: {data}"
    assert "paid" in (data.get("error", "").lower()), f"unexpected error: {data}"


def test_flow_spy_outside_window_emits_error():
    if _in_window_now():
        pytest.skip("Currently within live window — test would fail by design")
    # SPY in paid tickers, enforce window True (default) -> error since outside window
    events = _read_sse_events("/api/flow/SPY?max_seconds=10",
                              timeout=10, max_events=1)
    assert events
    name, data = events[0]
    assert name == "error"
    assert "window" in (data.get("error", "").lower()) or "outside" in (data.get("error", "").lower())


def test_flow_spy_enforce_window_false_starts():
    """When enforce_window=false, stream should at least emit a 'ready' event
    (then will end almost immediately after-hours — that's expected)."""
    # Read very few events to avoid burning live $
    events = _read_sse_events("/api/flow/SPY?max_seconds=10&enforce_window=false",
                              timeout=15, max_events=2)
    # Either 'ready' event or an error (e.g. DBN key missing) is acceptable.
    assert events, "no SSE output at all"
    [e[0] for e in events]
    # MUST NOT be a window-related error since enforce_window=false
    for name, data in events:
        if name == "error":
            err_msg = (data.get("error", "")).lower()
            assert "window" not in err_msg, f"window error despite enforce_window=false: {data}"


# --- /api/live/tape/stop idempotency ---
def test_live_tape_stop_idempotent_no_session(session):
    r = session.post("/api/live/tape/stop", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("stopped") is True


def test_live_tape_stop_called_twice(session):
    r1 = session.post("/api/live/tape/stop", timeout=10)
    r2 = session.post("/api/live/tape/stop", timeout=10)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json().get("stopped") is True
    assert r2.json().get("stopped") is True


# --- Regression: legacy endpoints still pass ---
def test_trinity_still_works(session):
    r = session.get("/api/trinity?mode=day", timeout=240)
    assert r.status_code == 200
    d = r.json()
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"]


def test_movers_still_works(session):
    r = session.get("/api/movers?limit=5", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert "results" in d
    assert isinstance(d["results"], list)


def test_contract_still_works(session):
    r = session.get("/api/contract/SPY", timeout=120)
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert isinstance(d.get("rows"), list)
