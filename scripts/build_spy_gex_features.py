#!/usr/bin/env python3
"""
scripts/build_spy_gex_features.py

Build combined SPY features: GEX + underlying bars + technical indicators.
This replaces the academic GEX dataset with real chain-computed GEX.
"""

from __future__ import annotations

import os, sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
FEATURE_VERSION = "v2.0_gex"


def main():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Load GEX features
    gex_docs = list(db["gex_features"].find({"ticker": "SPY"}).sort("day", 1))
    gex_by_day = {d["day"]: d for d in gex_docs}
    print(f"Loaded {len(gex_by_day)} GEX days")

    # Load underlying bars
    bars = list(db["underlying_bars"].find({"ticker": "SPY"}).sort("day", 1))
    bars_df = pd.DataFrame(bars).sort_values("date").reset_index(drop=True)
    print(f"Loaded {len(bars_df)} bars")

    # Compute technical features
    closes = bars_df["close"].values.astype(float)
    n = len(closes)

    # Returns
    for h in [1, 3, 5, 10, 21]:
        bars_df[f"ret_{h}d"] = bars_df["close"].pct_change(h)

    # SMA
    for w in [5, 10, 21, 50]:
        bars_df[f"sma_{w}"] = bars_df["close"].rolling(w).mean()
        bars_df[f"price_vs_sma_{w}"] = bars_df["close"] / bars_df[f"sma_{w}"] - 1

    # Realized vol
    log_ret = np.log(closes / np.roll(closes, 1))
    for w in [5, 10, 21, 60]:
        bars_df[f"realized_vol_{w}d"] = pd.Series(log_ret).rolling(w).std().values * np.sqrt(252)

    # ATR
    highs = bars_df["high"].values.astype(float)
    lows = bars_df["low"].values.astype(float)
    tr = pd.concat([
        pd.Series(highs - lows),
        pd.Series(np.abs(highs - np.roll(closes, 1))),
        pd.Series(np.abs(lows - np.roll(closes, 1)))
    ], axis=1).max(axis=1)
    bars_df["atr_14"] = tr.rolling(14).mean()

    # Volume
    bars_df["volume_sma_21"] = bars_df["volume"].rolling(21).mean()
    bars_df["relative_volume"] = bars_df["volume"] / bars_df["volume_sma_21"]

    # Calendar
    dates = pd.to_datetime(bars_df["date"])
    bars_df["day_of_week"] = dates.dt.dayofweek
    bars_df["day_of_month"] = dates.dt.day
    bars_df["month"] = dates.dt.month

    # RSI
    delta = bars_df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    bars_df["rsi_14"] = 100 - (100 / (1 + rs))

    # Merge with GEX
    feature_docs = []
    for _, row in bars_df.iterrows():
        day = row["date"]
        gex = gex_by_day.get(day)
        if not gex:
            continue

        # Target: next-day direction from SPY outcomes (if available) or from bars
        next_bar = bars_df[bars_df["date"] > day].sort_values("date").head(1)
        if next_bar.empty:
            continue
        next_close = next_bar.iloc[0]["close"]
        curr_close = row["close"]
        target_direction = 1 if next_close > curr_close else 0
        target_return = (next_close - curr_close) / curr_close

        doc = {
            "ticker": "SPY",
            "day": day,
            "feature_version": FEATURE_VERSION,
            "target_directional_move": target_direction,
            "target_return_pct": target_return,
            "_computed_at": datetime.now(timezone.utc).isoformat(),
            # GEX features
            "net_gex": gex["net_gex"],
            "call_gex": gex["call_gex"],
            "put_gex": gex["put_gex"],
            "total_vex": gex["total_vex"],
            "total_dex": gex["total_dex"],
            "total_vega": gex["total_vega"],
            "gamma_flip": gex.get("gamma_flip"),
            "gex_n_strikes": gex["n_strikes"],
            # Underlying features
            "spot": float(curr_close),
            "ret_1d": float(row.get("ret_1d", 0)),
            "ret_5d": float(row.get("ret_5d", 0)),
            "ret_21d": float(row.get("ret_21d", 0)),
            "sma_5": float(row.get("sma_5", 0)),
            "sma_21": float(row.get("sma_21", 0)),
            "price_vs_sma_5": float(row.get("price_vs_sma_5", 0)),
            "price_vs_sma_21": float(row.get("price_vs_sma_21", 0)),
            "realized_vol_5d": float(row.get("realized_vol_5d", 0)),
            "realized_vol_21d": float(row.get("realized_vol_21d", 0)),
            "atr_14": float(row.get("atr_14", 0)),
            "relative_volume": float(row.get("relative_volume", 0)),
            "rsi_14": float(row.get("rsi_14", 0)),
            "day_of_week": float(row.get("day_of_week", 0)),
            "month": float(row.get("month", 0)),
        }

        # Clean NaN
        for k, v in doc.items():
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                doc[k] = 0.0

        feature_docs.append(doc)

    # Bulk insert
    if feature_docs:
        # Use upsert
        for doc in feature_docs:
            db["ml_features"].update_one(
                {"ticker": "SPY", "day": day, "feature_version": FEATURE_VERSION},
                {"$set": doc},
                upsert=True,
            )

    print(f"Stored {len(feature_docs)} SPY v2.0 features")
    print(f"Date range: {feature_docs[0]['day']} to {feature_docs[-1]['day']}")
    print(f"Features per row: {len(feature_docs[0]) - 6}")  # exclude metadata

    client.close()


if __name__ == "__main__":
    main()
