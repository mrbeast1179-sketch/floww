"""
backend/tests/routes/test_insider_routes.py

RFC-7231 polish — GET safe / POST writes (steal-list #20 deferred #1)
======================================================================

Verifies the contract promised in ``backend/routes/steal_three.py``:

  - ``GET  /api/insider/{top,latest,{ticker}}``  MUST be safe per RFC-7231 §4.2.1
    → must NOT call ``services.insider_scraper.accumulate_today``. The legacy
    ``?accumulate=true`` query param is accepted for backward compat but is
    documented as deprecated and ignored.

  - ``POST /api/insider/{top,latest,{ticker}}/accumulate``  is the write
    side per RFC-7231 §4.2.2 and DOES call ``accumulate_today``.

Strategy: FastAPI ``TestClient`` mounted on a minimal app that includes
the steal-three router + ``unittest.mock.patch`` to spy on
``services.insider_scraper.accumulate_today`` (the canonical import
location — handler imports it inside its try-block so patching the
service module catches it).

Tests are deterministic-no-network: we canary-patch both
``accumulate_today`` AND the fetch helpers (``fetch_top_insider``,
``fetch_latest_insider``, ``fetch_ticker_insider``) so no Finviz call
leaks. Background ``yfinance`` import the steal-three module triggers is
harmless in the test environment (no ticker access happens).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# Built once at module load (fixture-ish) — the steal-three module
# imports yfinance at top level; that import is slow but harmless.
from routes.steal_three import router as steal_three_router     # noqa: E402


# ----------------------------------------------------------------------
# Test app + canned response fixtures
# ----------------------------------------------------------------------

app = FastAPI(title="insider-route-tests")
app.include_router(steal_three_router)
client = TestClient(app)


_CANNED_ROWS = [
    {
        "ticker": "SPY",
        "insider_name": "Jane Doe",
        "title": "CEO",
        "transaction_date": "2026-07-15",
        "transaction_type": "buy",
        "cost": 580.0,
        "shares": 1000,
        "value": 580_000.0,
        "shares_total": 5000,
    },
    {
        "ticker": "SPY",
        "insider_name": "John Smith",
        "title": "Director",
        "transaction_date": "2026-07-14",
        "transaction_type": "buy",
        "cost": 580.0,
        "shares": 500,
        "value": 290_000.0,
        "shares_total": 1500,
    },
    {
        "ticker": "SPY",
        "insider_name": "CFO Buyer",
        "title": "CFO",
        "transaction_date": "2026-07-13",
        "transaction_type": "sell",
        "cost": 580.0,
        "shares": 800,
        "value": -464_000.0,
        "shares_total": 12_000,
    },
]


# ----------------------------------------------------------------------
# GET handlers must be RFC-7231 safe (no accumulate_today call).
# ----------------------------------------------------------------------


def test_get_top_does_not_call_accumulate_today_with_or_without_accumulate_param():
    """GET /api/insider/top is safe — accumulate_today MUST NOT be
    invoked, even when callers pass the legacy ?accumulate=true param.
    """
    with patch("services.insider_scraper.accumulate_today") as mock_acc, \
         patch("services.insider_scraper.fetch_top_insider",
               return_value=_CANNED_ROWS) as mock_fetch:
        # First: plain GET (no param)
        r1 = client.get("/api/insider/top")
        assert r1.status_code == 200, r1.text
        assert mock_acc.call_count == 0
        assert mock_fetch.call_count == 1
        # Second: legacy ?accumulate=true — STILL must not accumulate.
        mock_acc.reset_mock()
        r2 = client.get("/api/insider/top?accumulate=true")
        assert r2.status_code == 200, r2.text
        assert mock_acc.call_count == 0, (
            "GET handler leaked a write — accumulate_today was called "
            f"{mock_acc.call_count} times despite the HTTP verb being GET"
        )
        # The deprecation warning is surfaced in the response payload.
        body = r2.json()
        assert any("deprecated" in w.lower()
                   for w in body.get("warnings", [])), (
            "missing deprecation warning in GET response"
        )


def test_get_latest_does_not_call_accumulate_today():
    """GET /api/insider/latest is safe."""
    with patch("services.insider_scraper.accumulate_today") as mock_acc, \
         patch("services.insider_scraper.fetch_latest_insider",
               return_value=_CANNED_ROWS):
        r = client.get("/api/insider/latest?accumulate=true")
        assert r.status_code == 200, r.text
        assert mock_acc.call_count == 0


def test_get_ticker_does_not_call_accumulate_today():
    """GET /api/insider/{ticker} is safe."""
    with patch("services.insider_scraper.accumulate_today") as mock_acc, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS):
        r = client.get("/api/insider/AAPL?accumulate=true")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ticker"] == "AAPL"
        assert mock_acc.call_count == 0


# ----------------------------------------------------------------------
# POST /accumulate handlers MUST call accumulate_today exactly once.
# ----------------------------------------------------------------------


def test_post_top_accumulate_writes_to_duckdb_via_accumulate_today():
    """POST /api/insider/top/accumulate is the RFC-7231 write side."""
    with patch("services.insider_scraper.accumulate_today",
               return_value=len(_CANNED_ROWS)) as mock_acc, \
         patch("services.insider_scraper.fetch_top_insider",
               return_value=_CANNED_ROWS) as mock_fetch, \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/top/accumulate?min_value=100000&tc=7&limit=20")
        assert r.status_code == 200, r.text
        body = r.json()
        assert mock_fetch.call_count == 1
        assert mock_acc.call_count == 1
        assert body["written_n_rows"] == len(_CANNED_ROWS)
        assert body["source"] == "steal-three-router"


def test_post_latest_accumulate_writes_to_duckdb_via_accumulate_today():
    """POST /api/insider/latest/accumulate is the RFC-7231 write side."""
    with patch("services.insider_scraper.accumulate_today",
               return_value=len(_CANNED_ROWS)) as mock_acc, \
         patch("services.insider_scraper.fetch_latest_insider",
               return_value=_CANNED_ROWS), \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/latest/accumulate?limit=50")
        assert r.status_code == 200, r.text
        body = r.json()
        assert mock_acc.call_count == 1
        assert body["written_n_rows"] == len(_CANNED_ROWS)


def test_post_ticker_accumulate_writes_to_duckdb_via_accumulate_today():
    """POST /api/insider/{ticker}/accumulate is the RFC-7231 write side."""
    with patch("services.insider_scraper.accumulate_today",
               return_value=len(_CANNED_ROWS)) as mock_acc, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS), \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/AAPL/accumulate?limit=50")
        assert r.status_code == 200, r.text
        body = r.json()
        assert mock_acc.call_count == 1
        assert body["written_n_rows"] == len(_CANNED_ROWS)
        assert body["ticker"] == "AAPL"


# ----------------------------------------------------------------------
# Route ordering / pattern correctness — static paths ALWAYS win over
# the {ticker} catch-all (both GET and POST).
# ----------------------------------------------------------------------


def test_get_static_top_resolves_before_catch_all():
    """GET /api/insider/top MUST hit the static top handler — NOT the
    {ticker} catch-all. Verify by checking the response: static returns
    a rows/summary payload keyed on ticker=None, catch-all would have
    ticker='TOP'."""
    with patch("services.insider_scraper.accumulate_today") as mock_acc, \
         patch("services.insider_scraper.fetch_top_insider",
               return_value=_CANNED_ROWS) as mock_top, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS) as mock_ticker:
        r = client.get("/api/insider/top")
        body = r.json()
        assert r.status_code == 200
        assert mock_top.call_count == 1, "static top handler did not fire"
        assert mock_ticker.call_count == 0, (
            "fetch_ticker_insider was called — static top handler leaked "
            "into the catch-all"
        )
        assert mock_acc.call_count == 0
        # Static handler returns rows + summary WITHOUT a 'ticker' top key.
        assert "ticker" not in body or body.get("ticker") is None


def test_post_static_top_accumulate_resolves_before_catch_all():
    """POST /api/insider/top/accumulate MUST hit the static top
    accumulate handler — NOT the {ticker}/accumulate catch-all."""
    with patch("services.insider_scraper.accumulate_today",
               return_value=len(_CANNED_ROWS)) as mock_acc, \
         patch("services.insider_scraper.fetch_top_insider",
               return_value=_CANNED_ROWS) as mock_top, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS) as mock_ticker, \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/top/accumulate?min_value=100000&tc=7&limit=20")
        body = r.json()
        assert r.status_code == 200
        assert mock_top.call_count == 1
        assert mock_ticker.call_count == 0, (
            "fetch_ticker_insider was called — static POST top handler "
            "leaked into the catch-all"
        )
        assert mock_acc.call_count == 1
        assert "ticker" not in body or body.get("ticker") is None


def test_post_static_latest_accumulate_resolves_before_catch_all():
    """POST /api/insider/latest/accumulate MUST hit the static latest
    handler — NOT the {ticker}/accumulate catch-all."""
    with patch("services.insider_scraper.accumulate_today",
               return_value=len(_CANNED_ROWS)) as mock_acc, \
         patch("services.insider_scraper.fetch_latest_insider",
               return_value=_CANNED_ROWS) as mock_latest, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS) as mock_ticker, \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/latest/accumulate?limit=50")
        body = r.json()
        assert r.status_code == 200
        assert mock_latest.call_count == 1
        assert mock_ticker.call_count == 0
        assert mock_acc.call_count == 1
        assert "ticker" not in body or body.get("ticker") is None


# ----------------------------------------------------------------------
# Defensive degrade — empty rows + failed accumulate (the documented
# contract — never 500s on a write hiccup).
# ----------------------------------------------------------------------


def test_post_ticker_accumulate_emits_warning_when_accumulate_fails():
    """If accumulate_today raises on a write error, the POST handler
    must surface that via the response payload's warnings key (and
    indicate zero rows were written via written_n_rows == 0).
    """
    with patch("services.insider_scraper.accumulate_today",
               side_effect=RuntimeError("duckdb disk full")) as mock_acc, \
         patch("services.insider_scraper.fetch_ticker_insider",
               return_value=_CANNED_ROWS), \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/AAPL/accumulate?limit=50")
        assert r.status_code == 200, r.text
        body = r.json()
        assert mock_acc.call_count == 1
        assert body["written_n_rows"] == 0
        warnings = body.get("warnings", [])
        assert any("accumulate failed" in w or "duckdb" in w.lower()
                   for w in warnings), (
            f"missing 'accumulate failed' warning in payload: {warnings}"
        )


def test_post_top_accumulate_returns_written_n_rows_zero_on_empty_fetch():
    """If Finviz returns no rows, the POST handler should still return
    200 with written_n_rows == 0 and an empty-rows warning.
    """
    with patch("services.insider_scraper.accumulate_today") as mock_acc, \
         patch("services.insider_scraper.fetch_top_insider",
               return_value=[]), \
         patch("services.insider_scraper.init_insider_daily_table"):
        r = client.post("/api/insider/top/accumulate?min_value=100000&tc=7&limit=20")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["written_n_rows"] == 0
        assert mock_acc.call_count == 0  # no rows means no write attempted
        warnings = body.get("warnings", [])
        assert any("empty" in w.lower() or "finviz" in w.lower()
                   for w in warnings)
