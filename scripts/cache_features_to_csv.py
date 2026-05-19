#!/usr/bin/env python3
"""Cache features using aggregation $merge to a temp collection, then export."""
import os, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('backend/.env'))
from pymongo import MongoClient
import pandas as pd

client = MongoClient(os.environ['MONGO_URL'], serverSelectionTimeoutMS=60000)
db = client['confluence_decoder']

cache_dir = Path('data/cached_features')
cache_dir.mkdir(parents=True, exist_ok=True)

# Just do QQQ v1.0 - the one we need for the bake-off
ticker = 'QQQ'
version = 'v1.0'

count = db['ml_features'].count_documents({'ticker': ticker, 'feature_version': version})
print(f"{ticker} {version}: {count} docs")

# Use aggregation with $out to copy to a temp collection
print("Copying via aggregation...")
t0 = time.time()
db['ml_features'].aggregate([
    {'$match': {'ticker': ticker, 'feature_version': version}},
    {'$project': {'_id': 0}},
    {'$out': f'_cache_{ticker}_{version}'}
], allowDiskUse=True)
print(f"  Aggregation done in {time.time()-t0:.1f}s")

# Now read from the temp collection
temp_col = db[f'_cache_{ticker}_{version}']
print(f"Temp collection count: {temp_col.count_documents({})}")

# Read in batches
all_docs = []
batch_size = 500
for i in range(0, count, batch_size):
    batch = list(temp_col.find().skip(i).limit(batch_size))
    all_docs.extend(batch)
    print(f"  Read {len(all_docs)}/{count}")

df = pd.DataFrame(all_docs)
csv_path = cache_dir / f"{ticker}_{version}.csv"
df.to_csv(csv_path, index=False)
print(f"Saved {len(df)} rows to {csv_path}")

# Clean up temp collection
temp_col.drop()
print("Cleaned up temp collection")

client.close()
