"""
backend/services/graph_trade_service.py

Trade Outcome Nodes for the knowledge graph.

Extends the DuckDB-backed knowledge graph with:
  - Trade nodes (executed trades: paper or live)
  - Signal nodes (VPIN, QI, etc. that triggered trades)
  - MarketCondition nodes (regime, volatility at execution time)
  - RetailFlowScore nodes (retail flow metrics: sweep ratio, block ratio,
    premium concentration, small-lot activity)
  - PriceMovement nodes (price changes linked to flow events)
  - Edges: Trade -[:TRIGGERED_BY]-> Signal
           Trade -[:EXECUTED_IN]-> MarketCondition
           Trade -[:FOR_SYMBOL]-> Symbol
           RetailFlowScore -[:FOR_SYMBOL]-> Symbol
           RetailFlowScore -[:INFLUENCED]-> PriceMovement
           Trade -[:INFLUENCED_BY_RETAIL]-> RetailFlowScore

Schema additions:
  nodes: trades, signals, market_conditions, symbols, retail_flow_scores,
         price_movements
  edges: trade_triggered_by, trade_executed_in, trade_for_symbol,
         signal_based_on, condition_for_symbol, retail_flow_for_symbol,
         retail_flow_influenced_movement, trade_influenced_by_retail
"""

from __future__ import annotations  # noqa: F821

import json
import logging
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

-- Retail Flow Score nodes
CREATE TABLE IF NOT EXISTS retail_flow_scores (
    id VARCHAR PRIMARY KEY,
    symbol VARCHAR,
    timestamp VARCHAR,
    sweep_ratio DOUBLE,          -- fraction of volume from sweeps
    block_ratio DOUBLE,          -- fraction of volume from blocks
    small_lot_ratio DOUBLE,      -- fraction of volume from small lots (<10 contracts)
    premium_concentration DOUBLE, -- Herfindahl index of premium across strikes
    call_put_ratio DOUBLE,       -- call volume / put volume
    total_volume DOUBLE,
    total_premium DOUBLE,
    trade_count INTEGER,
    avg_trade_size DOUBLE,
    retail_flow_score DOUBLE,    -- composite score [-1, 1]
    metadata JSON
);

-- Price Movement nodes
CREATE TABLE IF NOT EXISTS price_movements (
    id VARCHAR PRIMARY KEY,
    symbol VARCHAR,
    timestamp VARCHAR,
    start_price DOUBLE,
    end_price DOUBLE,
    price_change DOUBLE,
    price_change_pct DOUBLE,
    direction VARCHAR,           -- 'UP', 'DOWN', 'FLAT'
    timeframe VARCHAR,           -- '1m', '5m', '15m', '1h', '1d'
    volume DOUBLE,
    metadata JSON
);

-- Retail flow edges
CREATE TABLE IF NOT EXISTS retail_flow_for_symbol (
    flow_id VARCHAR,
    symbol_id VARCHAR,
    PRIMARY KEY (flow_id, symbol_id)
);

CREATE TABLE IF NOT EXISTS retail_flow_influenced_movement (
    flow_id VARCHAR,
    movement_id VARCHAR,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (flow_id, movement_id)
);

CREATE TABLE IF NOT EXISTS trade_influenced_by_retail (
    trade_id VARCHAR,
    flow_id VARCHAR,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (trade_id, flow_id)
);

-- Retail flow indexes
CREATE INDEX IF NOT EXISTS idx_retail_flow_symbol ON retail_flow_scores(symbol);
CREATE INDEX IF NOT EXISTS idx_retail_flow_score ON retail_flow_scores(retail_flow_score);
CREATE INDEX IF NOT EXISTS idx_retail_flow_timestamp ON retail_flow_scores(timestamp);
CREATE INDEX IF NOT EXISTS idx_price_movements_symbol ON price_movements(symbol);
CREATE INDEX IF NOT EXISTS idx_price_movements_timestamp ON price_movements(timestamp);
CREATE INDEX IF NOT EXISTS idx_price_movements_direction ON price_movements(direction);
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

    # ── Retail Flow Score CRUD ─────────────────────────────────────────

    def upsert_retail_flow_score(self, flow: Dict[str, Any]) -> None:
        """Insert or update a retail flow score node."""
        metadata = {
            k: v for k, v in flow.items()
            if k not in (
                "id", "symbol", "timestamp", "sweep_ratio", "block_ratio",
                "small_lot_ratio", "premium_concentration", "call_put_ratio",
                "total_volume", "total_premium", "trade_count",
                "avg_trade_size", "retail_flow_score"
            )
        }
        self.conn.execute("""
            INSERT INTO retail_flow_scores (
                id, symbol, timestamp, sweep_ratio, block_ratio,
                small_lot_ratio, premium_concentration, call_put_ratio,
                total_volume, total_premium, trade_count,
                avg_trade_size, retail_flow_score, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                sweep_ratio = excluded.sweep_ratio,
                block_ratio = excluded.block_ratio,
                small_lot_ratio = excluded.small_lot_ratio,
                premium_concentration = excluded.premium_concentration,
                call_put_ratio = excluded.call_put_ratio,
                total_volume = excluded.total_volume,
                total_premium = excluded.total_premium,
                trade_count = excluded.trade_count,
                avg_trade_size = excluded.avg_trade_size,
                retail_flow_score = excluded.retail_flow_score,
                metadata = excluded.metadata
        """, [
            flow["id"], flow.get("symbol"),
            flow.get("timestamp"), flow.get("sweep_ratio", 0.0),
            flow.get("block_ratio", 0.0), flow.get("small_lot_ratio", 0.0),
            flow.get("premium_concentration", 0.0),
            flow.get("call_put_ratio", 1.0),
            flow.get("total_volume", 0.0), flow.get("total_premium", 0.0),
            flow.get("trade_count", 0), flow.get("avg_trade_size", 0.0),
            flow.get("retail_flow_score", 0.0), json.dumps(metadata),
        ])

    def upsert_retail_flow_scores_batch(self, flows: List[Dict[str, Any]]) -> int:
        for f in flows:
            self.upsert_retail_flow_score(f)
        return len(flows)

    def get_retail_flow_scores_by_symbol(self, symbol: str,
                                          limit: int = 50) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT * FROM retail_flow_scores WHERE symbol = ?
            ORDER BY timestamp DESC LIMIT ?
        """, [symbol, limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_retail_flow_scores_by_score(self, min_score: float = None,
                                         max_score: float = None,
                                         limit: int = 50) -> List[Dict]:
        query = "SELECT * FROM retail_flow_scores WHERE 1=1"
        params = []
        if min_score is not None:
            query += " AND retail_flow_score >= ?"
            params.append(min_score)
        if max_score is not None:
            query += " AND retail_flow_score <= ?"
            params.append(max_score)
        query += " ORDER BY retail_flow_score DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_retail_flow_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM retail_flow_scores"
        ).fetchone()[0]

    # ── Price Movement CRUD ────────────────────────────────────────────

    def upsert_price_movement(self, movement: Dict[str, Any]) -> None:
        """Insert or update a price movement node."""
        metadata = {
            k: v for k, v in movement.items()
            if k not in (
                "id", "symbol", "timestamp", "start_price", "end_price",
                "price_change", "price_change_pct", "direction",
                "timeframe", "volume"
            )
        }
        self.conn.execute("""
            INSERT INTO price_movements (
                id, symbol, timestamp, start_price, end_price,
                price_change, price_change_pct, direction,
                timeframe, volume, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                end_price = excluded.end_price,
                price_change = excluded.price_change,
                price_change_pct = excluded.price_change_pct,
                direction = excluded.direction,
                metadata = excluded.metadata
        """, [
            movement["id"], movement.get("symbol"),
            movement.get("timestamp"), movement.get("start_price", 0.0),
            movement.get("end_price", 0.0), movement.get("price_change", 0.0),
            movement.get("price_change_pct", 0.0),
            movement.get("direction", "FLAT"),
            movement.get("timeframe", "5m"),
            movement.get("volume", 0.0), json.dumps(metadata),
        ])

    def upsert_price_movements_batch(self, movements: List[Dict[str, Any]]) -> int:
        for m in movements:
            self.upsert_price_movement(m)
        return len(movements)

    def get_price_movements_by_symbol(self, symbol: str,
                                       direction: str = None,
                                       limit: int = 50) -> List[Dict]:
        query = "SELECT * FROM price_movements WHERE symbol = ?"
        params = [symbol]
        if direction:
            query += " AND direction = ?"
            params.append(direction)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_price_movement_count(self) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM price_movements"
        ).fetchone()[0]

    # ── Retail Flow Edge operations ────────────────────────────────────

    def add_retail_flow_symbol_edge(self, flow_id: str, symbol_id: str) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO retail_flow_for_symbol (flow_id, symbol_id)
            VALUES (?, ?)
        """, [flow_id, symbol_id])

    def add_retail_flow_movement_edge(self, flow_id: str, movement_id: str,
                                       confidence: float = 1.0) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO retail_flow_influenced_movement
            (flow_id, movement_id, confidence)
            VALUES (?, ?, ?)
        """, [flow_id, movement_id, confidence])

    def add_trade_retail_flow_edge(self, trade_id: str, flow_id: str,
                                    confidence: float = 1.0) -> None:
        self.conn.execute("""
            INSERT OR IGNORE INTO trade_influenced_by_retail
            (trade_id, flow_id, confidence)
            VALUES (?, ?, ?)
        """, [trade_id, flow_id, confidence])

    # ── Graph queries for retail flow ──────────────────────────────────

    def get_retail_flow_with_movements(self, limit: int = 50) -> List[Dict]:
        """MATCH (rfs:RetailFlowScore)-[:INFLUCED]->(pm:PriceMovement)."""
        rows = self.conn.execute("""
            SELECT rfs.id as flow_id, rfs.symbol, rfs.retail_flow_score,
                   rfs.sweep_ratio, rfs.block_ratio, rfs.call_put_ratio,
                   pm.id as movement_id, pm.price_change, pm.price_change_pct,
                   pm.direction, pm.timeframe,
                   rfim.confidence
            FROM retail_flow_scores rfs
            JOIN retail_flow_influenced_movement rfim ON rfs.id = rfim.flow_id
            JOIN price_movements pm ON rfim.movement_id = pm.id
            ORDER BY rfs.timestamp DESC
            LIMIT ?
        """, [limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_trades_with_retail_flow(self, limit: int = 50) -> List[Dict]:
        """MATCH (t:Trade)-[:INFLUENCED_BY_RETAIL]->(rfs:RetailFlowScore)."""
        rows = self.conn.execute("""
            SELECT t.id as trade_id, t.symbol, t.side, t.pnl, t.pnl_pct,
                   t.strategy,
                   rfs.id as flow_id, rfs.retail_flow_score,
                   rfs.sweep_ratio, rfs.block_ratio, rfs.call_put_ratio,
                   tib.confidence
            FROM trades t
            JOIN trade_influenced_by_retail tib ON t.id = tib.trade_id
            JOIN retail_flow_scores rfs ON tib.flow_id = rfs.id
            ORDER BY t.entry_time DESC
            LIMIT ?
        """, [limit]).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def get_full_retail_flow_context(self, flow_id: str) -> Dict:
        """Get retail flow score + connected symbol, movements, trades."""
        flow = self.conn.execute(
            "SELECT * FROM retail_flow_scores WHERE id = ?", [flow_id]
        ).fetchone()
        if not flow:
            return {}
        cols = [d[0] for d in self.conn.description]
        flow_dict = dict(zip(cols, flow))

        movements = self.conn.execute("""
            SELECT pm.*, rfim.confidence
            FROM price_movements pm
            JOIN retail_flow_influenced_movement rfim ON pm.id = rfim.movement_id
            WHERE rfim.flow_id = ?
        """, [flow_id]).fetchall()
        mov_cols = [d[0] for d in self.conn.description]
        movements = [dict(zip(mov_cols, r)) for r in movements]

        trades = self.conn.execute("""
            SELECT t.*, tib.confidence
            FROM trades t
            JOIN trade_influenced_by_retail tib ON t.id = tib.trade_id
            WHERE tib.flow_id = ?
        """, [flow_id]).fetchall()
        trade_cols = [d[0] for d in self.conn.description]
        trades = [dict(zip(trade_cols, r)) for r in trades]

        return {
            "retail_flow": flow_dict,
            "price_movements": movements,
            "trades": trades,
        }

    def get_retail_flow_stats(self) -> Dict[str, Any]:
        """Aggregate retail flow statistics."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM retail_flow_scores"
        ).fetchone()[0]
        avg_score = self.conn.execute(
            "SELECT AVG(retail_flow_score) FROM retail_flow_scores"
        ).fetchone()[0]
        avg_sweep = self.conn.execute(
            "SELECT AVG(sweep_ratio) FROM retail_flow_scores"
        ).fetchone()[0]
        avg_block = self.conn.execute(
            "SELECT AVG(block_ratio) FROM retail_flow_scores"
        ).fetchone()[0]
        avg_cpr = self.conn.execute(
            "SELECT AVG(call_put_ratio) FROM retail_flow_scores"
        ).fetchone()[0]
        bullish = self.conn.execute(
            "SELECT COUNT(*) FROM retail_flow_scores WHERE retail_flow_score > 0.2"
        ).fetchone()[0]
        bearish = self.conn.execute(
            "SELECT COUNT(*) FROM retail_flow_scores WHERE retail_flow_score < -0.2"
        ).fetchone()[0]
        neutral = self.conn.execute(
            "SELECT COUNT(*) FROM retail_flow_scores WHERE retail_flow_score BETWEEN -0.2 AND 0.2"
        ).fetchone()[0]

        return {
            "total_flow_scores": total,
            "avg_retail_flow_score": round(avg_score or 0, 4),
            "avg_sweep_ratio": round(avg_sweep or 0, 4),
            "avg_block_ratio": round(avg_block or 0, 4),
            "avg_call_put_ratio": round(avg_cpr or 0, 4),
            "bullish_count": bullish,
            "bearish_count": bearish,
            "neutral_count": neutral,
        }

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
            "retail_flow_scores": self.get_retail_flow_count(),
            "price_movements": self.get_price_movement_count(),
            "retail_flow_symbol_edges": self.conn.execute(
                "SELECT COUNT(*) FROM retail_flow_for_symbol"
            ).fetchone()[0],
            "retail_flow_movement_edges": self.conn.execute(
                "SELECT COUNT(*) FROM retail_flow_influenced_movement"
            ).fetchone()[0],
            "trade_retail_flow_edges": self.conn.execute(
                "SELECT COUNT(*) FROM trade_influenced_by_retail"
            ).fetchone()[0],
        }
