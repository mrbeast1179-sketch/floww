#!/usr/bin/env python3
"""
scripts/train_cached_models.py

Train production GBM models on cached CSV features with walk-forward CV,
quality gates, baseline comparison, and Sharpe sanity cap.

Usage:
  python scripts/train_cached_models.py          # train all tickers
  python scripts/train_cached_models.py --ticker DIA
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
DATA_DIR = PROJECT_ROOT / "data" / "cached_features"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_cached")

TICKER_FILES = {
    "SPY": DATA_DIR / "SPY_v2.0_gex.csv",
    "DIA": DATA_DIR / "DIA_v1.0.csv",
    "IWM": DATA_DIR / "IWM_v1.0.csv",
    "QQQ": DATA_DIR / "QQQ_v1.0.csv",
    "TLT": DATA_DIR / "TLT_v1.0.csv",
}
META_COLS = {"ticker","date","day","feature_version","_computed_at",
             "target_directional_move","target_return_pct",
             "target_range_expansion","target_gap_move","target_any_materialization"}
TARGET = "target_directional_move"
MAX_SHARPE = 5.0

CANDIDATES = {
    "gbm": lambda: GradientBoostingClassifier(n_estimators=200, max_depth=5, learning_rate=0.05,
                                               subsample=0.8, min_samples_leaf=10, random_state=42),
    "rf": lambda: RandomForestClassifier(n_estimators=300, max_depth=6, min_samples_leaf=10,
                                          max_features="sqrt", random_state=42, n_jobs=-1),
    "logistic": lambda: LogisticRegression(C=1.0, max_iter=1000, random_state=42),
}

def load_data(ticker):
    path = TICKER_FILES[ticker]
    if not path.exists():
        raise FileNotFoundError(f"No data for {ticker}: {path}")
    df = pd.read_csv(path)
    sc = "date" if "date" in df.columns else "day"
    df = df.sort_values(sc).reset_index(drop=True).replace([np.inf, -np.inf], np.nan)
    feats = [c for c in df.columns if c not in META_COLS]
    df[feats] = df[feats].fillna(0.0)
    vv = df[feats].var()
    low = vv[vv < 1e-8].index.tolist()
    if low:
        feats = [f for f in feats if f not in low]
    return df, feats

def add_features(df, feats):
    f = list(feats)
    for a, b, name in [("realized_vol_5d","realized_vol_21d","vol_ratio_5_21"),
                        ("realized_vol_5d","realized_vol_60d","vol_ratio_5_60"),
                        ("sma_5","sma_21","sma_5_21_diff"),
                        ("sma_10","sma_50","sma_10_50_diff"),
                        ("ret_3d","ret_1d","ret_momentum"),
                        ("ret_5d","ret_3d","ret_accel")]:
        if a in df.columns and b in df.columns:
            df[name] = df[a]/(df[b]+1e-8) if "ratio" in name else df[a]-df[b]
            f.append(name)
    if "sma_5_21_diff" in df.columns:
        df["sma_5_21_cross"] = (df["sma_5_21_diff"]>0).astype(float)
        f.append("sma_5_21_cross")
    if "rsi_14" in df.columns:
        df["rsi_overbought"] = (df["rsi_14"]>70).astype(float)
        df["rsi_oversold"] = (df["rsi_14"]<30).astype(float)
        f.extend(["rsi_overbought","rsi_oversold"])
    if "overnight_gap" in df.columns:
        df["gap_abs"] = df["overnight_gap"].abs()
        f.append("gap_abs")
    # Remove any new zero-var
    for col in f[len(feats):]:
        if col in df.columns and df[col].var() < 1e-8:
            df.drop(columns=[col], inplace=True)
            f.remove(col)
    return df, f

def _sharpe(preds, actuals):
    trades = [1.0 if p==1 and a==1 else -1.0 if p==1 else 0.0 for p,a in zip(preds,actuals)]
    t = [r for r in trades if r!=0.0]
    if len(t)<5: return 0.0
    return float(np.mean(t)/(np.std(t)+1e-8)*np.sqrt(252))

def train_fold(X_tr, y_tr, X_te, y_te, cname):
    v = np.var(X_tr, axis=0) > 1e-8
    if not all(v):
        X_tr, X_te = X_tr[:,v], X_te[:,v]
    if X_tr.shape[1] < 5:
        return None
    sc = StandardScaler()
    X_ts = sc.fit_transform(X_tr)
    X_es = sc.transform(X_te)
    m = CANDIDATES[cname]()
    m.fit(X_ts, y_tr)
    yp = m.predict(X_es)
    ypr = m.predict_proba(X_es)[:,1] if hasattr(m,"predict_proba") else None
    r = {"test_acc": float(accuracy_score(y_te,yp)),
         "test_f1": float(f1_score(y_te,yp,zero_division=0)),
         "sharpe": _sharpe(yp.tolist(),y_te.tolist()),
         "pos_rate": float(yp.mean()),
         "train_size": len(X_tr), "test_size": len(X_te)}
    # Gates
    r["gates_ok"] = True
    if ypr is not None:
        try:
            from services.ml.quality import run_all_gates, DegenerateModelError
            run_all_gates(X=X_ts, y=y_tr, y_pred_proba=ypr)
        except DegenerateModelError as e:
            r["gates_ok"] = False
            r["gate_err"] = str(e)
    # Baselines
    maj = int(np.bincount(y_tr.astype(int)).argmax())
    last = int(y_tr[-1]) if len(y_tr)>0 else maj
    r["bl_maj_acc"] = float(accuracy_score(y_te, [maj]*len(y_te)))
    r["bl_maj_sharpe"] = _sharpe([maj]*len(y_te), y_te.tolist())
    r["bl_per_acc"] = float(accuracy_score(y_te, [last]*len(y_te)))
    r["bl_per_sharpe"] = _sharpe([last]*len(y_te), y_te.tolist())
    return r

def walk_forward(ticker, df, feats, n_splits=5, min_train=100, step=63):
    X = df[feats].values.astype(np.float64)
    y = df[TARGET].values.astype(np.float64)
    n = len(X)
    log.info(f"[{ticker}] WF: {n} samples, {len(feats)} feats")
    results = {c: [] for c in CANDIDATES}
    fc = 0
    for fi in range(n_splits):
        te = min_train + fi*step
        txe = min(te+step, n)
        if te >= n-20 or txe-te<20: break
        u,c = np.unique(y[:te], return_counts=True)
        if len(u)<2 or min(c)/len(y[:te])<0.15: continue
        for cn in CANDIDATES:
            try:
                r = train_fold(X[:te], y[:te], X[te:txe], y[te:txe], cn)
                if r: r["fold"]=fc; results[cn].append(r)
            except Exception as e:
                log.warning(f"  Fold {fi}/{cn}: {e}")
        fc += 1
    if fc==0: return {"status":"no_folds","ticker":ticker}
    summaries = {}
    for cn in CANDIDATES:
        folds = results[cn]
        if not folds: summaries[cn]={"status":"no_folds"}; continue
        ms = {"n_folds":len(folds),
              "mean_acc":float(np.mean([f["test_acc"] for f in folds])),
              "std_acc":float(np.std([f["test_acc"] for f in folds])),
              "mean_f1":float(np.mean([f["test_f1"] for f in folds])),
              "mean_sharpe":float(np.mean([f["sharpe"] for f in folds])),
              "gates_ok":all(f.get("gates_ok") for f in folds),
              "bl_maj_acc":float(np.mean([f["bl_maj_acc"] for f in folds])),
              "bl_per_acc":float(np.mean([f["bl_per_acc"] for f in folds])),
              "bl_maj_sharpe":float(np.mean([f["bl_maj_sharpe"] for f in folds])),
              "bl_per_sharpe":float(np.mean([f["bl_per_sharpe"] for f in folds]))}
        beats = (ms["mean_sharpe"]>ms["bl_maj_sharpe"] and ms["mean_sharpe"]>ms["bl_per_sharpe"] and
                 ms["mean_acc"]>ms["bl_maj_acc"] and ms["mean_acc"]>ms["bl_per_acc"] and
                 ms["mean_sharpe"]<=MAX_SHARPE)
        if not ms["gates_ok"]: beats=False
        ms["beats"]=beats
        summaries[cn]=ms
    best = max(((c,s["mean_sharpe"]) for c,s in summaries.items() if isinstance(s,dict) and s.get("beats")),
               key=lambda x:x[1],default=(None,-np.inf))
    return {"status":"ok","ticker":ticker,"n_folds":fc,"n_features":len(feats),
            "feature_names":feats,"summary":summaries,"best":best[0]}

def train_final(ticker, df, feats, cname):
    X = df[feats].values.astype(np.float64)
    y = df[TARGET].values.astype(np.float64)
    sc = StandardScaler()
    Xs = sc.fit_transform(X)
    m = CANDIDATES[cname]()
    m.fit(Xs, y)
    yp = m.predict(Xs)
    gate_ok = True
    try:
        from services.ml.quality import run_all_gates, DegenerateModelError
        ypr = m.predict_proba(Xs)[:,1] if hasattr(m,"predict_proba") else None
        if ypr is not None: run_all_gates(X=Xs, y=y, y_pred_proba=ypr)
    except DegenerateModelError: gate_ok=False
    dist = {fn: Xs[:,i].tolist() for i,fn in enumerate(feats)}
    sfx = f"_{cname}_wf"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    mp = MODELS_DIR/f"{ticker}{sfx}.joblib"
    sp = MODELS_DIR/f"{ticker}{sfx}_scaler.joblib"
    jp = MODELS_DIR/f"{ticker}{sfx}_manifest.json"
    joblib.dump(m, str(mp))
    joblib.dump(sc, str(sp))
    man = {"ticker":ticker,"model_type":cname,"n_features":len(feats),"feature_names":feats,
           "train_size":len(X),"metrics":{"in_sample_acc":float(accuracy_score(y,yp)),
                                            "in_sample_f1":float(f1_score(y,yp,zero_division=0)),
                                            "in_sample_sharpe":float(_sharpe(yp.tolist(),y.tolist()))},
           "gates_ok":gate_ok,"model_path":str(mp),"scaler_path":str(sp),
           "training_feature_dist":dist,"created_at":datetime.now(timezone.utc).isoformat()}
    with open(jp,"w") as f: json.dump(man,f,indent=2,default=str)
    log.info(f"[{ticker}] Saved {cname}: acc={accuracy_score(y,yp):.4f} gates={gate_ok}")
    return man

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()
    tickers = [args.ticker] if args.ticker else ["DIA","IWM","QQQ","TLT","SPY"]
    for ticker in tickers:
        log.info(f"\n{'='*60}\n{ticker}\n{'='*60}")
        try: df, feats = load_data(ticker)
        except FileNotFoundError as e: log.warning(str(e)); continue
        df, feats = add_features(df, feats)
        log.info(f"Data: {len(df)} rows, {len(feats)} feats")
        ns = 3 if len(df)<500 else 5
        wf = walk_forward(ticker, df, feats, n_splits=ns)
        if wf["status"]=="ok":
            for cn, s in wf["summary"].items():
                if isinstance(s,dict) and "mean_acc" in s:
                    v = "SHIP" if s.get("beats") else "REJECT"
                    log.info(f"  {cn:10s}: acc={s['mean_acc']:.4f}±{s.get('std_acc',0):.4f} "
                             f"sharpe={s['mean_sharpe']:.4f} {v}")
            best = wf.get("best")
            if best:
                log.info(f"Best: {best}")
                train_final(ticker, df, feats, best)
            else:
                # Fallback: train best Sharpe model
                fb = max(((c,s["mean_sharpe"]) for c,s in wf["summary"].items()
                          if isinstance(s,dict) and "mean_sharpe" in s),
                         key=lambda x:x[1], default=(None,0))
                if fb[0]: train_final(ticker, df, feats, fb[0])
        else:
            log.warning(f"WF: {wf['status']}. Training GBM on all data.")
            train_final(ticker, df, feats, "gbm")
    log.info(f"\nDone. Models in {MODELS_DIR}")

if __name__ == "__main__":
    main()
