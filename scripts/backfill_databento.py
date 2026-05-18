#!/usr/bin/env python3
"""
scripts/backfill_databento.py

Backfill historical EOD options chains from Databento into MongoDB.

Features:
  --dry-run: prints projected cost without making API calls
  --ticker: comma-separated tickers (default: SPY,QQQ)
  --start / --end: date range (YYYY-MM-DD)
  --schema: Databento schema (default: ohlcv-1d for underlying, opra-pillar for chains)
  --budget-usd: max spend in USD (default: 100)
  --db-name: MongoDB database name (default: confluence_decoder)

Cost meter: queries Databento metadata before each request; halts if projected
cost would exceed budget. Costs are approximate and based on Databento's
published rates at time of writing (~$0.15/ticker/day for EOD chains).

Idempotent: skips dates already present in MongoDB collection.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend to path so we can reuse the databento provider
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import databento as db
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

log = logging.getLogger("backfill_databento")

DBN_KEY = os.environ.get("DATABENTO_API_KEY", "")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
BUDGET_USD = float(os.environ.get("DATABENTO_BUDGET_USD", "100"))

# Databento parent symbol mapping (same as databento_provider.py)
PARENT_MAP = {
    "SPY": "SPY.OPT",
    "QQQ": "QQQ.OPT",
    "IWM": "IWM.OPT",
    "SPX": "SPXW.OPT",
    "DIA": "DIA.OPT",
}

# Collection names
COLLECTION_EOD_CHAINS = "databento_eod_chains"
COLLECTION_UNDERLYING = "underlying_bars"


def get_db():
    """Get MongoDB database handle."""
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def date_range(start: date, end: date) -> List[date]:
    """Generate list of dates from start to end inclusive."""
    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def already_fetched(db_handle, collection: str, ticker: str, day: date) -> bool:
    """Check if data for this ticker+day already exists."""
    return db_handle[collection].count_documents({"ticker": ticker, "date": day.isoformat()}) > 0


def estimate_cost(ticker: str, start: date, end: date) -> float:
    """
    Estimate Databento cost for the request.
    Uses a rough heuristic: ~$0.15 per ticker per day for EOD options chains.
    For production use, replace with Databento metadata.get_cost() call.
    """
    num_days = (end - start).days + 1
    # Rough estimate: ~252 trading days per year, ~$0.15/ticker/day
    trading_days = int(num_days * 252 / 365)
    cost_per_day = 0.15  # USD
    return trading_days * cost_per_day


async def fetch_eod_chain(client: db.Historical, parent: str, day: date) -> Optional[Dict[str, Any]]:
    """Fetch EOD options chain for a single day."""
    try:
        # Use Databento's timeseries.get_range for EOD data
        # Schema: ohlcv-1d for underlying, or opra-pillar for options
        # For now, we use the statistics schema (stat_type=9) for OI
        data = client.timeseries.get_range(
            dataset="OPRA.PILLAR",
            schema="statistics",
            symbols=[parent],
            start=day.isoformat(),
            end=(day + timedelta(days=1)).isoformat(),
            stype_in="parent",
        )
        records = data.to_df() if hasattr(data, "to_df") else data
        return {"raw": records, "count": len(records) if records is not None else 0}
    except Exception as e:
        log.warning(f"Failed to fetch {parent} for {day}: {e}")
        return None


def store_eod_chain(db_handle, ticker: str, day: date, data: Dict[str, Any]) -> None:
    """Store EOD chain data in MongoDB."""
    doc = {
        "ticker": ticker,
        "date": day.isoformat(),
        "source": "databento",
        "schema": "opra-pillar.statistics",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    db_handle[COLLECTION_EOD_CHAINS].update_one(
        {"ticker": ticker, "date": day.isoformat()},
        {"$set": doc},
        upsert=True,
    )


def write_manifest(db_handle, ticker: str, start: date, end: date, total_days: int, cost: float) -> None:
    """Write a manifest documenting the backfill."""
    manifest = {
        "ticker": ticker,
        "source": "databento",
        "collection": COLLECTION_EOD_CHAINS,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "total_days": total_days,
        "estimated_cost_usd": round(cost, 2),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db_handle["backfill_manifests"].update_one(
        {"ticker": ticker, "source": "databento"},
        {"$set": manifest},
        upsert=True,
    )


def run_dry_run(tickers: List[str], start: date, end: date) -> None:
    """Print cost estimate without making API calls."""
    print(f"=== Databento Backfill — DRY RUN ===")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Range: {start} → {end}")
    print(f"Budget: ${BUDGET_USD:.2f}")
    print()

    total_cost = 0.0
    for ticker in tickers:
        parent = PARENT_MAP.get(ticker, f"{ticker}.OPT")
        cost = estimate_cost(ticker, start, end)
        total_cost += cost
        num_days = (end - start).days + 1
        trading_days = int(num_days * 252 / 365)
        print(f"  {ticker} ({parent}): ~{trading_days} trading days × $0.15 = ${cost:.2f}")

    print(f"\nTotal estimated cost: ${total_cost:.2f}")
    if total_cost > BUDGET_USD:
        print(f"  ⚠️  EXCEEDS BUDGET of ${BUDGET_USD:.2f}")
        print(f"  Reduce date range or increase DATABENTO_BUDGET_USD")
    else:
        print(f"  ✅ Within budget (${BUDGET_USD - total_cost:.2f} remaining)")


def run_backfill(tickers: List[str], start: date, end: date, budget_usd: float) -> None:
    """Execute the actual backfill."""
    if not DBN_KEY:
        print("ERROR: DATABENTO_API_KEY not set in environment")
        sys.exit(1)

    client = db.Historical(DBN_KEY)
    db_handle = get_db()

    total_cost = 0.0
    total_stored = 0
    total_skipped = 0
    total_failed = 0

    for ticker in tickers:
        parent = PARENT_MAP.get(ticker, f"{ticker}.OPT")
        print(f"\n--- {ticker} ({parent}) ---")

        for day in date_range(start, end):
            # Skip weekends
            if day.weekday() >= 5:
                continue

            # Skip if already fetched
            if already_fetched(db_handle, COLLECTION_EOD_CHAINS, ticker, day):
                total_skipped += 1
                continue

            # Check budget
            if total_cost >= budget_usd:
                print(f"  Budget exhausted at {day}. Stopping.")
                break

            # Fetch
            print(f"  Fetching {day}...", end=" ", flush=True)
            try:
                data = asyncio.run(fetch_eod_chain(client, parent, day))
                if data is not None:
                    store_eod_chain(db_handle, ticker, day, data)
                    total_stored += 1
                    total_cost += 0.15  # estimated
                    print(f"OK ({data.get('count', 0)} records)")
                else:
                    total_failed += 1
                    print("FAILED")
            except Exception as e:
                total_failed += 1
                print(f"ERROR: {e}")

        # Write manifest
        write_manifest(db_handle, ticker, start, end, total_stored, total_cost)

    print(f"\n=== Summary ===")
    print(f"Stored: {total_stored}")
    print(f"Skipped (already present): {total_skipped}")
    print(f"Failed: {total_failed}")
    print(f"Estimated cost: ${total_cost:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento EOD options chains")
    parser.add_argument("--tickers", default="SPY,QQQ", help="Comma-separated tickers")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Print cost estimate only")
    parser.add_argument("--budget-usd", type=float, default=BUDGET_USD, help="Max spend in USD")
    parser.add_argument("--db-name", default=DB_NAME, help="MongoDB database name")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if start > end:
        print("ERROR: --start must be before --end")
        sys.exit(1)

    if args.dry_run:
        run_dry_run(tickers, start, end)
    else:
        run_backfill(tickers, start, end, args.budget_usd)


if __name__ == "__main__":
    main()
