#!/usr/bin/env python3
"""
scripts/merge_gex_into_features.py

Merge GEX features from gex_features collection into ml_features.
Creates a new feature version (e.g., v3.0_gex) with GEX + original features.

Usage:
  python scripts/merge_gex_into_features.py --ticker SPY --base-version v1.0 --new-version v3.0_gex
  python scripts/merge_gex_into_features.py --all  # all tickers with GEX data
"""
import argparse, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path('backend/.env'))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")

GEX_FIELDS = ['net_gex', 'call_gex', 'put_gex', 'total_vex', 'total_dex', 'total_vega', 'n_strikes']

def merge_ticker(db, ticker, base_version='v1.0', new_version='v3.0_gex'):
    """Merge GEX features into ml_features for one ticker."""
    print(f"\n{ticker}: merging GEX into {base_version} -> {new_version}")
    
    # Load GEX features
    gex_docs = list(db['gex_features'].find({'ticker': ticker}).sort('day', 1))
    if not gex_docs:
        print(f"  No GEX features for {ticker}, skipping")
        return 0
    
    gex_by_day = {d['day']: d for d in gex_docs}
    print(f"  GEX features: {len(gex_by_day)} days")
    
    # Load base features
    base_docs = list(db['ml_features'].find({'ticker': ticker, 'feature_version': base_version}).sort('date', 1))
    if not base_docs:
        print(f"  No base features for {ticker} {base_version}, skipping")
        return 0
    
    print(f"  Base features: {len(base_docs)} docs")
    
    merged = 0
    skipped = 0
    
    for doc in base_docs:
        day = doc.get('date') or doc.get('day')
        gex = gex_by_day.get(day)
        
        if not gex:
            skipped += 1
            continue
        
        # Create merged doc
        new_doc = dict(doc)
        new_doc.pop('_id', None)
        new_doc['feature_version'] = new_version
        new_doc['_merged_at'] = datetime.now(timezone.utc).isoformat()
        new_doc['_gex_source'] = gex.get('source', 'unknown')
        
        # Add GEX fields
        for field in GEX_FIELDS:
            new_doc[field] = gex.get(field)
        
        # Upsert
        db['ml_features'].update_one(
            {'ticker': ticker, 'day': day, 'feature_version': new_version},
            {'$set': new_doc},
            upsert=True
        )
        merged += 1
    
    print(f"  Merged: {merged}, Skipped (no GEX): {skipped}")
    return merged

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker to process")
    parser.add_argument("--base-version", default="v1.0")
    parser.add_argument("--new-version", default="v3.0_gex")
    parser.add_argument("--all", action="store_true", help="Process all tickers with GEX data")
    args = parser.parse_args()
    
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=30000)
    db = client[DB_NAME]
    
    if args.all:
        tickers = db['gex_features'].distinct('ticker')
        print(f"Processing all tickers with GEX: {tickers}")
    elif args.ticker:
        tickers = [args.ticker]
    else:
        print("Specify --ticker or --all")
        return
    
    total = 0
    for ticker in tickers:
        n = merge_ticker(db, ticker, args.base_version, args.new_version)
        total += n
    
    print(f"\nTotal merged: {total}")
    client.close()

if __name__ == "__main__":
    main()
