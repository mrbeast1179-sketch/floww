"""
backend/tests/services/test_insider_route.py

TestClient route-layer coverage for the steal-list #20 insider-trading endpoint
ship. Mirrors the pattern from ``tests/services/test_sentiment_route.py``.

Why this file exists (reviewer blocker #1 from code-reviewer-minimax-m3, 2026-07-15):
    The 18-case ``tests/services/test_insider_scraper.py`` covers the service
    layer (pure-logic + parsers + DuckDB I/O + header-based table lookup), but
    NONE of the pytest cases exercise the FastAPI router. If ``/api/insider/top``,
    ``/api/insider/latest``, or ``/api/insider/{ticker}`` have a wiring bug
    (wrong param binding, wrong response keys, missing handler call to its
    ``fetch_*`` counterpart), nothing in CI catches it pre-deploy.

What this file does:
    1. Copy the routes/social_flow → /api/social/sentiment/{ticker}
       TestClient pattern from test_sentiment_route.py — load the
       actual ``routes.steal_three.router``, instantiate TestClient,
       drive requests through it.
    2. Patch the Finviz-network ``fetch_*`` functions at their SOURCE
       module via ``unittest.mock.patch("services.insider_scraper.fetch_*")``
       so the suite NEVER hits the network (Finviz IP-bans us if we do).
       **Why source-module patching?** The route handlers in
       ``routes.steal_three.py`` do lazy function-level imports
       (``from services.insider_scraper import fetch_top_insider``
       INSIDE the handler body), so monkey-patching the route module's
       namespace is a no-op — the local binding inside the handler is
       captured at call-time from the SOURCE module's namespace, not
       the destination's. Patching the source bypasses this concern.
    3. Verify the response-shape contract per endpoint:
        - /api/insider/top  → returns {rows, summary, source, warnings}
        - /api/insider/latest → returns same shape
        - /api/insider/{ticker} → returns same shape
       All three call ``compute_insider_summary`` for the ``summary`` field,
       so the mock returns canned parsed rows.

Coverage profile (4 cases, focused on the reviewer-flagged coverage gap):

  1. test_insider_top_endpoint_canned_rows_returns_summary_shape
  2. test_insider_latest_endpoint_canned_rows_returns_summary_shape
  3. test_insider_per_ticker_endpoint_canned_rows_returns_summary_shape
  4. test_insider_top_empty_rows_returns_zero_state_summary

Steal-list #20 ship 2026-07-15.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.steal_three import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ----------------------------------------------------------------------------
# Canned Finviz-parsed row fixture — mirrors services/insider_scraper
# ``_parse_insider_table`` output shape so handlers consume it naturally.
# ----------------------------------------------------------------------------

def _canned_row(
    ticker: str, insider_name: str, title: str,
    transaction_type: str, value: float,
) -> dict:
    return {
        "ticker": ticker,
        "insider_name": insider_name,
        "title": title,
        "transaction_date": date(2026, 7, 15),
        "transaction_type": transaction_type,
        "cost": 200.0,
        "shares": 1000,
        "value": value,
        "shares_total": 5000,
    }


# ----------------------------------------------------------------------------
# 1. /api/insider/top — canned BUY rows, verify summary shape
# ----------------------------------------------------------------------------
def test_insider_top_endpoint_canned_rows_returns_summary_shape():
    """Patch fetch_top_insider@source → return 3 BUY rows for SPY → response
    ``rows`` is the canned list, ``summary`` dict contains the 10 baseline
    keys, ``source`` and ``warnings`` are string fields."""
    canned = [
        _canned_row("SPY", "Alice Smith", "CEO", "buy", 200_000.0),
        _canned_row("SPY", "Bob Johnson", "CFO", "buy", 75_000.0),
        _canned_row("SPY", "Carol Lee", "Director", "buy", 60_000.0),
    ]
    with patch("services.insider_scraper.fetch_top_insider", return_value=canned):
        resp = client.get("/api/insider/top?min_value=100000&tc=7&limit=20")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["source"] == "steal-three-router"
    assert isinstance(payload["rows"], list) and len(payload["rows"]) == 3
    # Pulled directly from compute_insider_summary baseline.
    summary = payload["summary"]
    assert summary["n_buys_30d"] == 3
    assert summary["n_sells_30d"] == 0
    assert summary["total_buy_value"] == 335_000.0
    assert summary["net_buy_pressure"] == 335_000.0
    assert summary["largest_buy_value"] == 200_000.0
    assert summary["ceo_bought_recent"] is True   # Alice is CEO
    assert isinstance(payload["warnings"], list)


# ----------------------------------------------------------------------------
# 2. /api/insider/latest — same wiring contract
# ----------------------------------------------------------------------------
def test_insider_latest_endpoint_canned_rows_returns_summary_shape():
    """Patch fetch_latest_insider@source → mixed BUY+SELL row → summary carries
    the expected BUY/SELL totals and net-pressure sign. Market-wide (no ticker
    filter) so both TSLA + NVDA rows count toward the summary."""
    canned = [
        _canned_row("TSLA", "P Person", "President", "buy", 50_000.0),
        _canned_row("NVDA", "D Person", "VP", "sell", 30_000.0),
    ]
    with patch("services.insider_scraper.fetch_latest_insider", return_value=canned):
        resp = client.get("/api/insider/latest?limit=10")
    assert resp.status_code == 200
    payload = resp.json()

    assert len(payload["rows"]) == 2
    summary = payload["summary"]
    assert summary["n_buys_30d"] == 1   # TSLA buy
    assert summary["n_sells_30d"] == 1   # NVDA sell
    assert summary["total_buy_value"] == 50_000.0
    assert summary["total_sell_value"] == 30_000.0
    assert summary["net_buy_pressure"] == 20_000.0


# ----------------------------------------------------------------------------
# 3. /api/insider/{ticker} — single ticker contract
# ----------------------------------------------------------------------------
def test_insider_per_ticker_endpoint_canned_rows_returns_summary_shape():
    """Patch fetch_ticker_insider@source → 2 BUY rows for AAPL → summary
    carries AAPL-only counts (cross-ticker protection from compute_insider_summary's
    filter at the route layer)."""
    canned = [
        _canned_row("AAPL", "Tim Cook", "CEO", "buy", 500_000.0),
        _canned_row("AAPL", "Luca Maestri", "CFO", "buy", 100_000.0),
    ]
    with patch("services.insider_scraper.fetch_ticker_insider", return_value=canned):
        resp = client.get("/api/insider/AAPL")
    assert resp.status_code == 200
    payload = resp.json()

    assert len(payload["rows"]) == 2
    summary = payload["summary"]
    assert summary["ticker"] == "AAPL"
    assert summary["n_buys_30d"] == 2
    assert summary["total_buy_value"] == 600_000.0
    assert summary["ceo_bought_recent"] is True   # Tim Cook is CEO


# ----------------------------------------------------------------------------
# 4. /api/insider/top — empty rows returns zero-state summary
# (Finviz unreachable path; the route must NOT crash, must still respond
# with the canonical 10-key zero-state dict.)
# ----------------------------------------------------------------------------
def test_insider_top_empty_rows_returns_zero_state_summary():
    with patch("services.insider_scraper.fetch_top_insider", return_value=[]):
        resp = client.get("/api/insider/top")
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["rows"] == []
    summary = payload["summary"]
    # Zero-state contract.
    assert summary["n_buys_30d"] == 0
    assert summary["n_sells_30d"] == 0
    assert summary["total_buy_value"] == 0.0
    assert summary["total_sell_value"] == 0.0
    assert summary["net_buy_pressure"] == 0.0
    assert summary["largest_buy_value"] is None
    assert summary["ceo_bought_recent"] is False
    # The defensive-degrade path emits a warning.
    assert len(payload["warnings"]) >= 1
    assert any("Finviz empty or unreachable" in w for w in payload["warnings"])
