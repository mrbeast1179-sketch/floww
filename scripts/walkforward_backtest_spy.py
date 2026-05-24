#!/usr/bin/env python3
"""
scripts/walkforward_backtest_spy.py

Proper walk-forward backtest of the SPY regime-enhanced model.
For each fold, trains on expanding window, tests on next quarter.
This gives honest OOS performance metrics.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / "backend" / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")


def main():
    print(f"\n{'='*60}\nSPY Walk-Forward Backtest (Proper OOS)\n{'='*60}\n")

    # Load features
    from train_spy_regime_enhanced import (
        load_existing_features, compute_regime_features,
        get_feature_cols, _create_model, _trading_sharpe,
    )

    df = load_existing_features()
    df = compute_regime_features(df)
    feature_cols = get_feature_cols(df)

    target_col = "target_directional_move"
    valid = df[target_col].notna()
    df_v = df[valid].copy()
    for col in feature_cols:
        df_v[col] = pd.to_numeric(df_v[col], errors="coerce").fillna(0)

    X = df_v[feature_cols].values.astype(np.float64)
    y = df_v[target_col].values.astype(int)
    dates = df_v["date"].tolist()

    n = len(y)
    n_splits = 8
    fold_size = n // (n_splits + 1)

    all_oos_preds = []
    all_oos_actuals = []
    all_oos_dates = []
    fold_results = []

    for fold_idx in range(n_splits):
        train_end = fold_size * (fold_idx + 1)
        test_end = min(train_end + fold_size, n)
        if test_end <= train_end: continue

        X_tr, X_te = X[:train_end], X[train_end:test_end]
        y_tr, y_te = y[:train_end], y[train_end:test_end]
        d_te = dates[train_end:test_end]

        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            continue

        model = _create_model("GBM_deep")
        scaler = StandardScaler()
        model.fit(scaler.fit_transform(X_tr), y_tr)
        preds = model.predict(scaler.transform(X_te))

        acc = accuracy_score(y_te, preds)
        prec = precision_score(y_te, preds, zero_division=0)
        rec = recall_score(y_te, preds, zero_division=0)
        f1 = f1_score(y_te, preds, zero_division=0)
        sharpe = _trading_sharpe(preds, y_te)

        fold_results.append({
            "fold": fold_idx, "train_end": dates[train_end-1],
            "acc": acc, "prec": prec, "recall": rec, "f1": f1, "sharpe": sharpe,
            "n_train": len(y_tr), "n_test": len(y_te),
        })
        all_oos_preds.extend(preds.tolist())
        all_oos_actuals.extend(y_te.tolist())
        all_oos_dates.extend(d_te)

        print(f"Fold {fold_idx} [{dates[train_end]} → {dates[test_end-1]}]: "
              f"acc={acc:.3f} prec={prec:.3f} sharpe={sharpe:.3f} n_test={len(y_te)}")

    # Aggregate OOS results
    all_oos_preds = np.array(all_oos_preds)
    all_oos_actuals = np.array(all_oos_actuals)

    oos_acc = accuracy_score(all_oos_actuals, all_oos_preds)
    oos_prec = precision_score(all_oos_actuals, all_oos_preds, zero_division=0)
    oos_rec = recall_score(all_oos_actuals, all_oos_preds, zero_division=0)
    oos_f1 = f1_score(all_oos_actuals, all_oos_preds, zero_division=0)
    oos_sharpe = _trading_sharpe(all_oos_preds, all_oos_actuals)

    # Trading P&L
    pnl = []
    for p, a in zip(all_oos_preds, all_oos_actuals):
        if p == 1:
            pnl.append(1.0 if a == 1 else -1.0)

    total_trades = len(pnl)
    winning_trades = sum(1 for p in pnl if p > 0)
    gross_wins = sum(p for p in pnl if p > 0)
    gross_losses = abs(sum(p for p in pnl if p < 0))
    profit_factor = gross_wins / max(gross_losses, 1e-10)
    win_rate = winning_trades / max(total_trades, 1)
    total_pnl = sum(pnl)

    # Baselines
    majority = pd.Series(all_oos_actuals).mode()[0]
    maj_sharpe = _trading_sharpe(np.full_like(all_oos_actuals, majority), all_oos_actuals)
    persist = np.roll(all_oos_actuals, 1); persist[0] = all_oos_actuals[0]
    persist_sharpe = _trading_sharpe(persist, all_oos_actuals)

    print(f"\n{'='*60}")
    print(f"AGGREGATE OOS RESULTS ({n_splits}-fold walk-forward)")
    print(f"{'='*60}")
    print(f"Total OOS samples: {len(all_oos_actuals)}")
    print(f"Accuracy:     {oos_acc:.3f}")
    print(f"Precision:    {oos_prec:.3f}")
    print(f"Recall:       {oos_rec:.3f}")
    print(f"F1:           {oos_f1:.3f}")
    print(f"OOS Sharpe:   {oos_sharpe:.3f}")
    print(f"\nTrading:")
    print(f"  Total trades: {total_trades}")
    print(f"  Win rate:     {win_rate:.3f} ({winning_trades}/{total_trades})")
    print(f"  Total P&L:    {total_pnl:+.0f} units")
    print(f"  Profit Factor:{profit_factor:.2f}")
    print(f"\nBaselines:")
    print(f"  Majority Sharpe:    {maj_sharpe:.3f}")
    print(f"  Persistence Sharpe: {persist_sharpe:.3f}")
    print(f"  Model vs Majority:  {'BEATS' if oos_sharpe > maj_sharpe else 'LOSES'}")

    # Quarterly OOS breakdown
    results_df = pd.DataFrame({"date": all_oos_dates, "pred": all_oos_preds, "actual": all_oos_actuals})
    results_df["quarter"] = results_df["date"].apply(lambda d: f"Q{(int(d.split('-')[1])-1)//3 + 1}")

    print(f"\nQuarterly OOS:")
    for q in sorted(results_df["quarter"].unique()):
        qdf = results_df[results_df["quarter"] == q]
        q_pnl = [1.0 if r.pred == 1 and r.actual == 1 else (-1.0 if r.pred == 1 and r.actual == 0 else 0.0)
                 for _, r in qdf.iterrows() if r.pred == 1]
        q_wr = sum(1 for p in q_pnl if p > 0) / max(len(q_pnl), 1)
        print(f"  {q}: WR={q_wr:.2f} P&L={sum(q_pnl):+.0f} ({len(q_pnl)} trades)")

    # Write report
    report_path = REPO_ROOT / "reports" / "walkforward_backtest_SPY_v2.md"
    with open(report_path, "w") as f:
        f.write(f"# SPY Walk-Forward Backtest Report (v2.0-regime)\n")
        f.write(f"\n**Date:** {datetime.now(timezone.utc).isoformat()}")
        f.write(f"\n**Method:** 8-fold expanding-window walk-forward")
        f.write(f"\n**Model:** GBM_deep, 62 features")
        f.write(f"\n\n## Aggregate OOS Metrics")
        f.write(f"\n| Metric | Value |")
        f.write(f"\n|--------|-------|")
        f.write(f"\n| Accuracy | {oos_acc:.3f} |")
        f.write(f"\n| Precision | {oos_prec:.3f} |")
        f.write(f"\n| Recall | {oos_rec:.3f} |")
        f.write(f"\n| F1 | {oos_f1:.3f} |")
        f.write(f"\n| OOS Sharpe | {oos_sharpe:.3f} |")
        f.write(f"\n| Win Rate | {win_rate:.3f} |")
        f.write(f"\n| Profit Factor | {profit_factor:.2f} |")
        f.write(f"\n| Total P&L | {total_pnl:+.0f} units |")
        f.write(f"\n| vs Majority Baseline | {'BEATS' if oos_sharpe > maj_sharpe else 'LOSES'} |")

        f.write(f"\n\n## Fold Details")
        for fr in fold_results:
            f.write(f"\n- Fold {fr['fold']} [{fr['train_end']}]: acc={fr['acc']:.3f} sharpe={fr['sharpe']:.3f} n_test={fr['n_test']}")

    print(f"\nReport: {report_path}")

    # Verdict
    if oos_sharpe > 1.0 and profit_factor > 1.5:
        verdict = "STRONG - Deploy to paper trading"
    elif oos_sharpe > 0.5 and profit_factor > 1.0:
        verdict = "PROMISING - Paper trade with caution"
    else:
        verdict = "NEEDS WORK - Do not deploy"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
