#!/usr/bin/env python3
"""Backfill the ``gex_history`` Mongo collection from Databento chains.

For each requested ticker, computes one ``gex_total`` value per trading day
that has both a ``databento_eod_chains`` document and an ``underlying_bars``
row, then upserts to ``gex_history`` keyed on ``(ticker, ts)``. Also writes
a manifest to ``qc/data/<ticker>_gex_history_manifest.json``.

Pure aggregation of real fields — no synthetic data, no interpolation. Days
missing either chain or bar are recorded in the manifest as
``days_with_missing_*`` and skipped.

Usage::

    python scripts/backfill_gex_history.py --tickers SPY,DIA,IWM \\
        --start 2022-01-01 --end 2024-12-31
    python scripts/backfill_gex_history.py --tickers SPY --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# Make ``backend.services`` importable when running as a top-level script.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / ".env")

from pymongo import MongoClient  # noqa: E402

from services.gex_history import build_gex_history  # type: ignore[import-not-found]  # noqa: E402

DEFAULT_TICKERS = ["SPY", "DIA", "IWM"]
COLLECTION = "gex_history"
MANIFEST_DIR = ROOT / "qc" / "data"


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def _build_manifest(
    ticker: str,
    rows: List[Dict[str, Any]],
    *,
    start: date,
    end: date,
    days_missing_chain: int,
    days_missing_bar: int,
) -> Dict[str, Any]:
    gex_vals = [r["gex_total"] for r in rows]
    if gex_vals:
        gex_min = float(min(gex_vals))
        gex_max = float(max(gex_vals))
        gex_mean = float(statistics.fmean(gex_vals))
        gex_std = float(statistics.pstdev(gex_vals)) if len(gex_vals) > 1 else 0.0
        ts_first = rows[0]["ts"]
        ts_last = rows[-1]["ts"]
    else:
        gex_min = gex_max = gex_mean = gex_std = 0.0
        ts_first = ts_last = None

    return {
        "ticker": ticker,
        "n_rows": len(rows),
        "start_requested": start.isoformat(),
        "end_requested": end.isoformat(),
        "ts_first": ts_first,
        "ts_last": ts_last,
        "gex_total_min": gex_min,
        "gex_total_max": gex_max,
        "gex_total_mean": gex_mean,
        "gex_total_std": gex_std,
        "days_with_missing_chain": days_missing_chain,
        "days_with_missing_bar": days_missing_bar,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _count_missing(db: Any, ticker: str, start: date, end: date) -> Dict[str, int]:
    """Count trading-day mismatches between chains and bars in the window."""
    start_s, end_s = start.isoformat(), end.isoformat()
    chain_days = {
        d["day"]
        for d in db["databento_eod_chains"].find(
            {"ticker": ticker, "day": {"$gte": start_s, "$lte": end_s}},
            {"day": 1, "_id": 0},
        )
        if d.get("day")
    }
    bar_days = {
        d["date"]
        for d in db["underlying_bars"].find(
            {"ticker": ticker, "date": {"$gte": start_s, "$lte": end_s}},
            {"date": 1, "_id": 0},
        )
        if d.get("date")
    }
    return {
        "days_with_missing_bar": len(chain_days - bar_days),
        "days_with_missing_chain": len(bar_days - chain_days),
    }


def _upsert_rows(db: Any, ticker: str, rows: List[Dict[str, Any]]) -> int:
    coll = db[COLLECTION]
    try:
        coll.create_index(
            [("ticker", 1), ("ts", 1)], unique=True, name="ticker_ts_unique"
        )
    except Exception as e:  # pragma: no cover — index may already exist
        print(f"  create_index warning: {e}", file=sys.stderr)
    stored = 0
    for r in rows:
        coll.update_one(
            {"ticker": ticker, "ts": r["ts"]},
            {"$set": {"ticker": ticker, **r}},
            upsert=True,
        )
        stored += 1
    return stored


def run(
    tickers: List[str], start: date, end: date, *, dry_run: bool
) -> Dict[str, Dict[str, Any]]:
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise RuntimeError(
            "MONGO_URL and DB_NAME must be set (load via backend/.env)"
        )
    client: Any = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
    db = client[db_name]

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Dict[str, Any]] = {}

    for ticker in tickers:
        print(f"\n=== {ticker} ===")
        rows = asyncio.run(build_gex_history(
            ticker, start_date=start, end_date=end, mongo_db=db
        ))
        gaps = _count_missing(db, ticker, start, end)
        manifest = _build_manifest(
            ticker,
            rows,
            start=start,
            end=end,
            days_missing_chain=gaps["days_with_missing_chain"],
            days_missing_bar=gaps["days_with_missing_bar"],
        )

        print(f"  rows: {manifest['n_rows']}")
        print(f"  date range: {manifest['ts_first']} → {manifest['ts_last']}")
        print(
            f"  gex_total: min={manifest['gex_total_min']:.2e} "
            f"max={manifest['gex_total_max']:.2e} "
            f"mean={manifest['gex_total_mean']:.2e} "
            f"std={manifest['gex_total_std']:.2e}"
        )
        print(
            f"  missing chain={manifest['days_with_missing_chain']} "
            f"missing bar={manifest['days_with_missing_bar']}"
        )

        if dry_run:
            print("  [DRY RUN] first 5 rows:")
            for r in rows[:5]:
                print(f"    {r}")
        else:
            stored = _upsert_rows(db, ticker, rows)
            manifest["stored"] = stored
            print(f"  upserted: {stored}")
            manifest_path = MANIFEST_DIR / f"{ticker}_gex_history_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"  manifest: {manifest_path}")

        results[ticker] = manifest

    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill gex_history collection from Databento chains"
    )
    parser.add_argument(
        "--tickers",
        default=",".join(DEFAULT_TICKERS),
        help="Comma-separated tickers (default: SPY,DIA,IWM)",
    )
    parser.add_argument(
        "--start", default="2022-01-01", help="Inclusive start YYYY-MM-DD"
    )
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="Inclusive end YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute + print manifest and first 5 rows; do NOT write to Mongo",
    )
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    start = _parse_date(args.start)
    end = _parse_date(args.end)
    run(tickers, start, end, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
