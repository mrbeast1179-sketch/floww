#!/usr/bin/env python3
"""
scripts/ingest_research_csvs.py

Ingest research CSV files already on disk into MongoDB.

Reads:
  1. iAmGiG_gex-llm-patterns/issue_141_enhanced_dataset.csv → gex_enhanced_snapshots
  2. iAmGiG_gex-llm-patterns/issue_145_next_day_outcomes_2024.csv → gex_llm_patterns_outcomes
  3. iAmGiG_gex-llm-patterns/gamma_positioning_timeseries_2024.csv → gex_llm_patterns_timeseries
  4. aaguiar10_gflows/spx_quotedata.csv → cboe_quotes_spx
  5. aaguiar10_gflows/ndx_quotedata.csv → cboe_quotes_ndx
  6. aaguiar10_gflows/rut_quotedata.csv → cboe_quotes_rut
  7. FlashAlpha-lab_gex-explained/sample_chain.csv → flashalpha_sample_chain

Writes per-file manifest to qc/data/<basename>_manifest.json

Idempotent: upsert on natural key (date or symbol+expiry+strike).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

log = logging.getLogger("ingest_research_csvs")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "github-repos" / "cloned"
QC_DIR = REPO_ROOT / "qc" / "data"

# File → (collection, description)
SOURCES = {
    "issue_141_enhanced_dataset": {
        "path": DATA_DIR / "iAmGiG_gex-llm-patterns" / "docs" / "papers" / "paper1" / "analysis" / "issue_141_enhanced_dataset.csv",
        "collection": "gex_enhanced_snapshots",
        "description": "Academic GEX dataset with engineered features for 2024",
        "key_fields": ["date"],
    },
    "issue_145_next_day_outcomes_2024": {
        "path": DATA_DIR / "iAmGiG_gex-llm-patterns" / "docs" / "papers" / "paper1" / "analysis" / "issue_145_next_day_outcomes_2024.csv",
        "collection": "gex_llm_patterns_outcomes",
        "description": "Labeled next-day outcomes for 2024 (directional_move, range_expansion, gap_move)",
        "key_fields": ["date"],
    },
    "gamma_positioning_timeseries_2024": {
        "path": DATA_DIR / "iAmGiG_gex-llm-patterns" / "reports" / "statistical_validation" / "gamma_positioning_timeseries_2024.csv",
        "collection": "gex_llm_patterns_timeseries",
        "description": "GEX time series 2024",
        "key_fields": ["date"],
    },
    "spx_quotedata": {
        "path": DATA_DIR / "aaguiar10_gflows" / "data" / "csv" / "spx_quotedata.csv",
        "collection": "cboe_quotes_spx",
        "description": "Real CBOE quote data, SPX",
        "key_fields": ["expiration_date", "strike", "option_type"],
    },
    "ndx_quotedata": {
        "path": DATA_DIR / "aaguiar10_gflows" / "data" / "csv" / "ndx_quotedata.csv",
        "collection": "cboe_quotes_ndx",
        "description": "Real CBOE quote data, NDX (QQQ proxy)",
        "key_fields": ["expiration_date", "strike", "option_type"],
    },
    "rut_quotedata": {
        "path": DATA_DIR / "aaguiar10_gflows" / "data" / "csv" / "rut_quotedata.csv",
        "collection": "cboe_quotes_rut",
        "description": "Real CBOE quote data, RUT (IWM proxy)",
        "key_fields": ["expiration_date", "strike", "option_type"],
    },
    "flashalpha_sample_chain": {
        "path": DATA_DIR / "FlashAlpha-lab_gex-explained" / "data" / "sample_chain.csv",
        "collection": "flashalpha_sample_chain",
        "description": "Vendor-blessed option chain fixture from FlashAlpha",
        "key_fields": ["strike", "expiry", "type"],
    },
}


def get_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_float(val: str) -> Optional[float]:
    """Parse float, returning None for empty/invalid."""
    if val is None:
        return None
    val = val.strip()
    if val == "" or val == "0" and "." not in val:
        return None
    try:
        result = float(val)
        if result == 0.0 and val.strip() != "0" and val.strip() != "0.0":
            return None
        return result
    except (ValueError, TypeError):
        return None


def safe_int(val: str) -> Optional[int]:
    if val is None:
        return None
    val = val.strip()
    if val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_str(val: str) -> Optional[str]:
    if val is None:
        return None
    val = val.strip()
    return val if val else None


def _parse_float(val: str) -> Optional[float]:
    """Parse a string to float, returning None for empty/invalid."""
    if not val or not val.strip():
        return None
    try:
        f = float(val.strip())
        return None if f == 0.0 and val.strip() not in ("0", "0.0", "-0", "-0.0") else f
    except (ValueError, TypeError):
        return None


def _parse_int(val: str) -> Optional[int]:
    """Parse a string to int, returning None for empty/invalid."""
    if not val or not val.strip():
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, TypeError):
        return None


def clean_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Clean a CSV row: convert numeric fields, handle booleans."""
    cleaned: Dict[str, Any] = {}
    for k, v in row.items():
        k = k.strip()
        if not k:
            continue
        v = v.strip() if v else ""

        # Boolean fields
        if v.lower() in ("true", "1", "yes"):
            cleaned[k] = True
        elif v.lower() in ("false", "0", "no"):
            cleaned[k] = False
        # Empty → None
        elif v == "":
            cleaned[k] = None
        # Try int
        elif v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            cleaned[k] = int(v)
        # Try float
        else:
            try:
                cleaned[k] = float(v)
            except ValueError:
                cleaned[k] = v
    return cleaned


def ingest_csv_simple(
    db_handle,
    source_key: str,
    source: Dict,
) -> int:
    """Ingest a simple CSV file (one doc per row)."""
    path = source["path"]
    collection = source["collection"]
    key_fields = source["key_fields"]

    if not path.exists():
        log.warning(f"File not found: {path}")
        return 0

    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = clean_row(row)
            doc["_source"] = source_key
            doc["_ingested_at"] = datetime.now(timezone.utc).isoformat()

            # Build upsert filter from key fields
            filt = {}
            for kf in key_fields:
                if kf in doc and doc[kf] is not None:
                    filt[kf] = doc[kf]

            if not filt:
                filt = {"_source": source_key, "_row_num": count}

            db_handle[collection].update_one(filt, {"$set": doc}, upsert=True)
            count += 1

    return count


def ingest_gflows_quotedata(
    db_handle,
    source_key: str,
    source: Dict,
    batch_size: int = 500,
) -> int:
    """
    Ingest aaguiar10_gflows quotedata CSV using bulk writes.
    Format: 3-line header, then CSV with Calls and Puts interleaved.
    """
    from pymongo import UpdateOne

    path = source["path"]
    collection = source["collection"]

    if not path.exists():
        log.warning(f"File not found: {path}")
        return 0

    count = 0
    batch: list = []
    ts = datetime.now(timezone.utc).isoformat()

    with open(path, newline="", encoding="utf-8") as f:
        for _ in range(3):
            next(f, None)

        reader = csv.DictReader(f)
        for row in reader:
            raw = {k.strip(): v.strip() if v else "" for k, v in row.items() if k and k.strip()}

            expiry = raw.get("Expiration Date", "")
            strike_val = raw.get("Strike", "")
            try:
                strike = float(strike_val) if strike_val else None
            except (ValueError, TypeError):
                strike = None

            def make_doc(otype, sym_key, suffix):
                return {
                    "source": source_key,
                    "expiration_date": expiry,
                    "strike": strike,
                    "option_type": otype,
                    "symbol": raw.get(sym_key, "") or None,
                    "last_sale": _parse_float(raw.get(f"Last Sale{suffix}", "")),
                    "net": _parse_float(raw.get(f"Net{suffix}", "")),
                    "bid": _parse_float(raw.get(f"Bid{suffix}", "")),
                    "ask": _parse_float(raw.get(f"Ask{suffix}", "")),
                    "volume": _parse_int(raw.get(f"Volume{suffix}", "")),
                    "iv": _parse_float(raw.get(f"IV{suffix}", "")),
                    "delta": _parse_float(raw.get(f"Delta{suffix}", "")),
                    "gamma": _parse_float(raw.get(f"Gamma{suffix}", "")),
                    "open_interest": _parse_int(raw.get(f"Open Interest{suffix}", "")),
                    "_ingested_at": ts,
                }

            call_doc = make_doc("call", "Calls", "")
            put_doc = make_doc("put", "Puts", ".1")

            # Upsert call
            c_filt = {"source": source_key, "expiration_date": expiry, "strike": strike, "option_type": "call"}
            batch.append(UpdateOne(c_filt, {"$set": call_doc}, upsert=True))

            # Upsert put
            p_filt = {"source": source_key, "expiration_date": expiry, "strike": strike, "option_type": "put"}
            batch.append(UpdateOne(p_filt, {"$set": put_doc}, upsert=True))

            count += 2

            if len(batch) >= batch_size:
                db_handle[collection].bulk_write(batch, ordered=False)
                batch = []

    # Flush remaining
    if batch:
        db_handle[collection].bulk_write(batch, ordered=False)

    return count


def write_manifest(source_key: str, source: Dict, row_count: int) -> None:
    """Write a manifest JSON file documenting the ingestion."""
    QC_DIR.mkdir(parents=True, exist_ok=True)
    path = source["path"]
    manifest = {
        "source_key": source_key,
        "file_path": str(path),
        "file_name": path.name,
        "collection": source["collection"],
        "description": source["description"],
        "row_count": row_count,
        "file_size_bytes": path.stat().st_size if path.exists() else 0,
        "sha256": sha256_file(path) if path.exists() else "",
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = QC_DIR / f"{source_key}_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    log.info(f"Manifest written: {manifest_path}")


def run_ingest(source_keys: List[str]) -> None:
    db_handle = get_db()

    for key in source_keys:
        if key not in SOURCES:
            print(f"ERROR: unknown source '{key}'. Available: {', '.join(SOURCES.keys())}")
            continue

        source = SOURCES[key]
        path = source["path"]
        collection = source["collection"]

        if not path.exists():
            print(f"SKIP: {key} — file not found: {path}")
            continue

        print(f"Ingesting {key} → {collection}...", end=" ", flush=True)

        # Use special handler for gflows quotedata
        if key in ("spx_quotedata", "ndx_quotedata", "rut_quotedata"):
            count = ingest_gflows_quotedata(db_handle, key, source)
        else:
            count = ingest_csv_simple(db_handle, key, source)

        write_manifest(key, source, count)
        print(f"OK ({count} docs)")

    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Ingest research CSVs into MongoDB")
    parser.add_argument("--all", action="store_true", help="Ingest all sources")
    parser.add_argument("--source", action="append", help="Specific source key to ingest")
    args = parser.parse_args()

    if args.all:
        source_keys = list(SOURCES.keys())
    elif args.source:
        source_keys = args.source
    else:
        parser.print_help()
        sys.exit(1)

    run_ingest(source_keys)


if __name__ == "__main__":
    main()
