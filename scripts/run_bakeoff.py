#!/usr/bin/env python3
"""
scripts/run_bakeoff.py

Full model bake-off: trains multiple models on cached CSV data.
Runs locally — no MongoDB needed.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml.quality import (
    assert_class_balance,
    assert_feature_variance,
    assert_prediction_distribution,
    DegenerateModelError,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data/cached_features"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

META_COLS = {'_computed_at', 'ticker', 'date', 'feature_version', 'day'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}


def load_data(ticker, version='v1.0'):
    csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No cached data: {csv_path}")
    df = pd.read_csv(csv_path)
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df['target_directional_move'].values.astype(int)
    return X, y, feature_cols


def walk_forward_splits(n, n_splits=8, train_size=500, test_size=100, embargo=5):
    splits = []
    for i in range(n_splits):
        test_start = n - (n_splits - i) * test_size
        test_end = test_start + test_size
        train_start = max(0, test_start - train_size)
        train_end = test_start - embargo
        if train_end <= train_start or test_end > n:
            continue
        splits.append((np.arange(train_start, train_end), np.arange(test_start, test_end)))
    return splits


def sharpe(preds, actuals):
    rets = [1.0 if p == 1 and a == 1 else -1.0 if p == 1 and a == 0 else 0.0
            for p, a in zip(preds, actuals)]
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def train_model(X, y, splits, model_name):
    all_preds, all_actuals = [], []
    models = {
        "logistic": LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        "gbm": GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, subsample=0.8, random_state=42),
        "gbm_deep": GradientBoostingClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, subsample=0.7, random_state=42),
        "rf": RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42),
    }
    model = models[model_name]

    for train_idx, test_idx in splits:
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        valid = np.std(X_train, axis=0) > 1e-8
        if valid.sum() < 5:
            continue
        X_train, X_test = X_train[:, valid], X_test[:, valid]

        try:
            assert_class_balance(y_train, min_ratio=0.05)
            assert_feature_variance(X_train, min_var=1e-6)
        except DegenerateModelError:
            continue

        scaler = StandardScaler()
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test), nan=0.0)

        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]

        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError:
            continue

        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())

    if not all_preds:
        return None

    return {
        "sharpe": sharpe(all_preds, all_actuals),
        "accuracy": float(np.mean(np.array(all_preds) == np.array(all_actuals))),
        "n_predictions": len(all_preds),
    }


def compute_baselines(y, splits):
    y_test_all = np.concatenate([y[test_idx] for _, test_idx in splits])
    majority_preds, persistence_preds = [], []
    for train_idx, test_idx in splits:
        y_train = y[train_idx]
        majority_preds.extend([int(np.bincount(y_train).argmax())] * len(test_idx))
        persistence_preds.extend([y_train[-1]] * len(test_idx))
    return {
        "majority": {"sharpe": sharpe(majority_preds, y_test_all), "accuracy": float(np.mean(np.array(majority_preds) == y_test_all))},
        "persistence": {"sharpe": sharpe(persistence_preds, y_test_all), "accuracy": float(np.mean(np.array(persistence_preds) == y_test_all))},
    }


def run_bakeoff(ticker, version='v1.0'):
    print(f"\n{'='*60}")
    print(f"Model bake-off: {ticker} {version}")
    print(f"{'='*60}")

    X, y, feature_cols = load_data(ticker, version)
    print(f"Data: {X.shape[0]} samples, {X.shape[1]} features")
    print(f"Target: {np.bincount(y)} ({np.mean(y)*100:.1f}% positive)")

    splits = walk_forward_splits(len(y))
    print(f"Splits: {len(splits)}")

    # Baselines
    baselines = compute_baselines(y, splits)
    print(f"\nBaselines:")
    for name, r in baselines.items():
        print(f"  {name:15s}: acc={r['accuracy']:.3f}, sharpe={r['sharpe']:.3f}")

    # Models
    results = {}
    for model_name in ["logistic", "gbm", "gbm_deep", "rf"]:
        t0 = time.time()
        result = train_model(X, y, splits, model_name)
        elapsed = time.time() - t0

        if result:
            results[model_name] = result
            beats_all = all(result["sharpe"] > baselines[b]["sharpe"] for b in ["majority", "persistence"])
            verdict = "SHIP" if beats_all else "REJECT"
            print(f"  {model_name:15s}: acc={result['accuracy']:.3f}, sharpe={result['sharpe']:.3f} -> {verdict} ({elapsed:.1f}s)")
        else:
            print(f"  {model_name:15s}: FAILED")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY (sorted by Sharpe):")
    all_results = {**baselines, **results}
    for name, r in sorted(all_results.items(), key=lambda x: x[1]["sharpe"], reverse=True):
        tag = " ★" if name in results and all(results[name]["sharpe"] > baselines[b]["sharpe"] for b in ["majority", "persistence"]) else ""
        print(f"  {name:15s}: acc={r['accuracy']:.3f}, sharpe={r['sharpe']:.3f}{tag}")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "ticker": ticker, "version": version,
        "n_samples": len(y), "n_features": X.shape[1],
        "splits": len(splits),
        "baselines": baselines,
        "models": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORTS_DIR / f"bakeoff_{ticker}_{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {report_path}")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="QQQ")
    parser.add_argument("--version", default="v1.0")
    parser.add_argument("--all", action="store_true", help="Run all tickers")
    args = parser.parse_args()

    if args.all:
        for ticker in ["QQQ", "DIA", "IWM", "TLT"]:
            try:
                run_bakeoff(ticker, args.version)
            except FileNotFoundError as e:
                print(f"\n{ticker}: SKIPPED ({e})")
    else:
        run_bakeoff(args.ticker, args.version)
