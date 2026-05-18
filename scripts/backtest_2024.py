#!/usr/bin/env python3
"""
scripts/backtest_2024.py

Walk-forward backtest of SPY direction model on 2024 data.

For each walk-forward fold:
1. Train on past data
2. Predict next 20 days
3. Track precision/recall/F1 per month
4. Compute equity curve

Output: reports/backtest_2024.md with monthly breakdown
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def load_features(ticker: str) -> pd.DataFrame:
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    cursor = db["ml_features"].find({"ticker": ticker}).sort("date", 1)
    docs = list(cursor)
    client.close()
    return pd.DataFrame(docs) if docs else pd.DataFrame()


def prepare_data(df: pd.DataFrame):
    """Extract features and targets."""
    exclude = {
        "_id", "ticker", "date", "feature_version", "_computed_at",
        "target_directional_move", "target_return_pct", "target_range_expansion",
        "target_gap_move", "target_any_materialization",
    }
    feature_cols = [c for c in df.columns if c not in exclude]
    y = (df["target_directional_move"].fillna(0).values > 0).astype(int)
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X, y, feature_cols, df["date"].values, df["target_return_pct"].fillna(0).values


def run_backtest(ticker: str = "SPY") -> dict:
    df = load_features(ticker)
    if df.empty:
        return {"error": "no_data"}

    X, y, feature_cols, dates, return_pcts = prepare_data(df)
    n = len(y)

    # Walk-forward: train on all prior data, predict next 20 days
    min_train = 50
    test_size = 20
    splits = []
    for i in range(min_train, n - test_size, test_size):
        train_idx = list(range(0, i))
        test_idx = list(range(i, min(i + test_size, n)))
        splits.append((train_idx, test_idx))

    print(f"Backtest: {n} samples, {len(splits)} folds, {X.shape[1]} features")

    all_results = []
    monthly_stats = {}

    for fold_i, (train_idx, test_idx) in enumerate(splits):
        X_train, X_test = X[train_idx][:, np.std(X[train_idx], axis=0) > 1e-8], \
                          X[test_idx][:, np.std(X[train_idx], axis=0) > 1e-8]

        # Recompute valid features for test set
        train_stds = np.std(X[train_idx], axis=0)
        valid = train_stds > 1e-8
        X_train = X[train_idx][:, valid]
        X_test = X[test_idx][:, valid]

        if X_train.shape[1] < 5:
            continue

        scaler = StandardScaler()
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test), nan=0.0)

        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )
        model.fit(X_train_s, y[train_idx])
        preds = model.predict(X_test_s)

        for j, idx in enumerate(test_idx):
            month = dates[idx][:7] if len(dates[idx]) >= 7 else "unknown"
            correct = int(preds[j] == y[idx])

            all_results.append({
                "date": dates[idx],
                "month": month,
                "predicted": int(preds[j]),
                "actual": int(y[idx]),
                "correct": correct,
                "return_pct": float(return_pcts[idx]),
            })

            if month not in monthly_stats:
                monthly_stats[month] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "total": 0, "returns": []}
            monthly_stats[month]["total"] += 1
            monthly_stats[month]["returns"].append(float(return_pcts[idx]))
            if preds[j] == 1 and y[idx] == 1:
                monthly_stats[month]["tp"] += 1
            elif preds[j] == 1 and y[idx] == 0:
                monthly_stats[month]["tp"] += 0
                monthly_stats[month]["fp"] += 1
            elif preds[j] == 0 and y[idx] == 1:
                monthly_stats[month]["fn"] += 1
            else:
                monthly_stats[month]["tn"] += 1

    # Generate report
    report_lines = [
        f"# SPY Direction Model — 2024 Backtest Report",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Model: GradientBoosting v1.0 | Features: {X.shape[1]}",
        f"Total predictions: {len(all_results)}",
        "",
        "## Monthly Breakdown",
        "",
        "| Month | N | Accuracy | Precision | Recall | F1 | Hit Rate |",
        "|-------|---|----------|-----------|--------|-----|----------|",
    ]

    total_tp = total_fp = total_fn = total_tn = 0
    for month in sorted(monthly_stats.keys()):
        s = monthly_stats[month]
        total = s["total"]
        acc = (s["tp"] + s["tn"]) / total if total > 0 else 0
        prec = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) > 0 else 0
        rec = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        report_lines.append(
            f"| {month} | {total} | {acc:.3f} | {prec:.3f} | {rec:.3f} | {f1:.3f} | {prec:.3f} |"
        )
        total_tp += s["tp"]
        total_fp += s["fp"]
        total_fn += s["fn"]
        total_tn += s["tn"]

    # Overall
    grand_total = total_tp + total_fp + total_fn + total_tn
    overall_acc = (total_tp + total_tn) / grand_total if grand_total > 0 else 0
    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    overall_f1 = 2 * overall_prec * overall_rec / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0

    report_lines.extend([
        "",
        "## Overall",
        f"- Accuracy: {overall_acc:.3f}",
        f"- Precision: {overall_prec:.3f}",
        f"- Recall: {overall_rec:.3f}",
        f"- F1: {overall_f1:.3f}",
        f"- Total predictions: {grand_total}",
    ])

    report_text = "\n".join(report_lines)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "backtest_2024.md"
    with open(report_path, "w") as f:
        f.write(report_text)

    print(report_text)
    print(f"\nReport saved: {report_path}")

    return {"report_path": str(report_path), "overall_accuracy": overall_acc, "overall_f1": overall_f1}


if __name__ == "__main__":
    result = run_backtest("SPY")
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)
