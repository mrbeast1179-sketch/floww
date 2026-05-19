#!/usr/bin/env python3
"""
scripts/train_spy_v3.py

Train SPY direction model v3.0 using the existing v1.0 ml_features
(2799 samples, 40+ features, 2015-2026) with walk-forward CV.

This uses the rich feature set already computed:
- Returns (1d, 3d, 5d, 10d, 21d)
- SMA (5, 10, 21, 50)
- Realized vol (5d, 10d, 21d, 60d)
- RSI, ATR, MACD, BB, volume, overnight gap, calendar
- Multiple targets: directional_move, return_pct, gap_move, range_expansion
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml.quality import (
    assert_class_balance,
    assert_feature_variance,
    assert_prediction_distribution,
    DegenerateModelError,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_spy_v3")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

# Metadata columns to exclude from features
META_COLS = {'_id', '_computed_at', 'ticker', 'date', 'feature_version', 'day'}
# Target columns
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}


def load_features(ticker: str, version: str = 'v1.0') -> pd.DataFrame:
    """Load features from MongoDB."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    cursor = db["ml_features"].find(
        {"ticker": ticker, "feature_version": version}
    ).sort("date", 1)
    docs = list(cursor)
    client.close()
    if not docs:
        raise ValueError(f"No features found for {ticker} v{version}")
    return pd.DataFrame(docs)


def prepare_data(df: pd.DataFrame, target: str = 'target_directional_move') -> Tuple[np.ndarray, np.ndarray, List[str], List[str]]:
    """Prepare feature matrix and target."""
    # Drop rows where target is NaN
    df = df.dropna(subset=[target]).reset_index(drop=True)
    
    # Feature columns
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    
    # Replace inf with NaN, then fill NaN with 0
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[target].values.astype(int)
    dates = df['date'].tolist()
    
    return X, y, feature_cols, dates


def walk_forward_splits(n_samples: int, n_splits: int = 8,
                         train_size: int = 500, test_size: int = 100,
                         embargo: int = 5) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test splits."""
    splits = []
    for i in range(n_splits):
        test_start = n_samples - (n_splits - i) * test_size
        test_end = test_start + test_size
        train_start = max(0, test_start - train_size)
        train_end = test_start - embargo

        if train_end <= train_start or test_end > n_samples:
            continue

        train_idx = np.arange(train_start, train_end)
        test_idx = np.arange(test_start, test_end)
        splits.append((train_idx, test_idx))
    return splits


def compute_trading_sharpe(predictions: List[int], actuals: List[int]) -> float:
    """Compute Sharpe ratio of a simple trading strategy."""
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def train_and_evaluate(X, y, splits, feature_names, dates, ticker, model_type="gbm"):
    """Train model with walk-forward CV."""
    all_preds = []
    all_probas = []
    all_actuals = []
    fold_metrics = []

    for fold_i, (train_idx, test_idx) in enumerate(splits):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Remove constant features
        feature_stds = np.std(X_train, axis=0)
        valid_features = feature_stds > 1e-8
        if valid_features.sum() < 5:
            log.warning(f"Fold {fold_i}: only {valid_features.sum()} non-constant features, skipping")
            continue
        X_train = X_train[:, valid_features]
        X_test = X_test[:, valid_features]

        # Quality gates
        try:
            assert_class_balance(y_train, min_ratio=0.05, label=f"{ticker} fold {fold_i}")
            assert_feature_variance(X_train, min_var=1e-6)
        except DegenerateModelError as e:
            log.warning(f"Fold {fold_i}: quality gate failed: {e}")
            continue

        # Scale
        scaler = StandardScaler()
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test), nan=0.0)

        # Train
        if model_type == "gbm":
            model = GradientBoostingClassifier(
                n_estimators=100, max_depth=4, learning_rate=0.1,
                subsample=0.8, random_state=42,
            )
        elif model_type == "logistic":
            model = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]

        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError as e:
            log.warning(f"Fold {fold_i}: prediction gate failed: {e}")
            continue

        accuracy = np.mean(preds == y_test)
        tp = np.sum((preds == 1) & (y_test == 1))
        fp = np.sum((preds == 1) & (y_test == 0))
        fn = np.sum((preds == 0) & (y_test == 1))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        fold_metrics.append({
            "fold": fold_i, "accuracy": accuracy, "precision": precision,
            "recall": recall, "f1": f1, "n_train": len(train_idx), "n_test": len(test_idx),
        })

        all_preds.extend(preds.tolist())
        all_probas.extend(probas.tolist())
        all_actuals.extend(y_test.tolist())

        log.info(f"  Fold {fold_i}: acc={accuracy:.3f}, f1={f1:.3f}, n_train={len(train_idx)}, n_test={len(test_idx)}")

    if not fold_metrics:
        return {"status": "failed", "message": "No folds succeeded"}

    avg_metrics = {
        "accuracy": np.mean([m["accuracy"] for m in fold_metrics]),
        "precision": np.mean([m["precision"] for m in fold_metrics]),
        "recall": np.mean([m["recall"] for m in fold_metrics]),
        "f1": np.mean([m["f1"] for m in fold_metrics]),
    }

    return {
        "status": "ok", "model_type": model_type, "n_folds": len(fold_metrics),
        "metrics": avg_metrics, "fold_metrics": fold_metrics,
        "predictions": all_preds, "probabilities": all_probas, "actuals": all_actuals,
    }


def compute_baselines_on_splits(X, y, splits):
    """Compute baseline predictions aligned with test folds."""
    baseline_preds = {"majority": [], "persistence": [], "logistic": []}
    
    for train_idx, test_idx in splits:
        y_train = y[train_idx]
        X_train, X_test = X[train_idx], X[test_idx]
        
        # Majority class
        majority_class = int(np.bincount(y_train).argmax())
        baseline_preds["majority"].extend([majority_class] * len(test_idx))
        
        # Persistence
        last_val = y_train[-1] if len(y_train) > 0 else 0
        baseline_preds["persistence"].extend([last_val] * len(test_idx))
        
        # Logistic regression
        feature_stds = np.std(X_train, axis=0)
        valid_features = feature_stds > 1e-8
        if valid_features.sum() < 2:
            baseline_preds["logistic"].extend([0] * len(test_idx))
            continue
        scaler = StandardScaler()
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train[:, valid_features]), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test[:, valid_features]), nan=0.0)
        try:
            lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
            lr.fit(X_train_s, y_train)
            baseline_preds["logistic"].extend(lr.predict(X_test_s).tolist())
        except Exception:
            baseline_preds["logistic"].extend([0] * len(test_idx))
    
    return baseline_preds


def run_training(ticker: str = "SPY", version: str = "v3.0",
                 feature_version: str = "v1.0", target: str = "target_directional_move",
                 dry_run: bool = False) -> Dict[str, Any]:
    """Full training pipeline."""
    log.info(f"Starting training pipeline for {ticker} {version}")

    # Load data
    df = load_features(ticker, feature_version)
    log.info(f"Loaded {len(df)} feature rows")

    # Prepare
    X, y, feature_names, dates = prepare_data(df, target)
    log.info(f"Feature matrix: {X.shape[0]} samples, {X.shape[1]} features")
    log.info(f"Target distribution: {np.bincount(y)} ({np.mean(y)*100:.1f}% positive)")

    # Walk-forward splits
    n_splits = min(8, (len(y) - 200) // 100)
    splits = walk_forward_splits(len(y), n_splits=n_splits, train_size=500, test_size=100)
    log.info(f"Walk-forward: {len(splits)} splits")

    if len(splits) < 3:
        return {"status": "error", "message": f"Only {len(splits)} valid splits, need >= 3"}

    # Baselines
    log.info("Computing baselines...")
    baseline_preds = compute_baselines_on_splits(X, y, splits)

    # Train model
    log.info("Training model...")
    result = train_and_evaluate(X, y, splits, feature_names, dates, ticker)

    if result["status"] != "ok":
        return result

    # Compute Sharpe
    sharpe = compute_trading_sharpe(result["predictions"], result["actuals"])
    result["sharpe"] = sharpe
    log.info(f"Model: acc={result['metrics']['accuracy']:.3f}, f1={result['metrics']['f1']:.3f}, sharpe={sharpe:.3f}")

    # Baseline metrics
    y_test_all = np.concatenate([y[test_idx] for _, test_idx in splits])
    baseline_metrics = {}
    for name, preds in baseline_preds.items():
        if len(preds) == len(y_test_all):
            bp = compute_trading_sharpe(preds, y_test_all.tolist())
            acc = np.mean(np.array(preds) == y_test_all)
            baseline_metrics[name] = {"accuracy": acc, "sharpe": bp}
            log.info(f"  baseline {name}: acc={acc:.3f}, sharpe={bp:.3f}")

    result["baselines"] = baseline_metrics

    # SHIP gate
    beats_all = all(
        sharpe > baseline_metrics.get(b, {}).get("sharpe", -999)
        for b in ["majority", "persistence", "logistic"]
    )
    result["beats_baselines"] = beats_all

    if beats_all and not dry_run:
        result["verdict"] = "SHIP"
    elif beats_all and dry_run:
        result["verdict"] = "SHIP (dry-run)"
    else:
        result["verdict"] = "REJECT"
        result["reason"] = "Does not beat all baselines"

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"training_{ticker}_{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "ticker": ticker, "version": version, "feature_version": feature_version,
        "target": target, "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"n_samples": len(y), "n_features": X.shape[1], "positive_rate": float(np.mean(y))},
        "splits": len(splits), "baselines": baseline_metrics, "metrics": result["metrics"],
        "sharpe": sharpe, "beats_baselines": beats_all, "verdict": result["verdict"],
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(f"Report saved: {report_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Train SPY v3.0 with v1.0 features")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--version", default="v3.0")
    parser.add_argument("--feature-version", default="v1.0")
    parser.add_argument("--target", default="target_directional_move")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_training(args.ticker, args.version, args.feature_version, args.target, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
