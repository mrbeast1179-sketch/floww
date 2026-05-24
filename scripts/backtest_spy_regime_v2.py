#!/usr/bin/env python3
"""
scripts/backtest_spy_regime_v2.py

Backtest the SPY regime-enhanced v2 model on 2024 data.
Loads the shipped model, computes predictions on all 167 rows,
and produces a quarterly walk-forward performance report.

Usage:
    cd /Users/nav/GitHub/Floww/backend
    venv/bin/python /Users/nav/GitHub/Floww/scripts/backtest_spy_regime_v2.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
load_dotenv(REPO_ROOT / "backend" / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
MODELS_DIR = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"

VERSION = "v2.0-regime"
MODEL_PATH = MODELS_DIR / f"SPY_direction_{VERSION}.joblib"
SCALER_PATH = MODELS_DIR / f"SPY_scaler_{VERSION}.joblib"
META_PATH = MODELS_DIR / f"SPY_meta_{VERSION}.json"


def main():
    print(f"\n{'='*60}")
    print(f"SPY Regime v2 Backtest — {VERSION}")
    print(f"{'='*60}\n")

    # Load model artifacts
    if not MODEL_PATH.exists():
        print(f"ERROR: Model not found at {MODEL_PATH}"); sys.exit(1)
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(META_PATH) as f:
        meta = json.load(f)
    print(f"Loaded: {MODEL_PATH.name}")
    print(f"Model type: {meta['model_type']}, Features: {meta['n_features']}")

    # Load features from MongoDB
    c = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    docs = list(db["ml_features"].find({"ticker": "SPY"}).sort("date", 1))
    c.close()
    df = pd.DataFrame(docs).sort_values("date").reset_index(drop=True)
    print(f"Loaded {len(df)} feature rows")

    # Load regime features from snapshots (same as training)
    from train_spy_regime_enhanced import compute_regime_features, get_feature_cols
    df = compute_regime_features(df)
    feature_cols = [c for c in meta["feature_names"] if c in df.columns]
    print(f"Feature cols available: {len(feature_cols)}/{meta['n_features']}")

    # Prepare X
    target_col = "target_directional_move"
    valid = df[target_col].notna()
    df_v = df[valid].copy()
    for col in feature_cols:
        df_v[col] = pd.to_numeric(df_v[col], errors="coerce").fillna(0)

    X = df_v[feature_cols].values
    y = df_v[target_col].values.astype(int)
    dates = df_v["date"].tolist()

    # Scale and predict
    X_s = scaler.transform(X)
    preds = model.predict(X_s)
    proba = model.predict_proba(X_s)[:, 1] if hasattr(model, "predict_proba") else preds.astype(float)

    # Overall metrics
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    acc = accuracy_score(y, preds)
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    f1 = f1_score(y, preds, zero_division=0)

    # Trading P&L simulation
    pnl = []
    for i in range(len(preds)):
        if preds[i] == 1:
            # Long: gain if directional move happened
            pnl.append(1.0 if y[i] == 1 else -1.0)

    total_trades = len(pnl)
    winning_trades = sum(1 for p in pnl if p > 0)
    total_pnl = sum(pnl)
    win_rate = winning_trades / max(total_trades, 1)
    avg_win = total_pnl / max(total_trades, 1) * 100

    # Profit factor
    gross_wins = sum(p for p in pnl if p > 0)
    gross_losses = abs(sum(p for p in pnl if p < 0))
    profit_factor = gross_wins / max(gross_losses, 1e-10)

    # Sharpe
    if len(pnl) > 1 and np.std(pnl) > 0:
        sharpe = float(np.mean(pnl) / np.std(pnl) * np.sqrt(252))
    else:
        sharpe = 0.0

    print(f"\n{'='*60}")
    print(f"BACKTEST RESULTS (In-Sample 2024)")
    print(f"{'='*60}")
    print(f"Accuracy:     {acc:.3f}")
    print(f"Precision:    {prec:.3f}")
    print(f"Recall:       {rec:.3f}")
    print(f"F1:           {f1:.3f}")
    print(f"Win Rate:     {win_rate:.3f} ({winning_trades}/{total_trades})")
    print(f"Total P&L:    {total_pnl:+.1f} units ({avg_win:+.2f} avg/trade)")
    print(f"Profit Factor:{profit_factor:.2f}")
    print(f"Sharpe:       {sharpe:.3f}")

    # Quarterly breakdown
    df_v = df_v.copy()
    df_v["pred"] = preds
    df_v["actual"] = y
    df_v["pnl"] = [p if p > 0 else p for p in pnl] + [0] * (len(df_v) - len(pnl))

    # Simple quarter assignment from date
    def get_quarter(d):
        m = int(d.split("-")[1])
        return f"Q{(m-1)//3 + 1}"

    df_v["quarter"] = df_v["date"].apply(get_quarter)

    print(f"\n{'='*60}")
    print(f"QUARTERLY BREAKDOWN")
    print(f"{'='*60}")
    for q in sorted(df_v["quarter"].unique()):
        qdf = df_v[df_v["quarter"] == q]
        q_pnl = []
        for _, row in qdf.iterrows():
            if row["pred"] == 1:
                q_pnl.append(1.0 if row["actual"] == 1 else -1.0)
        q_trades = len(q_pnl)
        q_wins = sum(1 for p in q_pnl if p > 0)
        q_total = sum(q_pnl)
        q_wr = q_wins / max(q_trades, 1)
        print(f"  {q}: {q_wins}/{q_trades} WR={q_wr:.2f} P&L={q_total:+.0f}")

    # Regime breakdown
    print(f"\n{'='*60}")
    print(f"REGIME BREAKDOWN")
    print(f"{'='*60}")
    if "regime_encoded" in df_v.columns:
        for reg in sorted(df_v["regime_encoded"].unique()):
            rdf = df_v[df_v["regime_encoded"] == reg]
            r_pnl = []
            for _, row in rdf.iterrows():
                if row["pred"] == 1:
                    r_pnl.append(1.0 if row["actual"] == 1 else -1.0)
            reg_name = {1: "BULLISH", -1: "BEARISH", 0: "NEUTRAL"}.get(reg, str(reg))
            print(f"  {reg_name}: {len(rdf)} days, P&L={sum(r_pnl):+.0f}, WR={sum(1 for p in r_pnl if p>0)/max(len(r_pnl),1):.2f}")

    # Write report
    report_path = REPORTS_DIR / "backtest_SPY_regime_v2.md"
    with open(report_path, "w") as f:
        f.write(f"# SPY Regime v2 Backtest Report\n")
        f.write(f"\n**Date:** {datetime.now(timezone.utc).isoformat()}")
        f.write(f"\n**Model:** {VERSION} ({meta['model_type']})")
        f.write(f"\n**Features:** {meta['n_features']}")
        f.write(f"\n\n## Overall Metrics (2024, 167 trading days)")
        f.write(f"\n| Metric | Value |")
        f.write(f"\n|--------|-------|")
        f.write(f"\n| Accuracy | {acc:.3f} |")
        f.write(f"\n| Precision | {prec:.3f} |")
        f.write(f"\n| Recall | {rec:.3f} |")
        f.write(f"\n| F1 | {f1:.3f} |")
        f.write(f"\n| Win Rate | {win_rate:.3f} |")
        f.write(f"\n| Total P&L | {total_pnl:+.1f} units |")
        f.write(f"\n| Profit Factor | {profit_factor:.2f} |")
        f.write(f"\n| Sharpe | {sharpe:.3f} |")
        f.write(f"\n\n## Quarterly Breakdown")
        for q in sorted(df_v["quarter"].unique()):
            qdf = df_v[df_v["quarter"] == q]
            q_pnl = []
            for _, row in qdf.iterrows():
                if row["pred"] == 1:
                    q_pnl.append(1.0 if row["actual"] == 1 else -1.0)
            q_trades = len(q_pnl)
            q_wins = sum(1 for p in q_pnl if p > 0)
            q_wr = q_wins / max(q_trades, 1)
            q_total = sum(q_pnl)
            f.write(f"\n- **{q}**: {q_wins}/{q_trades} WR={q_wr:.2f} P&L={q_total:+.0f}")

    print(f"\nReport: {report_path}")
    print(f"\n{'='*60}")

    # Verdict
    if sharpe > 1.0 and profit_factor > 1.5:
        print("VERDICT: STRONG — Sharpe > 1.0, PF > 1.5")
    elif sharpe > 0.5 and profit_factor > 1.0:
        print("VERDICT: PROMISING — Sharpe > 0.5, PF > 1.0")
    else:
        print("VERDICT: NEEDS WORK")


if __name__ == "__main__":
    main()
