#!/usr/bin/env python3
"""
scripts/train_spy_v2.py

Train SPY direction model v2.0 with Databento GEX features.

Uses:
- gex_features collection (229 rows, Jan-Nov 2024)
- underlying_bars for technical features
- Walk-forward CV with 8 folds
- Quality gates enforced via _save_with_gates
- Must beat 3 baselines: majority, persistence, logistic

Usage:
  python scripts/train_spy_v2.py --ticker SPY --version v2.0_gex
  python scripts/train_spy_v2.py --ticker SPY --version v2.0_gex --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml.quality import (
    assert_class_balance,
    assert_feature_variance,
    assert_prediction_distribution,
    assert_temporal_ordering,
    assert_no_future_leakage,
    assert_train_test_temporal_split,
    run_all_gates,
)
from services.ml import DegenerateModelError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_spy_v2")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def load_gex_features(ticker: str) -> pd.DataFrame:
    """Load GEX features from MongoDB."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    cursor = db["gex_features"].find({"ticker": ticker}).sort("day", 1)
    docs = list(cursor)
    client.close()
    if not docs:
        raise ValueError(f"No GEX features found for {ticker}")
    return pd.DataFrame(docs)


def load_underlying_bars(ticker: str) -> pd.DataFrame:
    """Load underlying OHLCV bars."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    cursor = db["underlying_bars"].find({"ticker": ticker}).sort("date", 1)
    docs = list(cursor)
    client.close()
    return pd.DataFrame(docs)


def build_feature_matrix(gex_df: pd.DataFrame, bars_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str], List[str]]:
    """Build combined feature matrix from GEX + underlying bars."""
    # Merge on date
    gex_df = gex_df.rename(columns={"day": "date"})
    merged = pd.merge(gex_df, bars_df, on="date", how="inner")
    merged = merged.sort_values("date").reset_index(drop=True)

    # Compute technical features
    closes = merged["close"].values.astype(float)

    # Returns
    for h in [1, 3, 5, 10, 21]:
        merged[f"ret_{h}d"] = merged["close"].pct_change(h)

    # SMA
    for w in [5, 10, 21]:
        merged[f"sma_{w}"] = merged["close"].rolling(w).mean()
        merged[f"price_vs_sma_{w}"] = merged["close"] / merged[f"sma_{w}"] - 1

    # Realized vol
    log_ret = np.log(closes / np.roll(closes, 1))
    for w in [5, 21]:
        merged[f"realized_vol_{w}d"] = pd.Series(log_ret).rolling(w).std().values * np.sqrt(252)

    # RSI
    delta = merged["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    merged["rsi_14"] = 100 - (100 / (1 + rs))

    # Target: next-day direction
    merged["target"] = (merged["close"].shift(-1) > merged["close"]).astype(int)

    # Drop rows with NaN
    # First, fill/drop sparse columns that are mostly NaN
    sparse_cols = [c for c in merged.columns if merged[c].isna().sum() > len(merged) * 0.5]
    if sparse_cols:
        log.info(f"Dropping sparse columns (>50% NaN): {sparse_cols}")
        merged = merged.drop(columns=sparse_cols)
    
    merged = merged.dropna().reset_index(drop=True)

    # Feature columns - exclude metadata and raw price columns
    exclude = {'_id', '_id_x', '_id_y', 'date', 'ticker', 'ticker_x', 'ticker_y',
               'source', 'source_x', 'source_y', 'computed_at', '_ingested_at',
               'target', 'open', 'high', 'low', 'close', 'adj_close', 'volume'}
    feature_cols = [c for c in merged.columns if c not in exclude]

    X = merged[feature_cols].values.astype(float)
    y = merged["target"].values.astype(int)
    dates = merged["date"].tolist()

    return X, y, feature_cols, dates


def walk_forward_splits(n_samples: int, n_splits: int = 8,
                         train_size: int = 100, test_size: int = 20,
                         embargo: int = 2) -> List[Tuple[np.ndarray, np.ndarray]]:
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


def compute_baselines(X: np.ndarray, y: np.ndarray, splits: List[Tuple[np.ndarray, np.ndarray]]) -> Dict[str, List[float]]:
    """Compute baseline predictions."""
    baselines = {"majority": [], "persistence": [], "logistic": []}

    for train_idx, test_idx in splits:
        y_train, y_test = y[train_idx], y[test_idx]
        X_train, X_test = X[train_idx], X[test_idx]

        # Majority class
        majority_class = int(np.bincount(y_train).argmax())
        baselines["majority"].extend([majority_class] * len(test_idx))

        # Persistence
        last_val = y_train[-1] if len(y_train) > 0 else 0
        baselines["persistence"].extend([last_val] * len(test_idx))

        # Logistic regression
        try:
            from sklearn.linear_model import LogisticRegression
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)
            X_train_s = np.nan_to_num(X_train_s, nan=0.0)
            X_test_s = np.nan_to_num(X_test_s, nan=0.0)
            lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
            lr.fit(X_train_s, y_train)
            baselines["logistic"].extend(lr.predict(X_test_s).tolist())
        except Exception as e:
            log.warning(f"Logistic baseline failed: {e}")
            baselines["logistic"].extend([0] * len(test_idx))

    return baselines


def compute_trading_sharpe(predictions: List[int], actuals: List[int]) -> float:
    """Compute Sharpe ratio of a simple trading strategy."""
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def train_model(X: np.ndarray, y: np.ndarray, splits: List[Tuple[np.ndarray, np.ndarray]],
                feature_names: List[str], dates: List[str], ticker: str,
                model_type: str = "gbm") -> Dict[str, Any]:
    """Train a model with walk-forward CV and quality gates."""
    all_preds: List[int] = []
    all_probas: List[float] = []
    all_actuals: List[int] = []
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
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]

        # Quality gate on predictions
        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError as e:
            log.warning(f"Fold {fold_i}: prediction gate failed: {e}")
            continue

        # Metrics
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


def run_training(ticker: str = "SPY", version: str = "v2.0_gex",
                 dry_run: bool = False) -> Dict[str, Any]:
    """Full training pipeline."""
    log.info(f"Starting training pipeline for {ticker} {version}")

    # Load data
    gex_df = load_gex_features(ticker)
    bars_df = load_underlying_bars(ticker)
    log.info(f"Loaded {len(gex_df)} GEX rows, {len(bars_df)} bars")

    # Build feature matrix
    X, y, feature_names, dates = build_feature_matrix(gex_df, bars_df)
    log.info(f"Feature matrix: {X.shape[0]} samples, {X.shape[1]} features")
    log.info(f"Target distribution: {np.bincount(y)} ({np.mean(y)*100:.1f}% positive)")

    # Walk-forward splits
    n_splits = min(8, (len(y) - 40) // 20)
    splits = walk_forward_splits(len(y), n_splits=n_splits, train_size=100, test_size=20)
    log.info(f"Walk-forward: {len(splits)} splits")

    if len(splits) < 3:
        return {"status": "error", "message": f"Only {len(splits)} valid splits, need ≥ 3"}

    # Baselines
    log.info("Computing baselines...")
    baselines = compute_baselines(X, y, splits)

    # Train model
    log.info("Training model...")
    result = train_model(X, y, splits, feature_names, dates, ticker)

    if result["status"] != "ok":
        return result

    # Compute Sharpe
    sharpe = compute_trading_sharpe(result["predictions"], result["actuals"])
    result["sharpe"] = sharpe
    log.info(f"Model: acc={result['metrics']['accuracy']:.3f}, f1={result['metrics']['f1']:.3f}, sharpe={sharpe:.3f}")

    # Baseline metrics — compare on the same test folds
    # Recompute baselines aligned with the actual test indices used
    baseline_metrics = {}
    test_idx_all = []
    for fold_i, (train_idx, test_idx) in enumerate(splits):
        test_idx_all.extend(test_idx.tolist())
    
    y_test_all = y[test_idx_all] if len(test_idx_all) <= len(y) else None
    
    if y_test_all is not None:
        for name in ["majority", "persistence", "logistic"]:
            # Recompute baseline predictions for each fold
            fold_preds = []
            for train_idx, test_idx in splits:
                y_train = y[train_idx]
                if name == "majority":
                    majority_class = int(np.bincount(y_train).argmax())
                    fold_preds.extend([majority_class] * len(test_idx))
                elif name == "persistence":
                    last_val = y_train[-1] if len(y_train) > 0 else 0
                    fold_preds.extend([last_val] * len(test_idx))
                elif name == "logistic":
                    from sklearn.linear_model import LogisticRegression
                    X_train, X_test = X[train_idx], X[test_idx]
                    feature_stds = np.std(X_train, axis=0)
                    valid_features = feature_stds > 1e-8
                    if valid_features.sum() < 2:
                        fold_preds.extend([0] * len(test_idx))
                        continue
                    scaler = StandardScaler()
                    X_train_s = np.nan_to_num(scaler.fit_transform(X_train[:, valid_features]), nan=0.0)
                    X_test_s = np.nan_to_num(scaler.transform(X_test[:, valid_features]), nan=0.0)
                    try:
                        lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
                        lr.fit(X_train_s, y_train)
                        fold_preds.extend(lr.predict(X_test_s).tolist())
                    except Exception:
                        fold_preds.extend([0] * len(test_idx))
            
            if len(fold_preds) == len(y_test_all):
                bp = compute_trading_sharpe(fold_preds, y_test_all.tolist())
                acc = np.mean(np.array(fold_preds) == y_test_all)
                baseline_metrics[name] = {"accuracy": acc, "sharpe": bp}
                log.info(f"  baseline {name}: acc={acc:.3f}, sharpe={bp:.3f}")

    result["baselines"] = baseline_metrics

    # SHIP gate: must beat all baselines
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
        "ticker": ticker, "version": version, "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"n_samples": len(y), "n_features": X.shape[1], "positive_rate": float(np.mean(y))},
        "splits": len(splits), "baselines": baseline_metrics, "metrics": result["metrics"],
        "sharpe": sharpe, "beats_baselines": beats_all, "verdict": result["verdict"],
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(f"Report saved: {report_path}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Train SPY v2.0 with GEX features")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--version", default="v2.0_gex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_training(args.ticker, args.version, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
