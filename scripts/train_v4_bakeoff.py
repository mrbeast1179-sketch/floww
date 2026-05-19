#!/usr/bin/env python3
"""
scripts/train_v4_bakeoff.py

Model bake-off: GBM, Logistic, RF, GBM-deep on QQQ.
Uses v1.0 features (2799 samples) with walk-forward CV.
"""
import os, sys, json, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml.quality import (
    assert_class_balance, assert_feature_variance,
    assert_prediction_distribution, DegenerateModelError,
)

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

META_COLS = {'_id', '_computed_at', 'ticker', 'date', 'feature_version', 'day'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}

def load_features(ticker, version='v1.0'):
    """Load features in batches to avoid timeout."""
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=30000)
    db = client[DB_NAME]
    
    # Get count first
    total = db['ml_features'].count_documents({'ticker': ticker, 'feature_version': version})
    print(f"Loading {total} docs for {ticker}...")
    
    # Fetch in batches
    all_docs = []
    batch_size = 200
    last_id = None
    
    while True:
        query = {'ticker': ticker, 'feature_version': version}
        if last_id:
            query['_id'] = {'$gt': last_id}
        
        cursor = db['ml_features'].find(query).sort('_id', 1).limit(batch_size)
        batch = list(cursor)
        
        if not batch:
            break
        
        all_docs.extend(batch)
        last_id = batch[-1]['_id']
        
        if len(all_docs) % 500 == 0:
            print(f"  Loaded {len(all_docs)}/{total}")
    
    client.close()
    print(f"Loaded {len(all_docs)} docs")
    return pd.DataFrame(all_docs)

def prepare_data(df, target='target_directional_move'):
    df = df.dropna(subset=[target]).reset_index(drop=True)
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[target].values.astype(int)
    return X, y, feature_cols

def walk_forward_splits(n, n_splits=8, train_size=500, test_size=100, embargo=5):
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

def compute_sharpe(preds, actuals):
    rets = [1.0 if p == 1 and a == 1 else -1.0 if p == 1 and a == 0 else 0.0 for p, a in zip(preds, actuals)]
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))

def train_model(X, y, splits, model_name):
    all_preds, all_probas, all_actuals = [], [], []
    
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
        
        if model_name == "gbm":
            model = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, subsample=0.8, random_state=42)
        elif model_name == "logistic":
            model = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
        elif model_name == "rf":
            model = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
        elif model_name == "gbm_deep":
            model = GradientBoostingClassifier(n_estimators=200, max_depth=6, learning_rate=0.05, subsample=0.7, random_state=42)
        else:
            raise ValueError(f"Unknown model: {model_name}")
        
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]
        
        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError:
            continue
        
        all_preds.extend(preds.tolist())
        all_probas.extend(probas.tolist())
        all_actuals.extend(y_test.tolist())
    
    if not all_preds:
        return None
    
    sharpe = compute_sharpe(all_preds, all_actuals)
    acc = np.mean(np.array(all_preds) == np.array(all_actuals))
    return {"sharpe": sharpe, "accuracy": acc, "n_predictions": len(all_preds)}

def main():
    ticker = "QQQ"
    print(f"Model bake-off for {ticker}")
    
    t0 = time.time()
    df = load_features(ticker)
    X, y, feature_cols = prepare_data(df)
    print(f"Data: {X.shape[0]} samples, {X.shape[1]} features ({time.time()-t0:.1f}s)")
    
    splits = walk_forward_splits(len(y))
    print(f"Splits: {len(splits)}")
    
    # Baselines
    baseline_preds = {"majority": [], "persistence": []}
    for train_idx, test_idx in splits:
        y_train = y[train_idx]
        majority = int(np.bincount(y_train).argmax())
        baseline_preds["majority"].extend([majority] * len(test_idx))
        baseline_preds["persistence"].extend([y_train[-1]] * len(test_idx))
    
    y_test_all = np.concatenate([y[test_idx] for _, test_idx in splits])
    
    results = {}
    
    # Baselines
    for name, preds in baseline_preds.items():
        results[name] = {
            "sharpe": compute_sharpe(preds, y_test_all.tolist()),
            "accuracy": float(np.mean(np.array(preds) == y_test_all)),
        }
        print(f"  {name}: acc={results[name]['accuracy']:.3f}, sharpe={results[name]['sharpe']:.3f}")
    
    # Models
    for model_name in ["logistic", "gbm", "gbm_deep", "rf"]:
        print(f"\nTraining {model_name}...")
        t1 = time.time()
        result = train_model(X, y, splits, model_name)
        if result:
            results[model_name] = result
            beats_all = all(result["sharpe"] > results[b]["sharpe"] for b in ["majority", "persistence"])
            verdict = "SHIP" if beats_all else "REJECT"
            print(f"  {model_name}: acc={result['accuracy']:.3f}, sharpe={result['sharpe']:.3f} -> {verdict} ({time.time()-t1:.1f}s)")
        else:
            print(f"  {model_name}: FAILED")
    
    # Save results
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"bakeoff_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump({"ticker": ticker, "results": results, "n_samples": len(y), "n_features": X.shape[1]}, f, indent=2)
    print(f"\nReport: {report_path}")
    
    # Summary
    print("\n=== SUMMARY ===")
    for name, r in sorted(results.items(), key=lambda x: x[1]["sharpe"], reverse=True):
        print(f"  {name:20s}: acc={r['accuracy']:.3f}, sharpe={r['sharpe']:.3f}")

if __name__ == "__main__":
    main()
