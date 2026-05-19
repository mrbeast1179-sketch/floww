#!/usr/bin/env python3
"""Quick data audit script."""
import pymongo, os
from dotenv import load_dotenv
load_dotenv('backend/.env')
client = pymongo.MongoClient(os.environ['MONGO_URL'])
db = client['confluence_decoder']

# ml_features - check schema
print('=== ml_features ===')
print('Total:', db['ml_features'].count_documents({}))
tickers = db['ml_features'].distinct('ticker')
versions = db['ml_features'].distinct('feature_version')
print('Tickers:', tickers)
print('Versions:', versions)

# Check a sample doc per ticker
for t in tickers:
    doc = db['ml_features'].find_one({'ticker': t})
    if doc:
        n = db['ml_features'].count_documents({'ticker': t})
        date_key = 'day' if 'day' in doc else 'date' if 'date' in doc else '?'
        print(f'\n{t} ({n} docs):')
        print(f'  Keys: {sorted(doc.keys())}')
        print(f'  Date key: {date_key}')
        if date_key in doc:
            # Get range
            docs_sorted = list(db['ml_features'].find({'ticker': t}, {date_key: 1}).sort(date_key, 1).limit(1))
            mn = docs_sorted[0].get(date_key, '?') if docs_sorted else '?'
            docs_sorted2 = list(db['ml_features'].find({'ticker': t}, {date_key: 1}).sort(date_key, -1).limit(1))
            mx = docs_sorted2[0].get(date_key, '?') if docs_sorted2 else '?'
            print(f'  Range: {mn} to {mx}')

# gex_features
print('\n=== gex_features ===')
print('Total:', db['gex_features'].count_documents({}))
for t in db['gex_features'].distinct('ticker'):
    n = db['gex_features'].count_documents({'ticker': t})
    docs = list(db['gex_features'].find({'ticker': t}, {'day': 1}).sort('day', 1).limit(1))
    mn = docs[0]['day'] if docs else '?'
    docs2 = list(db['gex_features'].find({'ticker': t}, {'day': 1}).sort('day', -1).limit(1))
    mx = docs2[0]['day'] if docs2 else '?'
    print(f'  {t}: {n} docs, {mn} to {mx}')

# underlying_bars
print('\n=== underlying_bars ===')
print('Total:', db['underlying_bars'].count_documents({}))
for t in db['underlying_bars'].distinct('ticker'):
    n = db['underlying_bars'].count_documents({'ticker': t})
    print(f'  {t}: {n} docs')

# databento_eod_chains
print('\n=== databento_eod_chains ===')
print('Total:', db['databento_eod_chains'].count_documents({}))
for t in db['databento_eod_chains'].distinct('ticker'):
    n = db['databento_eod_chains'].count_documents({'ticker': t})
    docs = list(db['databento_eod_chains'].find({'ticker': t}, {'day': 1}).sort('day', 1).limit(1))
    mn = docs[0]['day'] if docs else '?'
    docs2 = list(db['databento_eod_chains'].find({'ticker': t}, {'day': 1}).sort('day', -1).limit(1))
    mx = docs2[0]['day'] if docs2 else '?'
    print(f'  {t}: {n} docs, {mn} to {mx}')

client.close()
