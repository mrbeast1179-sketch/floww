"""
scripts/analyze_feature_importance.py

Feature importance analysis for trained ML models.
Uses built-in feature importance (tree models) and permutation importance.
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.inspection import permutation_importance
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from services.ml.quality import assert_feature_variance

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data/cached_features"


def load_model_and_data(ticker, model_name, feature_version='v1.0'):
    """Load model artifact and cached feature data."""
    # Load model
    model_path = MODELS_DIR / f"{ticker}_{model_name}_production.joblib"
    scaler_path = MODELS_DIR / f"{ticker}_{model_name}_production_scaler.joblib"
    
    if not model_path.exists():
        # Try alternative naming
        model_files = list(MODELS_DIR.glob(f"{ticker}*_production.joblib"))
        if not model_files:
            raise FileNotFoundError(f"No production model found for {ticker}")
        model_path = model_files[0]
        scaler_path = Path(str(model_path).replace("_production.joblib", "_production_scaler.joblib"))
    
    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path) if scaler_path.exists() else None
    
    # Load cached features
    csv_path = CACHE_DIR / f"{ticker}_{feature_version}.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"No cached features: {csv_path}")
    
    df = pd.read_csv(csv_path)
    
    return model, scaler, df


def compute_builtin_importance(model, feature_names):
    """Compute feature importance from tree-based models."""
    if hasattr(model, 'feature_importances_'):
        importance = model.feature_importances_
        return dict(zip(feature_names, importance.tolist()))
    return {}


def compute_permutation_importance(model, X, y, feature_names, n_repeats=10):
    """Compute permutation importance (model-agnostic)."""
    result = permutation_importance(
        model, X, y,
        n_repeats=n_repeats,
        random_state=42,
        scoring='accuracy'
    )
    return dict(zip(feature_names, result.importances_mean.tolist()))


def analyze(ticker, model_name, feature_version='v1.0', target='target_directional_move'):
    """Full feature importance analysis."""
    print(f"Analyzing feature importance for {ticker} {model_name}")
    t0 = time.time()
    
    model, scaler, df = load_model_and_data(ticker, model_name, feature_version)
    
    # Prepare features
    meta_cols = {'_computed_at', 'ticker', 'date', 'feature_version', 'day'}
    target_cols = {'target_directional_move', 'target_return_pct', 'target_gap_move',
                   'target_range_expansion', 'target_any_materialization'}
    feature_cols = [c for c in df.columns if c not in meta_cols and c not in target_cols]
    
    X = df[feature_cols].values.astype(float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df[target].values.astype(int) if target in df.columns else None
    
    if scaler:
        X_scaled = scaler.transform(X)
    else:
        X_scaled = X
    
    # Builtin importance
    builtin = compute_builtin_importance(model, feature_cols)
    
    # Permutation importance (if we have labels)
    perm = {}
    if y is not None and len(np.unique(y)) >= 2:
        print(f"  Computing permutation importance (this may take a moment)...")
        perm = compute_permutation_importance(model, X_scaled, y, feature_cols, n_repeats=5)
    
    # Combine results
    results = []
    for feat in feature_cols:
        results.append({
            'feature': feat,
            'builtin_importance': builtin.get(feat, 0),
            'permutation_importance': perm.get(feat, 0),
        })
    
    # Sort by builtin importance
    results.sort(key=lambda x: x['builtin_importance'], reverse=True)
    
    # Print top 20
    print(f"\nTop 20 features (builtin importance):")
    for i, r in enumerate(results[:20]):
        bar = '█' * int(r['builtin_importance'] * 100)
        print(f"  {i+1:2d}. {r['feature']:30s} {r['builtin_importance']:.4f} {bar}")
    
    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        'ticker': ticker,
        'model': model_name,
        'feature_version': feature_version,
        'n_features': len(feature_cols),
        'n_samples': len(X),
        'top_features': results[:30],
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORTS_DIR / f"feature_importance_{ticker}_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved: {report_path}")
    print(f"Total time: {time.time()-t0:.1f}s")
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Feature importance analysis")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--model", default="gbm_deep")
    parser.add_argument("--feature-version", default="v1.0")
    parser.add_argument("--target", default="target_directional_move")
    args = parser.parse_args()
    
    analyze(args.ticker, args.model, args.feature_version, args.target)


if __name__ == "__main__":
    main()
