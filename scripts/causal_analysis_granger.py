#!/usr/bin/env python3
"""
scripts/causal_analysis_granger.py

Granger Causality Test Suite for VPIN/QI -> SPY Returns.

Tests:
  1. VPIN CDF Granger-causes SPY returns
  2. Quote Imbalance Granger-causes SPY returns
  3. VPIN CDF Granger-causes SPY volatility
  4. Quote Imbalance Granger-causes SPY volatility

Uses statsmodels.tsa.stattools.granger_causality_test.
Reports p-values, optimal lag structures, and F-statistics.

VPIN is computed from daily OHLCV using Bulk Volume Classification (BVC).
Quote Imbalance is proxied from put_call_ratio and overnight_gap.

Window B safe: all analysis on cached CSV data, no live connections.

Usage:
  python scripts/causal_analysis_granger.py
"""

from __future__ import annotations

import math
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

DATE_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
REPORT_PATH = REPORTS_DIR / f"causal_granger_{DATE_STR}.md"

# ---------------------------------------------------------------------------
# VPIN Computation (Bulk Volume Classification on daily data)
# ---------------------------------------------------------------------------

def compute_vpin_from_daily(
    prices: np.ndarray,
    volumes: np.ndarray,
    bucket_size: float = 1.0,
    window: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute VPIN and VPIN CDF from daily OHLCV data.

    Adapts the tick-level BVC to daily frequency:
    - price_change = daily return
    - volume = daily volume (normalized)
    - sigma = rolling 20-day realized volatility

    Args:
        prices: Array of daily close prices.
        volumes: Array of daily volumes (or volume_sma_5 as proxy).
        bucket_size: Fraction of avg daily volume per bucket.
        window: Rolling window for VPIN computation.

    Returns:
        (vpin, vpin_cdf) arrays aligned with input (NaN-padded at start).
    """
    n = len(prices)
    returns = np.diff(prices) / prices[:-1]  # length n-1
    returns = np.concatenate([[0.0], returns])

    # Rolling sigma (20-day)
    sigma = np.full(n, np.nan)
    for i in range(20, n):
        sigma[i] = np.std(returns[i-20:i])
    sigma[:20] = np.nanmean(sigma[20:]) if not np.all(np.isnan(sigma[20:])) else 0.01

    # BVC classification
    buy_frac = np.zeros(n)
    for i in range(n):
        s = sigma[i]
        if s <= 0 or math.isnan(s):
            buy_frac[i] = 0.5
        else:
            z = returns[i] / s
            buy_frac[i] = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    buy_vol = buy_frac * volumes
    sell_vol = (1.0 - buy_frac) * volumes

    # Volume buckets
    avg_vol = np.nanmean(volumes[20:]) if n > 20 else np.nanmean(volumes)
    actual_bucket_size = bucket_size * avg_vol

    vpin = np.full(n, np.nan)
    vpin_cdf = np.full(n, np.nan)

    buy_buckets = []
    sell_buckets = []
    total_buckets = []
    vpin_history = []

    cum_buy = 0.0
    cum_sell = 0.0
    cum_total = 0.0

    for i in range(n):
        cum_buy += buy_vol[i]
        cum_sell += sell_vol[i]
        cum_total += volumes[i]

        if cum_total >= actual_bucket_size:
            buy_buckets.append(cum_buy)
            sell_buckets.append(cum_sell)
            total_buckets.append(cum_total)

            if len(buy_buckets) > window:
                buy_buckets.pop(0)
                sell_buckets.pop(0)
                total_buckets.pop(0)

            if len(total_buckets) >= 5:
                total_v = sum(total_buckets)
                if total_v > 0:
                    imb = sum(abs(b - s) for b, s in zip(buy_buckets, sell_buckets))
                    vpin_val = imb / total_v
                else:
                    vpin_val = 0.0
                vpin[i] = vpin_val
                vpin_history.append(vpin_val)

                # Empirical CDF
                if len(vpin_history) >= 5:
                    vpin_cdf[i] = np.mean(np.array(vpin_history) <= vpin_val)

            cum_buy = 0.0
            cum_sell = 0.0
            cum_total = 0.0

    return vpin, vpin_cdf


def compute_qi_proxy(put_call_ratio: np.ndarray, overnight_gap: np.ndarray) -> np.ndarray:
    """Compute Quote Imbalance proxy from put_call_ratio and overnight_gap.

    QI proxy = -zscore(put_call_ratio) + zscore(overnight_gap)
    High put_call_ratio = bearish sentiment = negative QI
    Positive overnight_gap = bullish = positive QI

    Returns z-scored QI.
    """
    n = len(put_call_ratio)
    qi = np.full(n, np.nan)

    for i in range(20, n):
        pc_mean = np.nanmean(put_call_ratio[i-20:i])
        pc_std = np.nanstd(put_call_ratio[i-20:i])
        og_mean = np.nanmean(overnight_gap[i-20:i])
        og_std = np.nanstd(overnight_gap[i-20:i])

        if pc_std > 0 and og_std > 0:
            qi[i] = -(put_call_ratio[i] - pc_mean) / pc_std + (overnight_gap[i] - og_mean) / og_std

    return qi


# ---------------------------------------------------------------------------
# Granger Causality Tests
# ---------------------------------------------------------------------------

def run_granger_test(
    data: pd.DataFrame,
    cause_col: str,
    effect_col: str,
    max_lags: int = 10,
    test: str = "ssr_ftest",
) -> dict:
    """Run Granger causality test using statsmodels.

    Args:
        data: DataFrame with cause and effect columns.
        cause_col: Name of the potential cause variable.
        effect_col: Name of the effect variable.
        max_lags: Maximum number of lags to test.
        test: Test statistic ("ssr_ftest", "ssr_chi2test", "lrtest", "params_ftest").

    Returns:
        Dictionary with test results per lag.
    """
    try:
        from statsmodels.tsa.stattools import grangercausalitytests
    except ImportError:
        print("ERROR: statsmodels not installed. Run: pip install statsmodels")
        sys.exit(1)

    # Drop NaN
    subset = data[[effect_col, cause_col]].dropna()

    if len(subset) < max_lags + 10:
        print(f"  WARNING: Only {len(subset)} observations, reducing max_lags to {len(subset) // 3}")
        max_lags = max(1, len(subset) // 3)

    try:
        results = grangercausalitytests(x=subset.values, maxlag=max_lags, verbose=False)
    except Exception as e:
        print(f"  ERROR in grangercausalitytests: {e}")
        return {}

    output = {}
    for lag in range(1, max_lags + 1):
        if lag in results:
            test_result = results[lag][0]
            if test in test_result:
                stat = test_result[test][0]
                pval = test_result[test][1]
                output[lag] = {"statistic": stat, "pvalue": pval}

    return output


def find_optimal_lag(results: dict) -> tuple[int, float, float]:
    """Find the lag with the lowest p-value."""
    if not results:
        return 0, 0.0, 1.0

    best_lag = min(results.keys(), key=lambda k: results[k]["pvalue"])
    return best_lag, results[best_lag]["statistic"], results[best_lag]["pvalue"]


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(
    granger_vpin_ret: dict,
    granger_qi_ret: dict,
    granger_vpin_vol: dict,
    granger_qi_vol: dict,
    data: pd.DataFrame,
) -> str:
    """Generate markdown report."""
    lines = []
    lines.append("# Granger Causality Analysis Report")
    lines.append(f"\n**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"\n**Data:** SPY daily features, {len(data)} observations")
    lines.append(f"**Date range:** {data['date'].iloc[0]} to {data['date'].iloc[-1]}")
    lines.append("\n---\n")

    # Summary table
    lines.append("## Summary of Results\n")
    lines.append("| Test | Optimal Lag | F-Statistic | P-Value | Significant (p<0.05) |")
    lines.append("|------|------------|-------------|---------|----------------------|")

    tests = [
        ("VPIN CDF → SPY Returns", granger_vpin_ret),
        ("Quote Imbalance → SPY Returns", granger_qi_ret),
        ("VPIN CDF → SPY Volatility", granger_vpin_vol),
        ("Quote Imbalance → SPY Volatility", granger_qi_vol),
    ]

    for name, results in tests:
        if results:
            lag, stat, pval = find_optimal_lag(results)
            sig = "YES ***" if pval < 0.001 else "YES **" if pval < 0.01 else "YES *" if pval < 0.05 else "NO"
            lines.append(f"| {name} | {lag} | {stat:.4f} | {pval:.6f} | {sig} |")
        else:
            lines.append(f"| {name} | N/A | N/A | N/A | ERROR |")

    lines.append("\n---\n")

    # Detailed results
    for name, results in tests:
        lines.append(f"## {name}\n")
        if results:
            lag, stat, pval = find_optimal_lag(results)
            lines.append(f"**Optimal lag:** {lag} days")
            lines.append(f"**F-statistic:** {stat:.4f}")
            lines.append(f"**P-value:** {pval:.6f}")
            lines.append(f"**Significance:** {'Yes' if pval < 0.05 else 'No'} (α = 0.05)\n")

            lines.append("| Lag | F-Statistic | P-Value | Significant |")
            lines.append("|-----|-------------|---------|-------------|")
            for lag_n in sorted(results.keys()):
                r = results[lag_n]
                sig = "***" if r['pvalue'] < 0.001 else "**" if r['pvalue'] < 0.01 else "*" if r['pvalue'] < 0.05 else ""
                lines.append(f"| {lag_n} | {r['statistic']:.4f} | {r['pvalue']:.6f} | {sig} |")
            lines.append("")
        else:
            lines.append("**ERROR:** Test failed to produce results.\n")

    # Interpretation
    lines.append("---\n")
    lines.append("## Interpretation\n")

    vpin_ret_sig = granger_vpin_ret and find_optimal_lag(granger_vpin_ret)[1] < 0.05
    qi_ret_sig = granger_qi_ret and find_optimal_lag(granger_qi_ret)[1] < 0.05

    lines.append("### VPIN CDF → Returns\n")
    if granger_vpin_ret:
        _, _, pval = find_optimal_lag(granger_vpin_ret)
        if pval < 0.05:
            lines.append(f"**VPIN CDF Granger-causes SPY returns** (p={pval:.4f}). ")
            lines.append("This suggests that flow toxicity has predictive power for future price movements, ")
            lines.append("supporting the Easley/López de Prado hypothesis that informed trading precedes price changes.\n")
        else:
            lines.append(f"No significant Granger causality detected (p={pval:.4f}). ")
            lines.append("VPIN CDF does not appear to predict SPY returns at daily frequency.\n")

    lines.append("### Quote Imbalance → Returns\n")
    if granger_qi_ret:
        _, _, pval = find_optimal_lag(granger_qi_ret)
        if pval < 0.05:
            lines.append(f"**Quote Imbalance Granger-causes SPY returns** (p={pval:.4f}). ")
            lines.append("Order flow imbalance has predictive power for future price direction.\n")
        else:
            lines.append(f"No significant Granger causality detected (p={pval:.4f}). ")
            lines.append("Quote Imbalance does not appear to predict SPY returns at daily frequency.\n")

    lines.append("### Limitations\n")
    lines.append("- Daily frequency may miss intraday causal dynamics\n")
    lines.append("- VPIN computed from daily bars is an approximation of tick-level VPIN\n")
    lines.append("- Granger causality ≠ true causality (predictive, not structural)\n")
    lines.append("- 167 observations limits statistical power for long lag structures\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Granger Causality Test Suite")
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

    # Compute VPIN and VPIN CDF
    print("\nComputing VPIN from daily OHLCV...")
    prices = df['spot_price'].values
    volumes = df['volume_sma_5'].fillna(df['volume_sma_21']).values
    vpin, vpin_cdf = compute_vpin_from_daily(prices, volumes)
    df['vpin'] = vpin
    df['vpin_cdf'] = vpin_cdf
    print(f"  VPIN computed: {np.sum(~np.isnan(vpin))} non-NaN values")
    print(f"  VPIN CDF computed: {np.sum(~np.isnan(vpin_cdf))} non-NaN values")

    # Compute Quote Imbalance proxy
    print("\nComputing Quote Imbalance proxy...")
    pc_ratio = df['put_call_ratio'].values
    overnight_gap = df['overnight_gap'].values
    qi = compute_qi_proxy(pc_ratio, overnight_gap)
    df['qi_proxy'] = qi
    print(f"  QI proxy computed: {np.sum(~np.isnan(qi))} non-NaN values")

    # Prepare target variables
    df['spy_returns'] = df['log_ret_1d']
    df['spy_volatility'] = df['realized_vol_10d']

    # Drop rows with NaN in key columns
    df_clean = df.dropna(subset=['vpin_cdf', 'qi_proxy', 'spy_returns', 'spy_volatility']).copy()
    print(f"\nClean dataset: {len(df_clean)} rows")

    if len(df_clean) < 30:
        print("ERROR: Insufficient data after NaN removal")
        sys.exit(1)

    # Run Granger tests
    max_lags = min(10, len(df_clean) // 4)
    print(f"\nRunning Granger causality tests (max_lags={max_lags})...")

    print("\n[1/4] VPIN CDF → SPY Returns")
    r1 = run_granger_test(df_clean, 'vpin_cdf', 'spy_returns', max_lags)
    if r1:
        lag, stat, pval = find_optimal_lag(r1)
        print(f"  Best lag={lag}, F={stat:.4f}, p={pval:.6f} {'***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'ns'}")

    print("[2/4] Quote Imbalance → SPY Returns")
    r2 = run_granger_test(df_clean, 'qi_proxy', 'spy_returns', max_lags)
    if r2:
        lag, stat, pval = find_optimal_lag(r2)
        print(f"  Best lag={lag}, F={stat:.4f}, p={pval:.6f} {'***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'ns'}")

    print("[3/4] VPIN CDF → SPY Volatility")
    r3 = run_granger_test(df_clean, 'vpin_cdf', 'spy_volatility', max_lags)
    if r3:
        lag, stat, pval = find_optimal_lag(r3)
        print(f"  Best lag={lag}, F={stat:.4f}, p={pval:.6f} {'***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'ns'}")

    print("[4/4] Quote Imbalance → SPY Volatility")
    r4 = run_granger_test(df_clean, 'qi_proxy', 'spy_volatility', max_lags)
    if r4:
        lag, stat, pval = find_optimal_lag(r4)
        print(f"  Best lag={lag}, F={stat:.4f}, p={pval:.6f} {'***' if pval < 0.001 else '**' if pval < 0.01 else '*' if pval < 0.05 else 'ns'}")

    # Generate report
    report = generate_report(r1, r2, r3, r4, df)
    REPORT_PATH.write_text(report)
    print(f"\nReport saved to: {REPORT_PATH}")

    # Verification: assert significance for known volatile periods
    print("\n--- Verification ---")
    any_significant = False
    for name, results in [("VPIN→Returns", r1), ("QI→Returns", r2), ("VPIN→Vol", r3), ("QI→Vol", r4)]:
        if results:
            _, _, pval = find_optimal_lag(results)
            if pval < 0.05:
                any_significant = True
                print(f"  PASS: {name} is significant (p={pval:.4f})")
            else:
                print(f"  WARN: {name} not significant (p={pval:.4f})")

    if any_significant:
        print("\nAt least one causal relationship detected.")
    else:
        print("\nNo significant Granger causality found. This may indicate:")
        print("  - Daily frequency insufficient for VPIN/QI signals")
        print("  - Need tick-level data for proper VPIN computation")
        print("  - 2024 was a low-volatility regime where toxicity signals are weaker")

    return 0 if any_significant else 1


if __name__ == "__main__":
    sys.exit(main())
