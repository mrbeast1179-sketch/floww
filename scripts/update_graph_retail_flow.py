#!/usr/bin/env python3
"""
scripts/update_graph_retail_flow.py

Populate retail flow score nodes and price movement nodes in the knowledge graph.

Creates:
  - RetailFlowScore nodes from options flow metrics
  - PriceMovement nodes from price data
  - Edges: RetailFlowScore -[:FOR_SYMBOL]-> Symbol
           RetailFlowScore -[:INFLUENCED]-> PriceMovement
           Trade -[:INFLUENCED_BY_RETAIL]-> RetailFlowScore

Usage:
    python scripts/update_graph_retail_flow.py [--reset] [--demo]
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

from services.graph_trade_service import GraphTradeService  # type: ignore[import-not-found]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update_graph_retail_flow")

KG_DB_PATH = REPO_ROOT / "data" / "research_kg.duckdb"


def generate_demo_retail_flow_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Generate realistic demo retail flow data.

    Retail flow metrics capture the behavior of retail vs institutional traders:
    - sweep_ratio: high = institutional (multi-exchange sweeps)
    - block_ratio: very high = institutional (large block trades)
    - small_lot_ratio: high = retail (small trade sizes)
    - premium_concentration: Herfindahl index (concentrated = directional bets)
    - call_put_ratio: >1 = bullish sentiment, <1 = bearish
    - retail_flow_score: composite [-1, 1], positive = bullish retail flow
    """
    now = datetime.now(timezone.utc)
    symbols = ["SPY", "QQQ"]
    flows = []
    movements = []

    # Demo scenarios: realistic retail flow patterns
    scenarios = [
        # (symbol, sweep_r, block_r, small_lot_r, prem_conc, cp_ratio,
        #  total_vol, total_prem, trade_cnt, avg_size, flow_score,
        #  price_start, price_end, timeframe)
        ("SPY", 0.15, 0.05, 0.65, 0.12, 1.8, 50000, 2500000, 350, 143, 0.72,
         450.0, 452.5, "5m"),
        ("SPY", 0.35, 0.20, 0.25, 0.30, 0.6, 80000, 5000000, 200, 400, -0.55,
         452.5, 449.0, "5m"),
        ("SPY", 0.10, 0.02, 0.78, 0.08, 2.2, 35000, 1200000, 420, 83, 0.85,
         449.0, 451.0, "5m"),
        ("QQQ", 0.18, 0.08, 0.55, 0.15, 1.5, 40000, 1800000, 280, 143, 0.45,
         380.0, 382.0, "5m"),
        ("QQQ", 0.40, 0.25, 0.18, 0.35, 0.4, 90000, 6000000, 150, 600, -0.78,
         382.0, 378.5, "5m"),
        ("SPY", 0.22, 0.10, 0.45, 0.20, 1.2, 60000, 3200000, 300, 200, 0.15,
         451.0, 451.8, "5m"),
        ("SPY", 0.08, 0.01, 0.85, 0.06, 2.5, 28000, 900000, 500, 56, 0.92,
         451.8, 454.0, "5m"),
        ("QQQ", 0.12, 0.03, 0.72, 0.10, 1.9, 32000, 1400000, 380, 84, 0.68,
         378.5, 381.0, "5m"),
        ("SPY", 0.30, 0.18, 0.30, 0.28, 0.7, 75000, 4500000, 220, 341, -0.42,
         454.0, 451.5, "5m"),
        ("QQQ", 0.25, 0.12, 0.40, 0.22, 1.0, 55000, 2800000, 260, 212, 0.05,
         381.0, 381.2, "5m"),
    ]

    for i, (sym, sr, br, slr, pc, cpr, tv, tp, tc, ats, fs,
            ps, pe, tf) in enumerate(scenarios):
        flow_id = f"rfs_{i:04d}_{uuid.uuid4().hex[:8]}"
        mov_id = f"pm_{i:04d}_{uuid.uuid4().hex[:8]}"

        ts = now.replace(hour=9 + i // 2, minute=(30 + i * 5) % 60).isoformat()

        flows.append({
            "id": flow_id,
            "symbol": sym,
            "timestamp": ts,
            "sweep_ratio": sr,
            "block_ratio": br,
            "small_lot_ratio": slr,
            "premium_concentration": pc,
            "call_put_ratio": cpr,
            "total_volume": tv,
            "total_premium": tp,
            "trade_count": tc,
            "avg_trade_size": ats,
            "retail_flow_score": fs,
        })

        price_change = pe - ps
        price_change_pct = (price_change / ps) * 100
        direction = "UP" if price_change > 0 else ("DOWN" if price_change < 0 else "FLAT")

        movements.append({
            "id": mov_id,
            "symbol": sym,
            "timestamp": ts,
            "start_price": ps,
            "end_price": pe,
            "price_change": round(price_change, 2),
            "price_change_pct": round(price_change_pct, 4),
            "direction": direction,
            "timeframe": tf,
            "volume": tv,
        })

    return flows, movements


def populate_retail_flow_graph(service: GraphTradeService, reset: bool = False,
                                demo: bool = True) -> Dict[str, Any]:
    """Populate the retail flow subgraph."""
    service.ensure_schema()

    if reset:
        log.info("Resetting retail flow tables...")
        for table in [
            "retail_flow_influenced_movement", "retail_flow_for_symbol",
            "trade_influenced_by_retail", "retail_flow_scores", "price_movements"
        ]:
            try:
                service.conn.execute(f"DELETE FROM {table}")
            except Exception:
                pass

    if demo:
        log.info("Generating demo retail flow data...")
        flows, movements = generate_demo_retail_flow_data()

        # Ensure symbols exist
        symbols_seen = set()
        for f in flows:
            sym = f["symbol"]
            if sym not in symbols_seen:
                symbols_seen.add(sym)
                service.upsert_symbol({
                    "id": f"sym_{sym.lower()}",
                    "name": sym,
                    "asset_class": "equity",
                })

        # Upsert retail flow scores
        service.upsert_retail_flow_scores_batch(flows)
        log.info(f"Inserted {len(flows)} retail flow score nodes")

        # Upsert price movements
        service.upsert_price_movements_batch(movements)
        log.info(f"Inserted {len(movements)} price movement nodes")

        # Create edges
        for i, flow in enumerate(flows):
            flow_id = flow["id"]
            mov_id = movements[i]["id"]
            sym_id = f"sym_{flow['symbol'].lower()}"

            service.add_retail_flow_symbol_edge(flow_id, sym_id)
            service.add_retail_flow_movement_edge(flow_id, mov_id, confidence=0.9)

            # Link trades that happened around the same time and symbol
            trades = service.get_trades_by_symbol(flow["symbol"], limit=5)
            for trade in trades:
                service.add_trade_retail_flow_edge(
                    trade["id"], flow_id, confidence=0.7
                )

        log.info(f"Created {len(flows)} retail-flow-to-symbol edges")
        log.info(f"Created {len(flows)} retail-flow-to-movement edges")

    graph_stats = service.get_graph_stats()
    retail_stats = service.get_retail_flow_stats()

    log.info(f"Graph stats: {json.dumps(graph_stats, indent=2)}")
    log.info(f"Retail flow stats: {json.dumps(retail_stats, indent=2)}")

    return {"graph_stats": graph_stats, "retail_flow_stats": retail_stats}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update knowledge graph with retail flow scores"
    )
    parser.add_argument("--reset", action="store_true",
                        help="Clear retail flow tables first")
    parser.add_argument("--demo", action="store_true", default=True,
                        help="Use demo data")
    parser.add_argument("--db-path", type=str, default=str(KG_DB_PATH))
    args = parser.parse_args()

    service = GraphTradeService(args.db_path)
    try:
        result = populate_retail_flow_graph(
            service, reset=args.reset, demo=args.demo
        )
        print(json.dumps(result, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
