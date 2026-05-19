#!/usr/bin/env python3
"""
scripts/cache_features_to_csv.py

Cache ml_features from MongoDB to local CSV for fast local training.
Uses small batches (50 docs) with retry logic for unreliable connections.
"""
import os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('backend/.env'))
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import pandas as pd

CACHE_DIR = Path('data/cached_features')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def fetch_with_retry(query, batch_size=50, max_retries=3):
    """Fetch documents in small batches with retry logic."""
    all_docs = []
    last_id = None
    total_fetched = 0
    
    while True:
        for attempt in range(max_retries):
            try:
                client = MongoClient(
                    os.environ['MONGO_URL'],
                    serverSelectionTimeoutMS=10000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=30000,
                    maxPoolSize=1
                )
                db = client['confluence_decoder']
                
                q = dict(query)
                if last_id:
                    q['_id'] = {'$gt': last_id}
                
                cursor = db['ml_features'].find(q).sort('_id', 1).limit(batch_size)
                batch = list(cursor)
                
                client.close()
                
                if not batch:
                    return all_docs
                
                last_id = batch[-1]['_id']
                for doc in batch:
                    doc.pop('_id', None)
                    all_docs.append(doc)
                
                total_fetched += len(batch)
                if total_fetched % 200 == 0:
                    print(f"  Fetched {total_fetched}...")
                
                break  # Success, exit retry loop
                
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                wait = 2 ** attempt
                print(f"  Connection error (attempt {attempt+1}/{max_retries}): {e}")
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(1)
    
    return all_docs

tickers = ['QQQ', 'DIA', 'IWM', 'TLT']
versions = ['v1.0']

for ticker in tickers:
    for version in versions:
        query = {'ticker': ticker, 'feature_version': version}
        
        # Check if already cached
        csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
        if csv_path.exists():
            existing = pd.read_csv(csv_path)
            print(f"{ticker} {version}: already cached ({len(existing)} rows)")
            continue
        
        print(f"\nFetching {ticker} {version}...")
        t0 = time.time()
        
        docs = fetch_with_retry(query, batch_size=50)
        
        if docs:
            df = pd.DataFrame(docs)
            df.to_csv(csv_path, index=False)
            print(f"  Saved {len(df)} rows to {csv_path} ({time.time()-t0:.1f}s)")
        else:
            print(f"  No data fetched for {ticker} {version}")

print("\nDone!")
