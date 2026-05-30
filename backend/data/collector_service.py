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

async def run_collection_loop():
    """Main collection loop for all tickers."""
    logging.info("Collection loop started")
    while True:
        for ticker in ["SPY", "QQQ", "DIA", "IWM", "TLT"]:
            from data_collector import collect_and_store
            await collect_and_store(ticker)
        await asyncio.sleep(300)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_collection_loop())
