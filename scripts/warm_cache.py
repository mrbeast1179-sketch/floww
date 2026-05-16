"""
Pre-warm yfinance cache for all supported tickers.
Fetches option chains with multiple expiries so the app is responsive during use.
"""
import yfinance as yf
import time
import sys

TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD"]
MAX_EXPIRIES = 8

for ticker_str in TICKERS:
    try:
        print(f"Fetching {ticker_str}...", flush=True)
        t = yf.Ticker(ticker_str)
        
        # Get spot price
        try:
            fi = t.fast_info
            spot = float(fi.get("lastPrice") or fi.get("last_price") or 0)
            print(f"  Spot: ${spot:.2f}", flush=True)
        except Exception as e:
            print(f"  Spot fetch failed: {e}", flush=True)
        
        # Get option chain expiries
        expiries = list(t.options or [])[:MAX_EXPIRIES]
        print(f"  Expiries: {expiries}", flush=True)
        
        # Fetch each expiry's chain
        for exp in expiries:
            try:
                ch = t.option_chain(exp)
                n_calls = len(ch.calls) if ch.calls is not None else 0
                n_puts = len(ch.puts) if ch.puts is not None else 0
                print(f"  {exp}: {n_calls} calls, {n_puts} puts", flush=True)
                time.sleep(0.3)  # Rate limit
            except Exception as e:
                print(f"  {exp} failed: {e}", flush=True)
        
        time.sleep(0.5)  # Rate limit between tickers
    except Exception as e:
        print(f"{ticker_str} failed: {e}", flush=True)

print("\nDone warming cache.", flush=True)
