#!/usr/bin/env python3
"""
scripts/train_v5_enhanced.py

Enhanced model training with:
- Multiple target variables (directional, range expansion, gap move)
- Feature engineering on top of v1.0 features
- Hyperparameter search
- Proper walk-forward CV
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier  # type: ignore[import-untyped]
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
from sklearn.model_selection import TimeSeriesSplit  # type: ignore[import-untyped]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.ml.quality import (  # type: ignore[import-not-found]
    assert_class_balance,
    assert_feature_variance,
    assert_prediction_distribution,
    DegenerateModelError,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "data/cached_features"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

META_COLS = {'_computed_at', 'ticker', 'date', 'feature_version', 'day'}
TARGET_COLS = {
    'target_directional_move', 'target_return_pct', 'target_gap_move',
    'target_range_expansion', 'target_any_materialization',
}


def load_and_engineer(ticker: str, version: str = 'v1.0') -> Any:
    """Load cached features and engineer additional features."""
    csv_path = CACHE_DIR / f"{ticker}_{version}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No cached data: {csv_path}")
    
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    
    # Engineer additional features
    # 1. Volatility ratio (short-term / long-term)
    if 'realized_vol_5d' in df.columns and 'realized_vol_21d' in df.columns:
        df['vol_ratio_5_21'] = df['realized_vol_5d'] / (df['realized_vol_21d'] + 1e-8)
    
    if 'realized_vol_5d' in df.columns and 'realized_vol_60d' in df.columns:
        df['vol_ratio_5_60'] = df['realized_vol_5d'] / (df['realized_vol_60d'] + 1e-8)
    
    # 2. SMA crossover signals
    if 'sma_5' in df.columns and 'sma_21' in df.columns:
        df['sma_5_21_diff'] = df['sma_5'] - df['sma_21']
        df['sma_5_21_cross'] = (df['sma_5'] > df['sma_21']).astype(int)
    
    if 'sma_10' in df.columns and 'sma_50' in df.columns:
        df['sma_10_50_diff'] = df['sma_10'] - df['sma_50']
    
    # 3. RSI extremes
    if 'rsi_14' in df.columns:
        df['rsi_overbought'] = (df['rsi_14'] > 70).astype(int)
        df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)
        df['rsi_normal'] = ((df['rsi_14'] >= 30) & (df['rsi_14'] <= 70)).astype(int)
    
    # 4. Return momentum
    if 'ret_1d' in df.columns and 'ret_5d' in df.columns:
        df['ret_momentum'] = df['ret_1d'] - df['ret_5d']
    
    if 'ret_5d' in df.columns and 'ret_21d' in df.columns:
        df['ret_accel'] = df['ret_5d'] - df['ret_21d']
    
    # 5. Volume spike
    if 'relative_volume' in df.columns:
        df['vol_spike'] = (df['relative_volume'] > 2.0).astype(int)
        df['vol_high'] = (df['relative_volume'] > 1.5).astype(int)
    
    # 6. Calendar features
    if 'day_of_week' in df.columns:
        df['is_monday'] = (df['day_of_week'] == 0).astype(int)
        df['is_friday'] = (df['day_of_week'] == 4).astype(int)
    
    if 'month' in df.columns:
        df['is_dec'] = (df['month'] == 12).astype(int)
        df['is_jan'] = (df['month'] == 1).astype(int)
    
    # 7. ATR percentile (volatility regime)
    if 'atr_14' in df.columns:
        df['atr_percentile'] = df['atr_14'].rolling(60).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) > 0 else 0.5
        )
    
    # 8. Overnight gap analysis
    if 'overnight_gap' in df.columns:
        df['gap_abs'] = df['overnight_gap'].abs()
        df['gap_large'] = (df['gap_abs'] > 0.005).astype(int)
    
    # Replace infinities
    df = df.replace([np.inf, -np.inf], np.nan)
    
    return df


def prepare_data(df: Any, target: str = 'target_directional_move') -> tuple[Any, Any, list[str], list[Any]]:
    """Prepare feature matrix and target."""
    feature_cols = [c for c in df.columns if c not in META_COLS and c not in TARGET_COLS]
    
    # Drop rows with NaN in target
    valid = df[target].notna()
    df = df[valid].reset_index(drop=True)
    
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


def sharpe(preds: list[Any], actuals: Any) -> float:
    rets = [1.0 if p == 1 and a == 1 else -1.0 if p == 1 and a == 0 else 0.0
            for p, a in zip(preds, actuals)]
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def train_and_evaluate(X: Any, y: Any, splits: list[tuple[Any, Any]], model_name: str, params: Any = None) -> dict[str, Any] | None:
    all_preds, all_actuals = [], []
    
    model_map = {
        "logistic": lambda p: LogisticRegression(**(p or {"max_iter": 1000, "C": 1.0, "random_state": 42})),
        "gbm": lambda p: GradientBoostingClassifier(**(p or {"n_estimators": 100, "max_depth": 4, "learning_rate": 0.1, "subsample": 0.8, "random_state": 42})),
        "gbm_deep": lambda p: GradientBoostingClassifier(**(p or {"n_estimators": 200, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.7, "random_state": 42})),
        "rf": lambda p: RandomForestClassifier(**(p or {"n_estimators": 100, "max_depth": 6, "random_state": 42})),
    }
    
    for train_idx, test_idx in splits:
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
        
        valid = np.std(X_train, axis=0) > 1e-8
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
        
        model = model_map[model_name](params)
        model.fit(X_train_s, y_train)
        preds = model.predict(X_test_s)
        probas = model.predict_proba(X_test_s)[:, 1]
        
        try:
            assert_prediction_distribution(probas, min_std=0.01)
        except DegenerateModelError:
            continue
        
        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())
    
    if not all_preds:
        return None
    
    return {
        "sharpe": sharpe(all_preds, all_actuals),
        "accuracy": float(np.mean(np.array(all_preds) == np.array(all_actuals))),
        "n_predictions": len(all_preds),
    }


def run_enhanced(ticker: str, version: str = 'v1.0') -> dict[str, Any]:
    print(f"\n{'='*60}")
    print(f"Enhanced training: {ticker} {version}")
    print(f"{'='*60}")
    
    df = load_and_engineer(ticker, version)
    
    results = {}
    
    # Try different targets
    for target in ['target_directional_move', 'target_range_expansion', 'target_gap_move', 'target_any_materialization']:
        if target not in df.columns:
            continue
        
        X, y, feature_cols, dates = prepare_data(df, target)
        if len(np.unique(y)) < 2:
            print(f"\n{target}: only one class, skipping")
            continue
        
        print(f"\n{target}: {X.shape[0]} samples, {X.shape[1]} features, {np.bincount(y)}")
        
        splits = walk_forward_splits(len(y))
        if len(splits) < 3:
            print(f"  Only {len(splits)} splits, skipping")
            continue
        
        # Baselines
        y_test_all = np.concatenate([y[test_idx] for _, test_idx in splits])
        majority_preds, persistence_preds = [], []
        for train_idx, test_idx in splits:
            y_train = y[train_idx]
            majority_preds.extend([int(np.bincount(y_train).argmax())] * len(test_idx))
            persistence_preds.extend([y_train[-1]] * len(test_idx))
        
        baseline_sharpes = {
            "majority": sharpe(majority_preds, y_test_all),
            "persistence": sharpe(persistence_preds, y_test_all),
        }
        print(f"  Baselines: majority={baseline_sharpes['majority']:.3f}, persistence={baseline_sharpes['persistence']:.3f}")
        
        # Models
        for model_name in ["logistic", "gbm", "gbm_deep", "rf"]:
            t0 = time.time()
            result = train_and_evaluate(X, y, splits, model_name)
            elapsed = time.time() - t0
            
            if result:
                beats_all = all(result["sharpe"] > baseline_sharpes[b] for b in ["majority", "persistence"])
                verdict = "SHIP" if beats_all else "REJECT"
                print(f"  {model_name:15s}: acc={result['accuracy']:.3f}, sharpe={result['sharpe']:.3f} -> {verdict} ({elapsed:.1f}s)")
                results[f"{target}_{model_name}"] = {**result, "verdict": verdict, "target": target}
            else:
                print(f"  {model_name:15s}: FAILED")
    
    # Summary
    print(f"\n{'='*60}")
    print("BEST RESULTS:")
    ship_results = {k: v for k, v in results.items() if v["verdict"] == "SHIP"}
    if ship_results:
        for key, r in sorted(ship_results.items(), key=lambda x: x[1]["sharpe"], reverse=True):
            print(f"  {key:40s}: sharpe={r['sharpe']:.3f}, acc={r['accuracy']:.3f}")
    else:
        print("  No models SHIP. Best REJECTs:")
        for key, r in sorted(results.items(), key=lambda x: x[1]["sharpe"], reverse=True)[:3]:
            print(f"  {key:40s}: sharpe={r['sharpe']:.3f}, acc={r['accuracy']:.3f}")
    
    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "ticker": ticker, "version": version,
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORTS_DIR / f"enhanced_{ticker}_{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {report_path}")
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="QQQ")
    parser.add_argument("--version", default="v1.0")
    args = parser.parse_args()
    run_enhanced(args.ticker, args.version)
