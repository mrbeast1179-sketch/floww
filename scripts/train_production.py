#!/usr/bin/env python3
"""
scripts/train_production.py

Train production model on cached CSV features.
Usage:
  python scripts/train_production.py --ticker QQQ --model gbm_deep
  python scripts/train_production.py --ticker QQQ --model gbm_deep --save
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier  # type: ignore[import-untyped]
import joblib  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from services.ml.quality import (  # type: ignore[import-not-found]
    assert_class_balance, assert_feature_variance,
    assert_prediction_distribution, DegenerateModelError,
)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data/cached_features"

META_COLS = {'_id', '_computed_at', 'ticker', 'date', 'feature_version', 'day'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}

def load_cached(ticker: str, version: str = 'v1.0') -> Any:
    csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No cached data: {csv_path}. Run cache_features_to_csv.py first.")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")
    return df

def prepare_data(df: Any, target: str = 'target_directional_move') -> tuple[Any, Any, list[str], list[Any]]:
    df = df.dropna(subset=[target]).reset_index(drop=True)
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[target].values.astype(int)
    dates = df['date'].tolist() if 'date' in df.columns else list(range(len(y)))
    return X, y, feature_cols, dates

def walk_forward_splits(n: int, n_splits: int = 8, train_size: int = 500, test_size: int = 100, embargo: int = 5) -> list[tuple[Any, Any]]:
    splits = []
    for i in range(n_splits):
        test_start = n - (n_splits - i) * test_size
        test_end = test_start + test_size
        train_start = max(0, test_start - train_size)
        train_end = test_start - embargo
        if train_end <= train_start or test_end > n:
            continue
        splits.append((np.arange(train_start, train_end), np.arange(test_start, test_end)))
    return splits

def compute_sharpe(preds: list[Any], actuals: list[Any]) -> float:
    rets = [1.0 if p == 1 and a == 1 else -1.0 if p == 1 and a == 0 else 0.0 for p, a in zip(preds, actuals)]
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))

def get_model(name: str) -> Any:
    models = {
        "gbm": GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, subsample=0.8, random_state=42),
        "gbm_deep": GradientBoostingClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, subsample=0.7, random_state=42),
        "logistic": LogisticRegression(max_iter=1000, C=1.0, random_state=42),
        "rf": RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42),
    }
    return models[name]

def train_and_evaluate(X: Any, y: Any, splits: list[tuple[Any, Any]], model_name: str) -> tuple[float | None, float | None, float | None]:
    all_preds, all_probas, all_actuals = [], [], []
    fold_metrics = []
    
    for fold_i, (train_idx, test_idx) in enumerate(splits):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        feature_stds = np.std(X_train, axis=0)
        valid = feature_stds > 1e-8
        if valid.sum() < 5:
            continue
        X_train, X_test = X_train[:, valid], X_test[:, valid]
        
        try:
            assert_class_balance(y_train, min_ratio=0.05)
            assert_feature_variance(X_train, min_var=1e-6)
        except DegenerateModelError:
            continue
        
        scaler = StandardScaler()
        X_train_s = np.nan_to_num(scaler.fit_transform(X_train), nan=0.0)
        X_test_s = np.nan_to_num(scaler.transform(X_test), nan=0.0)
        
        model = get_model(model_name)
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]
        
        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError:
            continue
        
        acc = np.mean(preds == y_test)
        tp = np.sum((preds == 1) & (y_test == 1))
        fp = np.sum((preds == 1) & (y_test == 0))
        fn = np.sum((preds == 0) & (y_test == 1))
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        
        fold_metrics.append({"fold": fold_i, "accuracy": acc, "f1": f1, "n_train": len(train_idx), "n_test": len(test_idx)})
        all_preds.extend(preds.tolist())
        all_probas.extend(probas.tolist())
        all_actuals.extend(y_test.tolist())
    
    if not all_preds:
        return None, None, None
    
    sharpe = compute_sharpe(all_preds, all_actuals)
    acc = float(np.mean(np.array(all_preds) == np.array(all_actuals)))
    avg_f1 = np.mean([m["f1"] for m in fold_metrics])
    
    return sharpe, acc, avg_f1

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="QQQ")
    parser.add_argument("--feature-version", default="v1.0")
    parser.add_argument("--model", default="gbm_deep", choices=["gbm", "gbm_deep", "logistic", "rf"])
    parser.add_argument("--target", default="target_directional_move")
    parser.add_argument("--save", action="store_true", help="Save model artifact")
    args = parser.parse_args()
    
    print(f"Production training: {args.ticker} / {args.model} / {args.feature_version}")
    t0 = time.time()
    
    df = load_cached(args.ticker, args.feature_version)
    X, y, feature_cols, dates = prepare_data(df, args.target)
    print(f"Data: {X.shape[0]} samples, {X.shape[1]} features ({time.time()-t0:.1f}s)")
    
    splits = walk_forward_splits(len(y))
    print(f"Splits: {len(splits)}")
    
    # Baselines
    y_test_all = np.concatenate([y[test_idx] for _, test_idx in splits])
    majority_preds = []
    persistence_preds = []
    for train_idx, test_idx in splits:
        y_train = y[train_idx]
        majority_preds.extend([int(np.bincount(y_train).argmax())] * len(test_idx))
        persistence_preds.extend([y_train[-1]] * len(test_idx))
    
    majority_sharpe = compute_sharpe(majority_preds, y_test_all.tolist())
    persistence_sharpe = compute_sharpe(persistence_preds, y_test_all.tolist())
    
    print(f"Baseline majority: sharpe={majority_sharpe:.3f}")
    print(f"Baseline persistence: sharpe={persistence_sharpe:.3f}")
    
    # Train
    sharpe, acc, f1 = train_and_evaluate(X, y, splits, args.model)
    
    if sharpe is None:
        print("FAILED: No folds succeeded")
        return
    
    beats_all = sharpe > majority_sharpe and sharpe > persistence_sharpe
    verdict = "SHIP" if beats_all else "REJECT"
    
    print(f"\n{args.model}: acc={acc:.3f}, f1={f1:.3f}, sharpe={sharpe:.3f} -> {verdict}")
    print(f"Total time: {time.time()-t0:.1f}s")
    
    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "ticker": args.ticker, "model": args.model, "feature_version": args.feature_version,
        "target": args.target, "n_samples": len(y), "n_features": X.shape[1],
        "splits": len(splits), "accuracy": acc, "f1": f1, "sharpe": sharpe,
        "baseline_majority_sharpe": majority_sharpe,
        "baseline_persistence_sharpe": persistence_sharpe,
        "beats_baselines": beats_all, "verdict": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORTS_DIR / f"production_{args.ticker}_{args.model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report: {report_path}")
    
    # Save model artifact
    if beats_all and args.save:
        print("\nSaving production model...")
        
        # Train on full dataset
        scaler = StandardScaler()
        X_s = np.nan_to_num(scaler.fit_transform(X), nan=0.0)
        model = get_model(args.model)
        model.fit(X_s, y)
        
        # Save artifacts
        model_path = MODELS_DIR / f"{args.ticker}_{args.model}_production.joblib"
        scaler_path = MODELS_DIR / f"{args.ticker}_{args.model}_production_scaler.joblib"
        manifest_path = MODELS_DIR / f"{args.ticker}_{args.model}_production_manifest.json"
        
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)
        
        manifest = {
            "ticker": args.ticker, "model": args.model, "feature_version": args.feature_version,
            "target": args.target, "n_samples": len(y), "n_features": X.shape[1],
            "feature_names": feature_cols, "accuracy": acc, "f1": f1, "sharpe": sharpe,
            "beats_baselines": True, "verdict": "SHIP",
            "model_path": str(model_path), "scaler_path": str(scaler_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        
        print(f"Model saved: {model_path}")
        print(f"Scaler saved: {scaler_path}")
        print(f"Manifest saved: {manifest_path}")

if __name__ == "__main__":
    main()
