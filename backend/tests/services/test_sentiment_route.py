"""
backend/tests/services/test_sentiment_route.py

Integration tests for the deferred (a) ship that wires aggregate_sentiment
flags into ``backend/routes/social_flow.py::/api/social/sentiment/{ticker}``.

Coverage profile (3 cases + 1 parametrized for the flag toggle):

  1. Cache miss → stub return with `aggregate_sentiment_available=True`
  2. Cache hit  → on-disk dict spread + `stale_as_of` from generated_at + flags
  3. Cache hit  → on-disk dict missing `generated_at` → falls back to file mtime
  4. Cache miss with both libs unavailable →
     `aggregate_sentiment_available=False` (parametrize over True/False)

The tests backend-monkeypatch ``routes.social_flow.{VADER,TEXTBLOB}_AVAILABLE``
so the library dep isn't required to run the suite — the wiring cares about the
flag the SENTIMENT FLAGS pass through, not the actual scoring.

Steal-list deferred (a) — ship 2026-07-15.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import social_flow as social_flow_mod
from routes.social_flow import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ----------------------------------------------------------------------------
# Fixtures: monkey-patch the module-level VADER/TEXTBLOB flags so the route's
# _aggregate_sentiment_available() helper sees the desired value without the
# actual libraries installed.
# ----------------------------------------------------------------------------

@pytest.fixture
def mock_sentiment_flags(monkeypatch):
    """Default: both libs available. Tests override via monkeypatch.setattr."""
    monkeypatch.setattr(social_flow_mod, "VADER_AVAILABLE", True)
    monkeypatch.setattr(social_flow_mod, "TEXTBLOB_AVAILABLE", True)
    return monkeypatch


# ----------------------------------------------------------------------------
# 1. Cache miss — stub return + flag populated
# ----------------------------------------------------------------------------
def test_sentiment_route_cache_miss_both_libs_available(mock_sentiment_flags, tmp_path, monkeypatch):
    monkeypatch.setattr(social_flow_mod, "DATA_DIR", str(tmp_path))
    resp = client.get("/api/social/sentiment/SPY")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "SPY"
    assert data["cached"] is False
    assert data["aggregate_sentiment_available"] is True
    assert data["sentiment"] is None
    assert "No sentiment data available yet" in data["message"]


# ----------------------------------------------------------------------------
# 2. Cache hit — generated_at propagates into stale_as_of verbatim
# ----------------------------------------------------------------------------
def test_sentiment_route_cache_hit_uses_generated_at(mock_sentiment_flags, tmp_path, monkeypatch):
    monkeypatch.setattr(social_flow_mod, "DATA_DIR", str(tmp_path))
    ticker = "QQQ"
    generated_at = "2026-07-15T12:00:00+00:00"
    fake_report = {
        "generated_at": generated_at,
        "sentiment": {
            "ticker": ticker,
            "avg_vader": 0.5,
            "avg_textblob": 0.4,
            "sentiment_label": "positive",
            "bullish_count": 2,
            "bearish_count": 1,
            "neutral_count": 0,
            "tweet_count": 3,
            "confidence": 1.0,
            "top_tweets": [],
        },
        "social_score": 0.45,
    }
    file_path = Path(tmp_path) / f"{ticker}_sentiment.json"
    file_path.write_text(json.dumps(fake_report))

    resp = client.get(f"/api/social/sentiment/{ticker}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == ticker
    assert data["cached"] is True
    assert data["aggregate_sentiment_available"] is True
    assert data["stale_as_of"] == generated_at
    # Underlying sentiment dict passes through unchanged.
    assert data["sentiment"]["sentiment_label"] == "positive"
    assert data["sentiment"]["avg_vader"] == 0.5
    assert data["social_score"] == 0.45


# ----------------------------------------------------------------------------
# 3. Cache hit — missing generated_at falls through to file mtime (ISO format)
# ----------------------------------------------------------------------------
def test_sentiment_route_cache_hit_missing_generated_at_uses_mtime(mock_sentiment_flags, tmp_path, monkeypatch):
    monkeypatch.setattr(social_flow_mod, "DATA_DIR", str(tmp_path))
    ticker = "TSLA"
    fake_report = {
        "sentiment": {
            "ticker": ticker,
            "sentiment_label": "neutral",
            "avg_vader": 0.0,
            "avg_textblob": 0.0,
        },
        # NO generated_at — covers older save_report() versions
    }
    file_path = Path(tmp_path) / f"{ticker}_sentiment.json"
    file_path.write_text(json.dumps(fake_report))

    resp = client.get(f"/api/social/sentiment/{ticker}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cached"] is True
    # stale_as_of is the ISO-format file mtime — we just assert it's a valid
    # ISO string parseable by datetime.fromisoformat, not the exact value
    # (mtime is environment-dependent).
    parsed = datetime.fromisoformat(data["stale_as_of"])
    assert isinstance(parsed, datetime)


# ----------------------------------------------------------------------------
# 4. Parametrize — both libs unavailable → flag false; one available → true
# ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    "vader,tb,expected_flag",
    [
        (True, True, True),     # both libs available
        (True, False, True),    # vader only — still single-library fallback
        (False, True, True),    # textblob only — still single-library fallback
        (False, False, False),  # both unavailable — degrade gracefully
    ],
)
def test_sentiment_route_aggregate_sentiment_available_flag_toggle(
    vader, tb, expected_flag, monkeypatch, tmp_path,
):
    monkeypatch.setattr(social_flow_mod, "VADER_AVAILABLE", vader)
    monkeypatch.setattr(social_flow_mod, "TEXTBLOB_AVAILABLE", tb)
    monkeypatch.setattr(social_flow_mod, "DATA_DIR", str(tmp_path))
    resp = client.get("/api/social/sentiment/SPY")
    assert resp.status_code == 200
    assert resp.json()["aggregate_sentiment_available"] is expected_flag
