#!/usr/bin/env python3
"""
scripts/backtest_retail_strategy.py

Backtest Retail Flow Strategy: CPR + OI Skew on SPY.

Strategy Logic:
  - CPR (Put/Call Ratio) > rolling_mean + 1*std → bearish signal (high put buying = contrarian long)
  - OI Skew (net_put_gex / net_call_gex ratio) > threshold → bearish positioning
  - Combined signal: when both CPR and OI Skew are elevated, take contrarian long
  - Exit after N days or on signal reversal

Metrics:
  - Sharpe Ratio (annualized)
  - Max Drawdown
  - Win Rate
  - Profit Factor
  - Total Return vs Buy & Hold

Window B safe: all analysis on cached CSV data, no live connections.

Usage:
  python scripts/backtest_retail_strategy.py
"""

from __future__ import annotations

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DATE_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
REPORT_PATH = REPORTS_DIR / f"backtest_retail_{DATE_STR}.md"


# ---------------------------------------------------------------------------
# Signal Generation
# ---------------------------------------------------------------------------

def compute_oi_skew(df: pd.DataFrame) -> pd.Series:
    """Compute OI Skew = net_put_gex / (net_call_gex + 1e-6).

    High OI Skew = more put gamma exposure = bearish positioning.
    We use the contrarian interpretation: extreme skew predicts reversals.
    """
    call_gex = df['net_call_gex'].values.astype(float)
    put_gex = df['net_put_gex'].values.astype(float)
    # OI Skew: ratio of put GEX to call GEX (absolute values)
    skew = np.abs(put_gex) / (np.abs(call_gex) + 1e-6)
    return pd.Series(skew, index=df.index)


def compute_cpr_signal(put_call_ratio: np.ndarray, window: int = 20) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute CPR z-score and signal.

    Returns:
        z_score: Rolling z-score of put_call_ratio
        signal: +1 (bullish contrarian, high PCR), -1 (bearish contrarian, low PCR), 0 (neutral)
        threshold: Rolling mean + std for signal generation
    """
    n = len(put_call_ratio)
    z_score = np.full(n, np.nan)
    signal = np.zeros(n)
    threshold_high = np.full(n, np.nan)
    threshold_low = np.full(n, np.nan)

    for i in range(window, n):
        window_data = put_call_ratio[i - window:i]
        mean = np.nanmean(window_data)
        std = np.nanstd(window_data)
        if std > 0:
            z_score[i] = (put_call_ratio[i] - mean) / std
            threshold_high[i] = mean + std
            threshold_low[i] = mean - std

            # Contrarian: high PCR (bearish sentiment) → bullish signal
            if put_call_ratio[i] > mean + std:
                signal[i] = 1  # Bullish contrarian
            elif put_call_ratio[i] < mean - std:
                signal[i] = -1  # Bearish contrarian (low PCR = complacent)

    return z_score, signal, threshold_high


def compute_oi_signal(oi_skew: np.ndarray, window: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """Compute OI Skew z-score and signal.

    High OI Skew = extreme put gamma = bearish positioning → contrarian long.
    """
    n = len(oi_skew)
    z_score = np.full(n, np.nan)
    signal = np.zeros(n)

    for i in range(window, n):
        window_data = oi_skew[i - window:i]
        mean = np.nanmean(window_data)
        std = np.nanstd(window_data)
        if std > 0:
            z_score[i] = (oi_skew[i] - mean) / std
            if oi_skew[i] > mean + std:
                signal[i] = 1  # Bullish contrarian (extreme put skew)
            elif oi_skew[i] < mean - std:
                signal[i] = -1  # Bearish contrarian (extreme call skew)

    return z_score, signal


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    combined_signal: np.ndarray,
    hold_days: int = 3,
    initial_capital: float = 5000.0,
) -> dict:
    """Run walk-forward backtest.

    Args:
        df: DataFrame with 'ret_1d' and 'spot_price' columns.
        combined_signal: Array of +1 (long), -1 (short), 0 (flat).
        hold_days: Number of days to hold each position.
        initial_capital: Starting capital.

    Returns:
        Dict with equity curve, trades, and performance metrics.
    """
    n = len(df)
    returns = df['ret_1d'].values
    prices = df['spot_price'].values

    equity = np.full(n, np.nan)
    equity[0] = initial_capital
    position = 0  # 0 = flat, +1 = long, -1 = short
    entry_day = 0
    trades = []
    daily_pnl = np.zeros(n)

    for i in range(1, n):
        # Check for new signal
        if combined_signal[i] != 0 and position == 0:
            position = combined_signal[i]
            entry_day = i

        # Check for exit
        if position != 0:
            days_held = i - entry_day
            if days_held >= hold_days or combined_signal[i] == -position:
                # Exit
                trade_ret = position * np.sum(returns[entry_day + 1:i + 1])
                trades.append({
                    'entry_day': entry_day,
                    'exit_day': i,
                    'direction': 'LONG' if position == 1 else 'SHORT',
                    'return': trade_ret,
                    'days_held': days_held,
                })
                position = 0

        # Daily P&L
        if position != 0:
            daily_pnl[i] = position * returns[i]
        else:
            daily_pnl[i] = 0.0

        equity[i] = equity[i - 1] * (1 + daily_pnl[i])

    # Close any open position at end
    if position != 0:
        trade_ret = position * np.sum(returns[entry_day + 1:])
        trades.append({
            'entry_day': entry_day,
            'exit_day': n - 1,
            'direction': 'LONG' if position == 1 else 'SHORT',
            'return': trade_ret,
            'days_held': n - 1 - entry_day,
        })
        equity[-1] = equity[entry_day] * (1 + trade_ret)

    # Remove NaN from equity
    valid_mask = ~np.isnan(equity)
    equity = equity[valid_mask]
    daily_pnl = daily_pnl[valid_mask]

    # Metrics
    total_return = (equity[-1] / initial_capital) - 1

    # Annualized Sharpe (252 trading days)
    if len(daily_pnl) > 1 and np.std(daily_pnl) > 0:
        sharpe = np.mean(daily_pnl) / np.std(daily_pnl) * np.sqrt(252)
    else:
        sharpe = 0.0

    # Max Drawdown
    peak = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / peak
    max_drawdown = np.min(drawdown)

    # Win Rate
    if trades:
        wins = sum(1 for t in trades if t['return'] > 0)
        win_rate = wins / len(trades)
    else:
        win_rate = 0.0

    # Profit Factor
    if trades:
        gross_profit = sum(t['return'] for t in trades if t['return'] > 0)
        gross_loss = abs(sum(t['return'] for t in trades if t['return'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    else:
        profit_factor = 0.0

    # Buy & Hold comparison
    bh_return = (prices[-1] / prices[0]) - 1
    bh_equity = initial_capital * (1 + bh_return)

    return {
        'equity': equity,
        'daily_pnl': daily_pnl,
        'trades': trades,
        'total_return': total_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'num_trades': len(trades),
        'bh_return': bh_return,
        'bh_equity': bh_equity,
        'initial_capital': initial_capital,
        'final_equity': equity[-1],
    }


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(
    results: dict,
    df: pd.DataFrame,
    cpr_z: np.ndarray,
    oi_z: np.ndarray,
    combined_signal: np.ndarray,
) -> str:
    """Generate markdown report."""
    lines = []
    lines.append("# Retail Flow Strategy Backtest Report")
    lines.append(f"\n**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"\n**Data:** SPY daily features, {len(df)} observations")
    lines.append(f"**Date range:** {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    lines.append(f"\n**Strategy:** CPR + OI Skew Contrarian")
    lines.append(f"**Hold period:** 3 days")
    lines.append(f"**Initial capital:** ${results['initial_capital']:,.2f}")

    lines.append("\n---\n")
    lines.append("## Performance Summary\n")
    lines.append("| Metric | Strategy | Buy & Hold |")
    lines.append("|--------|----------|------------|")
    lines.append(f"| Total Return | {results['total_return']*100:.2f}% | {results['bh_return']*100:.2f}% |")
    lines.append(f"| Final Equity | ${results['final_equity']:,.2f} | ${results['bh_equity']:,.2f} |")
    lines.append(f"| Sharpe Ratio (ann.) | {results['sharpe']:.3f} | N/A |")
    lines.append(f"| Max Drawdown | {results['max_drawdown']*100:.2f}% | N/A |")
    lines.append(f"| Win Rate | {results['win_rate']*100:.1f}% | N/A |")
    lines.append(f"| Profit Factor | {results['profit_factor']:.2f} | N/A |")
    lines.append(f"| Number of Trades | {results['num_trades']} | N/A |")

    # Expectancy
    if results['trades']:
        avg_win = np.mean([t['return'] for t in results['trades'] if t['return'] > 0]) if any(t['return'] > 0 for t in results['trades']) else 0
        avg_loss = np.mean([t['return'] for t in results['trades'] if t['return'] < 0]) if any(t['return'] < 0 for t in results['trades']) else 0
        expectancy = (results['win_rate'] * avg_win) + ((1 - results['win_rate']) * avg_loss)
        lines.append(f"| Avg Win | {avg_win*100:.3f}% | N/A |")
        lines.append(f"| Avg Loss | {avg_loss*100:.3f}% | N/A |")
        lines.append(f"| Expectancy per Trade | {expectancy*100:.4f}% | N/A |")

    lines.append("\n---\n")
    lines.append("## Signal Analysis\n")

    long_signals = np.sum(combined_signal == 1)
    short_signals = np.sum(combined_signal == -1)
    neutral = np.sum(combined_signal == 0)

    lines.append(f"| Signal Type | Count |")
    lines.append(f"|-------------|-------|")
    lines.append(f"| Long (contrarian) | {long_signals} |")
    lines.append(f"| Short (contrarian) | {short_signals} |")
    lines.append(f"| Neutral | {neutral} |")

    lines.append(f"\n**CPR Z-score range:** {np.nanmin(cpr_z):.2f} to {np.nanmax(cpr_z):.2f}")
    lines.append(f"**OI Skew Z-score range:** {np.nanmin(oi_z):.2f} to {np.nanmax(oi_z):.2f}")

    # Trade log
    lines.append("\n---\n")
    lines.append("## Trade Log (first 20)\n")
    lines.append("| # | Entry Date | Exit Date | Direction | Return | Days |")
    lines.append("|---|------------|-----------|-----------|--------|------|")

    for idx, t in enumerate(results['trades'][:20]):
        entry_date = df['date'].iloc[t['entry_day']] if t['entry_day'] < len(df) else 'N/A'
        exit_date = df['date'].iloc[t['exit_day']] if t['exit_day'] < len(df) else 'N/A'
        lines.append(f"| {idx+1} | {entry_date} | {exit_date} | {t['direction']} | {t['return']*100:.3f}% | {t['days_held']} |")

    if len(results['trades']) > 20:
        lines.append(f"\n... and {len(results['trades']) - 20} more trades")

    # Discussion
    lines.append("\n---\n")
    lines.append("## Discussion\n")

    if results['total_return'] > 0:
        lines.append(f"**The strategy shows positive expectancy** with a total return of {results['total_return']*100:.2f}% ")
        lines.append(f"vs buy-and-hold of {results['bh_return']*100:.2f}%.\n")
    else:
        lines.append(f"**The strategy shows negative expectancy** with a total return of {results['total_return']*100:.2f}% ")
        lines.append(f"vs buy-and-hold of {results['bh_return']*100:.2f}%.\n")

    if results['sharpe'] > 1.0:
        lines.append(f"The Sharpe ratio of {results['sharpe']:.3f} indicates good risk-adjusted returns.\n")
    elif results['sharpe'] > 0:
        lines.append(f"The Sharpe ratio of {results['sharpe']:.3f} indicates positive but modest risk-adjusted returns.\n")
    else:
        lines.append(f"The Sharpe ratio of {results['sharpe']:.3f} indicates negative risk-adjusted returns.\n")

    lines.append("### Limitations\n")
    lines.append("- 167 daily observations (~8 months) is a short backtest window\n")
    lines.append("- 2024 was a strong bull market; contrarian signals may underperform in trending markets\n")
    lines.append("- No transaction costs or slippage modeled\n")
    lines.append("- OI Skew derived from GEX data, not raw open interest\n")
    lines.append("- Daily frequency misses intraday signal dynamics\n")
    lines.append("- 3-day hold period is arbitrary; optimal hold may vary\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Retail Flow Strategy Backtest: CPR + OI Skew")
    print("=" * 60)

    # Load data
    csv_path = DATA_DIR / "SPY_v1.0.csv"
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found")
        sys.exit(1)

    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    print(f"\nLoaded {len(df)} rows from {csv_path.name}")

    # Compute signals
    print("\nComputing CPR signal...")
    cpr = df['put_call_ratio'].values
    cpr_z, cpr_signal, cpr_thresh = compute_cpr_signal(cpr, window=20)
    print(f"  CPR z-score range: {np.nanmin(cpr_z):.2f} to {np.nanmax(cpr_z):.2f}")
    print(f"  Long signals: {np.sum(cpr_signal == 1)}, Short signals: {np.sum(cpr_signal == -1)}")

    print("\nComputing OI Skew signal...")
    oi_skew = compute_oi_skew(df)
    oi_z, oi_signal = compute_oi_signal(oi_skew.values, window=20)
    print(f"  OI Skew z-score range: {np.nanmin(oi_z):.2f} to {np.nanmax(oi_z):.2f}")
    print(f"  Long signals: {np.sum(oi_signal == 1)}, Short signals: {np.sum(oi_signal == -1)}")

    # Combined signal: both must agree
    combined = np.zeros(len(df))
    combined_long_only = np.zeros(len(df))
    for i in range(len(df)):
        if cpr_signal[i] == 1 and oi_signal[i] == 1:
            combined[i] = 1  # Both bullish contrarian
            combined_long_only[i] = 1
        elif cpr_signal[i] == -1 and oi_signal[i] == -1:
            combined[i] = -1  # Both bearish contrarian
            # Long-only: skip short signals (flat instead)

    print(f"\nCombined signals: Long={np.sum(combined == 1)}, Short={np.sum(combined == -1)}")
    print(f"Long-only signals: Long={np.sum(combined_long_only == 1)}, Short=0")

    # Run backtests
    print("\nRunning backtest (directional)...")
    results_dir = run_backtest(df, combined, hold_days=3, initial_capital=5000.0)

    print("\nRunning backtest (long-only contrarian)...")
    results_long = run_backtest(df, combined_long_only, hold_days=3, initial_capital=5000.0)

    print(f"\n--- Results (Directional) ---")
    print(f"  Total Return: {results_dir['total_return']*100:.2f}%")
    print(f"  Buy & Hold:   {results_dir['bh_return']*100:.2f}%")
    print(f"  Sharpe:       {results_dir['sharpe']:.3f}")
    print(f"  Max DD:       {results_dir['max_drawdown']*100:.2f}%")
    print(f"  Win Rate:     {results_dir['win_rate']*100:.1f}%")
    print(f"  Profit Factor:{results_dir['profit_factor']:.2f}")
    print(f"  Trades:       {results_dir['num_trades']}")

    print(f"\n--- Results (Long-Only Contrarian) ---")
    print(f"  Total Return: {results_long['total_return']*100:.2f}%")
    print(f"  Buy & Hold:   {results_long['bh_return']*100:.2f}%")
    print(f"  Sharpe:       {results_long['sharpe']:.3f}")
    print(f"  Max DD:       {results_long['max_drawdown']*100:.2f}%")
    print(f"  Win Rate:     {results_long['win_rate']*100:.1f}%")
    print(f"  Profit Factor:{results_long['profit_factor']:.2f}")
    print(f"  Trades:       {results_long['num_trades']}")

    # Generate report for the long-only variant (more realistic for retail)
    report = generate_report(results_long, df, cpr_z, oi_z, combined_long_only)
    REPORT_PATH.write_text(report)
    print(f"\nReport saved to: {REPORT_PATH}")

    # Verification
    print("\n--- Verification ---")
    print(f"  Script ran: YES")
    print(f"  Trades generated: {results_long['num_trades']}")
    if results_long['total_return'] > 0:
        print(f"  Positive expectancy: YES")
    else:
        print(f"  Positive expectancy: NO (strategy needs refinement)")
    if results_long['num_trades'] > 0:
        print(f"  Sufficient sample: {'YES' if results_long['num_trades'] >= 5 else 'LOW'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
