#!/usr/bin/env python3
"""
scripts/backfill_yfinance.py

Backfill decades of daily OHLCV data from Yahoo Finance into MongoDB.

Free, no API key needed. Fetches daily bars for SPY, QQQ, and supplementary
tickers (IWM, DIA, VIX, VIX9D, DXY, TLT).

Writes to MongoDB collection `underlying_bars` with index (ticker, date).
Idempotent: upsert on (ticker, date).

Usage:
  python scripts/backfill_yfinance.py --tickers SPY,QQQ --start 2015-01-01
  python scripts/backfill_yfinance.py --all  # all default tickers, max history
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yfinance as yf
import pandas as pd
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

log = logging.getLogger("backfill_yfinance")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION = "underlying_bars"
QC_DIR = Path(__file__).resolve().parent.parent / "qc" / "data"

DEFAULT_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "VIX", "VIX9D", "DXY", "TLT"]
BATCH_SIZE = 500


def get_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def fetch_ticker_data(ticker: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from yfinance."""
    try:
        # yfinance end date is exclusive, so add one day
        from datetime import timedelta
        end_date = date.fromisoformat(end) + timedelta(days=1)
        df = yf.download(ticker, start=start, end=end_date.isoformat(), progress=False)
        if df is None or df.empty:
            log.warning(f"No data returned for {ticker}")
            return None
        return df
    except Exception as e:
        log.error(f"yfinance fetch failed for {ticker}: {e}")
        return None


def df_to_docs(ticker: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert yfinance DataFrame to MongoDB documents."""
    docs = []
    for idx, row in df.iterrows():
        # Handle MultiIndex columns from yfinance
        def get_val(col):
            v = row[col]
            if hasattr(v, 'item'):
                return v.item()
            return v

        # Date from index
        if isinstance(idx, datetime):
            date_str = idx.date().isoformat()
        elif isinstance(idx, str):
            date_str = idx
        else:
            date_str = str(idx)[:10]

        doc = {
            "ticker": ticker,
            "date": date_str,
            "open": _safe_float(get_val("Open")),
            "high": _safe_float(get_val("High")),
            "low": _safe_float(get_val("Low")),
            "close": _safe_float(get_val("Close")),
            "adj_close": _safe_float(get_val("Adj Close")) if "Adj Close" in row else None,
            "volume": _safe_int(get_val("Volume")),
            "source": "yfinance",
            "_ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        docs.append(doc)
    return docs


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN check
            return None
        return round(f, 6)
    except (ValueError, TypeError):
        return None


def _safe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def bulk_upsert(db_handle, collection: str, docs: List[Dict]) -> int:
    """Bulk upsert documents, returns count."""
    if not docs:
        return 0
    ops = [
        UpdateOne(
            {"ticker": d["ticker"], "date": d["date"]},
            {"$set": d},
            upsert=True,
        )
        for d in docs
    ]
    result = db_handle[collection].bulk_write(ops, ordered=False)
    return result.upserted_count + result.modified_count


def write_manifest(source_key: str, ticker: str, row_count: int, start: str, end: str) -> None:
    QC_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_key": source_key,
        "ticker": ticker,
        "collection": COLLECTION,
        "start": start,
        "end": end,
        "row_count": row_count,
        "source": "yfinance",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    path = QC_DIR / f"yfinance_{ticker}_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def run_backfill(tickers: List[str], start: str, end: str) -> None:
    db_handle = get_db()

    total_stored = 0
    total_skipped = 0

    for ticker in tickers:
        log.info(f"Fetching {ticker} from {start} to {end}...")
        print(f"Fetching {ticker}...", end=" ", flush=True)

        df = fetch_ticker_data(ticker, start, end)
        if df is None or df.empty:
            print("NO DATA")
            continue

        docs = df_to_docs(ticker, df)
        count = len(docs)

        # Check how many already exist
        existing = 0
        for d in docs:
            if db_handle[COLLECTION].count_documents({"ticker": ticker, "date": d["date"]}, limit=1) > 0:
                existing += 1

        # Bulk upsert all (idempotent)
        stored = bulk_upsert(db_handle, COLLECTION, docs)
        total_stored += stored
        total_skipped += (count - stored)

        write_manifest(f"yfinance_{ticker}", ticker, count, start, end)
        print(f"OK ({count} bars, {stored} upserted, {count - stored} already present)")

    print(f"\n=== Summary ===")
    print(f"Total upserted: {total_stored}")
    print(f"Total already present: {total_skipped}")
    print(f"Collection total: {db_handle[COLLECTION].count_documents({})}")


def main():
    parser = argparse.ArgumentParser(description="Backfill yfinance OHLCV into MongoDB")
    parser.add_argument("--tickers", default=",".join(DEFAULT_TICKERS), help="Comma-separated tickers")
    parser.add_argument("--start", default="2015-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=date.today().isoformat(), help="End date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true", help="All default tickers, max history")
    args = parser.parse_args()

    if args.all:
        tickers = DEFAULT_TICKERS
        start = "2015-01-01"
        end = date.today().isoformat()
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        start = args.start
        end = args.end

    run_backfill(tickers, start, end)


if __name__ == "__main__":
    main()
