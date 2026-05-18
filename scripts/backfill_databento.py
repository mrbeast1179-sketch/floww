#!/usr/bin/env python3
"""
scripts/backfill_databento.py

Backfill historical EOD options chains from Databento into MongoDB.

Uses the same approach as databento_provider.py:
- Tight pre-market window (10:00-13:30 UTC) where EOD OI is published
- Filters stat_type=9 (OI), groups by symbol, takes latest
- Parses OSI symbols into strike/expiry/type/OI

Cost: ~$0.43/ticker/day for SPY (~$109/yr), ~$0.36/ticker/day for QQQ
Budget: controlled by --budget-usd (default $100)

Usage:
  python scripts/backfill_databento.py --tickers SPY --start 2024-01-01 --end 2024-06-30 --budget-usd 50
  python scripts/backfill_databento.py --tickers SPY,QQQ --start 2024-06-01 --end 2024-08-31
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import databento as db
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

log = logging.getLogger("backfill_databento")

DBN_KEY = os.environ.get("DATABENTO_API_KEY", "")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
BUDGET_USD = float(os.environ.get("DATABENTO_BUDGET_USD", "100"))

COLLECTION_EOD_CHAINS = "databento_eod_chains"

PARENT_MAP = {
    "SPY": "SPY.OPT", "QQQ": "QQQ.OPT", "IWM": "IWM.OPT",
    "DIA": "DIA.OPT", "SPX": "SPXW.OPT",
}

OSI_RE = re.compile(r'^([A-Z]+)\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})$')


def parse_osi(raw: str) -> Optional[Dict[str, Any]]:
    m = OSI_RE.match(raw.strip())
    if not m:
        return None
    und, yy, mm, dd, typ, strike = m.groups()
    return {
        "underlying": und,
        "expiry": f"20{yy}-{mm}-{dd}",
        "type": "call" if typ == "C" else "put",
        "strike": int(strike) / 1000.0,
    }


def get_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def date_range(start: date, end: date) -> List[date]:
    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += timedelta(days=1)
    return dates


def already_fetched(db_handle, collection: str, ticker: str, day: date) -> bool:
    return db_handle[collection].count_documents({"ticker": ticker, "day": day.isoformat()}) > 0


def fetch_eod_chain(client: db.Historical, parent: str, day: date) -> Optional[Dict[str, Any]]:
    """Fetch and aggregate EOD options chain for a single day."""
    start = f"{day.isoformat()}T10:00:00"
    end = f"{day.isoformat()}T13:30:00"
    try:
        data = client.timeseries.get_range(
            dataset="OPRA.PILLAR",
            symbols=[parent],
            stype_in="parent",
            schema="statistics",
            start=start,
            end=end,
        )
        df = data.to_df()
    except Exception as e:
        log.warning(f"Fetch failed {parent} {day}: {e}")
        return None

    if df is None or df.empty:
        return None

    # Filter for OI (stat_type=9)
    df = df[df["stat_type"] == 9] if "stat_type" in df.columns else df
    if df.empty:
        return None

    # Latest per symbol
    df = df.sort_values("ts_event").groupby("symbol").last().reset_index()

    # Parse OSI symbols
    contracts = {}
    total_oi = 0
    for sym, qty in zip(df["symbol"], df.get("quantity", df.get("oi", [0]*len(df)))):
        p = parse_osi(sym)
        if not p:
            continue
        oi = int(qty) if qty == qty and qty is not None else 0  # NaN check
        if oi <= 0:
            continue
        p["oi"] = oi
        contracts[sym] = p
        total_oi += oi

    if not contracts:
        return None

    return {
        "contracts": contracts,
        "n_contracts": len(contracts),
        "total_oi": total_oi,
        "call_oi": sum(c["oi"] for c in contracts.values() if c["type"] == "call"),
        "put_oi": sum(c["oi"] for c in contracts.values() if c["type"] == "put"),
    }


def store_eod_chain(db_handle, ticker: str, day: date, data: Dict[str, Any]) -> None:
    """Store aggregated chain data in MongoDB."""
    doc = {
        "ticker": ticker,
        "day": day.isoformat(),
        "source": "databento",
        "schema": "opra-pillar.statistics",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "n_contracts": data["n_contracts"],
        "total_oi": data["total_oi"],
        "call_oi": data["call_oi"],
        "put_oi": data["put_oi"],
        "contracts": data["contracts"],
    }
    db_handle[COLLECTION_EOD_CHAINS].update_one(
        {"ticker": ticker, "day": day.isoformat()},
        {"$set": doc},
        upsert=True,
    )


def write_manifest(db_handle, ticker: str, start: date, end: date, total_days: int, cost: float) -> None:
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


def estimate_cost(ticker: str, start: date, end: date) -> float:
    """Use Databento cost API for accurate estimates."""
    if not DBN_KEY:
        return 0.0
    try:
        client = db.Historical(DBN_KEY)
        parent = PARENT_MAP.get(ticker, f"{ticker}.OPT")
        return client.metadata.get_cost(
            dataset="OPRA.PILLAR", schema="statistics",
            symbols=[parent], start=start.isoformat(), end=end.isoformat(),
            stype_in="parent",
        )
    except Exception as e:
        log.warning(f"Cost API failed: {e}")
        trading_days = int((end - start).days * 252 / 365)
        return trading_days * 0.43


def run_dry_run(tickers: List[str], start: date, end: date) -> None:
    print(f"=== Databento Backfill — DRY RUN ===")
    total = 0.0
    for ticker in tickers:
        cost = estimate_cost(ticker, start, end)
        total += cost
        print(f"  {ticker}: ${cost:.2f}")
    print(f"\nTotal: ${total:.2f} (budget: ${BUDGET_USD:.2f})")
    if total > BUDGET_USD:
        print(f"  ⚠️  OVER BUDGET by ${total - BUDGET_USD:.2f}")
    else:
        print(f"  ✅ Within budget (${BUDGET_USD - total:.2f} remaining)")


def run_backfill(tickers: List[str], start: date, end: date, budget_usd: float) -> None:
    if not DBN_KEY:
        print("ERROR: DATABENTO_API_KEY not set")
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
            if day.weekday() >= 5:
                continue
            if already_fetched(db_handle, COLLECTION_EOD_CHAINS, ticker, day):
                total_skipped += 1
                continue
            if total_cost >= budget_usd:
                print(f"  Budget exhausted at {day}. Stopping.")
                break

            print(f"  {day}...", end=" ", flush=True)
            try:
                data = fetch_eod_chain(client, parent, day)
                if data is not None:
                    store_eod_chain(db_handle, ticker, day, data)
                    total_stored += 1
                    total_cost += 0.43  # estimated per-day cost
                    print(f"OK ({data['n_contracts']} contracts, {data['total_oi']:,} OI)")
                else:
                    total_failed += 1
                    print("NO DATA")
            except Exception as e:
                total_failed += 1
                print(f"ERROR: {e}")

        write_manifest(db_handle, ticker, start, end, total_stored, total_cost)

    print(f"\n=== Summary ===")
    print(f"Stored: {total_stored} days | Skipped: {total_skipped} | Failed: {total_failed}")
    print(f"Estimated cost: ${total_cost:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Backfill Databento EOD options chains")
    parser.add_argument("--tickers", default="SPY", help="Comma-separated tickers")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Cost estimate only")
    parser.add_argument("--budget-usd", type=float, default=BUDGET_USD, help="Max spend in USD")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",")]
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    if args.dry_run:
        run_dry_run(tickers, start, end)
    else:
        run_backfill(tickers, start, end, args.budget_usd)


if __name__ == "__main__":
    main()
