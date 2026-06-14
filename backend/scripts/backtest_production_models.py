#!/usr/bin/env python3
"""
scripts/backtest_production_models.py

Walk-forward backtest for the v2 production 3-class ML models
against real cached historical features.

For each ticker:
  1. Load cached features from CSV (64 columns, 2GB total)
  2. Align features with model's selected features
  3. Walk-forward backtest: train on past, predict next N days
  4. Compute: accuracy, per-class accuracy, directional accuracy,
     simulated P&L (go long/short based on prediction), Sharpe ratio
  5. Compare against: buy-and-hold, majority-class baseline, persistence baseline

Usage:
    cd backend && .venv/bin/python3 -m scripts.backtest_production_models --ticker SPY
    cd backend && .venv/bin/python3 -m scripts.backtest_production_models --all
    cd backend && .venv/bin/python3 -m scripts.backtest_production_models --all --splits 10
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("backtest_prod")

REPO_ROOT = SCRIPT_DIR.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = SCRIPT_DIR.parent / "reports"
MODELS_DIR = SCRIPT_DIR.parent / "models"

# Target columns available in cached data
TARGET_COL = "target_directional_move"  # Binary: any directional move > threshold


def load_cached_features(ticker: str) -> pd.DataFrame:
    """Load cached features for a ticker."""
    # Try different version files
    for version in ["v1.0", "v1.5_gex_merged", "v2.0_gex"]:
        path = CACHE_DIR / f"{ticker}_{version}.csv"
        if path.exists():
            log.info(f"Loading {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
            df = pd.read_csv(path, parse_dates=["date"])
            df = df.sort_values("date").reset_index(drop=True)
            return df
    raise ValueError(f"No cached feature file found for {ticker}")


def load_production_model(ticker: str):
    """Load production model, scaler, and manifest."""
    # Find production manifest
    manifest_files = list(MODELS_DIR.glob(f"{ticker}_*_production_manifest.json"))
    if not manifest_files:
        raise ValueError(f"No production manifest for {ticker}")

    with open(sorted(manifest_files)[-1]) as _f:
        manifest = json.load(_f)
    model_path = manifest.get("model_path", "")
    scaler_path = manifest.get("scaler_path", "")

    # Resolve paths
    if not os.path.isabs(model_path):
        model_path = str(MODELS_DIR / model_path)
    if scaler_path and not os.path.isabs(scaler_path):
        scaler_path = str(MODELS_DIR / scaler_path)

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path) if scaler_path and os.path.exists(scaler_path) else None

    feature_names = manifest.get("feature_names", [])
    model_type = manifest.get("model_type", "unknown")

    log.info(f"Loaded {ticker} {model_type} model: {len(feature_names)} features, scaler={'yes' if scaler else 'no'}")
    return model, scaler, feature_names, manifest


def align_features(df: pd.DataFrame, feature_names: list) -> np.ndarray:
    """Align cached features with model's expected features. Missing = 0."""
    missing = [f for f in feature_names if f not in df.columns]
    if missing:
        log.warning(f"  {len(missing)} features missing from cache, filling with 0: {missing[:5]}...")
        for f in missing:
            df[f] = 0.0
    return df[feature_names].values.astype(float)


def compute_trading_pnl(predictions: np.ndarray, actual_returns: np.ndarray) -> dict:
    """Simulate trading P&L based on model predictions.

    Strategy:
        - Predicted UP → go long (+1x return)
        - Predicted DOWN → go short (-1x return)
        - Predicted HOLD → no position (0)

    Returns dict with total return, Sharpe, max drawdown, win rate.
    """
    # For binary target model: 0=DOWN, 1=UP (or 0=DOWN, 1=HOLD, 2=UP for 3-class)
    positions = np.zeros(len(predictions))

    for i, pred in enumerate(predictions):
        if pred == 2:  # UP
            positions[i] = 1.0
        elif pred == 0:  # DOWN
            positions[i] = -1.0
        else:  # HOLD
            positions[i] = 0.0

    # Daily returns from strategy
    strat_returns = positions * actual_returns

    # Cumulative
    cum_returns = np.cumprod(1 + strat_returns) - 1

    # Buy and hold
    bh_returns = np.cumprod(1 + actual_returns) - 1

    # Metrics
    total_return = cum_returns[-1] if len(cum_returns) > 0 else 0
    bh_return = bh_returns[-1] if len(bh_returns) > 0 else 0

    # Sharpe (annualized)
    if len(strat_returns) > 1 and np.std(strat_returns) > 0:
        sharpe = float(np.mean(strat_returns) / np.std(strat_returns) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Max drawdown
    peak = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - peak) / (1 + peak + 1e-10)
    max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0

    # Win rate
    wins = np.sum(strat_returns > 0)
    losses = np.sum(strat_returns < 0)
    total_trades = wins + losses
    win_rate = float(wins / total_trades) if total_trades > 0 else 0

    # Average win / average loss
    avg_win = float(np.mean(strat_returns[strat_returns > 0])) if np.any(strat_returns > 0) else 0
    avg_loss = float(np.mean(strat_returns[strat_returns < 0])) if np.any(strat_returns < 0) else 0

    return {
        "total_return": total_return,
        "buy_hold_return": bh_return,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "total_trades": int(total_trades),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "n_days": len(predictions),
    }


def walk_forward_backtest(
    df: pd.DataFrame,
    feature_names: list,
    model,
    scaler,
    n_splits: int = 8,
    train_size: int = 500,
    test_size: int = 50,
    embargo: int = 5,
) -> dict:
    """Walk-forward backtest with retraining each fold."""
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score

    X_full = align_features(df, feature_names)

    # Try to get actual returns for P&L simulation
    if "target_return_pct" in df.columns:
        actual_returns = df["target_return_pct"].values.astype(float)
    elif "ret_1d" in df.columns:
        actual_returns = df["ret_1d"].values.astype(float)
    else:
        actual_returns = np.zeros(len(df))

    # Determine target
    if "target_directional_move" in df.columns:
        y_full = df["target_directional_move"].values.astype(int)
    else:
        log.warning("No target column found, skipping backtest")
        return {"error": "no target column"}

    n = len(X_full)

    # Apply scaler
    if scaler is not None:
        # For walk-forward, we fit scaler only on training data
        pass  # Will fit per-fold

    all_preds = []
    all_actuals = []
    all_returns = []
    fold_metrics = []

    for i in range(n_splits):
        test_start = n - (n_splits - i) * test_size
        test_end = min(test_start + test_size, n)
        train_start = max(0, test_start - train_size)
        train_end = test_start - embargo

        if train_end <= train_start + 10 or test_end > n or test_start < 0:
            continue

        X_train = X_full[train_start:train_end]
        X_test = X_full[test_start:test_end]
        y_train = y_full[train_start:train_end]
        y_test = y_full[test_start:test_end]
        ret_test = actual_returns[test_start:test_end]

        # Fit scaler on training data only
        if scaler is not None:
            from sklearn.preprocessing import StandardScaler
            fold_scaler = StandardScaler()
            X_train = fold_scaler.fit_transform(X_train)
            X_test = fold_scaler.transform(X_test)

        # Clone and train model
        try:
            fold_model = clone(model)
            fold_model.fit(X_train, y_train)
        except Exception as e:
            log.warning(f"  Fold {i+1}: training failed: {e}")
            continue

        # Predict
        test_pred = fold_model.predict(X_test)
        test_acc = accuracy_score(y_test, test_pred)

        # Per-class accuracy
        for cls in [0, 1, 2]:
            mask = y_test == cls
            _cls_acc = accuracy_score(y_test[mask], test_pred[mask]) if mask.sum() > 0 else 0.0

        fold_metrics.append({
            "fold": i + 1,
            "test_acc": test_acc,
            "n_train": len(X_train),
            "n_test": len(X_test),
            "date_start": str(df["date"].iloc[test_start]) if "date" in df.columns else "",
            "date_end": str(df["date"].iloc[test_end - 1]) if "date" in df.columns else "",
        })

        all_preds.extend(test_pred.tolist())
        all_actuals.extend(y_test.tolist())
        all_returns.extend(ret_test.tolist())

    if not all_preds:
        return {"error": "no valid folds"}

    all_preds = np.array(all_preds)
    all_actuals = np.array(all_actuals)
    all_returns = np.array(all_returns)

    # Overall accuracy
    overall_acc = accuracy_score(all_actuals, all_preds)

    # Per-class accuracy
    per_class = {}
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        mask = all_actuals == cls
        if mask.sum() > 0:
            per_class[label] = {
                "accuracy": float(accuracy_score(all_actuals[mask], all_preds[mask])),
                "support": int(mask.sum()),
            }

    # Directional accuracy (ignore HOLD)
    directional_mask = (all_preds != 1) & (all_actuals != 1)
    dir_acc = float(accuracy_score(
        all_actuals[directional_mask], all_preds[directional_mask]
    )) if directional_mask.sum() > 0 else 0.0

    # Majority baseline
    majority_cls = int(np.bincount(all_actuals).argmax())
    majority_acc = float(np.mean(all_actuals == majority_cls))

    # Persistence baseline (predict same as previous)
    persistence_preds = np.roll(all_actuals, 1)
    persistence_preds[0] = majority_cls  # First prediction = majority
    persistence_acc = float(accuracy_score(all_actuals, persistence_preds))

    # Trading P&L
    pnl = compute_trading_pnl(all_preds, all_returns)

    return {
        "overall_accuracy": overall_acc,
        "per_class": per_class,
        "directional_accuracy": dir_acc,
        "majority_baseline": majority_acc,
        "persistence_baseline": persistence_acc,
        "n_predictions": len(all_preds),
        "n_folds": len(fold_metrics),
        "fold_metrics": fold_metrics,
        "pnl": pnl,
    }


def run_backtest(ticker: str, n_splits: int = 8) -> dict:
    """Run full backtest for a ticker."""
    log.info(f"{'=' * 60}")
    log.info(f"Backtesting {ticker}...")
    t0 = time.time()

    # Load data
    df = load_cached_features(ticker)
    log.info(f"  Data: {len(df)} rows, {len(df.columns)} columns")

    # Load model
    model, scaler, feature_names, manifest = load_production_model(ticker)

    # Run backtest
    result = walk_forward_backtest(
        df, feature_names, model, scaler,
        n_splits=n_splits, train_size=500, test_size=50, embargo=5,
    )

    result["ticker"] = ticker
    result["model_type"] = manifest.get("model_type", "unknown")
    result["n_features"] = len(feature_names)
    result["data_rows"] = len(df)
    result["feature_names"] = feature_names
    result["time_sec"] = time.time() - t0

    if "error" not in result:
        log.info(f"  Overall accuracy: {result['overall_accuracy']:.4f}")
        log.info(f"  Directional accuracy: {result['directional_accuracy']:.4f}")
        log.info(f"  Majority baseline: {result['majority_baseline']:.4f}")
        log.info(f"  Persistence baseline: {result['persistence_baseline']:.4f}")
        if result.get("pnl"):
            log.info(f"  Trading Sharpe: {result['pnl']['sharpe']:.2f}")
            log.info(f"  Total return: {result['pnl']['total_return']:.2%}")
            log.info(f"  Buy & hold return: {result['pnl']['buy_hold_return']:.2%}")
            log.info(f"  Win rate: {result['pnl']['win_rate']:.2%}")
            log.info(f"  Max drawdown: {result['pnl']['max_drawdown']:.2%}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Backtest production ML models")
    parser.add_argument("--ticker", type=str, help="Single ticker")
    parser.add_argument("--all", action="store_true", help="All tickers")
    parser.add_argument("--splits", type=int, default=8, help="Number of walk-forward splits")
    args = parser.parse_args()

    tickers = []
    if args.all:
        tickers = ["SPY", "QQQ", "DIA", "IWM", "TLT"]
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        parser.error("Specify --ticker or --all")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    all_results = {}
    for ticker in tickers:
        try:
            result = run_backtest(ticker, n_splits=args.splits)
            all_results[ticker] = result
        except Exception as e:
            log.error(f"Backtest failed for {ticker}: {e}", exc_info=True)
            all_results[ticker] = {"error": str(e)}

    # Summary
    log.info(f"\n{'=' * 70}")
    log.info("BACKTEST SUMMARY")
    log.info(f"{'=' * 70}")
    print(f"\n{'Ticker':<8} {'Model':<10} {'Acc':>8} {'DirAcc':>8} {'Base':>8} {'Sharpe':>8} {'Return':>10} {'B&H':>10} {'Win%':>8}")
    print("-" * 80)

    for ticker, r in all_results.items():
        if "error" in r:
            print(f"{ticker:<8} ERROR: {r['error'][:50]}")
        else:
            pnl = r.get("pnl", {})
            print(f"{ticker:<8} {r['model_type']:<10} {r['overall_accuracy']:>8.4f} {r.get('directional_accuracy', 0):>8.4f} {r['majority_baseline']:>8.4f} {pnl.get('sharpe', 0):>8.2f} {pnl.get('total_return', 0):>9.1%} {pnl.get('buy_hold_return', 0):>9.1%} {pnl.get('win_rate', 0):>7.1%}")

    # Save report
    report_path = REPORTS_DIR / f"backtest_production_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log.info(f"\nReport saved: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
