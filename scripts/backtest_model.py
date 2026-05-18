#!/usr/bin/env python3
"""
scripts/backtest_model.py

Backtest a trained model on historical data.

Reads model from models/ directory, loads features from MongoDB,
runs walk-forward backtest, and produces a detailed report.

Usage:
  python scripts/backtest_model.py --ticker SPY --model-path models/SPY_direction_v2.0_gex.joblib
  python scripts/backtest_model.py --ticker SPY --start 2024-01-01 --end 2024-12-31
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

import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backtest")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def load_model_and_scaler(model_path: str):
    """Load model and scaler from disk."""
    scaler_path = str(model_path).replace("_direction_", "_scaler_")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"Scaler not found: {scaler_path}")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    return model, scaler


def load_backtest_data(ticker: str, start_date: str = None, end_date: str = None):
    """Load GEX features and underlying bars for backtesting."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Load GEX features
    query: Dict[str, Any] = {"ticker": ticker}
    if start_date:
        query["day"] = {"$gte": start_date}
    if end_date:
        day_query = query.get("day", {})
        if isinstance(day_query, dict):
            day_query["$lte"] = end_date
            query["day"] = day_query

    gex_docs = list(db["gex_features"].find(query).sort("day", 1))
    if not gex_docs:
        raise ValueError(f"No GEX features found for {ticker}")
    gex_df = pd.DataFrame(gex_docs)

    # Load underlying bars
    bars_query: Dict[str, Any] = {"ticker": ticker}
    if start_date:
        bars_query["date"] = {"$gte": start_date}
    if end_date:
        date_query = bars_query.get("date", {})
        if isinstance(date_query, dict):
            date_query["$lte"] = end_date
            bars_query["date"] = date_query

    bars_docs = list(db["underlying_bars"].find(bars_query).sort("date", 1))
    if not bars_docs:
        raise ValueError(f"No bars found for {ticker}")
    bars_df = pd.DataFrame(bars_docs)

    client.close()
    return gex_df, bars_df


def build_backtest_features(gex_df: pd.DataFrame, bars_df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str], List[str], pd.DataFrame]:
    """Build feature matrix for backtesting."""
    gex_df = gex_df.rename(columns={"day": "date"})
    merged = pd.merge(gex_df, bars_df, on="date", how="inner")
    merged = merged.sort_values("date").reset_index(drop=True)

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

    # Target
    merged["target"] = (merged["close"].shift(-1) > merged["close"]).astype(int)
    merged["next_return"] = merged["close"].pct_change().shift(-1)

    # Drop NaN
    merged = merged.dropna().reset_index(drop=True)

    exclude = {"_id", "date", "ticker", "source", "computed_at", "target",
               "next_return", "open", "high", "low", "close", "adj_close", "volume"}
    feature_cols = [c for c in merged.columns if c not in exclude]

    X = merged[feature_cols].values.astype(float)
    y = merged["target"].values.astype(int)
    dates = merged["date"].tolist()
    next_returns = merged["next_return"].values

    return X, y, feature_cols, dates, next_returns


def run_backtest(model, scaler, X: np.ndarray, y: np.ndarray,
                 dates: List[str], next_returns: np.ndarray,
                 feature_names: List[str], n_splits: int = 10) -> Dict[str, Any]:
    """Run walk-forward backtest."""
    n_samples = len(y)
    test_size = max(10, n_samples // (n_splits + 2))
    train_size = max(50, n_samples // 3)

    all_preds = []
    all_probas = []
    all_actuals = []
    all_dates = []
    all_returns = []
    fold_results = []

    for i in range(n_splits):
        test_start = n_samples - (n_splits - i) * test_size
        test_end = min(test_start + test_size, n_samples)
        train_start = max(0, test_start - train_size)
        train_end = test_start

        if train_end <= train_start or test_end > n_samples:
            continue

        X_train = X[train_start:train_end]
        y_train = y[train_start:train_end]
        X_test = X[test_start:test_end]
        y_test = y[test_start:test_end]

        # Remove constant features
        feature_stds = np.std(X_train, axis=0)
        valid = feature_stds > 1e-8
        if valid.sum() < 5:
            continue
        X_train = X_train[:, valid]
        X_test = X_test[:, valid]

        # Scale
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test), nan=0.0)

        # Train
        from sklearn.ensemble import GradientBoostingClassifier
        fold_model = GradientBoostingClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )
        fold_model.fit(X_train_s, y_train)
        preds = fold_model.predict(X_test_s)
        probas = fold_model.predict_proba(X_test_s)[:, 1]

        # Metrics
        accuracy = np.mean(preds == y_test)
        tp = np.sum((preds == 1) & (y_test == 1))
        fp = np.sum((preds == 1) & (y_test == 0))
        fn = np.sum((preds == 0) & (y_test == 1))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

        # Trading returns
        trade_returns = []
        for pred, ret in zip(preds, next_returns[test_start:test_end]):
            if pred == 1:
                trade_returns.append(ret)
            elif pred == 0:
                trade_returns.append(-ret)

        avg_return = np.mean(trade_returns) if trade_returns else 0
        sharpe = np.mean(trade_returns) / (np.std(trade_returns) + 1e-8) * np.sqrt(252) if trade_returns else 0

        fold_results.append({
            "fold": i, "accuracy": accuracy, "precision": precision,
            "recall": recall, "f1": f1, "sharpe": sharpe,
            "avg_return": avg_return, "n_trades": len(trade_returns),
            "date_range": f"{dates[test_start]} to {dates[test_end-1]}",
        })

        all_preds.extend(preds.tolist())
        all_probas.extend(probas.tolist())
        all_actuals.extend(y_test.tolist())
        all_dates.extend(dates[test_start:test_end])
        all_returns.extend(next_returns[test_start:test_end].tolist())

    if not fold_results:
        return {"status": "failed", "message": "No folds succeeded"}

    return {
        "status": "ok",
        "n_folds": len(fold_results),
        "fold_results": fold_results,
        "overall": {
            "accuracy": np.mean([f["accuracy"] for f in fold_results]),
            "precision": np.mean([f["precision"] for f in fold_results]),
            "recall": np.mean([f["recall"] for f in fold_results]),
            "f1": np.mean([f["f1"] for f in fold_results]),
            "sharpe": np.mean([f["sharpe"] for f in fold_results]),
            "total_trades": sum(f["n_trades"] for f in fold_results),
        },
        "predictions": all_preds,
        "actuals": all_actuals,
        "dates": all_dates,
        "returns": all_returns,
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest a trained model")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--n-splits", type=int, default=10)
    args = parser.parse_args()

    # Load model
    if args.model_path:
        model, scaler = load_model_and_scaler(args.model_path)
    else:
        # Find latest model
        models_dir = Path(__file__).resolve().parent.parent / "models"
        pattern = f"{args.ticker}_direction_*.joblib"
        model_files = sorted(models_dir.glob(pattern))
        if not model_files:
            print(f"No model found matching {pattern}")
            sys.exit(1)
        model, scaler = load_model_and_scaler(str(model_files[-1]))

    log.info(f"Loaded model: {model}")

    # Load data
    gex_df, bars_df = load_backtest_data(args.ticker, args.start, args.end)
    log.info(f"Loaded {len(gex_df)} GEX rows, {len(bars_df)} bars")

    # Build features
    X, y, feature_names, dates, next_returns = build_backtest_features(gex_df, bars_df)
    log.info(f"Feature matrix: {X.shape}")

    # Run backtest
    result = run_backtest(model, scaler, X, y, dates, next_returns, feature_names, args.n_splits)

    if result["status"] != "ok":
        print(f"Backtest failed: {result['message']}")
        sys.exit(1)

    # Print results
    overall = result["overall"]
    print(f"\n=== Backtest Results ===")
    print(f"Ticker: {args.ticker}")
    print(f"Folds: {result['n_folds']}")
    print(f"Accuracy: {overall['accuracy']:.3f}")
    print(f"Precision: {overall['precision']:.3f}")
    print(f"Recall: {overall['recall']:.3f}")
    print(f"F1: {overall['f1']:.3f}")
    print(f"Sharpe: {overall['sharpe']:.3f}")
    print(f"Total trades: {overall['total_trades']}")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"backtest_{args.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    log.info(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
