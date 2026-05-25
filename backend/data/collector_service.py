"""
Continuous data collection service for ML training.

Runs as a background process during market hours.
Collects GEX snapshots every 5 minutes for all tracked tickers.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

TRACKED_TICKERS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "TSLA", "NVDA", "MSFT"]
COLLECTION_INTERVAL = 300  # 5 minutes


async def collect_all_tickers():
    """Collect snapshots for all tracked tickers."""
    from data_collector import collect_multiple_tickers
    
    results = await collect_multiple_tickers(TRACKED_TICKERS)
    
    success = sum(1 for r in results if r.get("status") == "stored")
    failed = len(results) - success
    
    logger.info(f"Data collection complete: {success} stored, {failed} failed")
    return results


async def run_collection_loop():
    """Run the collection loop continuously."""
    logger.info(f"Starting data collection loop for {len(TRACKED_TICKERS)} tickers")
    logger.info(f"Collection interval: {COLLECTION_INTERVAL}s")
    
    while True:
        try:
            await collect_all_tickers()
        except Exception as e:
            logger.error(f"Collection error: {e}")
        
        await asyncio.sleep(COLLECTION_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_collection_loop())