#!/usr/bin/env python3
"""
scripts/backtest_ml_regime.py

Regime-filtered ML backtest.
Tests whether adding a trend-following regime filter improves the strategy
by avoiding counter-trend trades (the key finding from the NEXT_TASKS analysis).

The filter: only take long signals when price > SMA_21 (uptrend),
only take short signals when price < SMA_21 (downtrend).
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # /Users/nav/GitHub/floww
BACKEND_ROOT = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data" / "cached_features"
MODELS_DIR = PROJECT_ROOT / "models"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

META_COLS = {
    "ticker", "date", "day", "feature_version", "_computed_at",
    "target_directional_move", "target_return_pct",
    "target_range_expansion", "target_gap_move", "target_any_materialization",
}

MODEL_PARAMS = {
    "n_estimators": 200, "max_depth": 5, "learning_rate": 0.05,
    "subsample": 0.8, "min_samples_leaf": 10, "random_state": 42,
}

WINDOW_SIZE = 500
STEP_SIZE = 63


def load_data(ticker: str) -> tuple[pd.DataFrame, list[str]]:
    path = DATA_DIR / f"{ticker}_v1.0.csv"
    if not path.exists():
        raise FileNotFoundError(f"No data: {path}")
    df = pd.read_csv(path).sort_values(by="date").reset_index(drop=True)
    feats = [c for c in df.columns if c not in META_COLS]
    return df, feats


def add_derived(df: pd.DataFrame, feats: list[str]) -> tuple[pd.DataFrame, list[str]]:
    f = list(feats)
    if "realized_vol_5d" in df.columns and "realized_vol_21d" in df.columns:
        df["vol_ratio_5_21"] = df["realized_vol_5d"] / (df["realized_vol_21d"] + 1e-8)
        f.append("vol_ratio_5_21")
    if "sma_5" in df.columns and "sma_21" in df.columns:
        df["sma_5_21_diff"] = df["sma_5"] - df["sma_21"]
        df["sma_5_21_cross"] = (df["sma_5_21_diff"] > 0).astype(float)
        f.extend(["sma_5_21_diff", "sma_5_21_cross"])
    if "sma_10" in df.columns and "sma_50" in df.columns:
        df["sma_10_50_diff"] = df["sma_10"] - df["sma_50"]
        f.append("sma_10_50_diff")
    if "rsi_14" in df.columns:
        df["rsi_overbought"] = (df["rsi_14"] > 70).astype(float)
        df["rsi_oversold"] = (df["rsi_14"] < 30).astype(float)
        f.extend(["rsi_overbought", "rsi_oversold"])
    if "ret_1d" in df.columns and "ret_3d" in df.columns:
        df["ret_momentum"] = df["ret_3d"] - df["ret_1d"]
        f.append("ret_momentum")
    if "ret_5d" in df.columns and "ret_3d" in df.columns:
        df["ret_accel"] = df["ret_5d"] - df["ret_3d"]
        f.append("ret_accel")
    if "overnight_gap" in df.columns:
        df["gap_abs"] = df["overnight_gap"].abs()
        f.append("gap_abs")
    return df, f


def run_backtest(
    ticker: str,
    df: pd.DataFrame,
    feature_names: list[str],
    regime_filter: bool = False,
) -> dict:
    """Run walk-forward backtest with optional regime filter."""
    X = df[feature_names].values.astype(np.float64)
    y = df["target_directional_move"].values.astype(np.float64)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    # Regime filter: price vs SMA_21
    if regime_filter and "price_vs_sma_21" in df.columns:
        regime = df["price_vs_sma_21"].values  # positive = uptrend
    else:
        regime = None

    n = len(X)
    folds = []
    all_preds = []
    all_actuals = []
    all_returns = []
    filtered_trades = 0
    total_trades = 0

    for start in range(0, n - WINDOW_SIZE - STEP_SIZE, STEP_SIZE):
        train_end = start + WINDOW_SIZE
        test_end = min(train_end + STEP_SIZE, n)
        if train_end < 200 or len(X[test_end - train_end:]) < 10:
            continue

        X_train = X[start:train_end]
        y_train = y[start:train_end]
        X_test = X[train_end:test_end]
        y_test = y[train_end:test_end]

        unique, counts = np.unique(y_train, return_counts=True)
        if len(unique) < 2 or min(counts) / len(y_train) < 0.1:
            continue

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = GradientBoostingClassifier(**MODEL_PARAMS)
        model.fit(X_train_s, y_train)
        y_pred = model.predict(X_test_s)

        # Apply regime filter
        if regime is not None:
            test_regime = regime[train_end:test_end]
            for i in range(len(y_pred)):
                total_trades += 1
                # If predicting up (1) but in downtrend (regime < 0), skip
                # If predicting down (0) but inuptrend (regime > 0), skip
                if (y_pred[i] == 1 and test_regime[i] < 0) or \
                   (y_pred[i] == 0 and test_regime[i] > 0):
                    filtered_trades += 1
                    # Set to "no trade" — use the regime direction instead
                    y_pred[i] = 1 if test_regime[i] > 0 else 0

        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        # Simulate returns: if prediction matches direction, collect return
        if "target_return_pct" in df.columns:
            returns = df["target_return_pct"].values[train_end:test_end]
            # Long when pred=1, short when pred=0
            strat_returns = [r if p == 1 else -r for p, r in zip(y_pred, returns)]
            all_returns.extend(strat_returns)

        folds.append({
            "fold": len(folds), "accuracy": float(acc), "f1": float(f1),
            "test_size": int(len(X_test)),
        })
        all_preds.extend(y_pred.tolist())
        all_actuals.extend(y_test.tolist())

    if not folds:
        return {"status": "no_valid_folds"}

    all_preds = np.array(all_preds)
    all_actuals = np.array(all_actuals)

    result = {
        "status": "ok",
        "ticker": ticker,
        "regime_filter": regime_filter,
        "n_folds": len(folds),
        "mean_accuracy": float(np.mean([f["accuracy"] for f in folds])),
        "std_accuracy": float(np.std([f["accuracy"] for f in folds])),
        "mean_f1": float(np.mean([f["f1"] for f in folds])),
        "overall_accuracy": float(accuracy_score(all_actuals, all_preds)),
        "overall_f1": float(f1_score(all_actuals, all_preds, zero_division=0)),
        "filtered_trades": filtered_trades,
        "total_trades": total_trades,
    }

    if all_returns:
        rets = np.array(all_returns)
        result["total_return"] = float(np.sum(rets))
        result["mean_return_per_trade"] = float(np.mean(rets))
        result["std_return"] = float(np.std(rets))
        result["sharpe"] = float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))
        result["win_rate"] = float(np.mean(rets > 0))
        result["n_trades"] = len(rets)

    return result


def main():
    tickers = ["QQQ", "DIA"]
    results = {}

    for ticker in tickers:
        logger.info(f"\n{'='*50}\n{ticker}\n{'='*50}")
        df, feats = load_data(ticker)
        df, feats = add_derived(df, feats)

        # Drop zero-variance
        X = df[feats].values.astype(np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        valid = np.var(X, axis=0) > 1e-6
        feats = [f for f, v in zip(feats, valid) if v]

        # Without regime filter
        logger.info("Running WITHOUT regime filter...")
        r_no_filter = run_backtest(ticker, df, feats, regime_filter=False)
        results[f"{ticker}_no_filter"] = r_no_filter

        # With regime filter
        logger.info("Running WITH regime filter...")
        r_filter = run_backtest(ticker, df, feats, regime_filter=True)
        results[f"{ticker}_regime_filter"] = r_filter

        # Print comparison
        for key, r in [(f"{ticker}_no_filter", r_no_filter), (f"{ticker}_regime_filter", r_filter)]:
            if r["status"] == "ok":
                logger.info(f"\n  {key}:")
                logger.info(f"    Accuracy: {r['overall_accuracy']:.4f}, F1: {r['overall_f1']:.4f}")
                if "total_return" in r:
                    logger.info(f"    Total return: {r['total_return']:.4f}")
                    logger.info(f"    Mean ret/trade: {r['mean_return_per_trade']:.4f}")
                    logger.info(f"    Sharpe: {r['sharpe']:.2f}")
                    logger.info(f"    Win rate: {r['win_rate']:.4f}")
                    logger.info(f"    N trades: {r['n_trades']}")
                if r.get("filtered_trades", 0) > 0:
                    logger.info(f"    Filtered trades: {r['filtered_trades']}/{r['total_trades']}")

    # Save results
    out_path = PROJECT_ROOT / "reports" / "backtest_regime_filter.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"\nResults saved to {out_path}")

    return results


if __name__ == "__main__":
    main()
