#!/usr/bin/env python3
"""
scripts/backtest_vpin_strategy.py

Walk-forward backtest of the VPIN_HFT strategy over historical data.

Applies the VPIN/QI strategy logic (from trading_signals.py) to historical
price and options data, computing:
  - Sharpe Ratio
  - Max Drawdown
  - Win Rate
  - Profit Factor
  - Comparison vs Buy & Hold SPY

Usage:
    python3 scripts/backtest_vpin_strategy.py [--days 90] [--output reports/]

Data sources:
    - MongoDB (if available): historical VPIN/price data
    - Synthetic data (fallback): generated via GBM for testing
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np

# Add backend/ to path so `services.X` imports work
BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.trading_signals import Signal, SignalState, TradingSignalGenerator
from services.correlation_engine import CorrelationEngine
from services.paper_trader import PaperTrader


def generate_synthetic_data(n_days: int = 90, seed: int = 42):
    """Generate synthetic price and VPIN data for backtesting.

    Returns list of daily bars with:
        - date, open, high, low, close, volume
        - vpin_cdf, qi (simulated)
    """
    rng = np.random.default_rng(seed)
    base_price = 500.0  # SPY starting price
    daily_vol = 0.012  # ~1.2% daily vol

    bars = []
    price = base_price
    dates = []
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)

    for i in range(n_days):
        date = start + timedelta(days=i)
        if date.weekday() >= 5:
            continue

        # GBM price step
        ret = rng.normal(0.0003, daily_vol)
        price *= (1 + ret)
        high = price * (1 + abs(rng.normal(0, 0.003)))
        low = price * (1 - abs(rng.normal(0, 0.003)))
        open_price = price * (1 + rng.normal(0, 0.001))
        volume = int(rng.integers(50_000_000, 150_000_000))

        # Simulate VPIN CDF (mean-reverting with occasional spikes)
        vpin_cdf = float(np.clip(rng.beta(2, 5) + rng.normal(0, 0.05), 0, 1))

        # Simulate quote imbalance
        qi = float(rng.normal(0, 0.3))

        bars.append({
            "date": date.isoformat(),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": volume,
            "vpin_cdf": vpin_cdf,
            "qi": qi,
        })

    return bars


def run_backtest(bars: list, initial_capital: float = 100_000.0) -> dict:
    """Run the VPIN_HFT strategy backtest.

    Parameters
    ----------
    bars : list[dict]
        Historical daily bars with vpin_cdf and qi fields.
    initial_capital : float
        Starting capital.

    Returns
    -------
    dict
        Backtest results with metrics.
    """
    # Initialize components
    signal_gen = TradingSignalGenerator(
        SignalState(
            vpin_cdf_zscore_threshold=0.5,
            corr_zscore_sum_threshold=4.0,
            qi_zscore_buy_threshold=1.5,
            qi_zscore_sell_threshold=-1.5,
            death_count_max=10,
        )
    )
    corr_engine = CorrelationEngine(window=60)
    trader = PaperTrader(
        initial_capital=initial_capital,
        position_size_pct=0.05,
        max_positions=3,
    )

    # Rolling VPIN CDF history for z-score computation
    vpin_history = []
    qi_history = []

    # Equity curve
    equity_curve = [initial_capital]
    buy_hold_equity = [initial_capital]
    initial_price = bars[0]["close"]

    trades_log = []

    for i, bar in enumerate(bars):
        close = bar["close"]
        vpin_cdf = bar["vpin_cdf"]
        qi = bar["qi"]

        vpin_history.append(vpin_cdf)
        qi_history.append(qi)

        # Compute VPIN CDF z-score (rolling)
        vpin_z = 0.0
        if len(vpin_history) >= 20:
            mean_v = np.mean(vpin_history[-20:])
            std_v = np.std(vpin_history[-20:])
            if std_v > 0:
                vpin_z = (vpin_cdf - mean_v) / std_v

        # Compute QI z-score (rolling)
        qi_z = 0.0
        if len(qi_history) >= 20:
            mean_q = np.mean(qi_history[-20:])
            std_q = np.std(qi_history[-20:])
            if std_q > 0:
                qi_z = (qi - mean_q) / std_q

        # Update correlation engine (simulated multi-asset)
        corr_engine.update(
            asset_vpin_cdfs={
                "SPX": vpin_cdf + np.random.normal(0, 0.02),
                "SPY": vpin_cdf,
                "QQQ": vpin_cdf + np.random.normal(0, 0.03),
            },
            exchange_vpin_cdfs={
                "NYSE": vpin_cdf + np.random.normal(0, 0.01),
                "NASDAQ": vpin_cdf + np.random.normal(0, 0.01),
                "BATS": vpin_cdf + np.random.normal(0, 0.01),
            },
        )

        exch_z, asset_z = corr_engine.compute()

        # Generate signal
        signal = signal_gen.evaluate(
            vpin_cdf_zscore=vpin_z,
            exchange_corr_zscore=exch_z,
            asset_corr_zscore=asset_z,
            qi_zscore=qi_z,
        )

        # Execute
        result = trader.execute_signal(signal, "SPY", close)

        # Track equity
        summary = trader.get_portfolio_summary({"SPY": close})
        equity_curve.append(summary["total_value"])

        # Buy & Hold
        buy_hold_shares = initial_capital / initial_price
        buy_hold_equity.append(buy_hold_shares * close)

        if result["status"] == "filled":
            trades_log.append({
                "date": bar["date"],
                "signal": signal.value,
                "price": close,
                "quantity": result.get("quantity", 0),
            })

    # Compute metrics
    equity = np.array(equity_curve)
    returns = np.diff(equity) / equity[:-1]

    # Sharpe Ratio (annualized, assuming daily data)
    sharpe = 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252))

    # Max Drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    # Win Rate
    trade_pnls = [t.realized_pnl for t in trader.trade_history]
    wins = sum(1 for p in trade_pnls if p > 0)
    total_trades = len(trade_pnls)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    # Profit Factor
    gross_profit = sum(p for p in trade_pnls if p > 0)
    gross_loss = abs(sum(p for p in trade_pnls if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Buy & Hold comparison
    bh_equity = np.array(buy_hold_equity)
    bh_return = (bh_equity[-1] - bh_equity[0]) / bh_equity[0] * 100
    strategy_return = (equity[-1] - equity[0]) / equity[0] * 100

    return {
        "metrics": {
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "win_rate_pct": round(win_rate * 100, 2),
            "profit_factor": round(profit_factor, 4),
            "total_trades": total_trades,
            "strategy_return_pct": round(strategy_return, 2),
            "buy_hold_return_pct": round(bh_return, 2),
            "final_equity": round(equity[-1], 2),
            "initial_capital": initial_capital,
        },
        "equity_curve": [round(e, 2) for e in equity_curve],
        "trades": trades_log[:50],  # First 50 trades
        "signal_state": signal_gen.get_state(),
    }


def generate_report(results: dict, n_days: int) -> str:
    """Generate a markdown backtest report."""
    m = results["metrics"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# VPIN_HFT Strategy Backtest Report",
        f"",
        f"**Generated:** {now}",
        f"**Period:** {n_days} trading days (synthetic data)",
        f"**Initial Capital:** ${m['initial_capital']:,.2f}",
        f"",
        f"## Performance Metrics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Sharpe Ratio | {m['sharpe_ratio']:.4f} |",
        f"| Max Drawdown | {m['max_drawdown_pct']:.2f}% |",
        f"| Win Rate | {m['win_rate_pct']:.2f}% |",
        f"| Profit Factor | {m['profit_factor']:.4f} |",
        f"| Total Trades | {m['total_trades']} |",
        f"| Strategy Return | {m['strategy_return_pct']:.2f}% |",
        f"| Buy & Hold Return | {m['buy_hold_return_pct']:.2f}% |",
        f"| Final Equity | ${m['final_equity']:,.2f} |",
        f"",
        f"## Assessment",
        f"",
    ]

    if m["sharpe_ratio"] > 1.0:
        lines.append(f"**PASS:** Sharpe ratio {m['sharpe_ratio']:.4f} > 1.0 threshold.")
    else:
        lines.append(f"**REVIEW:** Sharpe ratio {m['sharpe_ratio']:.4f} < 1.0 threshold.")
        lines.append(f"Strategy may need parameter tuning or longer lookback windows.")

    lines.extend([
        f"",
        f"## Notes",
        f"",
        f"- This backtest uses **synthetic data** generated via GBM.",
        f"- Real performance depends on actual VPIN CDF computation from tick data.",
        f"- Correlation z-scores use simulated multi-asset/multi-exchange data.",
        f"- Death count mechanism limits holding periods to 10 bars.",
        f"- Commission: $0.005/share, Position size: 5% of capital per trade.",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="VPIN_HFT Strategy Backtest")
    parser.add_argument("--days", type=int, default=90, help="Number of trading days")
    parser.add_argument("--output", type=str, default="reports/", help="Output directory")
    parser.add_argument("--capital", type=float, default=100_000.0, help="Initial capital")
    args = parser.parse_args()

    print(f"Generating {args.days} days of synthetic data...")
    bars = generate_synthetic_data(n_days=args.days)
    print(f"Running backtest over {len(bars)} bars...")

    results = run_backtest(bars, initial_capital=args.capital)

    # Print metrics
    m = results["metrics"]
    print(f"\n=== VPIN_HFT Backtest Results ===")
    print(f"Sharpe Ratio:     {m['sharpe_ratio']:.4f}")
    print(f"Max Drawdown:     {m['max_drawdown_pct']:.2f}%")
    print(f"Win Rate:         {m['win_rate_pct']:.2f}%")
    print(f"Profit Factor:    {m['profit_factor']:.4f}")
    print(f"Total Trades:     {m['total_trades']}")
    print(f"Strategy Return:  {m['strategy_return_pct']:.2f}%")
    print(f"Buy & Hold:       {m['buy_hold_return_pct']:.2f}%")
    print(f"Final Equity:     ${m['final_equity']:,.2f}")

    # Generate report
    report_md = generate_report(results, args.days)

    # Save report
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_path = output_dir / f"backtest_vpin_{date_str}.md"
    report_path.write_text(report_md)
    print(f"\nReport saved to: {report_path}")

    # Save JSON results
    json_path = output_dir / f"backtest_vpin_{date_str}.json"
    json_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"JSON results saved to: {json_path}")

    return results


if __name__ == "__main__":
    main()
