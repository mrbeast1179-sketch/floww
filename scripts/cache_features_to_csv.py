#!/usr/bin/env python3
"""
scripts/cache_features_to_csv.py

Cache ml_features from MongoDB to local CSV.
Uses small batches (100 docs) with _id pagination for unreliable connections.
"""
import os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('backend/.env'))
from pymongo import MongoClient
import pandas as pd

CACHE_DIR = Path('data/cached_features')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def fetch_all(ticker, version='v1.0', batch_size=100):
    """Fetch all documents in small batches."""
    client = MongoClient(
        os.environ['MONGO_URL'],
        serverSelectionTimeoutMS=10000,
        socketTimeoutMS=60000,
        maxPoolSize=1
    )
    db = client['confluence_decoder']
    
    all_docs = []
    last_id = None
    total = db['ml_features'].count_documents({'ticker': ticker, 'feature_version': version})
    print(f"  Total docs: {total}")
    
    while True:
        query = {'ticker': ticker, 'feature_version': version}
        if last_id:
            query['_id'] = {'$gt': last_id}
        
        t0 = time.time()
        cursor = db['ml_features'].find(query, {'_id': 0}).sort('_id', 1).limit(batch_size)
        batch = list(cursor)
        elapsed = time.time() - t0
        
        if not batch:
            break
        
        all_docs.extend(batch)
        last_id = batch[-1].get('_id')
        
        pct = len(all_docs) / total * 100 if total > 0 else 0
        print(f"  {len(all_docs)}/{total} ({pct:.0f}%) [{elapsed:.1f}s/batch]")
        
        if len(all_docs) >= total:
            break
    
    client.close()
    return all_docs

tickers = ['QQQ', 'DIA', 'IWM', 'TLT']
versions = ['v1.0']

for ticker in tickers:
    for version in versions:
        csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
        if csv_path.exists():
            existing = pd.read_csv(csv_path)
            print(f"{ticker} {version}: already cached ({len(existing)} rows)")
            continue
        
        print(f"\nFetching {ticker} {version}...")
        t0 = time.time()
        docs = fetch_all(ticker, version, batch_size=100)
        
        if docs:
            df = pd.DataFrame(docs)
            df.to_csv(csv_path, index=False)
            print(f"  Saved {len(df)} rows ({time.time()-t0:.0f}s total)")
        else:
            print(f"  No data fetched")

print("\nDone!")
