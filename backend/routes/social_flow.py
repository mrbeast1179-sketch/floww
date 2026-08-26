"""
API routes for Social Sentiment & Options Flow data.
Mount these in server.py.
"""

import json
import logging
import os
from datetime import UTC, datetime

from fastapi import APIRouter

# Steal-list deferred (a) ship 2026-07-15: surface the library-availability flags
# so the cached route can report a graceful `aggregate_sentiment_available`
# verdict when at least one of VADER / TextBlob is installed. The single-library
# fallback policy lives in services.sentiment._label_from_agreement().
from services.sentiment import TEXTBLOB_AVAILABLE, VADER_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/social", tags=["social"])

# Data directory for cached reports
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "social-reports")
os.makedirs(DATA_DIR, exist_ok=True)


def _aggregate_sentiment_available() -> bool:
    """True iff at least one of VADER / TextBlob is importable.

    One-line helper so the route handler stays clean; both flags are
    bound at routes.social_flow module-load time so this cannot raise.
    """
    return bool(VADER_AVAILABLE or TEXTBLOB_AVAILABLE)


@router.get("/sentiment/{ticker}")
async def get_sentiment(ticker: str):
    """Get social sentiment for a ticker.

    Steal-list deferred (a) ship 2026-07-15: now reports
    ``aggregate_sentiment_available`` (true iff at least one VADER / TextBlob
    library is importable) and ``stale_as_of`` (the on-disk mtime if the
    cache file lacks a ``generated_at``). When the cache file exists we
    pass the cached ``sentiment`` dict through verbatim — we CANNOT
    re-score without the raw tweet corpus that produced it, so the cache
    shape is the canonical "as-of" snapshot.
    """
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_sentiment.json")
    agg_available = _aggregate_sentiment_available()

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        # Prefer the report's own timestamp; fall back to file mtime so the
        # field is always populated when reports come from older versions
        # of save_report() that didn't include generated_at.
        stale_as_of = (
            data.pop("generated_at", None)
            or datetime.fromtimestamp(os.path.getmtime(report_path)).isoformat()
        )
        # Spread data FIRST, then overwrite with our explicit metadata keys
        # so a future cached file that happened to include either of these
        # keys can never override the route's authoritative answer.
        return {
            **data,
            "ticker": ticker.upper(),
            "cached": True,
            "aggregate_sentiment_available": agg_available,
            "stale_as_of": stale_as_of,
        }

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "aggregate_sentiment_available": agg_available,
        "message": "No sentiment data available yet. Run the social flow pipeline first.",
        "sentiment": None,
    }


@router.get("/flow/{ticker}")
async def get_flow(ticker: str, min_premium: float = 50000):
    """Get options flow signals for a ticker."""
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_flow.json")

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        return {"ticker": ticker.upper(), "cached": True, **data}

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "message": "No flow data available yet. Run the social flow pipeline first.",
        "signals": [],
    }


@router.get("/report/{ticker}")
async def get_full_report(ticker: str):
    """Get combined social + flow + GEX report for a ticker."""
    report_path = os.path.join(DATA_DIR, f"{ticker.upper()}_report.json")

    if os.path.exists(report_path):
        with open(report_path) as f:
            data = json.load(f)
        return {"ticker": ticker.upper(), "cached": True, **data}

    return {
        "ticker": ticker.upper(),
        "cached": False,
        "message": "No report available yet. Run the social flow pipeline first.",
        "report": None,
    }


@router.get("/status")
async def get_pipeline_status():
    """Get status of the social flow pipeline."""
    from social_flow_pipeline import TwitterCollector

    collector = TwitterCollector()
    xurl_auth = collector.is_authenticated()

    # Check for cached reports
    reports = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith("_report.json"):
                ticker = f.replace("_report.json", "")
                reports.append(ticker)

    return {
        "xurl_authenticated": xurl_auth,
        "cached_reports": reports,
        "data_dir": DATA_DIR,
        "timestamp": datetime.now(UTC).isoformat(),
    }
