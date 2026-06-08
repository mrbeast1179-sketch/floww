#!/usr/bin/env python3
"""Retrain all 5 tickers with adaptive thresholds + more features + regularization."""
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scripts.train_real_data_ml import FEATURE_NAMES, compute_features, select_features, walk_forward_cv

MODEL_DIR = Path('models')
TICKERS = ['SPY', 'QQQ', 'DIA', 'IWM', 'TLT']

results = {}
for ticker in TICKERS:
    print(f"\n=== {ticker} ===")
    t0 = time.time()

    df = compute_features(ticker, period='5y')
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ['target_3class']].dropna().iloc[:-1]
    X_full = clean[feat_cols].values.astype(float)
    y_full = clean['target_3class'].values.astype(int)

    # Compute adaptive threshold from training data
    split = int(len(X_full) * 0.8)
    y_train_raw = y_full[:split]

    # Recompute target with adaptive threshold based on ret_1d std
    if 'ret_1d' in clean.columns:
        ret_1d = clean['ret_1d'].values
        train_std = np.std(ret_1d[:split])
        adaptive_threshold = 0.5 * train_std
        print(f'  Adaptive threshold: {adaptive_threshold:.4f} (train_std={train_std:.4f})')

        y_adaptive = np.ones(len(ret_1d), dtype=int)  # HOLD
        y_adaptive[ret_1d > adaptive_threshold] = 2   # UP
        y_adaptive[ret_1d < -adaptive_threshold] = 0  # DOWN
        y = y_adaptive
    else:
        y = y_full
        adaptive_threshold = 0.003

    for cls, label in [(0,'DOWN'),(1,'HOLD'),(2,'UP')]:
        pct = (y == cls).mean()
        print(f'  {label}: {pct:.1%}')

    X_train, X_test = X_full[:split], X_full[split:]
    y_train, y_test = y[:split], y[split:]

    # Feature selection
    sel_names, sel_idx = select_features(X_train, y_train, feat_cols,
                                         min_variance=0.0003, max_correlation=0.85,
                                         max_features=25)
    X_train_sel = X_train[:, sel_idx]
    X_test_sel = X_test[:, sel_idx]

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train_sel)
    X_test_s = scaler.transform(X_test_sel)

    # Candidates with stronger regularization
    candidates = {
        'rf': RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=20,
                                      max_features='sqrt', random_state=42, n_jobs=-1),
        'gbm': GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.03,
                                           subsample=0.7, min_samples_leaf=25, random_state=42),
        'logistic': LogisticRegression(C=0.05, max_iter=2000, solver='lbfgs', random_state=42),
    }

    best_model, best_name, best_score, best_cv = None, None, -999, None
    for name, model in candidates.items():
        cv = walk_forward_cv(model, X_train_s, y_train, n_splits=5, embargo=5)
        print(f"  {name}: wf_acc={cv['mean_test_accuracy']:.4f} +/- {cv['std_test_accuracy']:.4f}")
        if cv['mean_test_accuracy'] > best_score:
            best_score = cv['mean_test_accuracy']
            best_model = model
            best_name = name
            best_cv = cv

    if best_model is None or best_cv is None:
        raise RuntimeError(f"No model trained for {ticker}")

    best_model.fit(X_train_s, y_train)
    train_acc = accuracy_score(y_train, best_model.predict(X_train_s))
    test_acc = accuracy_score(y_test, best_model.predict(X_test_s))
    gap = train_acc - test_acc

    preds = best_model.predict(X_test_s)
    oos_acc = accuracy_score(y_test, preds)

    # Directional P&L
    pnl = []
    for i in range(len(y_test) - 1):
        if preds[i] == 2:
            pnl.append(1 if y_test[i+1] == 2 else (-1 if y_test[i+1] == 0 else 0))
        elif preds[i] == 0:
            pnl.append(1 if y_test[i+1] == 0 else (-1 if y_test[i+1] == 2 else 0))
    if len(pnl) > 1:
        arr = np.array(pnl)
        sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252)
    else:
        sharpe = 0

    elapsed = time.time() - t0
    print(f'  Best: {best_name} test={test_acc:.4f} gap={gap:.4f} oos={oos_acc:.4f} sharpe={sharpe:.2f} ({elapsed:.1f}s)')

    # Save
    import joblib
    ts = time.strftime('%Y%m%d_%H%M%S')
    m_path = MODEL_DIR / f'{ticker}_{best_name}_adaptive_{ts}.joblib'
    s_path = MODEL_DIR / f'{ticker}_{best_name}_adaptive_{ts}_scaler.joblib'
    manifest_path = MODEL_DIR / f'{ticker}_{best_name}_adaptive_{ts}_manifest.json'

    joblib.dump(best_model, m_path)
    joblib.dump(scaler, s_path)

    manifest = {
        'ticker': ticker, 'model_type': best_name, 'n_samples': len(X_full),
        'n_train': len(X_train), 'n_test': len(X_test), 'n_features': len(sel_names),
        'feature_names': sel_names, 'train_accuracy': train_acc, 'test_accuracy': test_acc,
        'overfit_gap': gap, 'oos_accuracy': oos_acc, 'oos_n': len(X_test),
        'walk_forward_mean': best_cv['mean_test_accuracy'],
        'walk_forward_std': best_cv['std_test_accuracy'],
        'directional_sharpe': round(sharpe, 4), 'n_folds': best_cv['n_folds'],
        'fold_test_scores': best_cv['fold_test_scores'],
        'threshold': 'adaptive_0.5std', 'adaptive_threshold': round(float(adaptive_threshold), 6),
        'data': '5y',
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    print(f'  Saved: {m_path.name}')

    results[ticker] = {
        'model': best_name, 'test_acc': test_acc, 'oos_acc': oos_acc,
        'sharpe': round(sharpe, 2), 'gap': gap, 'threshold': float(adaptive_threshold),
    }

print("\n=== SUMMARY ===")
for t, r in results.items():
    print(f"{t}: {r['model']} test={r['test_acc']:.4f} oos={r['oos_acc']:.4f} sharpe={r['sharpe']:.2f} gap={r['gap']:.4f} thresh={r['threshold']:.4f}")

report_path = MODEL_DIR / f'training_adaptive_{time.strftime("%Y%m%d_%H%M%S")}.json'
report_path.write_text(json.dumps(results, indent=2))
print(f"\nReport: {report_path}")
