#!/usr/bin/env python3
"""
scripts/compute_qqq_features.py

Compute QQQ features from underlying bars (no GEX data available).
Uses technical indicators, returns, volatility, and calendar features.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
FEATURE_VERSION = "v1.0"


def load_bars(ticker: str) -> pd.DataFrame:
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    cursor = db["underlying_bars"].find({"ticker": ticker}).sort("date", 1)
    docs = list(cursor)
    client.close()
    return pd.DataFrame(docs) if docs else pd.DataFrame()


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute features from OHLCV bars."""
    if df.empty:
        return df

    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].values.astype(float)
    highs = df["high"].values.astype(float)
    lows = df["low"].values.astype(float)
    volumes = df["volume"].values.astype(float)
    n = len(closes)

    # Returns
    for h in [1, 3, 5, 10, 21]:
        df[f"ret_{h}d"] = df["close"].pct_change(h)

    # Log returns
    df["log_ret_1d"] = np.log(closes / np.roll(closes, 1))

    # Overnight gap
    df["overnight_gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

    # SMAs
    for w in [5, 10, 21, 50]:
        df[f"sma_{w}"] = df["close"].rolling(w).mean()
        df[f"price_vs_sma_{w}"] = df["close"] / df[f"sma_{w}"] - 1

    # ATR
    tr = pd.concat([
        pd.Series(highs - lows),
        pd.Series(np.abs(highs - np.roll(closes, 1))),
        pd.Series(np.abs(lows - np.roll(closes, 1)))
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()

    # Volume
    df["volume_sma_5"] = df["volume"].rolling(5).mean()
    df["volume_sma_21"] = df["volume"].rolling(21).mean()
    df["relative_volume"] = df["volume"] / df["volume_sma_21"]

    # Realized vol
    log_ret = np.log(closes / np.roll(closes, 1))
    for w in [5, 10, 21, 60]:
        df[f"realized_vol_{w}d"] = pd.Series(log_ret).rolling(w).std().values * np.sqrt(252)

    # Calendar
    dates = pd.to_datetime(df["date"])
    df["day_of_week"] = dates.dt.dayofweek
    df["day_of_month"] = dates.dt.day
    df["month"] = dates.dt.month
    df["is_month_end"] = (dates.dt.day >= 28).astype(int)
    df["is_month_start"] = (dates.dt.day <= 3).astype(int)

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-10)

    return df


def store_features(df: pd.DataFrame, ticker: str):
    """Store features in MongoDB."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Get SPY directional_move as target (aligned by date)
    spy_outcomes = {}
    for doc in db["gex_llm_patterns_outcomes"].find({}).sort("date", 1):
        spy_outcomes[doc["date"]] = doc

    feature_cols = [c for c in df.columns if c not in ("_id", "date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "source", "_computed_at")]
    # Safety: only keep numeric columns
    feature_cols = [c for c in feature_cols if df[c].dtype in (np.float64, np.int64, float, int)]

    stored = 0
    batch = []
    for i, (_, row) in enumerate(df.iterrows()):
        date_str = row["date"]
        spy = spy_outcomes.get(date_str, {})

        doc = {
            "ticker": ticker,
            "date": date_str,
            "feature_version": FEATURE_VERSION,
            "target_directional_move": float(spy.get("directional_move", 0)),
            "target_return_pct": float(spy.get("return_pct", 0)),
            "target_range_expansion": float(spy.get("range_expansion", 0)),
            "target_gap_move": float(spy.get("gap_move", 0)),
            "target_any_materialization": float(spy.get("any_materialization", 0)),
            "_computed_at": datetime.now(timezone.utc).isoformat(),
        }
        for col in feature_cols:
            val = row[col]
            if pd.notna(val):
                doc[col] = float(val)
            else:
                doc[col] = 0.0

        batch.append(doc)
        if len(batch) >= 100:
            db["ml_features"].insert_many(batch, ordered=False)
            stored += len(batch)
            batch = []
            if stored % 500 == 0:
                print(f"    ... {stored} stored")

    if batch:
        db["ml_features"].insert_many(batch, ordered=False)
        stored += len(batch)

    print(f"Stored {stored} rows for {ticker} with {len(feature_cols)} features")
    return stored


def main():
    for ticker in ["QQQ", "IWM"]:
        print(f"\n=== {ticker} ===")
        df = load_bars(ticker)
        if df.empty:
            print(f"  No data for {ticker}")
            continue
        print(f"  Loaded {len(df)} bars")
        df = compute_features(df)
        df = df.iloc[60:].reset_index(drop=True) if len(df) > 60 else df
        n = store_features(df, ticker)
        print(f"  Done: {n} rows stored")


if __name__ == "__main__":
    main()
