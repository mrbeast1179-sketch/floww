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

import logging

logger = logging.getLogger("graph_updater")


