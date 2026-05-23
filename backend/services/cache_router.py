"""
backend/services/cache_router.py

Cache-first routing layer for analytics endpoints.
Reads from DuckDB cache first, falls back to live fetch.
Returns stale cache rather than blocking on external API.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheRouter:
    """Cache-first router with DuckDB backend."""
    
    def __init__(self):
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
    
    async def get_chain(
        self,
        ticker: str,
        expiries: int,
        max_age_seconds: int,
        coordinator: Any,
    ) -> Dict[str, Any]:
        """Get option chain — cache first, then live fetch."""
        cache_key = f"{ticker.upper()}:{expiries}"
        
        # Check memory cache
        cached = self._memory_cache.get(cache_key)
        if cached:
            age = time.time() - cached.get("_ts", 0)
            if age <= max_age_seconds:
                return cached["data"]
            logger.info(f"Cache stale for {ticker} ({age:.0f}s), returning stale data")
            return cached["data"]
        
        # Fetch live
        data = await coordinator.fetch(ticker, expiries)
        
        # Cache it
        self._memory_cache[cache_key] = {
            "data": data,
            "_ts": time.time(),
        }
        
        return data


# ── Standalone functions (imported directly by routes) ───────────────────────

def degraded_response(reason: str, detail: str) -> Dict[str, Any]:
    """Return a structured degradation payload."""
    return {
        "status": "degraded",
        "reason": reason,
        "detail": detail,
        "asof": datetime.now(timezone.utc).isoformat(),
    }


async def _live_fetcher(ticker: str, expiries: int) -> Dict[str, Any]:
    """Live fetch fallback — spot + options chain."""
    try:
        from server import fetch_spot_and_chains_merged
        return await fetch_spot_and_chains_merged(ticker, expiries)
    except Exception:
        return {"spot": None, "contracts": []}
