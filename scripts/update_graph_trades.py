#!/usr/bin/env python3
"""
scripts/update_graph_trades.py

Populate trade outcome nodes in the knowledge graph from paper trading history.

Creates:
  - Trade nodes from paper_trading.py trade_history
  - Signal nodes from trading_signals.py evaluations
  - MarketCondition nodes from VPIN/volatility data
  - Edges linking trades to signals and conditions

Usage:
    python scripts/update_graph_trades.py [--reset-trades] [--demo]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.graph_trade_service import GraphTradeService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update_graph_trades")

KG_DB_PATH = REPO_ROOT / "data" / "research_kg.duckdb"


def generate_demo_trades() -> List[Dict[str, Any]]:
    """Generate realistic demo trade data for testing."""
    now = datetime.now(timezone.utc)
    trades = []
    signals = []
    conditions = []

    # Demo trade scenarios based on VPIN_HFT strategy
    scenarios = [
        # (symbol, side, qty, entry, exit, signal_type, signal_z, regime, vol, vpin_cdf)
        ("SPY", "BUY", 100, 450.0, 455.5, "VPIN", 2.1, "low_vol", 12.5, 0.85),
        ("SPY", "SELL", 100, 455.0, 452.0, "QI", -1.8, "high_vol", 22.3, 0.72),
        ("SPY", "BUY", 50, 448.0, 451.0, "COMPOSITE", 2.5, "trending", 15.0, 0.91),
        ("QQQ", "BUY", 75, 380.0, 385.0, "VPIN", 1.8, "low_vol", 11.0, 0.78),
        ("QQQ", "SELL", 75, 385.0, 382.5, "QI", -2.2, "mean_reverting", 18.5, 0.65),
        ("SPY", "SELL", 100, 460.0, 458.0, "GEX", -1.6, "high_vol", 25.0, 0.55),
        ("SPY", "BUY", 200, 445.0, 450.0, "VPIN", 2.8, "trending", 14.0, 0.95),
        ("SPY", "SELL", 50, 452.0, 448.0, "CORR", -2.5, "crisis", 35.0, 0.45),
        ("QQQ", "BUY", 100, 375.0, 382.0, "COMPOSITE", 3.0, "low_vol", 10.5, 0.88),
        ("SPY", "BUY", 150, 440.0, 447.0, "VPIN", 2.3, "trending", 13.5, 0.82),
        ("SPY", "SELL", 100, 447.0, 443.0, "QI", -1.9, "high_vol", 21.0, 0.68),
        ("QQQ", "SELL", 50, 388.0, 384.0, "GEX", -2.1, "mean_reverting", 19.0, 0.58),
        ("SPY", "BUY", 80, 435.0, 442.0, "VPIN", 2.6, "low_vol", 12.0, 0.90),
        ("SPY", "SELL", 120, 445.0, 441.0, "CORR", -2.8, "crisis", 38.0, 0.40),
        ("QQQ", "BUY", 60, 370.0, 378.0, "COMPOSITE", 2.9, "trending", 14.5, 0.86),
    ]

    for i, (symbol, side, qty, entry, exit_p, sig_type, sig_z, regime, vol, vpin) in enumerate(scenarios):
        trade_id = f"trade_{i:04d}_{uuid.uuid4().hex[:8]}"
        signal_id = f"sig_{i:04d}_{uuid.uuid4().hex[:8]}"
        cond_id = f"cond_{i:04d}_{uuid.uuid4().hex[:8]}"
        sym_id = f"sym_{symbol.lower()}"

        pnl = (exit_p - entry) * qty if side == "BUY" else (entry - exit_p) * qty
        pnl_pct = (pnl / (entry * qty)) * 100

        entry_time = now.replace(hour=9 + i // 3, minute=30 + (i * 5) % 30).isoformat()
        exit_time = now.replace(hour=10 + i // 3, minute=15 + (i * 7) % 45).isoformat()

        trades.append({
            "id": trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "entry_price": entry,
            "exit_price": exit_p,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 4),
            "trade_type": "paper",
            "entry_time": entry_time,
            "exit_time": exit_time,
            "holding_period_bars": 10 + i * 2,
            "strategy": "VPIN_HFT",
        })

        signals.append({
            "id": signal_id,
            "signal_type": sig_type,
            "value": round(abs(sig_z) * 0.5, 4),
            "z_score": round(sig_z, 4),
            "threshold": 1.5 if sig_type == "QI" else 0.5,
            "direction": "BUY" if sig_z > 0 else "SELL",
            "timestamp": entry_time,
        })

        conditions.append({
            "id": cond_id,
            "regime": regime,
            "volatility": vol,
            "vpin_cdf": vpin,
            "correlation_zscore": round(2.0 + i * 0.3, 2),
            "timestamp": entry_time,
        })

    return trades, signals, conditions


def populate_trade_graph(service: GraphTradeService, reset: bool = False,
                          demo: bool = True) -> Dict[str, int]:
    """Populate the trade subgraph."""
    service.ensure_schema()

    if reset:
        log.info("Resetting trade tables...")
        for table in ["trade_triggered_by", "trade_executed_in", "trade_for_symbol",
                       "signal_based_on", "condition_for_symbol",
                       "trades", "signals", "market_conditions", "symbols"]:
            try:
                service.conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass

    if demo:
        log.info("Generating demo trade data...")
        trades, signals, conditions = generate_demo_trades()

        # Upsert symbols
        symbols_seen = set()
        for t in trades:
            sym = t["symbol"]
            if sym not in symbols_seen:
                symbols_seen.add(sym)
                service.upsert_symbol({
                    "id": f"sym_{sym.lower()}",
                    "name": sym,
                    "asset_class": "equity",
                })

        # Upsert signals
        service.upsert_signals_batch(signals)
        log.info(f"Inserted {len(signals)} signal nodes")

        # Upsert market conditions
        for cond in conditions:
            service.upsert_market_condition(cond)
        log.info(f"Inserted {len(conditions)} market condition nodes")

        # Upsert trades
        service.upsert_trades_batch(trades)
        log.info(f"Inserted {len(trades)} trade nodes")

        # Create edges
        for i, trade in enumerate(trades):
            trade_id = trade["id"]
            signal_id = signals[i]["id"]
            cond_id = conditions[i]["id"]
            sym_id = f"sym_{trade['symbol'].lower()}"

            service.add_trade_signal_edge(trade_id, signal_id, confidence=1.0)
            service.add_trade_condition_edge(trade_id, cond_id)
            service.add_trade_symbol_edge(trade_id, sym_id)
            service.add_signal_symbol_edge(signal_id, sym_id)
            service.add_condition_symbol_edge(cond_id, sym_id)

        log.info(f"Created {len(trades)} trade-signal edges")
        log.info(f"Created {len(trades)} trade-condition edges")
        log.info(f"Created {len(trades)} trade-symbol edges")

    stats = service.get_graph_stats()
    trade_stats = service.get_trade_stats()

    log.info(f"Graph stats: {json.dumps(stats, indent=2)}")
    log.info(f"Trade stats: {json.dumps(trade_stats, indent=2)}")

    return {"graph_stats": stats, "trade_stats": trade_stats}


def main():
    parser = argparse.ArgumentParser(description="Update knowledge graph with trade outcomes")
    parser.add_argument("--reset-trades", action="store_true", help="Clear trade tables first")
    parser.add_argument("--demo", action="store_true", default=True, help="Use demo data")
    parser.add_argument("--db-path", type=str, default=str(KG_DB_PATH))
    args = parser.parse_args()

    service = GraphTradeService(args.db_path)
    try:
        result = populate_trade_graph(service, reset=args.reset_trades, demo=args.demo)
        print(json.dumps(result, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
