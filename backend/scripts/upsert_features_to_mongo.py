#!/usr/bin/env python3
"""
scripts/upsert_features_to_mongo.py

Upsert cached CSV features into MongoDB ml_features collection.
Used when ml_features is missing tickers that exist in CSV cache.

Usage:
  cd backend && python -m scripts.upsert_features_to_mongo --dry-run
  cd backend && python -m scripts.upsert_features_to_mongo --upsert
"""
import argparse
import asyncio
import os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient
import pandas as pd
import numpy as np

import logging

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"

# CSV files to upsert (ticker -> csv_path)
CSV_FILES = {
    "IWM": CACHE_DIR / "IWM_v1.0.csv",
    "TLT": CACHE_DIR / "TLT_v1.0.csv",
    "QQQ": CACHE_DIR / "QQQ_v1.0.csv",
    "DIA": CACHE_DIR / "DIA_v1.0.csv",
    "SPY": CACHE_DIR / "SPY_v1.0.csv",
}

META_COLS = {'ticker', 'date', 'feature_version', '_computed_at', '_id'}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upsert", action="store_true", help="Actually upsert (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(upsert_all(dry_run=not args.upsert))