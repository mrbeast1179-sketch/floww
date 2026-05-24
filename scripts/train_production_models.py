#!/usr/bin/env python3
"""
scripts/train_production_models.py

Train production ML models on real cached GEX feature data.
Uses walk-forward validation, quality gates from services.ml.quality,
and saves models + manifests for SPY, QQQ, DIA.

Usage:
  python scripts/train_production_models.py                  # train all tickers
  python scripts/train_production_models.py --ticker SPY     # train single ticker
  python scripts/train_production_models.py --walk-forward    # walk-forward backtest
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# Setup paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # /Users/nav/GitHub/floww
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data" / "cached_features"

# Ticker → feature file mapping
TICKER_FILES = {
    "SPY": DATA_DIR / "SPY_v1.0.csv",
    "DIA": DATA_DIR / "DIA_v1.0.csv",
    "IWM": DATA_DIR / "IWM_v1.0.csv",
    "QQQ": DATA_DIR / "QQQ_v1.0.csv",
    "TLT": DATA_DIR / "TLT_v1.0.csv",
}

# Columns to exclude from features
META_COLS = {
    "ticker", "date", "day", "feature_version", "_computed_at",
    "target_directional_move", "target_return_pct",
    "target_range_expansion", "target_gap_move", "target_any_materialization",
}

TARGET_COL = "target_directional_move"

# Model hyperparameters (matching existing production models)
MODEL_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "min_samples_leaf": 10,
    "random_state": 42,
}

# Walk-forward parameters
WINDOW_SIZE = 500   # training window
STEP_SIZE = 63      # ~3 months forward step
MIN_TRAIN = 200     # minimum training samples


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def load_and_prepare(ticker: str) -> tuple[pd.DataFrame, list[str]]:
    """Load cached feature CSV and return (dataframe, feature_names)."""
    path = TICKER_FILES.get(ticker)
    if path is None or not path.exists():
        raise FileNotFoundError(f"No cached data for {ticker}: {path}")

    df = pd.read_csv(path)
    df = df.sort_values(by="date" if "date" in df.columns else "day").reset_index(drop=True)

    feature_names = [c for c in df.columns if c not in META_COLS]
    return df, feature_names


def add_derived_features(df: pd.DataFrame, feature_names: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Add derived features that improve model performance."""
    new_features = list(feature_names)

    # Volatility ratio features
    if "realized_vol_5d" in df.columns and "realized_vol_21d" in df.columns:
        df["vol_ratio_5_21"] = df["realized_vol_5d"] / (df["realized_vol_21d"] + 1e-8)
        new_features.append("vol_ratio_5_21")

    if "realized_vol_5d" in df.columns and "realized_vol_60d" in df.columns:
        df["vol_ratio_5_60"] = df["realized_vol_5d"] / (df["realized_vol_60d"] + 1e-8)
        new_features.append("vol_ratio_5_60")

    # SMA crossover features
    if "sma_5" in df.columns and "sma_21" in df.columns:
        df["sma_5_21_diff"] = df["sma_5"] - df["sma_21"]
        df["sma_5_21_cross"] = (df["sma_5_21_diff"] > 0).astype(float)
        new_features.extend(["sma_5_21_diff", "sma_5_21_cross"])

    if "sma_10" in df.columns and "sma_50" in df.columns:
        df["sma_10_50_diff"] = df["sma_10"] - df["sma_50"]
        new_features.append("sma_10_50_diff")

    # RSI extreme features
    if "rsi_14" in df.columns:
        df["rsi_overbought"] = (df["rsi_14"] > 70).astype(float)
        df["rsi_oversold"] = (df["rsi_14"] < 30).astype(float)
        new_features.extend(["rsi_overbought", "rsi_oversold"])

    # Return momentum / acceleration
    if "ret_1d" in df.columns and "ret_3d" in df.columns:
        df["ret_momentum"] = df["ret_3d"] - df["ret_1d"]
        new_features.append("ret_momentum")

    if "ret_5d" in df.columns and "ret_3d" in df.columns:
        df["ret_accel"] = df["ret_5d"] - df["ret_3d"]
        new_features.append("ret_accel")

    # Vol spike
    if "realized_vol_5d" in df.columns and "realized_vol_21d" in df.columns:
        df["vol_spike"] = (df["realized_vol_5d"] > 2 * df["realized_vol_21d"]).astype(float)
        new_features.append("vol_spike")

    # Gap features
    if "overnight_gap" in df.columns:
        df["gap_abs"] = df["overnight_gap"].abs()
        df["gap_large"] = (df["gap_abs"] > df["gap_abs"].quantile(0.9)).astype(float) if len(df) > 10 else 0.0
        new_features.extend(["gap_abs", "gap_large"])

    return df, new_features


# ---------------------------------------------------------------------------
# Training with quality gates
# ---------------------------------------------------------------------------

def train_single_model(
    ticker: str,
    df: pd.DataFrame,
    feature_names: list[str],
    target_col: str = TARGET_COL,
) -> dict:
    """Train a single model with quality gates and return manifest."""

    # Prepare data
    X = df[feature_names].values.astype(np.float64)
    y = df[target_col].values.astype(np.float64)

    # Handle NaN/inf in features
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Drop zero-variance features before training (prevents quality gate failures on small datasets)
    feature_vars = np.var(X, axis=0)
    valid_mask = feature_vars > 1e-6
    if not all(valid_mask):
        dropped = [f for f, v in zip(feature_names, valid_mask) if not v]
        logger.info(f"[{ticker}] Dropping {len(dropped)} zero-variance features: {dropped[:5]}")
        feature_names = [f for f, v in zip(feature_names, valid_mask) if v]
        X = X[:, valid_mask]

    if len(feature_names) < 5:
        return {"status": "too_few_features", "n_features": len(feature_names)}

    # Temporal train/test split (80/20)
    split_idx = int(len(X) * 0.8)
    if split_idx < 50 or (len(X) - split_idx) < 20:
        return {"status": "insufficient_data", "samples": len(X)}

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # Train model
    model = GradientBoostingClassifier(**MODEL_PARAMS)
    model.fit(X_train_scaled, y_train)

    # Predictions
    y_pred = model.predict(X_test_scaled)
    y_pred_proba = model.predict_proba(X_test_scaled)[:, 1]

    # Quality gates
    from services.ml.quality import run_all_gates, DegenerateModelError

    gate_results = {}
    try:
        gate_results = run_all_gates(
            X=X_train_scaled,
            y=y_train,
            y_pred_proba=y_pred_proba,
            feature_names=feature_names,
        )
        verdict = "SHIP"
    except DegenerateModelError as e:
        logger.warning(f"[{ticker}] Quality gate failed: {e}")
        verdict = "REJECT"
        gate_results["failed"] = str(e)

    # Metrics
    metrics = {
        "train_accuracy": float(accuracy_score(y_train, model.predict(X_train_scaled))),
        "test_accuracy": float(accuracy_score(y_test, y_pred)),
        "test_precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "test_recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "test_f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "train_samples": int(len(X_train)),
        "test_samples": int(len(X_test)),
    }

    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_.tolist()))
    importance = dict(sorted(importance.items(), key=lambda x: abs(x[1]), reverse=True))

    # Build manifest
    manifest = {
        "ticker": ticker,
        "model": "gbm",
        "feature_version": "v1.0",
        "target": target_col,
        "n_samples": len(X),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "model_params": MODEL_PARAMS,
        "metrics": metrics,
        "top_features": dict(list(importance.items())[:10]),
        "gate_results": gate_results,
        "verdict": verdict,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if verdict == "SHIP":
        # Save model and scaler
        model_path = MODELS_DIR / f"{ticker}_gbm_production.joblib"
        scaler_path = MODELS_DIR / f"{ticker}_gbm_production_scaler.joblib"
        manifest_path = MODELS_DIR / f"{ticker}_gbm_production_manifest.json"

        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, str(model_path))
        joblib.dump(scaler, str(scaler_path))

        manifest["model_path"] = str(model_path)
        manifest["scaler_path"] = str(scaler_path)

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)

        logger.info(f"[{ticker}] Model saved: {model_path}")
        logger.info(f"[{ticker}] Test accuracy: {metrics['test_accuracy']:.4f}, F1: {metrics['test_f1']:.4f}")
    else:
        logger.warning(f"[{ticker}] Model REJECTED by quality gates")

    return manifest


# ---------------------------------------------------------------------------
# Walk-forward backtest
# ---------------------------------------------------------------------------

def walk_forward_backtest(
    ticker: str,
    df: pd.DataFrame,
    feature_names: list[str],
    window_size: int = WINDOW_SIZE,
    step_size: int = STEP_SIZE,
    min_train: int = MIN_TRAIN,
) -> dict:
    """
    Walk-forward backtest with expanding window.
    Returns per-fold metrics and aggregate statistics.
    """
    X = df[feature_names].values.astype(np.float64)
    y = df[TARGET_COL].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    n = len(X)
    folds = []
    predictions_all = []
    actuals_all = []

    for start in range(0, n - window_size - step_size, step_size):
        train_end = start + window_size
        test_end = min(train_end + step_size, n)

        if train_end < min_train:
            continue

        X_train = X[start:train_end]
        y_train = y[start:train_end]
        X_test = X[train_end:test_end]
        y_test = y[train_end:test_end]

        if len(X_test) < 10:
            continue

        # Check class balance
        unique, counts = np.unique(y_train, return_counts=True)
        if len(unique) < 2 or min(counts) / len(y_train) < 0.1:
            logger.debug(f"[{ticker}] Fold {len(folds)}: skipping (class imbalance)")
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = GradientBoostingClassifier(**MODEL_PARAMS)
        model.fit(X_train_s, y_train)

        y_pred = model.predict(X_test_s)
        y_proba = model.predict_proba(X_test_s)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        folds.append({
            "fold": len(folds),
            "train_start": int(start),
            "train_end": int(train_end),
            "test_size": int(len(X_test)),
            "accuracy": float(acc),
            "f1": float(f1),
            "positive_rate": float(y_pred.mean()),
        })

        predictions_all.extend(y_pred.tolist())
        actuals_all.extend(y_test.tolist())

    if not folds:
        return {"status": "no_valid_folds", "total_samples": n}

    predictions_all = np.array(predictions_all)
    actuals_all = np.array(actuals_all)

    return {
        "status": "ok",
        "ticker": ticker,
        "n_folds": len(folds),
        "total_samples": n,
        "window_size": window_size,
        "step_size": step_size,
        "mean_accuracy": float(np.mean([f["accuracy"] for f in folds])),
        "std_accuracy": float(np.std([f["accuracy"] for f in folds])),
        "mean_f1": float(np.mean([f["f1"] for f in folds])),
        "overall_accuracy": float(accuracy_score(actuals_all, predictions_all)),
        "overall_f1": float(f1_score(actuals_all, predictions_all, zero_division=0)),
        "mean_positive_rate": float(np.mean([f["positive_rate"] for f in folds])),
        "folds": folds,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train production ML models on real GEX data")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to train (default: all)")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward backtest")
    parser.add_argument("--window", type=int, default=WINDOW_SIZE, help="Walk-forward window size")
    parser.add_argument("--step", type=int, default=STEP_SIZE, help="Walk-forward step size")
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else ["SPY", "QQQ", "DIA"]

    results = {}

    for ticker in tickers:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {ticker}")
        logger.info(f"{'='*60}")

        try:
            df, feature_names = load_and_prepare(ticker)
        except FileNotFoundError as e:
            logger.warning(str(e))
            continue

        logger.info(f"Loaded {len(df)} rows, {len(feature_names)} base features")

        # Add derived features
        df, feature_names = add_derived_features(df, feature_names)
        logger.info(f"After derived features: {len(feature_names)} features")

        if args.walk_forward:
            logger.info(f"Running walk-forward backtest (window={args.window}, step={args.step})")
            result = walk_forward_backtest(ticker, df, feature_names, args.window, args.step)
            results[ticker] = result

            if result["status"] == "ok":
                logger.info(f"Walk-forward: {result['n_folds']} folds")
                logger.info(f"  Mean accuracy: {result['mean_accuracy']:.4f} ± {result['std_accuracy']:.4f}")
                logger.info(f"  Mean F1: {result['mean_f1']:.4f}")
                logger.info(f"  Overall accuracy: {result['overall_accuracy']:.4f}")
                logger.info(f"  Overall F1: {result['overall_f1']:.4f}")
                logger.info(f"  Mean positive rate: {result['mean_positive_rate']:.4f}")
            else:
                logger.warning(f"Walk-forward failed: {result['status']}")
        else:
            result = train_single_model(ticker, df, feature_names)
            results[ticker] = result

            if result.get("verdict") == "SHIP":
                m = result["metrics"]
                logger.info(f"SHIP — Test acc: {m['test_accuracy']:.4f}, F1: {m['test_f1']:.4f}")
                logger.info(f"Top features: {list(result['top_features'].keys())[:5]}")
            else:
                logger.warning(f"REJECTED — {result.get('gate_results', {})}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    for ticker, result in results.items():
        if args.walk_forward:
            status = result.get("status", "?")
            if status == "ok":
                logger.info(f"{ticker}: {result['n_folds']} folds, acc={result['mean_accuracy']:.4f}, f1={result['mean_f1']:.4f}")
            else:
                logger.info(f"{ticker}: {status}")
        else:
            verdict = result.get("verdict", result.get("status", "?"))
            if "metrics" in result:
                logger.info(f"{ticker}: {verdict} — acc={result['metrics'].get('test_accuracy', 0):.4f}")
            else:
                logger.info(f"{ticker}: {verdict}")

    return results


if __name__ == "__main__":
    main()
