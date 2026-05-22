"""
backend/services/graph_trade_service.py

Trade Outcome Nodes for the knowledge graph.

Extends the DuckDB-backed knowledge graph with:
  - Trade nodes (executed trades: paper or live)
  - Signal nodes (VPIN, QI, etc. that triggered trades)
  - MarketCondition nodes (regime, volatility at execution time)
  - Edges: Trade -[:TRIGGERED_BY]-> Signal
           Trade -[:EXECUTED_IN]-> MarketCondition
           Trade -[:FOR_SYMBOL]-> Symbol

Schema additions:
  nodes: trades, signals, market_conditions, symbols
  edges: trade_triggered_by, trade_executed_in, trade_for_symbol,
         signal_based_on, condition_regime
"""

from __future__ import annotations  # noqa: F821

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("graph_trade_service")

# SQL for new tables
TRADE_SCHEMA_SQL = """
-- Trade nodes
CREATE TABLE IF NOT EXISTS trades (
    id VARCHAR PRIMARY KEY,
    symbol VARCHAR,
    side VARCHAR,           -- 'BUY' or 'SELL'
    quantity INTEGER,
    entry_price DOUBLE,
    exit_price DOUBLE,
    pnl DOUBLE,
    pnl_pct DOUBLE,
    trade_type VARCHAR,     -- 'paper' or 'live'
    entry_time VARCHAR,
    exit_time VARCHAR,
    holding_period_bars INTEGER DEFAULT 0,
    strategy VARCHAR,
    metadata JSON
);

-- Signal nodes
CREATE TABLE IF NOT EXISTS signals (
    id VARCHAR PRIMARY KEY,
    signal_type VARCHAR,    -- 'VPIN', 'QI', 'GEX', 'CORR', 'COMPOSITE'
    value DOUBLE,
    z_score DOUBLE,
    threshold DOUBLE,
    direction VARCHAR,      -- 'BUY', 'SELL', 'HOLD'
    timestamp VARCHAR,
    metadata JSON
);

-- Market condition nodes
CREATE TABLE IF NOT EXISTS market_conditions (
    id VARCHAR PRIMARY KEY,
    regime VARCHAR,         -- 'low_vol', 'high_vol', 'trending', 'mean_reverting', 'crisis'
    volatility DOUBLE,      -- realized vol or VIX
    vpin_cdf DOUBLE,
    correlation_zscore DOUBLE,
    timestamp VARCHAR,
    metadata JSON
);

-- Symbol nodes
CREATE TABLE IF NOT EXISTS symbols (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    asset_class VARCHAR,    -- 'equity', 'option', 'future', 'crypto'
    metadata JSON
);

-- Edges
CREATE TABLE IF NOT EXISTS trade_triggered_by (
    trade_id VARCHAR,
    signal_id VARCHAR,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (trade_id, signal_id)
);

CREATE TABLE IF NOT EXISTS trade_executed_in (
    trade_id VARCHAR,
    condition_id VARCHAR,
    PRIMARY KEY (trade_id, condition_id)
);

CREATE TABLE IF NOT EXISTS trade_for_symbol (
    trade_id VARCHAR,
    symbol_id VARCHAR,
    PRIMARY KEY (trade_id, symbol_id)
);

CREATE TABLE IF NOT EXISTS signal_based_on (
    signal_id VARCHAR,
    symbol_id VARCHAR,
    PRIMARY KEY (signal_id, symbol_id)
);

CREATE TABLE IF NOT EXISTS condition_for_symbol (
    condition_id VARCHAR,
    symbol_id VARCHAR,
    PRIMARY KEY (condition_id, symbol_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades(pnl);
CREATE INDEX IF NOT EXISTS idx_trades_type ON trades(trade_type);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_direction ON signals(direction);
CREATE INDEX IF NOT EXISTS idx_market_conditions_regime ON market_conditions(regime);
"""


class GraphTradeService:
    """Manages trade outcome nodes in the knowledge graph."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(
                Path(__file__).resolve().parents[2]
                / "data"
                / "research_kg.duckdb"
            )
        self.db_path = db_path
        import duckdb
        self.conn = duckdb.connect(db_path)
        self._duckdb = duckdb

    def ensure_schema(self) -> None:
        """Create trade-related tables if they don't exist."""
        self.conn.execute(TRADE_SCHEMA_SQL)
        logger.info("Trade graph schema ensured at %s", self.db_path)

    def close(self) -> None:
        self.conn.close()

    # ── Trade CRUD ─────────────────────────────────────────────────────

    def upsert_trade(self, trade: Dict[str, Any]) -> None:
        """Insert or update a trade node."""
        metadata = {
            k: v for k, v in trade.items()
            if k not in (
                "id", "symbol", "side", "quantity", "entry_price",
                "exit_price", "pnl", "pnl_pct", "trade_type",
                "entry_time", "exit_time", "holding_period_bars", "strategy"
            )
        }
        self.conn.execute("""
            INSERT INTO trades (
                id, symbol, side, quantity, entry_price, exit_price,
                pnl, pnl_pct, trade_type, entry_time, exit_time,
                holding_period_bars, strategy, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                exit_price = excluded.exit_price,
                pnl = excluded.pnl,
                pnl_pct = excluded.pnl_pct,
                exit_time = excluded.exit_time,
                holding_period_bars = excluded.holding_period_bars,
                metadata = excluded.metadata
        """, [
            trade["id"], trade.get("symbol"), trade.get("side"),
            trade.get("quantity", 0), trade.get("entry_price", 0.0),
            trade.get("exit_price", 0.0), trade.get("pnl", 0.0),
            trade.get("pnl_pct", 0.0), trade.get("trade_type", "paper"),
            trade.get("entry_time"), trade.get("exit_time"),
            trade.get("holding_period_bars", 0),
            trade.get("strategy", ""), json.dumps(metadata),
        ])

    def upsert_trades_batch(self, trades: List[Dict[str, Any]]) -> int:
        """Batch insert trades. Returns count."""
        for t in trades:
            self.upsert_trade(t)
        return len(trades)

    def get_trade(self, trade_id: str) -> Optional[Dict]:
        """Get a single trade by ID."""
        row = self.conn.execute(
            "SELECT * FROM trades WHERE id = ?", [trade_id]
        ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self.conn.description]
        return dict(zip(cols, row))

    def get_trades_by_symbol(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get all trades for a symbol."""
        rows = self.conn.execute("""
            SELECT * FROM trades WHERE symbol = ?
            ORDER BY entry_time DESC LIMIT ?
        """, [symbol, limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_trades_by_pnl(self, min_pnl: float = None, max_pnl: float = None,
                          limit: int = 50) -> List[Dict]:
        """Get trades filtered by P&L range."""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        if min_pnl is not None:
            query += " AND pnl >= ?"
            params.append(min_pnl)
        if max_pnl is not None:
            query += " AND pnl <= ?"
            params.append(max_pnl)
        query += " ORDER BY pnl DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_trade_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]

    def get_profitable_trades(self, limit: int = 50) -> List[Dict]:
        return self.get_trades_by_pnl(min_pnl=0.01, limit=limit)

    def get_losing_trades(self, limit: int = 50) -> List[Dict]:
        return self.get_trades_by_pnl(max_pnl=-0.01, limit=limit)

    # ── Signal CRUD ────────────────────────────────────────────────────

    def upsert_signal(self, signal: Dict[str, Any]) -> None:
        """Insert or update a signal node."""
        metadata = {
            k: v for k, v in signal.items()
            if k not in ("id", "signal_type", "value", "z_score",
                         "threshold", "direction", "timestamp")
        }
        self.conn.execute("""
            INSERT INTO signals (
                id, signal_type, value, z_score, threshold,
                direction, timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                value = excluded.value,
                z_score = excluded.z_score,
                direction = excluded.direction,
                metadata = excluded.metadata
        """, [
            signal["id"], signal.get("signal_type"),
            signal.get("value", 0.0), signal.get("z_score", 0.0),
            signal.get("threshold", 0.0), signal.get("direction", "HOLD"),
            signal.get("timestamp"), json.dumps(metadata),
        ])

    def upsert_signals_batch(self, signals: List[Dict[str, Any]]) -> int:
        for s in signals:
            self.upsert_signal(s)
        return len(signals)

    def get_signals_by_type(self, signal_type: str, limit: int = 50) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT * FROM signals WHERE signal_type = ?
            ORDER BY timestamp DESC LIMIT ?
        """, [signal_type, limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_signal_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    # ── Market Condition CRUD ──────────────────────────────────────────

    def upsert_market_condition(self, condition: Dict[str, Any]) -> None:
        metadata = {
            k: v for k, v in condition.items()
            if k not in ("id", "regime", "volatility", "vpin_cdf",
                         "correlation_zscore", "timestamp")
        }
        self.conn.execute("""
            INSERT INTO market_conditions (
                id, regime, volatility, vpin_cdf,
                correlation_zscore, timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                regime = excluded.regime,
                volatility = excluded.volatility,
                vpin_cdf = excluded.vpin_cdf,
                metadata = excluded.metadata
        """, [
            condition["id"], condition.get("regime", ""),
            condition.get("volatility", 0.0),
            condition.get("vpin_cdf", 0.0),
            condition.get("correlation_zscore", 0.0),
            condition.get("timestamp"), json.dumps(metadata),
        ])

    def get_market_conditions_by_regime(self, regime: str,
                                         limit: int = 50) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT * FROM market_conditions WHERE regime = ?
            ORDER BY timestamp DESC LIMIT ?
        """, [regime, limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_market_condition_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM market_conditions"
        ).fetchone()[0]

    # ── Symbol CRUD ────────────────────────────────────────────────────

    def upsert_symbol(self, symbol: Dict[str, Any]) -> None:
        metadata = {
            k: v for k, v in symbol.items()
            if k not in ("id", "name", "asset_class")
        }
        self.conn.execute("""
            INSERT INTO symbols (id, name, asset_class, metadata)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                asset_class = excluded.asset_class,
                metadata = excluded.metadata
        """, [
            symbol["id"], symbol.get("name", ""),
            symbol.get("asset_class", "equity"), json.dumps(metadata),
        ])

    # ── Edge operations ────────────────────────────────────────────────

    def add_trade_signal_edge(self, trade_id: str, signal_id: str,
                               confidence: float = 1.0) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO trade_triggered_by (trade_id, signal_id, confidence)
            VALUES (?, ?, ?)
        """, [trade_id, signal_id, confidence])

    def add_trade_condition_edge(self, trade_id: str, condition_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO trade_executed_in (trade_id, condition_id)
            VALUES (?, ?)
        """, [trade_id, condition_id])

    def add_trade_symbol_edge(self, trade_id: str, symbol_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO trade_for_symbol (trade_id, symbol_id)
            VALUES (?, ?)
        """, [trade_id, symbol_id])

    def add_signal_symbol_edge(self, signal_id: str, symbol_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO signal_based_on (signal_id, symbol_id)
            VALUES (?, ?)
        """, [signal_id, symbol_id])

    def add_condition_symbol_edge(self, condition_id: str, symbol_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO condition_for_symbol (condition_id, symbol_id)
            VALUES (?, ?)
        """, [condition_id, symbol_id])

    # ── Graph queries ──────────────────────────────────────────────────

    def get_trades_with_signals(self, limit: int = 50) -> List[Dict]:
        """MATCH (t:Trade)-[:TRIGGERED_BY]->(s:Signal) RETURN t, s."""
        rows = self.conn.execute("""
            SELECT t.id as trade_id, t.symbol, t.side, t.pnl, t.pnl_pct,
                   t.trade_type, t.strategy,
                   s.id as signal_id, s.signal_type, s.value, s.z_score,
                   s.direction, s.threshold
            FROM trades t
            JOIN trade_triggered_by ttb ON t.id = ttb.trade_id
            JOIN signals s ON ttb.signal_id = s.id
            ORDER BY t.entry_time DESC
            LIMIT ?
        """, [limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_trades_with_conditions(self, limit: int = 50) -> List[Dict]:
        """MATCH (t:Trade)-[:EXECUTED_IN]->(mc) RETURN t, mc."""
        rows = self.conn.execute("""
            SELECT t.id as trade_id, t.symbol, t.side, t.pnl,
                   mc.regime, mc.volatility, mc.vpin_cdf
            FROM trades t
            JOIN trade_executed_in tei ON t.id = tei.trade_id
            JOIN market_conditions mc ON tei.condition_id = mc.id
            ORDER BY t.entry_time DESC
            LIMIT ?
        """, [limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_full_trade_context(self, trade_id: str) -> Dict:
        """Get trade + all connected signals, conditions, symbols."""
        trade = self.get_trade(trade_id)
        if not trade:
            return {}

        signals = self.conn.execute("""
            SELECT s.* FROM signals s
            JOIN trade_triggered_by ttb ON s.id = ttb.signal_id
            WHERE ttb.trade_id = ?
        """, [trade_id]).fetchall()
        signal_cols = [d[0] for d in self.conn.description]
        signals = [dict(zip(signal_cols, r)) for r in signals]

        conditions = self.conn.execute("""
            SELECT mc.* FROM market_conditions mc
            JOIN trade_executed_in tei ON mc.id = tei.condition_id
            WHERE tei.trade_id = ?
        """, [trade_id]).fetchall()
        cond_cols = [d[0] for d in self.conn.description]
        conditions = [dict(zip(cond_cols, r)) for r in conditions]

        return {
            "trade": trade,
            "signals": signals,
            "market_conditions": conditions,
        }

    def get_trade_stats(self) -> Dict[str, Any]:
        """Aggregate trade statistics."""
        total = self.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        profitable = self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE pnl > 0"
        ).fetchone()[0]
        losing = self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE pnl < 0"
        ).fetchone()[0]
        breakeven = self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE pnl = 0"
        ).fetchone()[0]
        avg_pnl = self.conn.execute(
            "SELECT AVG(pnl) FROM trades"
        ).fetchone()[0]
        max_pnl = self.conn.execute(
            "SELECT MAX(pnl) FROM trades"
        ).fetchone()[0]
        min_pnl = self.conn.execute(
            "SELECT MIN(pnl) FROM trades"
        ).fetchone()[0]
        total_pnl = self.conn.execute(
            "SELECT SUM(pnl) FROM trades"
        ).fetchone()[0]

        win_rate = profitable / total if total > 0 else 0.0

        return {
            "total_trades": total,
            "profitable": profitable,
            "losing": losing,
            "breakeven": breakeven,
            "win_rate": round(win_rate, 4),
            "avg_pnl": round(avg_pnl or 0, 2),
            "max_pnl": round(max_pnl or 0, 2),
            "min_pnl": round(min_pnl or 0, 2),
            "total_pnl": round(total_pnl or 0, 2),
        }

    def get_graph_stats(self) -> Dict[str, int]:
        """Return node/edge counts for the trade subgraph."""
        return {
            "trades": self.get_trade_count(),
            "signals": self.get_signal_count(),
            "market_conditions": self.get_market_condition_count(),
            "symbols": self.conn.execute(
                "SELECT COUNT(*) FROM symbols"
            ).fetchone()[0],
            "trade_signal_edges": self.conn.execute(
                "SELECT COUNT(*) FROM trade_triggered_by"
            ).fetchone()[0],
            "trade_condition_edges": self.conn.execute(
                "SELECT COUNT(*) FROM trade_executed_in"
            ).fetchone()[0],
            "trade_symbol_edges": self.conn.execute(
                "SELECT COUNT(*) FROM trade_for_symbol"
            ).fetchone()[0],
        }
