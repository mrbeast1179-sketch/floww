#!/usr/bin/env python3
"""
scripts/train_gex_models.py

Train production ML models using the rich cached feature set (64 cols, 2799 rows).
Includes GEX, options chain data, and technical indicators.

Key differences from train_real_data_ml.py:
- Uses cached CSV features instead of yfinance download
- 64 raw features → feature selection → top 25-30
- 2799 rows per ticker (vs ~500 from yfinance)
- 3-class target derived from target_return_pct at ±0.3% thresholds
- Walk-forward CV with embargo for robust evaluation

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_gex_models --ticker QQQ
    cd backend && .venv/bin/python3 -m scripts.train_gex_models --all
"""

from __future__ import annotations

import argparse
import json
import logging
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
log = logging.getLogger("train_gex")

REPO_ROOT = SCRIPT_DIR.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"
REPORTS_DIR = SCRIPT_DIR.parent / "reports"
MODELS_DIR = SCRIPT_DIR.parent / "models"

UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003

# Columns to exclude from features
META_COLS = {"ticker", "date", "feature_version", "_computed_at", "_id", "spot_price"}
TARGET_COLS = {
    "target_directional_move", "target_return_pct", "target_gap_move",
    "target_range_expansion", "target_any_materialization",
}


def load_cached_features(ticker: str) -> pd.DataFrame:
    """Load and prepare cached features for a ticker."""
    for version in ["v1.0", "v1.5_gex_merged", "v2.0_gex"]:
        path = CACHE_DIR / f"{ticker}_{version}.csv"
        if path.exists():
            log.info(f"Loading {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MB)")
            df = pd.read_csv(path, parse_dates=["date"])
            df = df.sort_values("date").reset_index(drop=True)
            return df
    raise ValueError(f"No cached feature file for {ticker}")


def prepare_target(df: pd.DataFrame) -> pd.DataFrame:
    """Create 3-class target from target_return_pct."""
    if "target_return_pct" not in df.columns:
        raise ValueError("No target_return_pct column in cached data")

    df = df.copy()
    df["target_3class"] = 1  # default HOLD
    df.loc[df["target_return_pct"] > UP_THRESHOLD, "target_3class"] = 2   # UP
    df.loc[df["target_return_pct"] < DOWN_THRESHOLD, "target_3class"] = 0  # DOWN
    return df


def get_feature_cols(df: pd.DataFrame) -> list:
    """Get feature columns, excluding meta and target columns."""
    return [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS and c != "target_3class"]


def select_features(X: np.ndarray, y: np.ndarray, feature_names: list,
                     max_features: int = 25) -> tuple:
    """Quick feature selection: variance + correlation + importance."""
    n_samples, n_features = X.shape
    selected = np.ones(n_features, dtype=bool)

    # Variance filter
    variances = np.var(X, axis=0)
    selected[variances < 0.0005] = False

    # Correlation pruning
    remaining = np.where(selected)[0]
    if len(remaining) > 1:
        corr = np.corrcoef(X[:, remaining], rowvar=False)
        to_drop = set()
        for i in range(len(remaining)):
            for j in range(i + 1, len(remaining)):
                if abs(corr[i, j]) > 0.92:
                    to_drop.add(remaining[j])
        for idx in to_drop:
            selected[idx] = False

    # Importance ranking
    remaining = np.where(selected)[0]
    if len(remaining) > max_features:
        from sklearn.ensemble import RandomForestClassifier
        rf = RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42, n_jobs=-1)
        rf.fit(X[:, remaining], y)
        top = np.argsort(rf.feature_importances_)[-max_features:]
        new_sel = np.zeros(n_features, dtype=bool)
        for idx in top:
            new_sel[remaining[idx]] = True
        selected = new_sel

    names = [feature_names[i] for i in range(n_features) if selected[i]]
    indices = [int(i) for i in range(n_features) if selected[i]]
    log.info(f"Selected {len(names)} features from {n_features}")
    return names, indices


def walk_forward_cv(model, X, y, n_splits=5, embargo=5):
    """Walk-forward cross-validation."""
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score

    fold_size = len(X) // (n_splits + 1)
    scores = []
    train_scores = []

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))
        if test_end > len(X) or test_start >= len(X):
            break

        X_tr, X_te = X[:train_end], X[test_start:test_end]
        y_tr, y_te = y[:train_end], y[test_start:test_end]

        try:
            m = clone(model)
            m.fit(X_tr, y_tr)
            te_pred = m.predict(X_te)
            tr_pred = m.predict(X_tr)
            te_acc = accuracy_score(y_te, te_pred)
            tr_acc = accuracy_score(y_tr, tr_pred)
            scores.append(te_acc)
            train_scores.append(tr_acc)
            log.info(f"  Fold {fold+1}: train={tr_acc:.4f} test={te_acc:.4f} gap={tr_acc-te_acc:.4f}")
        except Exception as e:
            log.warning(f"  Fold {fold+1}: failed: {e}")

    if not scores:
        return {"error": "no valid folds"}

    return {
        "n_folds": len(scores),
        "mean_train": float(np.mean(train_scores)),
        "mean_test": float(np.mean(scores)),
        "std_test": float(np.std(scores)),
        "mean_gap": float(np.mean([t - s for t, s in zip(train_scores, scores, strict=False)])),
    }


def train_ticker(ticker: str, output_dir: Path = None) -> dict:
    """Train models for a ticker using cached features."""
    output_dir = output_dir or MODELS_DIR
    log.info(f"{'=' * 60}")
    log.info(f"Training {ticker} with GEX features...")
    t0 = time.time()

    # Load data
    df = load_cached_features(ticker)
    df = prepare_target(df)

    # Remove rows with NaN target
    df = df.dropna(subset=["target_3class", "target_return_pct"])

    feature_cols = get_feature_cols(df)
    log.info(f"  {len(df)} rows, {len(feature_cols)} raw features")

    # Class balance
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        pct = (df["target_3class"] == cls).mean()
        log.info(f"  {label}: {pct:.1%}")

    X_full = df[feature_cols].values.astype(float)
    y = df["target_3class"].values.astype(int)

    # Train/test split FIRST — prevent leakage
    split_idx = int(len(X_full) * 0.8)
    X_full_train, X_full_test = X_full[:split_idx], X_full[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Feature selection on train-only (no leakage)
    selected_names, selected_idx = select_features(X_full_train, y_train, feature_cols, max_features=25)

    X_train_sel = X_full_train[:, selected_idx]
    X_test_sel = X_full_test[:, selected_idx]

    # Scale on train-only (no leakage), then transform test
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train_sel)
    X_test = scaler.transform(X_test_sel)

    # Candidate models
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    candidates = {
        "rf": RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=15,
                                      max_features="sqrt", random_state=42, n_jobs=-1),
        "gbm": GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                           subsample=0.7, min_samples_leaf=20, random_state=42),
        "logistic": LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42),
    }

    best_model = None
    best_name = None
    best_score = -999
    best_cv = None

    for name, model in candidates.items():
        log.info(f"Evaluating {name}...")
        cv = walk_forward_cv(model, X_train, y_train, n_splits=5, embargo=5)
        if "error" in cv:
            continue
        log.info(f"  {name}: test={cv['mean_test']:.4f} gap={cv['mean_gap']:.4f}")
        if cv["mean_test"] > best_score:
            best_score = cv["mean_test"]
            best_model = model
            best_name = name
            best_cv = cv

    if best_model is None:
        return {"error": "no model trained successfully"}

    # Train best on full training set
    log.info(f"Best: {best_name} (OOS acc={best_score:.4f})")
    best_model.fit(X_train, y_train)

    from sklearn.metrics import accuracy_score
    train_acc = accuracy_score(y_train, best_model.predict(X_train))
    test_acc = accuracy_score(y_test, best_model.predict(X_test))

    log.info(f"Final: train={train_acc:.4f} test={test_acc:.4f} gap={train_acc-test_acc:.4f}")

    # Per-class accuracy
    test_pred = best_model.predict(X_test)
    per_class = {}
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        mask = y_test == cls
        if mask.sum() > 0:
            per_class[label] = {
                "accuracy": float(accuracy_score(y_test[mask], test_pred[mask])),
                "support": int(mask.sum()),
            }

    result = {
        "ticker": ticker,
        "model_type": best_name,
        "n_samples": len(X_train) + len(X_test),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(selected_names),
        "n_raw_features": len(feature_cols),
        "feature_names": selected_names,
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "overfit_gap": train_acc - test_acc,
        "walk_forward_mean": best_cv["mean_test"],
        "walk_forward_std": best_cv["std_test"],
        "walk_forward_gap": best_cv["mean_gap"],
        "n_folds": best_cv["n_folds"],
        "per_class_test": per_class,
        "feature_version": "v3.0_gex",
        "target": "target_3class_0.3pct",
        "time_sec": time.time() - t0,
    }

    # Save artifacts
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    model_path = output_dir / f"{ticker}_{best_name}_gex_{ts}.joblib"
    scaler_path = output_dir / f"{ticker}_{best_name}_gex_{ts}_scaler.joblib"
    manifest_path = output_dir / f"{ticker}_{best_name}_gex_{ts}_manifest.json"

    joblib.dump(best_model, model_path)
    joblib.dump(scaler, scaler_path)

    manifest = {k: v for k, v in result.items() if k != "fold_scores"}
    manifest["model_path"] = str(model_path.name)
    manifest["scaler_path"] = str(scaler_path.name)
    manifest["created_at"] = datetime.now(UTC).isoformat()
    manifest["model_id"] = f"{ticker}_{best_name}_gex_v3"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    result["model_path"] = str(model_path)
    result["scaler_path"] = str(scaler_path)
    result["manifest_path"] = str(manifest_path)
    result["model_id"] = f"{ticker}_{best_name}_gex_v3"

    log.info(f"Saved: {model_path.name}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Train ML models with GEX features")
    parser.add_argument("--ticker", type=str)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    tickers = ["QQQ", "DIA", "IWM", "TLT"] if args.all else [args.ticker.upper()]

    results = {}
    for ticker in tickers:
        try:
            results[ticker] = train_ticker(ticker)
        except Exception as e:
            log.error(f"{ticker} FAILED: {e}", exc_info=True)
            results[ticker] = {"error": str(e)}

    # Summary
    log.info(f"\n{'=' * 70}")
    log.info("GEX TRAINING SUMMARY")
    log.info(f"{'=' * 70}")
    print(f"\n{'Ticker':<8} {'Model':<10} {'Test':>8} {'Gap':>8} {'Features':>10} {'Time':>8}")
    print("-" * 70)
    for ticker, r in results.items():
        if "error" in r:
            print(f"{ticker:<8} ERROR: {r['error'][:40]}")
        else:
            print(f"{ticker:<8} {r['model_type']:<10} {r['test_accuracy']:>8.4f} {r['overfit_gap']:>8.4f} {r['n_features']:>10} {r['time_sec']:>7.1f}s")

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"training_gex_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info(f"Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
