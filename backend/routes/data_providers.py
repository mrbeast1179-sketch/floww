import logging
from typing import Any, Dict, Optional

from services.request_deduplicator import deduplicator

logger = logging.getLogger(__name__)


def build_chain_data_key(ticker: str, dte_max: int, expiries: int) -> str:
    return f"chain:{ticker}:{dte_max}:{expiries}"


async def fetch_chain_data_with_dedup(
    ticker: str,
    dte_max: int,
    expiries: int,
    fetch_func,
) -> Any:
    """Fetch chain data once per unique request key and share the result."""
    key = build_chain_data_key(ticker, dte_max, expiries)

    async def _call() -> Any:
        return await fetch_func(ticker=ticker, dte_max=dte_max, expiries=expiries)

    return await deduplicator.execute(key, _call)
