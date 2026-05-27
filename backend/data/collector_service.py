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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_collection_loop())