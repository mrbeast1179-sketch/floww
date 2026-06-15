#!/usr/bin/env python3
"""Compute GEX features for all tickers with databento chains."""
import sys, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('backend/.env'))
from pymongo import MongoClient
import numpy as np
from scipy.stats import norm  # type: ignore[import-untyped]
from datetime import date as dt_date
from typing import Any

db: Any = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]

# Load underlying bars for all tickers
bars: dict[str, dict[str, float]] = {}
for doc in db['underlying_bars'].find():
    t = doc['ticker']
    if t not in bars:
        bars[t] = {}
    bars[t][doc['date']] = float(doc['close'])

print(f"Loaded bars for {len(bars)} tickers")

# Get tickers with databento chains
tickers = db['databento_eod_chains'].distinct('ticker')
print(f"Databento tickers: {tickers}")

total_computed = 0
total_errors = 0

for ticker in tickers:
    if ticker not in bars:
        print(f"  SKIP {ticker}: no underlying bars")
        continue
    
    # Get already computed days
    done = {d['day'] for d in db['gex_features'].find({'ticker': ticker}, {'day': 1})}
    
    # Get all days with databento chains
    all_days = [d['day'] for d in db['databento_eod_chains'].find({'ticker': ticker}, {'day': 1}).sort('day', 1)]
    pending = [d for d in all_days if d not in done]
    
    print(f"\n{ticker}: {len(all_days)} chains, {len(done)} computed, {len(pending)} pending")
    
    computed = 0
    errors = 0
    
    for day in pending:
        spot = bars[ticker].get(day, 0)
        if spot <= 0:
            continue
        
        doc = db['databento_eod_chains'].find_one({'ticker': ticker, 'day': day}, {'contracts': 1})
        if not doc:
            continue
        
        contracts = doc.get('contracts', {})
        strikes, ois, signs, Ts = [], [], [], []
        today = dt_date.fromisoformat(day)
        
        for sym, c in contracts.items():
            k, oi = c.get('strike', 0), c.get('oi', 0)
            if k <= 0 or oi <= 0:
                continue
            try:
                T = max((dt_date.fromisoformat(c['expiry']) - today).days / 365.0, 0.01)
            except:
                T = 0.25
            strikes.append(k)
            ois.append(float(oi))
            signs.append(1.0 if c.get('type') == 'call' else -1.0)
            Ts.append(T)
        
        if not strikes:
            continue
        
        K = np.array(strikes)
        OI = np.array(ois)
        sgn = np.array(signs)
        T_arr = np.array(Ts)
        
        # Use realized vol estimate or fallback
        iv = 0.20
        
        d1 = (np.log(spot / K) + (0.045 + 0.5 * iv**2) * T_arr) / (iv * np.sqrt(T_arr))
        gamma = norm.pdf(d1) / (spot * iv * np.sqrt(T_arr))
        gex = sgn * gamma * OI * 100.0 * spot * 0.01
        total_gex = float(np.sum(gex))
        call_gex = float(np.sum(gex[np.array(signs) > 0]))
        put_gex = float(np.sum(gex[np.array(signs) < 0]))
        d2 = d1 - iv * np.sqrt(T_arr)
        vanna = -norm.pdf(d1) * d2 / iv
        vex = float(np.sum(vanna * OI * spot))
        dex = float(np.sum(sgn * norm.cdf(d1) * OI * 100.0 * spot))
        vega = float(np.sum(spot * norm.pdf(d1) * np.sqrt(T_arr) * OI))
        
        db['gex_features'].update_one(
            {'ticker': ticker, 'day': day},
            {'$set': {
                'ticker': ticker, 'day': day, 'source': 'databento_computed',
                'net_gex': round(total_gex, 2), 'call_gex': round(call_gex, 2),
                'put_gex': round(put_gex, 2), 'total_vex': round(vex, 2),
                'total_dex': round(dex, 2), 'total_vega': round(vega, 2),
                'n_strikes': len(strikes), 'spot': spot,
                'computed_at': str(dt_date.today()),
            }},
            upsert=True
        )
        computed += 1
    
    print(f"  Computed: {computed}, Errors: {errors}")
    total_computed += computed
    total_errors += errors

print(f"\nTotal computed: {total_computed}, Total errors: {total_errors}")
print(f"GEX features total: {db['gex_features'].count_documents({})}")
