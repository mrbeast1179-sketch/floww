#!/usr/bin/env python3
"""
backend/scripts/backtest_retail_flow.py

Backtest the Retail Flow Score strategy using mock data.

Generates synthetic option flow data (CPR, OI change, IV skew) and
OHLCV price data, then runs the RetailFlowSignal through the backtest
engine with and without the regime filter.

Usage:
    python3 scripts/backtest_retail_flow.py
"""

from __future__ import annotations

import sys
import os
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.backtest.engine import BacktestEngine, EngineConfig
from services.backtest.retail_flow_signal import RetailFlowSignal, RegimeFilter


import logging

logger = logging.getLogger(__name__)
def run_backtest(snapshots, bars, ticker, label, **signal_kwargs):
    """Run a backtest and print results."""
    signal = RetailFlowSignal(**signal_kwargs)
    config = EngineConfig(
        initial_capital=10_000.0,
        slippage_pct=0.0005,
        commission_per_contract=0.65,
        contracts_per_trade=1,
        price_per_contract=5.0,
    )
    engine = BacktestEngine(signal=signal, config=config)
    result = engine.run(snapshots, bars, ticker=ticker)

    logger.info(f"\n{'='*60}")
    logger.info(f"  {label}")
    logger.info(f"{'='*60}")
    logger.info(result.summary_text())
    return result


def main():
    logger.info("Retail Flow Score Backtest")
    logger.info("=" * 60)

    snapshots, bars, ticker = generate_mock_data(n_bars=252)

    # 1. Without regime filter (raw signal)
    r1 = run_backtest(
        snapshots, bars, ticker,
        label="Retail Flow Score — No Regime Filter",
        entry_threshold=30.0,
        exit_threshold=10.0,
        regime_filter=RegimeFilter(enabled=False),
    )

    # 2. With regime filter (SMA 21)
    r2 = run_backtest(
        snapshots, bars, ticker,
        label="Retail Flow Score — With SMA-21 Regime Filter",
        entry_threshold=30.0,
        exit_threshold=10.0,
        regime_filter=RegimeFilter(sma_period=21, enabled=True),
    )

    # 3. Higher threshold (more selective)
    r3 = run_backtest(
        snapshots, bars, ticker,
        label="Retail Flow Score — Higher Threshold (45) + Regime Filter",
        entry_threshold=45.0,
        exit_threshold=15.0,
        regime_filter=RegimeFilter(sma_period=21, enabled=True),
    )

    # Comparison
    logger.info(f"\n{'='*60}")
    logger.info("  COMPARISON")
    logger.info(f"{'='*60}")

    def get(result, key):
        return result.metrics.get(key, 0)

    metrics = [
        ("Net Return %", "net_return_pct"),
        ("Sharpe", "sharpe"),
        ("Max Drawdown %", "max_drawdown_pct"),
        ("Hit Rate", "hit_rate"),
        ("Profit Factor", "profit_factor"),
        ("Num Trades", "n_trades"),
    ]
    logger.info(f"{'Metric':<25} {'No Filter':>12} {'SMA-21':>12} {'High Thresh':>12}")
    logger.info(f"{'-'*61}")
    for label, key in metrics:
        v1 = get(r1, key)
        v2 = get(r2, key)
        v3 = get(r3, key)
        logger.info(f"{label:<25} {v1:>12.2f} {v2:>12.2f} {v3:>12.2f}")


if __name__ == "__main__":
    main()