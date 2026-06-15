#!/usr/bin/env python3
"""
scripts/train_real_data_v2.py

Real-data ML training pipeline v2 — trains on cached feature CSVs with:
- 3-class target (DOWN/HOLD/UP) using configurable thresholds
- Walk-forward CV with embargo gap
- Feature selection: variance filter + correlation pruning + importance ranking
- Multiple model types: RF, GBM, Logistic
- Per-ticker best model selection by walk-forward Sharpe
- Saves production artifacts: model.joblib + scaler.joblib + manifest.json
- Generates training report

Data sources (auto-detected per ticker):
  SPY -> data/cached_features/SPY_v1.5_gex_merged.csv (70 features, 244 rows, GEX)
  Others -> data/cached_features/{TICKER}_v1.0.csv (53 features, 2799 rows)

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_real_data_v2 --ticker SPY
    cd backend && .venv/bin/python3 -m scripts.train_real_data_v2 --all
    cd backend && .venv/bin/python3 -m scripts.train_real_data_v2 --ticker SPY --quick
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("train_real_data_v2")

# ── Configuration ──────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cached_features"
MODELS_DIR = SCRIPT_DIR.parent / "models"
REPORTS_DIR = REPO_ROOT / "reports"

# Target: 3-class from directional move (binary -> 3-class via return magnitude)
UP_THRESHOLD = 0.003    # > +0.3% next-day return → UP
DOWN_THRESHOLD = -0.003  # < -0.3% next-day return → DOWN

# Meta columns to exclude from features
META_COLS = {"day", "date", "ticker", "feature_version", "_computed_at", "spot", "spot_price"}
TARGET_COLS = {
    "target_directional_move", "target_return_pct", "target_gap_move",
    "target_range_expansion", "target_any_materialization",
}

# Model hyperparameters
RF_PARAMS = dict(
    n_estimators=200, max_depth=4, min_samples_leaf=15,
    max_features="sqrt", random_state=42, n_jobs=-1,
)
GBM_PARAMS = dict(
    n_estimators=200, max_depth=3, learning_rate=0.05,
    subsample=0.7, min_samples_leaf=20, random_state=42,
)
LR_PARAMS = dict(C=0.1, max_iter=1000, solver="lbfgs", random_state=42)


def load_data(ticker: str) -> tuple[pd.DataFrame, str]:
    """Load the best available cached feature dataset for a ticker."""
    ticker = ticker.upper()

    # Priority: v1.5_gex_merged > v2.0_gex > v1.0
    candidates = [
        CACHE_DIR / f"{ticker}_v1.5_gex_merged.csv",
        CACHE_DIR / f"{ticker}_v2.0_gex.csv",
        CACHE_DIR / f"{ticker}_v1.0.csv",
    ]

    for path in candidates:
        if path.exists():
            log.info("Loading %s (%d rows)", path.name, sum(1 for _ in open(path)) - 1)
            df = pd.read_csv(path)
            # Sort by date
            date_col = "date" if "date" in df.columns else "day"
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col).reset_index(drop=True)
            return df, path.stem

    raise FileNotFoundError(f"No cached data found for {ticker} in {CACHE_DIR}")


def prepare_target(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Create 3-class target from available target columns.

    Strategy:
    - If target_return_pct exists: use thresholds directly
    - If target_directional_move exists: map 0→DOWN, 1→UP, add HOLD band
    """
    if "target_return_pct" in df.columns:
        ret = df["target_return_pct"]
        target = pd.Series(1, index=df.index, dtype=int)  # default HOLD
        target = target.where(~ret.gt(UP_THRESHOLD), 2)   # UP
        target = target.where(~ret.lt(DOWN_THRESHOLD), 0)  # DOWN
        df["target_3class"] = target
        return df, "target_return_pct_thresholded"

    if "target_directional_move" in df.columns:
        # Binary → 3-class: use return magnitude for HOLD band
        if "target_return_pct" in df.columns:
            ret = df["target_return_pct"]
            direction = df["target_directional_move"]
            target = pd.Series(1, index=df.index, dtype=int)
            target = target.where(~((direction == 1) & (ret > UP_THRESHOLD)), 2)
            target = target.where(~((direction == 0) & (ret < DOWN_THRESHOLD)), 0)
        else:
            # No return magnitude: map binary to 3-class with HOLD=majority
            direction = df["target_directional_move"]
            target = pd.Series(1, index=df.index, dtype=int)
            target = direction.where(direction.isin([0, 2]), 1)
            target = target.where(direction != 1, 2)   # 1 → UP
            target = target.where(direction != 0, 0)   # 0 → DOWN
        df["target_3class"] = target
        return df, "target_directional_move_mapped"

    raise ValueError("No suitable target column found")


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Extract feature columns, excluding meta and target columns."""
    exclude = META_COLS | TARGET_COLS | {"target_3class"}
    return [c for c in df.columns if c not in exclude]


def select_features(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: list[str],
    min_variance: float = 0.0005,
    max_correlation: float = 0.90,
    max_features: int = 25,
) -> tuple[list[str], list[int]]:
    """Three-stage feature selection: variance → correlation → importance."""
    n_samples, n_features = X.shape
    selected_mask = np.ones(n_features, dtype=bool)

    # Stage 1: Variance filter
    variances = np.var(X, axis=0)
    low_var = variances < min_variance
    selected_mask[low_var] = False
    dropped = [feature_names[i] for i in range(n_features) if low_var[i]]
    if dropped:
        log.info("  Variance filter: dropped %d: %s", len(dropped), dropped[:5])

    # Stage 2: Correlation pruning
    remaining_idx = np.where(selected_mask)[0]
    if len(remaining_idx) > 1:
        corr_matrix = np.corrcoef(X[:, remaining_idx], rowvar=False)
        to_drop = set()
        for i in range(len(remaining_idx)):
            for j in range(i + 1, len(remaining_idx)):
                if abs(corr_matrix[i, j]) > max_correlation:
                    to_drop.add(remaining_idx[j])
        for idx in to_drop:
            selected_mask[idx] = False
        dropped = [feature_names[i] for i in to_drop]
        if dropped:
            log.info("  Correlation filter: dropped %d: %s", len(dropped), dropped[:5])

    # Stage 3: Importance ranking
    remaining_idx = np.where(selected_mask)[0]
    if len(remaining_idx) > max_features:
        from sklearn.ensemble import RandomForestClassifier
        rf_quick = RandomForestClassifier(
            n_estimators=50, max_depth=3, random_state=42, n_jobs=-1,
        )
        rf_quick.fit(X[:, remaining_idx], y)
        importances = rf_quick.feature_importances_
        top_indices = np.argsort(importances)[-max_features:]
        top_global = [remaining_idx[i] for i in top_indices]
        new_mask = np.zeros(n_features, dtype=bool)
        new_mask[top_global] = True
        selected_mask = new_mask
        log.info("  Importance filter: kept top %d of %d", max_features, len(remaining_idx))

    selected_names = [feature_names[i] for i in range(n_features) if selected_mask[i]]
    selected_indices = [int(i) for i in range(n_features) if selected_mask[i]]
    log.info("  Final: %d features: %s", len(selected_names), selected_names[:10])
    return selected_names, selected_indices


def walk_forward_cv(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    n_splits: int = 5,
    embargo: int = 5,
) -> dict[str, Any]:
    """Walk-forward CV with embargo. Returns per-fold metrics."""
    from sklearn.metrics import accuracy_score
    from sklearn.base import clone

    fold_size = len(X) // (n_splits + 1)
    scores = []
    train_scores = []
    sharpes = []

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

        fold_model = clone(model)
        fold_model.fit(X_train, y_train)

        train_pred = fold_model.predict(X_train)
        test_pred = fold_model.predict(X_test)

        train_acc = accuracy_score(y_train, train_pred)
        test_acc = accuracy_score(y_test, test_pred)

        # Trading Sharpe: long when pred=UP, short when pred=DOWN, flat HOLD
        rets = []
        for pred, actual in zip(test_pred, y_test):
            if pred == 2:  # UP
                rets.append(1.0 if actual == 2 else -1.0)
            elif pred == 0:  # DOWN
                rets.append(-1.0 if actual == 0 else 1.0)
            else:
                rets.append(0.0)
        sharpe = float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))

        train_scores.append(train_acc)
        scores.append(test_acc)
        sharpes.append(sharpe)

        log.info(
            "  Fold %d: train=%.4f test=%.4f sharpe=%.3f (%d train, %d test)",
            fold + 1, train_acc, test_acc, sharpe, len(X_train), len(X_test),
        )

    return {
        "n_folds": len(scores),
        "mean_train_accuracy": float(np.mean(train_scores)) if train_scores else 0.0,
        "mean_test_accuracy": float(np.mean(scores)) if scores else 0.0,
        "std_test_accuracy": float(np.std(scores)) if scores else 0.0,
        "mean_sharpe": float(np.mean(sharpes)) if sharpes else 0.0,
        "mean_gap": float(np.mean([t - s for t, s in zip(train_scores, scores, strict=False)])) if scores else 0.0,
        "fold_test_scores": [float(s) for s in scores],
        "fold_sharpes": [float(s) for s in sharpes],
    }


def train_ticker(ticker: str, quick: bool = False) -> dict[str, Any]:
    """Full training pipeline for a single ticker."""
    log.info("=" * 60)
    log.info("Training %s", ticker)
    t0 = time.time()

    # Load data
    df, dataset_name = load_data(ticker)
    log.info("Dataset: %s (%d rows, %d cols)", dataset_name, len(df), len(df.columns))

    # Prepare target
    df, target_method = prepare_target(df)
    y = df["target_3class"].values.astype(int)
    log.info("Target: %s", target_method)
    for cls, label in [(0, "DOWN"), (1, "HOLD"), (2, "UP")]:
        pct = (y == cls).mean()
        log.info("  %s: %.1f%% (%d samples)", label, pct * 100, (y == cls).sum())

    # Get feature columns
    feature_cols = get_feature_columns(df)
    log.info("Raw features: %d", len(feature_cols))

    # Drop rows with NaN in features or target
    clean = df[feature_cols + ["target_3class"]].copy()
    # Fill feature NaNs with 0 (features are already normalized/centered)
    clean[feature_cols] = clean[feature_cols].fillna(0.0)
    # Only drop rows where target is NaN
    clean = clean.dropna(subset=["target_3class"])
    # Remove last row (no next-day target)
    clean = clean.iloc[:-1]
    log.info("Clean rows: %d", len(clean))

    if len(clean) < 50:
        raise ValueError(f"Insufficient data: {len(clean)} rows")

    X_full = clean[feature_cols].values.astype(float)
    y = clean["target_3class"].values.astype(int)

    # Temporal train/test split (80/20)
    split_idx = int(len(X_full) * 0.8)
    X_train_full, X_test = X_full[:split_idx], X_full[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    log.info("Train: %d, Test: %d", len(X_train_full), len(X_test))

    # Feature selection on train only
    log.info("Feature selection...")
    selected_names, selected_indices = select_features(
        X_train_full, y_train, feature_cols,
        min_variance=0.0005,
        max_correlation=0.90,
        max_features=min(25, len(feature_cols)),
    )

    X_train_sel = X_train_full[:, selected_indices]
    X_test_sel = X_test[:, selected_indices]

    # Scale
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train_sel)
    X_test = scaler.transform(X_test_sel)

    # Candidate models
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    n_est = 50 if quick else 200
    candidates = {
        "rf": RandomForestClassifier(
            n_estimators=n_est, max_depth=4, min_samples_leaf=15,
            max_features="sqrt", random_state=42, n_jobs=-1,
        ),
        "gbm": GradientBoostingClassifier(
            n_estimators=n_est, max_depth=3, learning_rate=0.05,
            subsample=0.7, min_samples_leaf=20, random_state=42,
        ),
        "logistic": LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42),
    }

    # Walk-forward CV for each candidate
    best_model = None
    best_name = None
    best_score = -999
    best_cv = None

    for name, model in candidates.items():
        log.info("Evaluating %s...", name)
        cv = walk_forward_cv(model, X_train, y_train, n_splits=3 if quick else 5, embargo=5)
        log.info("  %s: test_acc=%.4f ± %.4f, sharpe=%.3f, gap=%.4f",
                 name, cv["mean_test_accuracy"], cv["std_test_accuracy"],
                 cv["mean_sharpe"], cv["mean_gap"])

        # Select by Sharpe (primary) and accuracy (tiebreaker)
        score = cv["mean_sharpe"] + cv["mean_test_accuracy"]
        if score > best_score:
            best_score = score
            best_model = model
            best_name = name
            best_cv = cv

    # Train best on full training set
    log.info("Best: %s (score=%.4f)", best_name, best_score)
    best_model.fit(X_train, y_train)

    from sklearn.metrics import accuracy_score, classification_report
    train_pred = best_model.predict(X_train)
    test_pred = best_model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)

    log.info("Final: train=%.4f, test=%.4f, gap=%.4f", train_acc, test_acc, train_acc - test_acc)
    log.info("\n%s", classification_report(y_test, test_pred, target_names=["DOWN", "HOLD", "UP"]))

    # Trading Sharpe on test set
    rets = []
    for pred, actual in zip(test_pred, y_test):
        if pred == 2:
            rets.append(1.0 if actual == 2 else -1.0)
        elif pred == 0:
            rets.append(-1.0 if actual == 0 else 1.0)
        else:
            rets.append(0.0)
    test_sharpe = float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))

    # Baselines
    majority_cls = int(pd.Series(y_train).mode().iloc[0])
    majority_acc = accuracy_score(y_test, [majority_cls] * len(y_test))
    persistence_preds = np.roll(y_test, 1)
    persistence_preds[0] = y_test[0]
    persistence_acc = accuracy_score(y_test, persistence_preds)

    train_time = time.time() - t0
    log.info("Training time: %.1fs", train_time)

    result = {
        "ticker": ticker,
        "dataset": dataset_name,
        "model_type": best_name,
        "n_samples": len(X_train) + len(X_test),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "n_features": len(selected_names),
        "feature_names": selected_names,
        "n_raw_features": len(feature_cols),
        "train_accuracy": train_acc,
        "test_accuracy": test_acc,
        "test_sharpe": test_sharpe,
        "overfit_gap": train_acc - test_acc,
        "walk_forward_mean_acc": best_cv["mean_test_accuracy"],
        "walk_forward_std_acc": best_cv["std_test_accuracy"],
        "walk_forward_mean_sharpe": best_cv["mean_sharpe"],
        "walk_forward_gap": best_cv["mean_gap"],
        "n_folds": best_cv["n_folds"],
        "fold_scores": best_cv["fold_test_scores"],
        "fold_sharpes": best_cv["fold_sharpes"],
        "majority_baseline": majority_acc,
        "persistence_baseline": persistence_acc,
        "beats_majority": test_acc > majority_acc,
        "beats_persistence": test_acc > persistence_acc,
        "target_method": target_method,
        "train_time_sec": round(train_time, 1),
    }

    # Save artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    model_path = MODELS_DIR / f"{ticker}_{best_name}_3class_{ts}.joblib"
    scaler_path = MODELS_DIR / f"{ticker}_{best_name}_3class_{ts}_scaler.joblib"
    manifest_path = MODELS_DIR / f"{ticker}_{best_name}_3class_{ts}_manifest.json"

    import joblib
    joblib.dump(best_model, model_path)
    joblib.dump(scaler, scaler_path)

    manifest = {k: v for k, v in result.items() if k not in ("fold_scores", "fold_sharpes")}
    manifest["model_path"] = str(model_path)
    manifest["scaler_path"] = str(scaler_path)
    manifest["created_at"] = datetime.now(UTC).isoformat()
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    log.info("Saved: %s", model_path.name)
    log.info("Saved: %s", scaler_path.name)
    log.info("Saved: %s", manifest_path.name)

    result["model_path"] = str(model_path)
    result["scaler_path"] = str(scaler_path)
    result["manifest_path"] = str(manifest_path)
    return result


def main():
    parser = argparse.ArgumentParser(description="Train real-data ML models v2")
    parser.add_argument("--ticker", type=str, default=None, help="Single ticker to train")
    parser.add_argument("--all", action="store_true", help="Train all tickers")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer estimators)")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else ["SPY", "QQQ", "DIA", "IWM", "TLT"]

    results = {}
    for ticker in tickers:
        try:
            results[ticker] = train_ticker(ticker, quick=args.quick)
        except Exception as e:
            log.error("Failed to train %s: %s", ticker, e, exc_info=True)
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("\n" + "=" * 60)
    log.info("TRAINING SUMMARY")
    log.info("=" * 60)
    for ticker, r in sorted(results.items()):
        if "error" in r:
            log.info("%s: ERROR - %s", ticker, r["error"])
        else:
            log.info(
                "%s: %s | test_acc=%.4f | sharpe=%.3f | beats_maj=%s | %d features",
                ticker, r["model_type"], r["test_accuracy"], r["test_sharpe"],
                r["beats_majority"], r["n_features"],
            )

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"training_real_data_v2_{ts}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("Report: %s", report_path)

    return results


if __name__ == "__main__":
    main()
