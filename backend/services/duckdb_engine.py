"""
backend/services/duckdb_engine.py

DuckDB OLAP engine for real-time options analytics.
In-memory instance with async batch writer for tick/LOB data.

Schema:
  ticks:       (timestamp, symbol, bid, ask, last, volume, oi, delta, gamma, theta, vega, data_source, delay_seconds)
  chains:      (timestamp, symbol, ticker, strike, expiry, type, bid, ask, last, volume, open_interest, iv, delta, gamma, theta, vega, data_source, delay_seconds)
  lob_snapshots: (timestamp, symbol, bid_size, ask_size, bid_price, ask_price, level)
  flow_prints:   (timestamp, ticker, strike, expiration, side, type, size, price,
                  premium, volume, oi, exchange, classification)
  vpin_buckets:  (timestamp, bucket_id, total_volume, buy_volume, sell_volume, vpin_value)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

import duckdb
import numpy as np

import services.observability as obs_metrics

logger = logging.getLogger(__name__)


class DuckDBEngine:
    """Thread-safe DuckDB wrapper with async batch writer."""

    def __init__(self, db_path: str = ":memory:"):
        self._conn = duckdb.connect(db_path)
        self._lock = asyncio.Lock()
        self._tick_buffer: List[tuple] = []
        self._lob_buffer: List[tuple] = []
        self._flow_buffer: List[tuple] = []
        self._batch_size = 100
        self._flush_interval_ms = 50
        self._running = False
        self._init_schema()

    def _init_schema(self):
        """Create all tables if they don't exist, then apply migrations."""
        self._create_base_tables()
        self._create_chains_table()
        self._apply_delayed_data_migration()
        self._create_indexes()
        logger.info("DuckDB schema initialized with delayed-data support")

    def _create_base_tables(self):
        """Create the original base tables."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                bid          DOUBLE,
                ask          DOUBLE,
                last         DOUBLE,
                volume       BIGINT,
                oi           BIGINT,
                delta_val    DOUBLE,
                gamma_val    DOUBLE,
                theta_val    DOUBLE,
                vega_val     DOUBLE,
                vanna_val    DOUBLE,
                charm_val    DOUBLE,
                vomma_val    DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS lob_snapshots (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                bid_size     BIGINT,
                ask_size     BIGINT,
                bid_price    DOUBLE,
                ask_price    DOUBLE,
                level        INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS lob_depth (
                timestamp    TIMESTAMP,
                symbol       VARCHAR,
                expiry       DATE,
                strike       DOUBLE,
                option_type  VARCHAR(1),
                level        INTEGER,
                bid_size     BIGINT,
                bid_price    DOUBLE,
                ask_size     BIGINT,
                ask_price    DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS flow_prints (
                timestamp       TIMESTAMP,
                ticker          VARCHAR,
                strike          DOUBLE,
                expiration      VARCHAR,
                side            VARCHAR,
                type            VARCHAR,
                size            INTEGER,
                price           DOUBLE,
                premium         DOUBLE,
                volume          BIGINT,
                oi              BIGINT,
                exchange        VARCHAR,
                classification  VARCHAR,
                bid             DOUBLE,
                ask             DOUBLE,
                spot            DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vpin_buckets (
                timestamp    TIMESTAMP,
                bucket_id    INTEGER,
                total_volume DOUBLE,
                buy_volume   DOUBLE,
                sell_volume  DOUBLE,
                vpin_value   DOUBLE,
                qi_zscore    DOUBLE
            )
        """)

    def _create_chains_table(self):
        """Create the chains table for options data with multi-source support."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS chains (
                timestamp     TIMESTAMP,
                symbol        VARCHAR,
                ticker        VARCHAR,
                strike        DOUBLE,
                expiry        DATE,
                type          VARCHAR(4),
                bid           DOUBLE,
                ask           DOUBLE,
                last          DOUBLE,
                volume        BIGINT,
                open_interest BIGINT,
                iv            DOUBLE,
                delta_val     DOUBLE,
                gamma_val     DOUBLE,
                theta_val     DOUBLE,
                vega_val      DOUBLE,
                data_source   VARCHAR DEFAULT 'Yahoo',
                delay_seconds INTEGER DEFAULT 0
            )
        """)

    def _apply_delayed_data_migration(self):
        """Add data_source and delay_seconds columns to existing tables. Safe to call multiple times."""
        for col, typ, default in [("data_source", "VARCHAR", "'Yahoo'"), ("delay_seconds", "INTEGER", "0")]:
            for table in ("ticks", "chains"):
                try:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {typ} DEFAULT {default}"
                    )
                    logger.info(f"Added {col} to {table}")
                except Exception:
                    pass  # Column already exists

    def _create_indexes(self):
        """Create indexes for fast queries."""
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_symbol ON ticks(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_ts ON ticks(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_symbol ON lob_snapshots(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_depth_symbol ON lob_depth(symbol)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_lob_depth_ts ON lob_depth(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_flow_ticker ON flow_prints(ticker)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_ticker ON chains(ticker)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_chains_ts ON chains(timestamp)")

    async def start(self):
        """Start the background batch writer."""
        self._running = True
        asyncio.create_task(self._flush_loop())
        logger.info("DuckDB async writer started")

    async def stop(self):
        """Stop and flush remaining buffers."""
        self._running = False
        await self._flush_all()

    async def insert_tick(self, symbol: str, bid: float, ask: float, last: float,
                          volume: int, oi: int, delta: float, gamma: float,
                          theta: float, vega: float, vanna: float = 0.0,
                          charm: float = 0.0, vomma: float = 0.0):
        """Buffer a tick for batch insert."""
        ts = datetime.now(timezone.utc)
        self._tick_buffer.append((ts, symbol, bid, ask, last, volume, oi,
                                  delta, gamma, theta, vega, vanna, charm, vomma))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        if len(self._tick_buffer) >= self._batch_size:
            await self._flush_ticks()

    async def insert_lob(self, symbol: str, bid_size: int, ask_size: int,
                         bid_price: float, ask_price: float, level: int = 0):
        """Buffer a LOB snapshot for batch insert."""
        ts = datetime.now(timezone.utc)
        self._lob_buffer.append((ts, symbol, bid_size, ask_size, bid_price, ask_price, level))
        if len(self._lob_buffer) >= self._batch_size:
            await self._flush_lob()

    async def insert_flow(self, **kwargs):
        """Buffer a flow print for batch insert."""
        ts = datetime.now(timezone.utc)
        row = (
            ts,
            kwargs.get("ticker", ""),
            kwargs.get("strike", 0.0),
            kwargs.get("expiration", ""),
            kwargs.get("side", ""),
            kwargs.get("type", ""),
            kwargs.get("size", 0),
            kwargs.get("price", 0.0),
            kwargs.get("premium", 0.0),
            kwargs.get("volume", 0),
            kwargs.get("oi", 0),
            kwargs.get("exchange", ""),
            kwargs.get("classification", "regular"),
            kwargs.get("bid", 0.0),
            kwargs.get("ask", 0.0),
            kwargs.get("spot", 0.0),
        )
        self._flow_buffer.append(row)
        if len(self._flow_buffer) >= self._batch_size:
            await self._flush_flow()

    async def _flush_loop(self):
        """Background loop that flushes buffers every 50ms."""
        while self._running:
            await asyncio.sleep(self._flush_interval_ms / 1000.0)
            await self._flush_all()

    async def _flush_all(self):
        """Flush all buffers."""
        await asyncio.gather(
            self._flush_ticks(),
            self._flush_lob(),
            self._flush_flow(),
        )

    async def _flush_ticks(self):
        if not self._tick_buffer:
            return
        async with self._lock:
            buf = self._tick_buffer
            self._tick_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await asyncio.to_thread(
                lambda: self._conn.executemany(
                    """INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    buf,
                )
            )
        except Exception as e:
            logger.error(f"DuckDB tick flush error: {e}")

    async def _flush_lob(self):
        if not self._lob_buffer:
            return
        async with self._lock:
            buf = self._lob_buffer
            self._lob_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await asyncio.to_thread(
                lambda: self._conn.executemany(
                    """INSERT INTO lob_snapshots VALUES (?,?,?,?,?,?,?)""",
                    buf,
                )
            )
        except Exception as e:
            logger.error(f"DuckDB LOB flush error: {e}")

    async def _flush_flow(self):
        if not self._flow_buffer:
            return
        async with self._lock:
            buf = self._flow_buffer
            self._flow_buffer = []
        obs_metrics.duckdb_batch_size.observe(len(buf))
        obs_metrics.duckdb_queue_depth.set(
            len(self._tick_buffer) + len(self._lob_buffer) + len(self._flow_buffer)
        )
        try:
            await asyncio.to_thread(
                lambda: self._conn.executemany(
                    """INSERT INTO flow_prints VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    buf,
                )
            )
        except Exception as e:
            logger.error(f"DuckDB flow flush error: {e}")

    def query(self, sql: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Synchronous query returning list of dicts. Non-blocking wrapper available as query_async."""
        try:
            result = self._conn.execute(sql, params or []).fetchdf()
            return result.replace({np.nan: None}).to_dict("records")
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return []

    async def query_async(self, sql: str, params: Optional[List] = None) -> List[Dict[str, Any]]:
        """Async wrapper for query — runs in thread pool to avoid blocking event loop."""
        return await asyncio.to_thread(self.query, sql, params)

    def query_df(self, sql: str, params: Optional[List] = None):
        """Return result as pandas DataFrame."""
        try:
            return self._conn.execute(sql, params or []).fetchdf()
        except Exception as e:
            logger.error(f"DuckDB query error: {e}")
            return None

    @property
    def conn(self):
        return self._conn


# Global singleton
db = DuckDBEngine()
