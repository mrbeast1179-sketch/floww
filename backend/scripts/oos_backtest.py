#!/usr/bin/env python3
"""OOS backtest for freshly trained models using the real feature pipeline."""
import sys, json, joblib, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path
from sklearn.metrics import accuracy_score

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripts.train_real_data_ml as trd
compute_features = trd.compute_features
FEATURE_NAMES = trd.FEATURE_NAMES

MODELS = {
    'SPY': 'SPY_logistic_v2_20260607_232053',
    'QQQ': 'QQQ_rf_v2_20260607_232058',
    'DIA': 'DIA_logistic_v2_20260607_232103',
    'IWM': 'IWM_rf_v2_20260607_232107',
    'TLT': 'TLT_rf_v2_20260607_232112',
}

model_dir = Path('models')
report = {}

for ticker, name in MODELS.items():
    print(f"\n=== {ticker} ===")
    model = joblib.load(model_dir / f'{name}.joblib')
    scaler = joblib.load(model_dir / f'{name}_scaler.joblib')
    manifest = json.loads((model_dir / f'{name}_manifest.json').read_text())
    feat_names = manifest['feature_names']

    df = compute_features(ticker, period='2y')
    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ['target_3class']].dropna().iloc[:-1]
    X = clean[feat_cols].values.astype(float)
    y = clean['target_3class'].values.astype(int)

    # Use the SELECTED features from manifest
    selected_indices = [feat_cols.index(f) for f in feat_names if f in feat_cols]
    X_sel = X[:, selected_indices]
    X_scaled = scaler.transform(X_sel)

    # Last 20% OOS
    split = int(len(X_scaled) * 0.8)
    X_oos = X_scaled[split:]
    y_oos = y[split:]

    preds = model.predict(X_oos)
    proba = model.predict_proba(X_oos) if hasattr(model, 'predict_proba') else None
    acc = accuracy_score(y_oos, preds)

    # Per-class
    for cls, label in [(0,'DOWN'),(1,'HOLD'),(2,'UP')]:
        mask = y_oos == cls
        n = mask.sum()
        if n > 0:
            ca = accuracy_score(y_oos[mask], preds[mask])
            print(f"  {label}: {ca:.3f} (n={n})")
        else:
            print(f"  {label}: n=0")

    # Directional P&L simulation
    # Map: UP=long next day, DOWN=short, HOLD=flat
    # Simplified: correct if prediction matches actual direction
    correct_directional = 0
    total_trades = 0
    daily_pnl = []
    for i in range(len(y_oos) - 1):
        if preds[i] == 2:  # predicted UP
            total_trades += 1
            if y_oos[i+1] == 2: correct_directional += 1; daily_pnl.append(1)
            elif y_oos[i+1] == 0: daily_pnl.append(-1)
            else: daily_pnl.append(0)
        elif preds[i] == 0:  # predicted DOWN
            total_trades += 1
            if y_oos[i+1] == 0: correct_directional += 1; daily_pnl.append(1)
            elif y_oos[i+1] == 2: daily_pnl.append(-1)
            else: daily_pnl.append(0)
        # HOLD: no trade, no pnl

    win_rate = correct_directional / max(total_trades, 1)
    if len(daily_pnl) > 1:
        arr = np.array(daily_pnl)
        sharpe = arr.mean() / (arr.std() + 1e-10) * np.sqrt(252)
    else:
        sharpe = 0

    print(f"  OOS Accuracy: {acc:.4f} (n={len(y_oos)})")
    print(f"  Directional Win Rate: {win_rate:.2%} ({correct_directional}/{total_trades})")
    print(f"  Simplified Sharpe: {sharpe:.2f}")

    report[ticker] = {
        'model_type': manifest['model_type'],
        'oos_accuracy': round(acc, 4),
        'oos_n': len(y_oos),
        'win_rate': round(win_rate, 4),
        'n_trades': total_trades,
        'sharpe': round(sharpe, 2),
        'features': feat_names,
    }

print("\n" + "="*60)
print("OOS BACKTEST SUMMARY (last 20%)")
print("="*60)
print(f"{'Ticker':8} {'Model':10} {'Acc':>6} {'Win%':>7} {'Trades':>7} {'Sharpe':>7}")
for t, r in report.items():
    print(f"{t:8} {r['model_type']:10} {r['oos_accuracy']:>6.2%} {r['win_rate']:>6.1%} {r['n_trades']:>7} {r['sharpe']:>7.2f}")

# Save report
report_path = Path('reports') / 'oos_backtest_20260607.json'
report_path.parent.mkdir(exist_ok=True)
report_path.write_text(json.dumps(report, indent=2))
print(f"\nSaved: {report_path}")
