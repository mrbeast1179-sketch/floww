#!/usr/bin/env python3
"""
scripts/train_spy_model.py

Train SPY direction prediction model on real GEX features.

Pipeline:
1. Load features from MongoDB ml_features collection
2. Compute 3 baselines: majority class, persistence, logistic regression
3. Train XGBoost and LightGBM with walk-forward cross-validation
4. Enforce quality gates (class balance, feature variance, prediction distribution)
5. Beat all 3 baselines on Sharpe-of-simulated-strategy or reject
6. Save best model + report

Usage:
  python scripts/train_spy_model.py --ticker SPY
  python scripts/train_spy_model.py --ticker SPY --dry-run
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

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml import DegenerateModelError
from services.ml.quality import (
    assert_class_balance,
    assert_feature_variance,
    assert_prediction_distribution,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_spy")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
FEATURE_VERSION = "v1.0"


def load_features(ticker: str, version: str = None) -> pd.DataFrame:
    """Load feature matrix from MongoDB."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    query = {"ticker": ticker}
    if version:
        query["feature_version"] = version
    cursor = db["ml_features"].find(query).sort("date", 1)
    docs = list(cursor)
    client.close()

    if not docs:
        raise ValueError(f"No features found for {ticker}")

    df = pd.DataFrame(docs)
    df = df.sort_values("date").reset_index(drop=True)
    log.info(f"Loaded {len(df)} rows for {ticker}")
    return df


def prepare_data(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Extract feature matrix X and target y from dataframe."""
    # Target: directional_move (-1, 0, +1) → convert to binary (0, 1)
    # We'll predict: 1 if directional_move > 0, 0 otherwise
    y_raw = df["target_directional_move"].fillna(0).values
    y = (y_raw > 0).astype(int)

    # Feature columns: exclude metadata and targets
    exclude = {
        "_id", "ticker", "date", "feature_version", "_computed_at",
        "target_directional_move", "target_return_pct", "target_range_expansion",
        "target_gap_move", "target_any_materialization",
    }
    feature_cols = [c for c in df.columns if c not in exclude]

    X = df[feature_cols].values.astype(float)

    # Replace NaN/inf with 0
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, y, feature_cols


def walk_forward_splits(
    n_samples: int,
    n_splits: int = 8,
    train_size: int = 100,
    test_size: int = 20,
    embargo: int = 2,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Generate walk-forward train/test splits."""
    splits = []
    min_required = train_size + test_size + embargo

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


def compute_baselines(
    X: np.ndarray, y: np.ndarray, splits: List[Tuple[np.ndarray, np.ndarray]]
) -> Dict[str, List[float]]:
    """Compute baseline predictions."""
    baselines = {
        "majority": [],
        "persistence": [],
        "logistic": [],
    }

    for train_idx, test_idx in splits:
        y_train = y[train_idx]
        y_test = y[test_idx]
        X_train = X[train_idx]
        X_test = X[test_idx]

        # Majority class baseline
        majority_class = int(np.bincount(y_train).argmax())
        baselines["majority"].extend([majority_class] * len(test_idx))

        # Persistence baseline (predict same as last observed)
        last_val = y_train[-1] if len(y_train) > 0 else 0
        baselines["persistence"].extend([last_val] * len(test_idx))

        # Logistic regression baseline
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            # Scale features
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Handle constant features
            X_train_scaled = np.nan_to_num(X_train_scaled, nan=0.0)
            X_test_scaled = np.nan_to_num(X_test_scaled, nan=0.0)

            lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
            lr.fit(X_train_scaled, y_train)
            lr_pred = lr.predict(X_test_scaled)
            baselines["logistic"].extend(lr_pred.tolist())
        except Exception as e:
            log.warning(f"Logistic baseline failed: {e}")
            baselines["logistic"].extend([0] * len(test_idx))

    return baselines


def train_model(
    X: np.ndarray,
    y: np.ndarray,
    splits: List[Tuple[np.ndarray, np.ndarray]],
    model_type: str = "xgboost",
) -> Dict[str, Any]:
    """Train a model with walk-forward CV."""
    from sklearn.preprocessing import StandardScaler

    all_preds = []
    all_probas = []
    all_actuals = []
    fold_metrics = []

    for fold_i, (train_idx, test_idx) in enumerate(splits):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # Remove constant features before quality gate
        feature_stds = np.std(X_train, axis=0)
        valid_features = feature_stds > 1e-8
        if valid_features.sum() < 5:
            log.warning(f"Fold {fold_i}: only {valid_features.sum()} non-constant features, skipping")
            continue
        X_train = X_train[:, valid_features]
        X_test = X_test[:, valid_features]

        # Quality gates on training data (relaxed for small folds)
        try:
            assert_class_balance(y_train, min_ratio=0.05)
            assert_feature_variance(X_train, min_var=1e-6)
        except DegenerateModelError as e:
            log.warning(f"Fold {fold_i}: quality gate failed: {e}")
            continue

        # Scale
        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)
        X_train_s = np.nan_to_num(X_train_s, nan=0.0)
        X_test_s = np.nan_to_num(X_test_s, nan=0.0)

        # Train
        try:
            if model_type == "xgboost":
                try:
                    from xgboost import XGBClassifier
                    model = XGBClassifier(
                        n_estimators=100, max_depth=4, learning_rate=0.1,
                        subsample=0.8, colsample_bytree=0.8, random_state=42,
                        eval_metric="logloss", verbosity=0,
                    )
                except (ImportError, OSError):
                    log.warning("XGBoost not available (needs OpenMP), falling back to sklearn GBM")
                    from sklearn.ensemble import GradientBoostingClassifier
                    model = GradientBoostingClassifier(
                        n_estimators=100, max_depth=4, learning_rate=0.1,
                        subsample=0.8, random_state=42,
                    )
            elif model_type == "lightgbm":
                try:
                    from lightgbm import LGBMClassifier
                    model = LGBMClassifier(
                        n_estimators=100, max_depth=4, learning_rate=0.1,
                        subsample=0.8, colsample_bytree=0.8, random_state=42,
                        verbose=-1,
                    )
                except (ImportError, OSError):
                    log.warning("LightGBM not available (needs OpenMP), falling back to sklearn GBM")
                    from sklearn.ensemble import GradientBoostingClassifier
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

        except Exception as e:
            log.warning(f"Fold {fold_i}: training failed: {e}")
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
            "fold": fold_i,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
        })

        all_preds.extend(preds.tolist())
        all_probas.extend(probas.tolist())
        all_actuals.extend(y_test.tolist())

    if not fold_metrics:
        return {"status": "failed", "message": "No folds succeeded"}

    # Aggregate metrics
    avg_metrics = {
        "accuracy": np.mean([m["accuracy"] for m in fold_metrics]),
        "precision": np.mean([m["precision"] for m in fold_metrics]),
        "recall": np.mean([m["recall"] for m in fold_metrics]),
        "f1": np.mean([m["f1"] for m in fold_metrics]),
    }

    return {
        "status": "ok",
        "model_type": model_type,
        "n_folds": len(fold_metrics),
        "metrics": avg_metrics,
        "fold_metrics": fold_metrics,
        "predictions": all_preds,
        "probabilities": all_probas,
        "actuals": all_actuals,
    }


def compute_trading_sharpe(predictions: List[int], actuals: List[int]) -> float:
    """Compute Sharpe ratio of a simple trading strategy based on predictions."""
    rets = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:  # Predicted up
            rets.append(1.0 if actual == 1 else -1.0)
        # Skip flat predictions
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def run_training(ticker: str, dry_run: bool = False) -> Dict[str, Any]:
    """Full training pipeline."""
    log.info(f"Starting training pipeline for {ticker}")

    # Load data
    df = load_features(ticker)
    X, y, feature_cols = prepare_data(df)

    log.info(f"Data: {X.shape[0]} samples, {X.shape[1]} features")
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

    # Train models
    results = {}
    for model_type in ["xgboost", "lightgbm"]:
        log.info(f"Training {model_type}...")
        result = train_model(X, y, splits, model_type)
        results[model_type] = result

        if result["status"] == "ok":
            sharpe = compute_trading_sharpe(result["predictions"], result["actuals"])
            result["sharpe"] = sharpe
            log.info(f"  {model_type}: acc={result['metrics']['accuracy']:.3f}, "
                     f"f1={result['metrics']['f1']:.3f}, sharpe={sharpe:.3f}")

    # Baseline metrics
    baseline_metrics = {}
    for name, preds in baselines.items():
        if len(preds) == len(y):
            preds_arr = np.array(preds[:len(y)])
            acc = np.mean(preds_arr == y[:len(preds_arr)])
            sharpe = compute_trading_sharpe(preds[:len(y)], y[:len(preds)].tolist())
            baseline_metrics[name] = {"accuracy": acc, "sharpe": sharpe}
            log.info(f"  baseline {name}: acc={acc:.3f}, sharpe={sharpe:.3f}")

    # Determine best model
    best_model = None
    best_sharpe = -999
    for model_type, result in results.items():
        if result["status"] == "ok":
            sharpe = result.get("sharpe", -999)
            # Must beat all baselines on Sharpe
            # If any baseline is missing, beats_baselines = False (not True)
            if baseline_metrics and all(b in baseline_metrics for b in ["majority", "persistence", "logistic"]):
                beats_all = all(
                    sharpe > baseline_metrics[b].get("sharpe", -999)
                    for b in ["majority", "persistence", "logistic"]
                )
            else:
                beats_all = False  # missing baselines = unverified
            result["beats_baselines"] = beats_all
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_model = model_type

    # Generate report
    report = {
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {
            "n_samples": len(y),
            "n_features": X.shape[1],
            "positive_rate": float(np.mean(y)),
            "date_range": f"{df['date'].iloc[0]} to {df['date'].iloc[-1]}",
        },
        "splits": len(splits),
        "baselines": baseline_metrics,
        "models": {},
        "verdict": "REJECT",
    }

    for model_type, result in results.items():
        if result["status"] == "ok":
            report["models"][model_type] = {
                "metrics": result["metrics"],
                "sharpe": result.get("sharpe", 0),
                "beats_baselines": result.get("beats_baselines", False),
                "n_folds": result["n_folds"],
            }

    if best_model and results[best_model].get("beats_baselines"):
        report["verdict"] = "SHIP"
        report["best_model"] = best_model

        # Save the best model trained on all available data
        from sklearn.preprocessing import StandardScaler
        from sklearn.ensemble import GradientBoostingClassifier
        import joblib

        # Remove constant features
        feature_stds = np.std(X, axis=0)
        valid_features = feature_stds > 1e-8
        X_filtered = X[:, valid_features]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_filtered)
        X_scaled = np.nan_to_num(X_scaled, nan=0.0)

        final_model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )
        final_model.fit(X_scaled, y)

        # Save model + scaler + feature info
        model_path = MODELS_DIR / f"{ticker}_direction_{FEATURE_VERSION}.joblib"
        scaler_path = MODELS_DIR / f"{ticker}_scaler_{FEATURE_VERSION}.joblib"
        meta_path = MODELS_DIR / f"{ticker}_meta_{FEATURE_VERSION}.json"

        joblib.dump(final_model, model_path)
        joblib.dump(scaler, scaler_path)

        # Save metadata
        import json
        meta = {
            "model_type": best_model,
            "feature_version": FEATURE_VERSION,
            "n_samples": len(y),
            "n_features_raw": X.shape[1],
            "n_features_used": int(valid_features.sum()),
            "feature_names": [feature_cols[i] for i in range(len(feature_cols)) if valid_features[i]],
            "metrics": results[best_model]["metrics"],
            "sharpe": results[best_model].get("sharpe", 0),
            "beats_baselines": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        report["model_path"] = str(model_path)
        report["scaler_path"] = str(scaler_path)
        log.info(f"Model saved: {model_path}")
        log.info(f"Scaler saved: {scaler_path}")
    elif best_model:
        report["verdict"] = "ITERATE"
        report["best_model"] = best_model
        report["reason"] = f"Best model ({best_model}) does not beat all baselines"

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"training_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    log.info(f"Verdict: {report['verdict']}")
    log.info(f"Report saved: {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Train SPY direction model")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = run_training(args.ticker, args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
