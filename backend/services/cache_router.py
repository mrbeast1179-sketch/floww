"""
backend/services/cache_router.py

Cache-first routing for analytics endpoints.

All /api/analytics/* endpoints read from DuckDB `chains` table first.
Only on cache miss or stale data do we trigger an external fetch — and even
then we return stale data immediately rather than blocking the response.

Cache key:  (ticker, expiries)
Cache table: chains (DuckDB, with `timestamp` column for TTL checks)
Stale flag:  included in response metadata so UI can show "stale" badge.

Usage:
    cache = CacheRouter()
    result = await cache.get_chain("SPY", 4, max_age_seconds=300, coordinator)
    # result["_cache"] = {"hit": True, "age_seconds": 12, "stale": False}
"""
from __future__ import annotations

import logging
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# DuckDB table name for chain cache
_CACHE_TABLE = "analytics_chain_cache"

# Default max age (seconds) before we consider cache stale
DEFAULT_MAX_AGE = 300


@dataclass
class CacheEntry:
    """Represents a cached chain result."""
    ticker: str
    expiries: int
    data: Dict[str, Any]
    cached_at: float  # monotonic timestamp
    raw_contracts: List[Dict[str, Any]]

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.cached_at

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > DEFAULT_MAX_AGE


class CacheRouter:
    """Cache-first routing with DuckDB backing and in-memory LRU.

    Strategy:
      1. Check in-memory cache → return if fresh.
      2. Check DuckDB → populate memory, return if fresh.
      3. If stale/miss → coordinator fetches, returns stale immediately.
      4. Background: write new fetch to DuckDB + memory.

    Never blocks the HTTP response on an external API call.
    """

    def __init__(self, max_memory_entries: int = 50) -> None._CacheEntry"] = []
        self._max_memory = max_memory_entries
        self._duckdb_initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_chain(
        self,
        ticker: str,
        expiries: int,
        max_age_seconds: int,
        coordinator: "FetchCoordinator",
    ) -> Dict[str, Any]:
        """Return chain data, preferring cache over live fetch.

        Always returns data (cached if possible). Never raises on
        external API failure — returns stale data with degradation info.
        """
        cache_key = _make_key(ticker, expiries)

        # 1. In-memory cache check
        mem = self._memory_get(cache_key)
        if mem and mem.age_seconds < max_age_seconds:
            logger.debug(f"Memory cache HIT for {cache_key} (age={mem.age_seconds:.1f}s)")
            return self._attach_meta(mem.data, hit=True, age=mem.age_seconds, stale=False)

        # 2. DuckDB cache check
        duck = await self._duckdb_get(cache_key)
        if duck and duck.age_seconds < max_age_seconds:
            logger.debug(f"DuckDB cache HIT for {cache_key} (age={duck.age_seconds:.1f}s)")
            self._memory_put(cache_key, duck)
            return self._attach_meta(duck.data, hit=True, age=duck.age_seconds, stale=False)

        # 3. Stale cache — return immediately, refresh in background
        stale = mem or duck
        if stale:
            logger.info(f"Cache STALE for {cache_key} (age={stale.age_seconds:.1f}s), background refresh")
            # Trigger background refresh without awaiting
            asyncio.create_task(self._refresh(cache_key, ticker, expiries, coordinator))
            return self._attach_meta(
                stale.data, hit=True, age=stale.age_seconds, stale=True,
                stale_reason="max_age_exceeded",
            )

        # 4. Complete miss — must fetch (but with dedup via coordinator)
        logger.info(f"Cache MISS for {cache_key}, fetching via coordinator")
        try:
            data = await coordinator.fetch(ticker, expiries, self._live_fetcher)
            entry = CacheEntry(
                ticker=ticker, expiries=expiries, data=data,
                cached_at=time.monotonic(), raw_contracts=data.get("contracts", []),
            )
            self._memory_put(cache_key, entry)
            await self._duckdb_put(cache_key, entry)
            return self._attach_meta(data, hit=False, age=0.0, stale=False)
        except Exception as e:
            logger.warning(f"External fetch failed for {ticker}: {e}")
            return self.degraded_response("external_api_error", str(e))

    def degraded_response(self, reason: str, detail: str, retry_after: int = 15) -> Dict[str, Any]:
        """Return a structured degradation payload.

        HTTP status is always 200 — the UI reads `status: "degraded"` to
        show a stale/rate-limited badge instead of crashing.
        """
        return {
            "data": None,
            "status": "degraded",
            "reason": reason,
            "detail": detail,
            "retry_after": retry_after,
            "stale": True,
            "asof": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Internal — memory cache (LRU)
    # ------------------------------------------------------------------

    def _memory_get(self, key str) -> Optional[CacheEntry]:
        for item in self._memory:
            if item.ticker == ticker and item.expiries == expiries:
                return item
        return None

    def _memory_put(self, key: str, entry: CacheEntry) -> None:
        # Remove existing
        self._memory = [e for e in self._memory if not (
            e.ticker == entry.ticker and e.expiries == entry.expiries
        )]
        self._memory.append(entry)
        # Evict oldest if over limit
        if len(self._memory) > self._max_memory:
            self._memory = self._memory[-self._max_memory:]

    # ------------------------------------------------------------------
    # Internal — DuckDB cache
    # ------------------------------------------------------------------

    async def _ensure_duckdb(self) -> None:
        if self._duckdb_initialized:
            return
        try:
            from services.duckdb_engine import db
            db._conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} (
                    key         VARCHAR PRIMARY KEY,
                    ticker      VARCHAR,
                    expiries    INTEGER,
                    ts          TIMESTAMP,
                     JSON,
                    contracts   JSON,
                    written_at  DOUBLE
                )
            """)
            self._conn = db._conn
            self._duckdb_initialized = True
        except Exception as e:
            logger.warning(f"DuckDB cache table init failed (non-fatal): {e}")

    async def _duckdb_get(self, key: str) -> Optional[CacheEntry]:
        await self._ensure_duckdb()
        if not self._duckdb_initialized:
            return None
        try:
            import json
            result = self._conn.execute(
                f"SELECT ts, data, contracts, written_at FROM {_CACHE_TABLE} WHERE key = ?",
                [key],
            ).fetchone()
            if result:
                ts, data_json, contracts_json, written_at = result
                data = json.loads(data_json)
                data["contracts"] = json.loads(contracts_json)
                return CacheEntry(
                    ticker=key.split(":")[0],
                    expiries=int(key.split(":")[1]),
                    data=data,
                    cached_at=written_at,
                    raw_contracts=data.get("contracts", []),
                )
        except Exception as e:
            logger.debug(f"DuckDB cache read error: {e}")
        return None

    async def _duckdb_put(self, key: str, entry: CacheEntry) -> None:
        await self._ensure_duckdb()
        if not self._duckdb_initialized:
            return
        try:
            import json
            contracts_json = json.dumps(entry.data.get("contracts", []))
            data_copy = {k: v for k, v in entry.data.items() if k != "contracts"}
            data_json = json.dumps(data_copy, default=str)
            ts = datetime.now(timezone.utc)
            self._conn.execute(
                f"""INSERT OR REPLACE INTO {_CACHE_TABLE} (key, ticker, expiries, ts, data, contracts, written_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [key, entry.ticker, entry.expiries, ts, data_json, contracts_json, entry.cached_at],
            )
        except Exception as e:
            logger.warning(f"DuckDB cache write error: {e}")

    # ------------------------------------------------------------------
    # Internal — background refresh
    # ------------------------------------------------------------------

    async def _refresh(
        self, key: str, ticker: str, expiries: int, coordinator: "FetchCoordinator",
    ) -> None:
        try:
            data = await coordinator.fetch(ticker, expiries, self._live_fetcher)
            entry = CacheEntry(
                ticker=ticker, expiries=expiries, data=data,
                cached_at=time.monotonic(), raw_contracts=data.get("contracts", []),
            )
            self._memory_put(key, entry)
            await self._duckdb_put(key, entry)
            logger.info(f"Background refresh complete for {key}")
        except Exception as e:
            logger.warning(f"Background refresh failed for {key}: {e}")

    @staticmethod
    async def _live_fetcher(ticker: str, expiries: int) -> Dict[str, Any]:
        """Actual external fetch — called by coordinator."""
        from server import fetch_spot_and_chains_merged
        return await fetch_spot_and_chains_merged(ticker, expiries)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _attach_meta(
        data: Dict[str, Any],
        hit: bool,
        age: float,
        stale: bool,
        stale_reason: str = "",
    ) -> Dict[str, Any]:
        """Attach cache metadata to response."""
        result = dict(data)
        result["_cache"] = {
            "hit": hit,
            "age_seconds": round(age, 1),
            "stale": stale,
        }
        if stale_reason:
            result["_cache"]["stale_reason"] = stale_reason
        return result


def _make_key(ticker: str, expiries: int) -> str:
    return f"{ticker.upper()}:{expiries}"
