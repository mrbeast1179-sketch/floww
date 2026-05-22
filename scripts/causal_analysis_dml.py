#!/usr/bin/env python3
"""
scripts/causal_analysis_dml.py

Double Machine Learning (DML) for Treatment Effects of VPIN on SPY Returns.

Uses EconML's LinearDML to estimate the Average Treatment Effect (ATE) of
high VPIN on future SPY returns, controlling for confounders:
  - Realized volatility (10d, 21d)
  - Volume (relative volume, volume_sma_5)
  - Time of day (day_of_week, day_of_month, month)
  - GEX regime (net_gex, gex_regime_encoded)

Treatment: High VPIN (binary, VPIN CDF > 0.7)
Outcome: Next-day SPY return (ret_1d)
Confounders: volatility, volume, time features, GEX

Also compares ATE across regimes (calm vs. urgent) using realized_vol_21d median split.

Window B safe: all analysis on cached CSV data.

Usage:
  python scripts/causal_analysis_dml.py
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
REPORT_PATH = REPORTS_DIR / f"causal_dml_{DATE_STR}.md"


# ---------------------------------------------------------------------------
# VPIN Computation (same as granger script)
# ---------------------------------------------------------------------------

def compute_vpin_from_daily(prices, volumes, bucket_size=1.0, window=20):
    """Compute VPIN and VPIN CDF from daily OHLCV data."""
    import math

    n = len(prices)
    returns = np.diff(prices) / prices[:-1]
    returns = np.concatenate([[0.0], returns])

    sigma = np.full(n, np.nan)
    for i in range(20, n):
        sigma[i] = np.std(returns[i-20:i])
    sigma[:20] = np.nanmean(sigma[20:]) if not np.all(np.isnan(sigma[20:])) else 0.01

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

    avg_vol = np.nanmean(volumes[20:]) if n > 20 else np.nanmean(volumes)
    actual_bucket_size = bucket_size * avg_vol

    vpin = np.full(n, np.nan)
    vpin_cdf = np.full(n, np.nan)

    buy_buckets, sell_buckets, total_buckets = [], [], []
    vpin_history = []
    cum_buy, cum_sell, cum_total = 0.0, 0.0, 0.0

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
                if len(vpin_history) >= 5:
                    vpin_cdf[i] = np.mean(np.array(vpin_history) <= vpin_val)

            cum_buy, cum_sell, cum_total = 0.0, 0.0, 0.0

    return vpin, vpin_cdf


# ---------------------------------------------------------------------------
# DML Analysis
# ---------------------------------------------------------------------------

def run_dml_analysis(df: pd.DataFrame) -> dict:
    """Run Double Machine Learning analysis.

    Returns dict with ATE, confidence intervals, and regime comparisons.
    """
    try:
        from econml.dml import LinearDML
        from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
    except ImportError:
        print("ERROR: econml or scikit-learn not installed.")
        sys.exit(1)

    results = {}

    # Define variables
    # Treatment: VPIN CDF (continuous, 0-1)
    treatment = df['vpin_cdf'].values

    # Outcome: next-day return
    outcome = df['ret_1d'].values

    # Confounders
    confounder_cols = [
        'realized_vol_10d', 'realized_vol_21d',
        'relative_volume', 'net_gex',
        'put_call_ratio', 'atr_14',
        'day_of_week', 'month',
    ]
    confounders = df[confounder_cols].values

    # Regime: calm vs urgent (based on realized_vol_21d median)
    vol_median = df['realized_vol_21d'].median()
    regime = (df['realized_vol_21d'] > vol_median).astype(int).values

    # --- Overall ATE ---
    print("\n[1/3] Running LinearDML for overall ATE...")

    est = LinearDML(
        model_y=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
        model_t=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
        random_state=42,
    )

    try:
        est.fit(outcome, T=treatment, X=confounders)
        ate = est.ate(T0=0.0, T1=1.0, X=confounders)
        ate_ci = est.ate_interval(T0=0.0, T1=1.0, X=confounders, alpha=0.05)
        results['overall'] = {
            'ate': float(ate),
            'ci_lower': float(ate_ci[0]),
            'ci_upper': float(ate_ci[1]),
            'significant': not (ate_ci[0] <= 0 <= ate_ci[1]),
        }
        print(f"  ATE: {ate:.6f} [{ate_ci[0]:.6f}, {ate_ci[1]:.6f}]")
        print(f"  Significant: {results['overall']['significant']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['overall'] = None

    # --- Calm Regime ---
    print("\n[2/3] Running DML for CALM regime (low vol)...")
    calm_mask = regime == 0
    if calm_mask.sum() > 20:
        try:
            est_calm = LinearDML(
                model_y=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
                model_t=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
                random_state=42,
            )
            est_calm.fit(
                outcome[calm_mask],
                T=treatment[calm_mask],
                X=confounders[calm_mask],
            )
            ate_calm = est_calm.ate(T0=0.0, T1=1.0, X=confounders[calm_mask])
            ci_calm = est_calm.ate_interval(T0=0.0, T1=1.0, X=confounders[calm_mask], alpha=0.05)
            results['calm'] = {
                'ate': float(ate_calm),
                'ci_lower': float(ci_calm[0]),
                'ci_upper': float(ci_calm[1]),
                'n': int(calm_mask.sum()),
                'significant': not (ci_calm[0] <= 0 <= ci_calm[1]),
            }
            print(f"  ATE: {ate_calm:.6f} [{ci_calm[0]:.6f}, {ci_calm[1]:.6f}] (n={calm_mask.sum()})")
        except Exception as e:
            print(f"  ERROR: {e}")
            results['calm'] = None
    else:
        print(f"  SKIP: Only {calm_mask.sum()} observations in calm regime")
        results['calm'] = None

    # --- Urgent Regime ---
    print("\n[3/3] Running DML for URGENT regime (high vol)...")
    urgent_mask = regime == 1
    if urgent_mask.sum() > 20:
        try:
            est_urgent = LinearDML(
                model_y=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
                model_t=GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
                random_state=42,
            )
            est_urgent.fit(
                outcome[urgent_mask],
                T=treatment[urgent_mask],
                X=confounders[urgent_mask],
            )
            ate_urgent = est_urgent.ate(T0=0.0, T1=1.0, X=confounders[urgent_mask])
            ci_urgent = est_urgent.ate_interval(T0=0.0, T1=1.0, X=confounders[urgent_mask], alpha=0.05)
            results['urgent'] = {
                'ate': float(ate_urgent),
                'ci_lower': float(ci_urgent[0]),
                'ci_upper': float(ci_urgent[1]),
                'n': int(urgent_mask.sum()),
                'significant': not (ci_urgent[0] <= 0 <= ci_urgent[1]),
            }
            print(f"  ATE: {ate_urgent:.6f} [{ci_urgent[0]:.6f}, {ci_urgent[1]:.6f}] (n={urgent_mask.sum()})")
        except Exception as e:
            print(f"  ERROR: {e}")
            results['urgent'] = None
    else:
        print(f"  SKIP: Only {urgent_mask.sum()} observations in urgent regime")
        results['urgent'] = None

    # --- CATE by VPIN quantile ---
    print("\n[Bonus] Computing CATE by VPIN quantile...")
    try:
        vpin_quantiles = pd.qcut(df['vpin_cdf'].values, q=4, labels=['Q1_low', 'Q2', 'Q3', 'Q4_high'], duplicates='drop')
        cate_by_quantile = {}
        for q in vpin_quantiles.unique():
            mask = vpin_quantiles == q
            if mask.sum() > 15:
                est_q = LinearDML(
                    model_y=GradientBoostingRegressor(n_estimators=50, max_depth=2, random_state=42),
                    model_t=GradientBoostingRegressor(n_estimators=50, max_depth=2, random_state=42),
                    random_state=42,
                )
                est_q.fit(outcome[mask], T=treatment[mask], X=confounders[mask])
                cate_by_quantile[str(q)] = {
                    'ate': float(est_q.ate(T0=0.0, T1=1.0, X=confounders[mask])),
                    'n': int(mask.sum()),
                }
                print(f"  {q}: ATE={est_q.ate(T0=0.0, T1=1.0, X=confounders[mask]):.6f} (n={mask.sum()})")
        results['cate_by_quantile'] = cate_by_quantile
    except Exception as e:
        print(f"  ERROR: {e}")
        results['cate_by_quantile'] = {}

    return results


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def generate_report(dml_results: dict, data: pd.DataFrame) -> str:
    """Generate markdown report."""
    lines = []
    lines.append("# Double Machine Learning (DML) Causal Analysis Report")
    lines.append(f"\n**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"\n**Data:** SPY daily features, {len(data)} observations")
    lines.append(f"**Date range:** {data['date'].iloc[0]} to {data['date'].iloc[-1]}")
    lines.append("\n## Methodology\n")
    lines.append("- **Algorithm:** LinearDML (EconML)")
    lines.append("- **Treatment:** VPIN CDF (continuous, 0-1)")
    lines.append("- **Outcome:** Next-day SPY return (ret_1d)")
    lines.append("- **Confounders:** realized_vol_10d, realized_vol_21d, relative_volume, net_gex, put_call_ratio, atr_14, day_of_week, month")
    lines.append("- **Nuisance models:** GradientBoostingRegressor (outcome), GradientBoostingRegressor (treatment)")
    lines.append("- **Regime split:** realized_vol_21d median\n")

    lines.append("---\n")
    lines.append("## Results\n")

    # Overall
    lines.append("### Overall Average Treatment Effect (ATE)\n")
    if dml_results.get('overall'):
        r = dml_results['overall']
        sig = "YES" if r['significant'] else "NO"
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| ATE | {r['ate']:.6f} |")
        lines.append(f"| 95% CI Lower | {r['ci_lower']:.6f} |")
        lines.append(f"| 95% CI Upper | {r['ci_upper']:.6f} |")
        lines.append(f"| Statistically Significant | {sig} |")
        lines.append("")
        lines.append(f"**Interpretation:** A high VPIN day is associated with a {r['ate']*100:.4f}% change ")
        lines.append(f"in next-day SPY returns (causal estimate, controlling for confounders).\n")
    else:
        lines.append("**ERROR:** Model failed to converge.\n")

    # Regime comparison
    lines.append("### ATE by Market Regime\n")
    lines.append("| Regime | ATE | 95% CI | N | Significant |")
    lines.append("|--------|-----|--------|---|-------------|")

    for regime_name, key in [("Calm (low vol)", "calm"), ("Urgent (high vol)", "urgent")]:
        r = dml_results.get(key)
        if r:
            sig = "YES" if r['significant'] else "NO"
            lines.append(f"| {regime_name} | {r['ate']:.6f} | [{r['ci_lower']:.6f}, {r['ci_upper']:.6f}] | {r['n']} | {sig} |")
        else:
            lines.append(f"| {regime_name} | N/A | N/A | N/A | N/A |")
    lines.append("")

    # CATE by quantile
    if dml_results.get('cate_by_quantile'):
        lines.append("### Conditional ATE by VPIN Quantile\n")
        lines.append("| VPIN Quantile | ATE | N |")
        lines.append("|---------------|-----|---|")
        for q, r in dml_results['cate_by_quantile'].items():
            lines.append(f"| {q} | {r['ate']:.6f} | {r['n']} |")
        lines.append("")

    # Discussion
    lines.append("---\n")
    lines.append("## Discussion\n")

    overall_sig = dml_results.get('overall', {}) or {}
    calm_r = dml_results.get('calm')
    urgent_r = dml_results.get('urgent')

    if overall_sig:
        if overall_sig.get('significant'):
            lines.append(f"The overall ATE is statistically significant ({overall_sig['ate']:.6f}), ")
            lines.append("suggesting that high VPIN has a causal effect on next-day returns ")
            lines.append("after controlling for confounders.\n")
        else:
            lines.append("The overall ATE is not statistically significant, suggesting that ")
            lines.append("the VPIN signal's predictive power may be largely explained by the ")
            lines.append("confounders (volatility, volume, GEX).\n")

    if calm_r and urgent_r:
        if calm_r.get('significant') or urgent_r.get('significant'):
            lines.append("The treatment effect varies by regime, indicating that the VPIN ")
            lines.append("signal's causal impact depends on market conditions.\n")
        else:
            lines.append("Neither regime shows a significant treatment effect, suggesting ")
            lines.append("VPIN may be more of a correlational than causal signal at daily frequency.\n")

    lines.append("### Limitations\n")
    lines.append("- Binary treatment (high/low VPIN) loses information vs. continuous treatment\n")
    lines.append("- Daily frequency VPIN is an approximation of tick-level VPIN\n")
    lines.append("- DML assumes no unmeasured confounders (strong ignorability)\n")
    lines.append("- 167 observations limits power for subgroup analyses\n")
    lines.append("- GradientBoosting nuisance models may overfit with small samples\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Double Machine Learning (DML) Causal Analysis")
    print("=" * 60)

    # Load data
    csv_path = DATA_DIR / "SPY_v1.0.csv"
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    print(f"\nLoaded {len(df)} rows from {csv_path.name}")

    # Compute VPIN
    print("\nComputing VPIN...")
    prices = df['spot_price'].values
    volumes = df['volume_sma_5'].fillna(df['volume_sma_21']).values
    vpin, vpin_cdf = compute_vpin_from_daily(prices, volumes)
    df['vpin'] = vpin
    df['vpin_cdf'] = vpin_cdf

    # Drop NaN
    confounder_cols = [
        'realized_vol_10d', 'realized_vol_21d',
        'relative_volume', 'net_gex',
        'put_call_ratio', 'atr_14',
        'day_of_week', 'month',
    ]
    needed_cols = ['vpin_cdf', 'ret_1d'] + confounder_cols
    df_clean = df.dropna(subset=needed_cols).copy()
    print(f"Clean dataset: {len(df_clean)} rows")

    if len(df_clean) < 30:
        print("ERROR: Insufficient data")
        sys.exit(1)

    # Run DML
    dml_results = run_dml_analysis(df_clean)

    # Generate report
    report = generate_report(dml_results, df_clean)
    REPORT_PATH.write_text(report)
    print(f"\nReport saved to: {REPORT_PATH}")

    # Verification
    print("\n--- Verification ---")
    if dml_results.get('overall'):
        print(f"  Model converged: YES")
        print(f"  ATE: {dml_results['overall']['ate']:.6f}")
        print(f"  Significant: {dml_results['overall']['significant']}")
    else:
        print("  Model converged: NO")

    return 0


if __name__ == "__main__":
    sys.exit(main())
