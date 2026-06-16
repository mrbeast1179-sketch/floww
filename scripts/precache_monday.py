"""
Pre-cache all ticker data for Monday trading.
Run this before market open to warm up all caches.
"""
import yfinance as yf  # type: ignore[import-untyped]
import time
import json
import os

TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD"]
MAX_EXPIRIES = 8
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def warm_ticker(ticker_str: str) -> bool:
    """Warm cache for a single ticker."""
    try:
        print(f"Warming {ticker_str}...", flush=True)
        t = yf.Ticker(ticker_str)
        
        # Get spot
        try:
            fi = t.fast_info
            spot = float(fi.get("lastPrice") or fi.get("last_price") or 0)
        except:
            spot = 0
        
        # Get all expiries
        expiries = list(t.options or [])[:MAX_EXPIRIES]
        
        # Fetch each expiry's chain
        total_contracts = 0
        for exp in expiries:
            try:
                ch = t.option_chain(exp)
                total_contracts += len(ch.calls) + len(ch.puts) if ch.calls is not None and ch.puts is not None else 0
                time.sleep(0.2)
            except:
                continue
        
        # Save cache info
        cache_info = {
            "ticker": ticker_str,
            "spot": spot,
            "expiries": expiries,
            "total_contracts": total_contracts,
            "warmed_at": time.time(),
        }
        
        cache_file = os.path.join(CACHE_DIR, f"{ticker_str.replace('^', 'IDX_')}.json")
        with open(cache_file, "w") as f:
            json.dump(cache_info, f)
        
        print(f"  ✓ {ticker_str}: spot={spot}, {len(expiries)} expiries, {total_contracts} contracts", flush=True)
        return True
    except Exception as e:
        print(f"  ✗ {ticker_str} failed: {e}", flush=True)
        return False

def main() -> None:
    print(f"Warming cache for {len(TICKERS)} tickers...", flush=True)
    print("=" * 60)
    
    success = 0
    failed = 0
    
    for ticker in TICKERS:
        if warm_ticker(ticker):
            success += 1
        else:
            failed += 1
        time.sleep(0.5)  # Rate limit
    
    print("=" * 60)
    print(f"Done: {success} success, {failed} failed")
    
    # Summary
    print("\nCache summary:")
    for ticker in TICKERS:
        cache_file = os.path.join(CACHE_DIR, f"{ticker.replace('^', 'IDX_')}.json")
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                info = json.load(f)
            print(f"  {ticker}: spot={info.get('spot', 0):.2f}, {len(info.get('expiries', []))} expiries, {info.get('total_contracts', 0)} contracts")

if __name__ == "__main__":
    main()
