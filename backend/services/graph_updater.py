"""
backend/services/graph_updater.py

Continuous graph updates - listens to trade execution events and
automatically updates the Neo4j (DuckDB) graph in real-time.

Usage:
    updater = GraphUpdater()
    updater.on_trade_executed(trade_data)
    updater.on_signal_generated(signal_data)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("graph_updater")


class GraphUpdater:
    """
    Real-time graph updater that listens to trade events and
    automatically updates the knowledge graph.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            # backend/services/graph_updater.py -> repo root = parents[2]
            db_path = str(
                Path(__file__).resolve().parents[2]
                / "data"
                / "research_kg.duckdb"
            )
        self.db_path = db_path
        # Avoid circular import: import here
        from services.graph_trade_service import GraphTradeService
        self.service = GraphTradeService(db_path)
        self.service.ensure_schema()
        self._callbacks: List[Callable] = []
        self._update_count = 0
        self._last_update_time = 0.0

    def close(self):
        self.service.close()

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to be called after each update."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, event_type: str, data: Dict) -> None:
        for cb in self._callbacks:
            try:
                cb(event_type, data)
            except Exception as e:
                logger.warning(f"Callback error: {e}")

    def on_trade_executed(self, trade_data: Dict[str, Any]) -> str:
        """
        Handle a trade execution event.

        Args:
            trade_data: Dict with keys: symbol, side, quantity, fill_price,
                       order_id, strategy, signals (list), conditions (dict)

        Returns:
            trade_id of the created/updated trade node
        """
        start = time.monotonic()

        trade_id = trade_data.get("order_id", f"trade_{uuid.uuid4().hex[:12]}")
        now = datetime.now(timezone.utc).isoformat()

        # Create or update trade node
        trade = {
            "id": trade_id,
            "symbol": trade_data.get("symbol", "UNKNOWN"),
            "side": trade_data.get("side", "BUY"),
            "quantity": trade_data.get("quantity", 0),
            "entry_price": trade_data.get("fill_price", 0.0),
            "exit_price": trade_data.get("exit_price", 0.0),
            "pnl": trade_data.get("pnl", 0.0),
            "pnl_pct": trade_data.get("pnl_pct", 0.0),
            "trade_type": trade_data.get("trade_type", "paper"),
            "entry_time": trade_data.get("entry_time", now),
            "exit_time": trade_data.get("exit_time", ""),
            "holding_period_bars": trade_data.get("holding_period_bars", 0),
            "strategy": trade_data.get("strategy", ""),
        }
        self.service.upsert_trade(trade)

        # Ensure symbol exists
        symbol_id = f"sym_{trade['symbol'].lower()}"
        self.service.upsert_symbol({
            "id": symbol_id,
            "name": trade["symbol"],
            "asset_class": trade_data.get("asset_class", "equity"),
        })
        self.service.add_trade_symbol_edge(trade_id, symbol_id)

        # Process signals
        signals = trade_data.get("signals", [])
        for sig in signals:
            sig_id = sig.get("id", f"sig_{uuid.uuid4().hex[:12]}")
            signal = {
                "id": sig_id,
                "signal_type": sig.get("signal_type", "UNKNOWN"),
                "value": sig.get("value", 0.0),
                "z_score": sig.get("z_score", 0.0),
                "threshold": sig.get("threshold", 0.0),
                "direction": sig.get("direction", "HOLD"),
                "timestamp": sig.get("timestamp", now),
            }
            self.service.upsert_signal(signal)
            self.service.add_trade_signal_edge(trade_id, sig_id, confidence=sig.get("confidence", 1.0))
            self.service.add_signal_symbol_edge(sig_id, symbol_id)

        # Process market conditions
        conditions = trade_data.get("conditions", {})
        if conditions:
            cond_id = conditions.get("id", f"cond_{uuid.uuid4().hex[:12]}")
            condition = {
                "id": cond_id,
                "regime": conditions.get("regime", ""),
                "volatility": conditions.get("volatility", 0.0),
                "vpin_cdf": conditions.get("vpin_cdf", 0.0),
                "correlation_zscore": conditions.get("correlation_zscore", 0.0),
                "timestamp": conditions.get("timestamp", now),
            }
            self.service.upsert_market_condition(condition)
            self.service.add_trade_condition_edge(trade_id, cond_id)
            self.service.add_condition_symbol_edge(cond_id, symbol_id)

        elapsed = time.monotonic() - start
        self._update_count += 1
        self._last_update_time = elapsed

        logger.info(f"Trade {trade_id} updated in {elapsed:.4f}s")
        self._notify_callbacks("trade_executed", {"trade_id": trade_id, "elapsed_s": elapsed})

        return trade_id

    def on_signal_generated(self, signal_data: Dict[str, Any]) -> str:
        """
        Handle a signal generation event.

        Args:
            signal_data: Dict with keys: signal_type, value, z_score, direction, symbol

        Returns:
            signal_id of the created signal node
        """
        start = time.monotonic()

        sig_id = signal_data.get("id", f"sig_{uuid.uuid4().hex[:12]}")
        now = datetime.now(timezone.utc).isoformat()

        signal = {
            "id": sig_id,
            "signal_type": signal_data.get("signal_type", "UNKNOWN"),
            "value": signal_data.get("value", 0.0),
            "z_score": signal_data.get("z_score", 0.0),
            "threshold": signal_data.get("threshold", 0.0),
            "direction": signal_data.get("direction", "HOLD"),
            "timestamp": signal_data.get("timestamp", now),
        }
        self.service.upsert_signal(signal)

        # Link to symbol if provided
        symbol = signal_data.get("symbol")
        if symbol:
            symbol_id = f"sym_{symbol.lower()}"
            self.service.upsert_symbol({
                "id": symbol_id,
                "name": symbol,
                "asset_class": signal_data.get("asset_class", "equity"),
            })
            self.service.add_signal_symbol_edge(sig_id, symbol_id)

        elapsed = time.monotonic() - start
        logger.info(f"Signal {sig_id} updated in {elapsed:.4f}s")
        self._notify_callbacks("signal_generated", {"signal_id": sig_id, "elapsed_s": elapsed})

        return sig_id

    def on_market_condition_update(self, condition_data: Dict[str, Any]) -> str:
        """
        Handle a market condition update event.

        Args:
            condition_data: Dict with keys: regime, volatility, vpin_cdf, symbol

        Returns:
            condition_id
        """
        start = time.monotonic()

        cond_id = condition_data.get("id", f"cond_{uuid.uuid4().hex[:12]}")
        now = datetime.now(timezone.utc).isoformat()

        condition = {
            "id": cond_id,
            "regime": condition_data.get("regime", ""),
            "volatility": condition_data.get("volatility", 0.0),
            "vpin_cdf": condition_data.get("vpin_cdf", 0.0),
            "correlation_zscore": condition_data.get("correlation_zscore", 0.0),
            "timestamp": condition_data.get("timestamp", now),
        }
        self.service.upsert_market_condition(condition)

        symbol = condition_data.get("symbol")
        if symbol:
            symbol_id = f"sym_{symbol.lower()}"
            self.service.upsert_symbol({
                "id": symbol_id,
                "name": symbol,
                "asset_class": condition_data.get("asset_class", "equity"),
            })
            self.service.add_condition_symbol_edge(cond_id, symbol_id)

        elapsed = time.monotonic() - start
        logger.info(f"Condition {cond_id} updated in {elapsed:.4f}s")
        self._notify_callbacks("market_condition", {"condition_id": cond_id, "elapsed_s": elapsed})

        return cond_id

    def on_retail_flow_event(self, flow_data: Dict[str, Any]) -> str:
        """
        Handle a retail flow event.

        Args:
            flow_data: Dict with keys: symbol, timestamp, sweep_ratio,
                       block_ratio, small_lot_ratio, premium_concentration,
                       call_put_ratio, total_volume, total_premium,
                       trade_count, avg_trade_size, retail_flow_score,
                       price_movement (dict), trade_ids (list)

        Returns:
            flow_id
        """
        start = time.monotonic()

        flow_id = flow_data.get("id", f"rfs_{uuid.uuid4().hex[:12]}")
        now = datetime.now(timezone.utc).isoformat()

        flow = {
            "id": flow_id,
            "symbol": flow_data.get("symbol", "UNKNOWN"),
            "timestamp": flow_data.get("timestamp", now),
            "sweep_ratio": flow_data.get("sweep_ratio", 0.0),
            "block_ratio": flow_data.get("block_ratio", 0.0),
            "small_lot_ratio": flow_data.get("small_lot_ratio", 0.0),
            "premium_concentration": flow_data.get("premium_concentration", 0.0),
            "call_put_ratio": flow_data.get("call_put_ratio", 1.0),
            "total_volume": flow_data.get("total_volume", 0.0),
            "total_premium": flow_data.get("total_premium", 0.0),
            "trade_count": flow_data.get("trade_count", 0),
            "avg_trade_size": flow_data.get("avg_trade_size", 0.0),
            "retail_flow_score": flow_data.get("retail_flow_score", 0.0),
        }
        self.service.upsert_retail_flow_score(flow)

        # Ensure symbol exists and link
        symbol = flow_data.get("symbol", "UNKNOWN")
        symbol_id = f"sym_{symbol.lower()}"
        self.service.upsert_symbol({
            "id": symbol_id,
            "name": symbol,
            "asset_class": flow_data.get("asset_class", "equity"),
        })
        self.service.add_retail_flow_symbol_edge(flow_id, symbol_id)

        # Process linked price movement
        price_movement = flow_data.get("price_movement")
        if price_movement:
            mov_id = price_movement.get("id", f"pm_{uuid.uuid4().hex[:12]}")
            movement = {
                "id": mov_id,
                "symbol": symbol,
                "timestamp": price_movement.get("timestamp", now),
                "start_price": price_movement.get("start_price", 0.0),
                "end_price": price_movement.get("end_price", 0.0),
                "price_change": price_movement.get("price_change", 0.0),
                "price_change_pct": price_movement.get("price_change_pct", 0.0),
                "direction": price_movement.get("direction", "FLAT"),
                "timeframe": price_movement.get("timeframe", "5m"),
                "volume": price_movement.get("volume", flow_data.get("total_volume", 0.0)),
            }
            self.service.upsert_price_movement(movement)
            self.service.add_retail_flow_movement_edge(
                flow_id, mov_id,
                confidence=price_movement.get("confidence", 0.9)
            )

        # Link to trades
        trade_ids = flow_data.get("trade_ids", [])
        for trade_id in trade_ids:
            self.service.add_trade_retail_flow_edge(
                trade_id, flow_id,
                confidence=flow_data.get("trade_confidence", 0.7)
            )

        elapsed = time.monotonic() - start
        self._update_count += 1
        self._last_update_time = elapsed

        logger.info(f"Retail flow {flow_id} updated in {elapsed:.4f}s")
        self._notify_callbacks("retail_flow", {
            "flow_id": flow_id, "elapsed_s": elapsed,
            "retail_flow_score": flow["retail_flow_score"]
        })

        return flow_id

    def on_price_movement_event(self, movement_data: Dict[str, Any]) -> str:
        """
        Handle a price movement event.

        Args:
            movement_data: Dict with keys: symbol, timestamp, start_price,
                          end_price, price_change, price_change_pct,
                          direction, timeframe, volume

        Returns:
            movement_id
        """
        start = time.monotonic()

        mov_id = movement_data.get("id", f"pm_{uuid.uuid4().hex[:12]}")
        now = datetime.now(timezone.utc).isoformat()

        movement = {
            "id": mov_id,
            "symbol": movement_data.get("symbol", "UNKNOWN"),
            "timestamp": movement_data.get("timestamp", now),
            "start_price": movement_data.get("start_price", 0.0),
            "end_price": movement_data.get("end_price", 0.0),
            "price_change": movement_data.get("price_change", 0.0),
            "price_change_pct": movement_data.get("price_change_pct", 0.0),
            "direction": movement_data.get("direction", "FLAT"),
            "timeframe": movement_data.get("timeframe", "5m"),
            "volume": movement_data.get("volume", 0.0),
        }
        self.service.upsert_price_movement(movement)

        elapsed = time.monotonic() - start
        logger.info(f"Price movement {mov_id} updated in {elapsed:.4f}s")
        self._notify_callbacks("price_movement", {
            "movement_id": mov_id, "elapsed_s": elapsed
        })

        return mov_id

    def get_update_stats(self) -> Dict[str, Any]:
        """Return update statistics."""
        return {
            "total_updates": self._update_count,
            "last_update_time_s": round(self._last_update_time, 6),
            "graph_stats": self.service.get_graph_stats(),
            "trade_stats": self.service.get_trade_stats(),
        }
