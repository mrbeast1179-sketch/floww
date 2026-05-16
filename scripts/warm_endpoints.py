"""
Pre-warm the backend's internal cache by hitting the heavy endpoints.
This ensures the app is responsive when the user starts using it.
"""
import httpx
import asyncio

BASE = "http://localhost:8000/api"

TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOGL", "AMD"]
HEAVY_TICKERS = ["SPY", "QQQ", "^SPX", "IWM"]  # These get the full treatment

async def warm():
    async with httpx.AsyncClient(timeout=60) as client:
        # Hit root to verify backend is up
        r = await client.get(f"{BASE}/")
        print(f"Backend: {r.json()}")
        
        # Warm tickers endpoint
        r = await client.get(f"{BASE}/tickers")
        print(f"Tickers: {len(r.json().get('default', []))} default tickers")
        
        # Warm heavy endpoints for main tickers
        for ticker in HEAVY_TICKERS:
            print(f"\nWarming {ticker}...")
            
            # Heatmap (already warmed by yfinance cache, but hits the endpoint)
            r = await client.get(f"{BASE}/heatmap/{ticker}?expiries=4")
            d = r.json()
            print(f"  heatmap: {len(d.get('strikes', []))} strikes, source={d.get('data_source')}")
            
            # Chain
            r = await client.get(f"{BASE}/chain/{ticker}?min_oi=100")
            d = r.json()
            print(f"  chain: {d.get('count', 0)} rows")
            
            # Advanced analytics
            r = await client.get(f"{BASE}/advanced/{ticker}?expiries=4")
            d = r.json()
            print(f"  advanced: regime={d.get('regime', {}).get('regime')}, pdf={'implied_pdf' in d}")
            
            # GEX timeframes
            r = await client.get(f"{BASE}/gex-timeframes/{ticker}")
            d = r.json()
            print(f"  timeframes: {list(d.get('timeframes', {}).keys())}")
            
            # UOA
            r = await client.get(f"{BASE}/uoa/{ticker}")
            d = r.json()
            print(f"  uoa: {len(d.get('unusual', []))} unusual")
            
            await asyncio.sleep(1)
        
        # Light warm for other tickers (just heatmap)
        for ticker in [t for t in TICKERS if t not in HEAVY_TICKERS]:
            print(f"\nLight warm {ticker}...")
            r = await client.get(f"{BASE}/heatmap/{ticker}?expiries=4")
            d = r.json()
            print(f"  heatmap: {len(d.get('strikes', []))} strikes")
            await asyncio.sleep(0.5)
        
        print("\nAll caches warmed!")

asyncio.run(warm())
