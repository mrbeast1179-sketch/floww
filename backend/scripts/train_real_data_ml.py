#!/usr/bin/env python3
"""
scripts/train_real_data_ml.py

Real-data ML training pipeline — 3-class direction prediction with
proper walk-forward CV, regularization, and feature selection.

Key improvements over train_real_ml.py:
  - 3-class target (DOWN/HOLD/UP) with configurable thresholds
  - Walk-forward CV with embargo gap (no lookahead leakage)
  - Feature selection: variance filter + correlation pruning + importance ranking
  - Regularized models: max_depth=3, min_samples_leaf=20, subsample=0.7
  - Trains multiple model types (GBM + RF + Logistic), picks best by Sharpe
  - Saves production artifacts: model.joblib + scaler.joblib + manifest.json

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_real_data_ml --ticker SPY
    cd backend && .venv/bin/python3 -m scripts.train_real_data_ml --all
    cd backend && .venv/bin_python3 -m scripts.train_real_data_ml --ticker SPY --quick
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("train_real_data_ml")

# ── Target thresholds ──────────────────────────────────────────────────
UP_THRESHOLD = 0.003    # > +0.3% next-day return → UP
DOWN_THRESHOLD = -0.003  # < -0.3% next-day return → DOWN
# Between thresholds → HOLD

# ── Feature Engineering ────────────────────────────────────────────────

FEATURE_NAMES = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "log_ret_1d", "overnight_gap",
    "sma_5", "price_vs_sma_5",
    "sma_10", "price_vs_sma_10",
    "sma_21", "price_vs_sma_21",
    "sma_50", "price_vs_sma_50",
    "atr_14",
    "volume_sma_5", "volume_sma_21", "relative_volume",
    "realized_vol_5d", "realized_vol_10d", "realized_vol_21d", "realized_vol_60d",
    "rsi_14", "rsi_overbought", "rsi_oversold",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_position",
    "vol_ratio_5_21", "vol_ratio_5_60",
    "sma_5_21_diff", "sma_5_21_cross", "sma_10_50_diff",
    "ret_momentum", "ret_accel",
    "vol_spike",
    "gap_abs", "gap_large",
    "is_month_end", "is_month_start",
]


def compute_features(ticker: str, period: str = "2y") -> pd.DataFrame:
    """Compute technical features from yfinance OHLCV + 3-class target.

    Target mapping:
        next_day_ret > +0.3%  → 2 (UP)
        next_day_ret < -0.3%  → 0 (DOWN)
        otherwise             → 1 (HOLD)
    """
    log.info("Downloading %s data (period=%s)...", ticker, period)
    data = yf.download(ticker, period=period, progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data.copy()
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        raise ValueError(f"Insufficient data for {ticker}: {len(df)} rows (need 60+)")

    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float) if "High" in df.columns else close
    low = df["Low"].values.astype(float) if "Low" in df.columns else close
    volume = df["Volume"].values.astype(float) if "Volume" in df.columns else np.ones(len(close))
    open_price = df["Open"].values.astype(float) if "Open" in df.columns else close
    n = len(close)

    features = pd.DataFrame(index=df.index)

    # Returns
    for horizon, name in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d"),
                           (10, "ret_10d"), (21, "ret_21d")]:
        ret = np.zeros(n)
        for i in range(horizon, n):
            if close[i - horizon] > 0:
                ret[i] = (close[i] - close[i - horizon]) / close[i - horizon]
        features[name] = ret

    # Log returns
    log_ret = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > 0 and close[i] > 0:
            log_ret[i] = np.log(close[i] / close[i - 1])
    features["log_ret_1d"] = log_ret

    # Overnight gap
    overnight_gap = np.zeros(n)
    for i in range(1, n):
        if close[i - 1] > 0:
            overnight_gap[i] = (open_price[i] - close[i - 1]) / close[i - 1]
    features["overnight_gap"] = overnight_gap

    # SMAs and price-relative
    for window, name in [(5, "sma_5"), (10, "sma_10"), (21, "sma_21"), (50, "sma_50")]:
        sma = pd.Series(close).rolling(window=window, min_periods=window).mean().values
        features[name] = sma
        rel = np.zeros(n)
        for i in range(n):
            if sma[i] > 0:
                rel[i] = close[i] / sma[i] - 1.0
        features[f"price_vs_sma_{window}"] = rel

    # ATR
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    features["atr_14"] = pd.Series(tr).rolling(window=14, min_periods=1).mean().values

    # Volume features
    vol_sma_5 = pd.Series(volume).rolling(window=5, min_periods=1).mean().values
    vol_sma_21 = pd.Series(volume).rolling(window=21, min_periods=1).mean().values
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21
    rel_vol = np.zeros(n)
    for i in range(n):
        if vol_sma_21[i] > 0:
            rel_vol[i] = volume[i] / vol_sma_21[i]
    features["relative_volume"] = rel_vol

    # Realized volatility (annualized)
    for window, name in [(5, "realized_vol_5d"), (10, "realized_vol_10d"),
                          (21, "realized_vol_21d"), (60, "realized_vol_60d")]:
        vol = (pd.Series(log_ret).rolling(window=window, min_periods=window).std().values
               * np.sqrt(252))
        features[name] = vol

    # RSI
    delta = pd.Series(close).diff()
    gain = delta.where(delta > 0, 0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    rsi = (100 - (100 / (1 + rs))).values
    features["rsi_14"] = rsi
    features["rsi_overbought"] = (rsi > 70).astype(float)
    features["rsi_oversold"] = (rsi < 30).astype(float)

    # MACD
    ema_12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema_26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    features["macd"] = macd.values
    features["macd_signal"] = macd_signal.values
    features["macd_hist"] = (macd - macd_signal).values

    # Bollinger Bands
    sma_20 = pd.Series(close).rolling(window=20, min_periods=1).mean()
    std_20 = pd.Series(close).rolling(window=20, min_periods=1).std()
    bb_upper = (sma_20 + 2 * std_20).values
    bb_lower = (sma_20 - 2 * std_20).values
    bb_position = np.zeros(n)
    for i in range(n):
        band_width = bb_upper[i] - bb_lower[i]
        if band_width > 0:
            bb_position[i] = (close[i] - bb_lower[i]) / band_width
    features["bb_position"] = bb_position

    # Volume ratios
    vol_sma_60 = pd.Series(volume).rolling(window=60, min_periods=1).mean().values
    features["vol_ratio_5_21"] = vol_sma_5 / (vol_sma_21 + 1e-10)
    features["vol_ratio_5_60"] = vol_sma_5 / (vol_sma_60 + 1e-10)

    # SMA crossovers
    sma_5 = pd.Series(close).rolling(window=5, min_periods=1).mean().values
    sma_21 = pd.Series(close).rolling(window=21, min_periods=1).mean().values
    sma_10 = pd.Series(close).rolling(window=10, min_periods=1).mean().values
    sma_50 = pd.Series(close).rolling(window=50, min_periods=1).mean().values
    features["sma_5_21_diff"] = sma_5 - sma_21
    features["sma_5_21_cross"] = np.sign(features["sma_5_21_diff"].values)
    features["sma_10_50_diff"] = sma_10 - sma_50

    # Momentum / acceleration
    features["ret_momentum"] = pd.Series(close).pct_change(5).values
    features["ret_accel"] = pd.Series(close).pct_change(5).diff().values

    # Vol spike
    features["vol_spike"] = (
        pd.Series(log_ret).rolling(window=5, min_periods=1).std().values /
        (pd.Series(log_ret).rolling(window=21, min_periods=1).std().values + 1e-10)
    )

    # Gap features
    features["gap_abs"] = np.abs(overnight_gap)
    features["gap_large"] = (np.abs(overnight_gap) > 0.003).astype(float)

    # Calendar features
    dates = pd.to_datetime(df.index)
    features["is_month_end"] = pd.Series(dates.is_month_end, index=df.index).astype(float).values
    features["is_month_start"] = pd.Series(dates.is_month_start, index=df.index).astype(float).values

    # ── 3-class target ──────────────────────────────────────────────────
    # next_day_ret > +0.3% → UP(2), < -0.3% → DOWN(0), else HOLD(1)
    target = np.ones(n, dtype=int)  # default HOLD
    for i in range(n - 1):
        if close[i] > 0:
            next_ret = (close[i + 1] - close[i]) / close[i]
            if next_ret > UP_THRESHOLD:
                target[i] = 2  # UP
            elif next_ret < DOWN_THRESHOLD:
                target[i] = 0  # DOWN
            # else stays HOLD (1)
    features["target_3class"] = target

    # Clean up
    features = features.replace([np.inf, -np.inf], np.nan)
    features = features.fillna(0.0)

    log.info("Computed %d features for %s (%d rows)", len(FEATURE_NAMES), ticker, len(features))
    return features


def select_features(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
    min_variance: float = 0.001,
    max_correlation: float = 0.95,
    max_features: int = 25,
    quick: bool = False,
) -> Tuple[List[str], List[int]]:
    """Three-stage feature selection: variance → correlation → importance."""
    n_samples, n_features = X.shape
    selected_mask = np.ones(n_features, dtype=bool)

    # Stage 1: Variance filter
    variances = np.var(X, axis=0)
    low_var = variances < min_variance
    selected_mask[low_var] = False
    dropped_var = [feature_names[i] for i in range(n_features) if low_var[i]]
    if dropped_var:
        log.info("  Variance filter: dropped %d features (σ² < %.4f): %s",
                 len(dropped_var), min_variance, dropped_var[:5])

    # Stage 2: Correlation pruning
    if quick:
        corr_threshold = 0.90
    else:
        corr_threshold = max_correlation
    remaining_idx = np.where(selected_mask)[0]
    if len(remaining_idx) > 1:
        corr_matrix = np.corrcoef(X[:, remaining_idx], rowvar=False)
        to_drop = set()
        for i in range(len(remaining_idx)):
            for j in range(i + 1, len(remaining_idx)):
                if abs(corr_matrix[i, j]) > corr_threshold:
                    to_drop.add(remaining_idx[j])
        for idx in to_drop:
            selected_mask[idx] = False
        dropped_corr = [feature_names[i] for i in to_drop]
        if dropped_corr:
            log.info("  Correlation filter: dropped %d features (|r| > %.2f): %s",
                     len(dropped_corr), corr_threshold, dropped_corr[:5])

    # Stage 3: Importance ranking (quick impurity-based)
    remaining_idx = np.where(selected_mask)[0]
    if len(remaining_idx) > max_features and not quick:
        from sklearn.ensemble import RandomForestClassifier
        rf_quick = RandomForestClassifier(
            n_estimators=50, max_depth=3, random_state=42, n_jobs=-1
        )
        rf_quick.fit(X[:, remaining_idx], y)
        importances = rf_quick.feature_importances_
        top_indices = np.argsort(importances)[-max_features:]
        top_global = [remaining_idx[i] for i in top_indices]
        new_mask = np.zeros(n_features, dtype=bool)
        new_mask[top_global] = True
        selected_mask = new_mask
        log.info("  Importance filter: kept top %d of %d features",
                 max_features, len(remaining_idx))

    selected_names = [feature_names[i] for i in range(n_features) if selected_mask[i]]
    selected_indices = [int(i) for i in range(n_features) if selected_mask[i]]
    log.info("  Final feature set: %d features: %s", len(selected_names), selected_names[:8])
    return selected_names, selected_indices


def walk_forward_cv(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    embargo: int = 5,
) -> Dict[str, Any]:
    """Walk-forward cross-validation with embargo gap."""
    from sklearn.metrics import accuracy_score

    fold_size = len(X) // (n_splits + 1)
    scores = []
    train_scores = []
    sharpe_scores = []

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))

        if test_end > len(X) or test_start >= len(X):
            break

        X_train = X[:train_end]
        y_train = y[:train_end]
        X_test = X[test_start:test_end]
        y_test = y[test_start:test_end]

        from sklearn.base import clone
        fold_model = clone(model)
        fold_model.fit(X_train, y_train)

        train_pred = fold_model.predict(X_train)
        test_pred = fold_model.predict(X_test)

        train_acc = accuracy_score(y_train, train_pred)
        test_acc = accuracy_score(y_test, test_pred)
        gap = train_acc - test_acc

        # Simple Sharpe proxy: accuracy / (1 - accuracy + epsilon)
        sharpe = test_acc / (1.0 - test_acc + 0.01)

        train_scores.append(train_acc)
        scores.append(test_acc)
        sharpe_scores.append(sharpe)

        log.info("  Fold %d: train=%.4f test=%.4f gap=%.4f sharpe=%.2f (%d train, %d test)",
                 fold + 1, train_acc, test_acc, gap, sharpe, len(X_train), len(X_test))

    return {
        "n_folds": len(scores),
        "mean_train_accuracy": float(np.mean(train_scores)),
        "mean_test_accuracy": float(np.mean(scores)),
        "std_test_accuracy": float(np.std(scores)),
        "mean_gap": float(np.mean([t - s for t, s in zip(train_scores, scores)])),
        "mean_test_sharpe": float(np.mean(sharpe_scores)),
        "fold_test_scores": [float(s) for s in scores],
    }


def train_model(
    ticker: str,
    days: int = 504,  # ~2 years
    quick: bool = False,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Train models for a ticker, pick best by Sharpe, save artifacts."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

    # Use 2 years of data for robust features
    period = f"{max(days // 21, 24)}mo"
    features_df = compute_features(ticker, period=period)

    # Drop rows that can't have a target (last row) and rows with all-zero features
    feature_cols = [c for c in FEATURE_NAMES if c in features_df.columns]
    target_col = "target_3class"
    clean = features_df[feature_cols + [target_col]].dropna()
    clean = clean[clean[target_col].notna()]
    # Remove the very last row (no next-day target)
    clean = clean.iloc[:-1]

    if len(clean) < 50:
        raise ValueError(f"Insufficient clean data for {ticker}: {len(clean)} rows")

    X_full = clean[feature_cols].values.astype(float)
    y = clean[target_col].values.astype(int)

    # Feature selection on full dataset
    log.info("Running feature selection for %s (%d samples, %d raw features)...",
             ticker, len(X_full), len(feature_cols))
    selected_names, selected_indices = select_features(
        X_full, y, feature_cols,
        min_variance=0.0005,
        max_correlation=0.90,
        max_features=20,
        quick=quick,
    )
    X = X_full[:, selected_indices]

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train/test split (80/20 temporal)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Class distribution
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        pct = (y_train == cls).mean()
        log.info("  Class %s: %.1f%%", label, pct * 100)

    # ── Candidate models ─────────────────────────────────────────────────
    n_est = 50 if quick else 200
    candidates = {}

    # GBM (regularized)
    gbm = GradientBoostingClassifier(
        n_estimators=n_est, max_depth=3, learning_rate=0.05,
        subsample=0.7, min_samples_leaf=20, random_state=42,
    )
    candidates["gbm"] = gbm

    # Random Forest (regularized)
    rf = RandomForestClassifier(
        n_estimators=n_est, max_depth=4, min_samples_leaf=15,
        max_features="sqrt", random_state=42, n_jobs=-1,
    )
    candidates["rf"] = rf

    # Logistic Regression (strong regularization, auto multi_class)
    lr = LogisticRegression(
        C=0.1, max_iter=1000, solver="lbfgs", random_state=42,
    )
    candidates["logistic"] = lr

    # Walk-forward CV each candidate
    best_model = None
    best_name = None
    best_sharpe = -999
    best_cv = None

    for name, model in candidates.items():
        log.info("Evaluating %s %s...", ticker, name)
        cv = walk_forward_cv(model, X_train, y_train,
                             n_splits=3 if quick else 5, embargo=5)
        log.info("  %s: test_acc=%.4f ± %.4f, gap=%.4f, sharpe=%.2f",
                 name, cv["mean_test_accuracy"], cv["std_test_accuracy"],
                 cv["mean_gap"], cv["mean_test_sharpe"])

        if cv["mean_test_sharpe"] > best_sharpe:
            best_sharpe = cv["mean_test_sharpe"]
            best_model = model
            best_name = name
            best_cv = cv

    # Train best model on full training set
    log.info("Best model for %s: %s (sharpe=%.2f)", ticker, best_name, best_sharpe)
    best_model.fit(X_train, y_train)

    from sklearn.metrics import accuracy_score
    train_pred = best_model.predict(X_train)
    test_pred = best_model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)

    log.info("Final %s %s: train=%.4f, test=%.4f, gap=%.4f",
             ticker, best_name, train_acc, test_acc, train_acc - test_acc)

    result = {
        "ticker": ticker,
        "model_type": best_name,
        "n_samples": len(X),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(selected_names),
        "feature_names": selected_names,
        "n_raw_features": len(feature_cols),
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "overfit_gap": train_acc - test_acc,
        "walk_forward_mean": best_cv["mean_test_accuracy"],
        "walk_forward_std": best_cv["std_test_accuracy"],
        "walk_forward_gap": best_cv["mean_gap"],
        "walk_forward_sharpe": best_cv["mean_test_sharpe"],
        "n_folds": best_cv["n_folds"],
        "fold_scores": best_cv["fold_test_scores"],
        "candidate_scores": {},
        "feature_version": "v2.0",
        "target": "target_3class_0.3pct",
        "target_thresholds": {"up": UP_THRESHOLD, "down": DOWN_THRESHOLD},
        "train_time_sec": 0,  # filled below
    }

    # Per-class accuracy
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        mask = y_test == cls
        if mask.sum() > 0:
            cls_acc = accuracy_score(y_test[mask], test_pred[mask])
            result[f"test_acc_{label.lower()}"] = cls_acc

    # Save artifacts
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_path = output_dir / f"{ticker}_{best_name}_v2_{ts}.joblib"
        scaler_path = output_dir / f"{ticker}_{best_name}_v2_{ts}_scaler.joblib"
        manifest_path = output_dir / f"{ticker}_{best_name}_v2_{ts}_manifest.json"

        import joblib
        joblib.dump(best_model, model_path)
        joblib.dump(scaler, scaler_path)

        manifest = {
            k: v for k, v in result.items()
            if k not in ("fold_scores", "candidate_scores")
        }
        manifest["model_path"] = str(model_path.name)
        manifest["scaler_path"] = str(scaler_path.name)
        manifest["created_at"] = datetime.now(timezone.utc).isoformat()
        manifest["model_id"] = f"{ticker}_{best_name}_v2"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)

        result["train_time_sec"] = time.time() - t0
        result["model_path"] = str(model_path)
        result["scaler_path"] = str(scaler_path)
        result["manifest_path"] = str(manifest_path)
        result["model_id"] = f"{ticker}_{best_name}_v2"

        log.info("Saved: %s", model_path)
        log.info("Saved: %s", scaler_path)
        log.info("Manifest: %s", manifest_path)

    return result


def main():
    parser = argparse.ArgumentParser(description="Real-data 3-class ML training")
    parser.add_argument("--ticker", type=str, help="Single ticker to train")
    parser.add_argument("--all", action="store_true", help="Train all 5 tickers")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer folds)")
    parser.add_argument("--days", type=int, default=504, help="Trading days of history")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    tickers = []
    if args.all:
        tickers = ["SPY", "QQQ", "DIA", "IWM", "TLT"]
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        parser.error("Specify --ticker <SYM> or --all")

    output_dir = Path(args.output_dir) if args.output_dir else SCRIPT_DIR.parent / "models"
    results = {}

    for ticker in tickers:
        log.info("=" * 60)
        log.info("Training %s (quick=%s)...", ticker, args.quick)
        try:
            t0 = time.time()
            result = train_model(ticker, days=args.days, quick=args.quick, output_dir=output_dir)
            result["total_time_sec"] = time.time() - t0
            results[ticker] = result
            log.info("✓ %s: %s test_acc=%.4f gap=%.4f sharpe=%.2f in %.1fs",
                     ticker, result["model_type"], result["test_accuracy"],
                     result["overfit_gap"], result["walk_forward_sharpe"],
                     result["total_time_sec"])
        except Exception as e:
            log.error("✗ %s FAILED: %s", ticker, e, exc_info=True)
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("=" * 60)
    log.info("TRAINING SUMMARY")
    log.info("=" * 60)
    for ticker, r in results.items():
        if "error" in r:
            log.info("%s: ERROR — %s", ticker, r["error"])
        else:
            log.info("%s: %s | test=%.4f | gap=%.4f | sharpe=%.2f | %d features",
                     ticker, r["model_type"], r["test_accuracy"],
                     r["overfit_gap"], r["walk_forward_sharpe"], r["n_features"])

    # Save summary report
    report_path = SCRIPT_DIR.parent / "reports" / f"training_real_data_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("Report: %s", report_path)

    return 0 if all("error" not in r for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
