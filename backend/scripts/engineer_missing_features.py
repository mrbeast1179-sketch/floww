#!/usr/bin/env python3
"""
scripts/engineer_missing_features.py

Compute the 12 missing engineered features from existing CSV columns
and update both the CSV files and MongoDB ml_features collection.

Missing features:
  gap_abs         = abs(overnight_gap)
  gap_large       = int(overnight_gap > 0.02)  # >2% gap
  ret_accel       = ret_3d - ret_1d            # acceleration
  ret_momentum    = ret_5d + ret_21d           # momentum combo
  rsi_overbought  = int(rsi_14 > 70)
  rsi_oversold    = int(rsi_14 < 30)
  sma_10_50_diff  = sma_10 - sma_50
  sma_5_21_cross  = int(sma_5 > sma_21)        # 1 if bullish cross
  sma_5_21_diff   = sma_5 - sma_21
  vol_ratio_5_21  = realized_vol_5d / (realized_vol_21d + 1e-8)
  vol_ratio_5_60  = realized_vol_5d / (realized_vol_60d + 1e-8)
  vol_spike       = int(relative_volume > 2.0)
"""
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

import logging

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"

CSV_FILES = ["IWM_v1.0.csv", "TLT_v1.0.csv", "QQQ_v1.0.csv", "DIA_v1.0.csv", "SPY_v1.0.csv"]


async def main():
    for csv_name in CSV_FILES:
        csv_path = CACHE_DIR / csv_name
        ticker = csv_name.split("_")[0]

        if not csv_path.exists():
            logger.info(f"SKIP {ticker}: {csv_path} not found")
            continue

        df = pd.read_csv(csv_path)
        n_before = len(df.columns)

        # Check if already has the features
        if 'gap_abs' in df.columns and 'vol_spike' in df.columns:
            logger.info(f"{ticker}: already has engineered features ({n_before} cols)")
            continue

        df = compute_missing_features(df)
        n_after = len(df.columns)
        logger.info(f"{ticker}: {n_before} -> {n_after} columns (+{n_after - n_before} features)")

        # Save updated CSV
        df.to_csv(csv_path, index=False)
        logger.info(f"  CSV saved: {csv_path}")

        # Update MongoDB
        await update_mongo(ticker, df)

    logger.info("\nDone. Verifying...")
    # Quick verify
    for csv_name in CSV_FILES:
        csv_path = CACHE_DIR / csv_name
        if csv_path.exists():
            df = pd.read_csv(csv_path, nrows=1)
            has_all = all(f in df.columns for f in ['gap_abs', 'vol_spike', 'ret_accel'])
            logger.info(f"  {csv_name}: {'OK' if has_all else 'MISSING'} ({len(df.columns)} cols)")


if __name__ == "__main__":
    asyncio.run(main())