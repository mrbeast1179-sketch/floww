#!/usr/bin/env python3
"""Fix QQQ/IWM/DIA/TLT targets using their own underlying bar data."""
from __future__ import annotations
import os, sys
from pathlib import Path
import pandas as pd
from pymongo import MongoClient, UpdateOne
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")

def fix_targets(ticker):
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    bars = list(db["underlying_bars"].find({"ticker": ticker}).sort("date", 1))
    if not bars:
        return
    df = pd.DataFrame(bars).sort_values("date").reset_index(drop=True)
    df["next_ret"] = df["close"].shift(-1) / df["close"] - 1
    df["next_direction"] = (df["next_ret"] > 0).astype(int)

    ops = []
    for _, row in df.iterrows():
        ops.append(UpdateOne(
            {"ticker": ticker, "date": row["date"]},
            {"$set": {
                "target_directional_move": int(row["next_direction"]) if pd.notna(row["next_direction"]) else 0,
                "target_return_pct": float(row["next_ret"]) if pd.notna(row["next_ret"]) else 0.0,
            }},
        ))

    # Bulk write in batches
    total = 0
    for i in range(0, len(ops), 500):
        batch = ops[i:i+500]
        result = db["ml_features"].bulk_write(batch, ordered=False)
        total += result.modified_count

    pos = db.ml_features.count_documents({"ticker": ticker, "target_directional_move": 1})
    n = db.ml_features.count_documents({"ticker": ticker})
    print(f"{ticker}: updated {total}, {pos}/{n} positive ({pos/n*100:.1f}%)" if n > 0 else f"{ticker}: 0 rows")

def main():
    for ticker in ["QQQ", "IWM", "DIA", "TLT"]:
        fix_targets(ticker)

if __name__ == "__main__":
    main()
