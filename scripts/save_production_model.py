#!/usr/bin/env python3
"""
scripts/save_production_model.py

Train on full dataset and save production model artifact.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

CACHE_DIR = Path(__file__).resolve().parent.parent / "data/cached_features"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"

META_COLS = {'_computed_at', 'ticker', 'date', 'feature_version', 'day'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}


def load_and_engineer(ticker, version='v1.0'):
    csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
    df = pd.read_csv(csv_path)
    
    # Same feature engineering as train_v5_enhanced.py
    if 'realized_vol_5d' in df.columns and 'realized_vol_21d' in df.columns:
        df['vol_ratio_5_21'] = df['realized_vol_5d'] / (df['realized_vol_21d'] + 1e-8)
    if 'realized_vol_5d' in df.columns and 'realized_vol_60d' in df.columns:
        df['vol_ratio_5_60'] = df['realized_vol_5d'] / (df['realized_vol_60d'] + 1e-8)
    if 'sma_5' in df.columns and 'sma_21' in df.columns:
        df['sma_5_21_diff'] = df['sma_5'] - df['sma_21']
        df['sma_5_21_cross'] = (df['sma_5'] > df['sma_21']).astype(int)
    if 'sma_10' in df.columns and 'sma_50' in df.columns:
        df['sma_10_50_diff'] = df['sma_10'] - df['sma_50']
    if 'rsi_14' in df.columns:
        df['rsi_overbought'] = (df['rsi_14'] > 70).astype(int)
        df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)
    if 'ret_1d' in df.columns and 'ret_5d' in df.columns:
        df['ret_momentum'] = df['ret_1d'] - df['ret_5d']
    if 'ret_5d' in df.columns and 'ret_21d' in df.columns:
        df['ret_accel'] = df['ret_5d'] - df['ret_21d']
    if 'relative_volume' in df.columns:
        df['vol_spike'] = (df['relative_volume'] > 2.0).astype(int)
    if 'day_of_week' in df.columns:
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)
    if 'overnight_gap' in df.columns:
        df['gap_abs'] = df['overnight_gap'].abs()
        df['gap_large'] = (df['gap_abs'] > 0.005).astype(int)
    
    df = df.replace([np.inf, -np.inf], np.nan)
    return df


def save_model(ticker, model_name, model_params, version='v1.0', target='target_directional_move'):
    """Train on full dataset and save production model."""
    print(f"\nSaving production model: {ticker} {model_name}")
    
    df = load_and_engineer(ticker, version)
    
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    valid = df[target].notna()
    df = df[valid].reset_index(drop=True)
    
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[target].values.astype(int)
    
    print(f"Training on {len(X)} samples, {X.shape[1]} features")
    
    # Train
    scaler = StandardScaler()
    X_s = np.nan_to_num(scaler.fit_transform(X), nan=0.0)
    
    model = GradientBoostingClassifier(**model_params)
    model.fit(X_s, y)
    
    # Evaluate on training data
    train_acc = model.score(X_s, y)
    print(f"Training accuracy: {train_acc:.4f}")
    
    # Save artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    model_path = MODELS_DIR / f"{ticker}_{model_name}_production.joblib"
    scaler_path = MODELS_DIR / f"{ticker}_{model_name}_production_scaler.joblib"
    manifest_path = MODELS_DIR / f"{ticker}_{model_name}_production_manifest.json"
    
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    
    manifest = {
        "ticker": ticker,
        "model": model_name,
        "feature_version": version,
        "target": target,
        "n_samples": len(X),
        "n_features": X.shape[1],
        "feature_names": feature_cols,
        "train_accuracy": train_acc,
        "model_params": model_params,
        "model_path": str(model_path),
        "scaler_path": str(scaler_path),
        "verdict": "SHIP",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"Model saved: {model_path}")
    print(f"Scaler saved: {scaler_path}")
    print(f"Manifest saved: {manifest_path}")
    
    return manifest


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--model", default="gbm")
    parser.add_argument("--params", type=json.loads, default='{"n_estimators": 200, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.7, "random_state": 42}')
    args = parser.parse_args()
    
    save_model(args.ticker, args.model, args.params)
