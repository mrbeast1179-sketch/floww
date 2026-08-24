#!/usr/bin/env python3
"""
scripts/train_v5_real_data_ml.py

Production ML training v5 — real 5yr yfinance data with:
  - 44 technical features from OHLCV
  - 3-class target (DOWN/HOLD/UP) with ±0.3% thresholds
  - Walk-forward CV with embargo gap
  - Feature selection: variance + correlation + importance filtering
  - Trains GBM + RF + LogR, picks best by walk-forward accuracy
  - Saves to models/<TICKER>_rf_5y_production.joblib + scaler + manifest

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_v5_real_data_ml --tickers SPY QQQ DIA IWM TLT
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("train_v5")

MODEL_DIR = SCRIPT_DIR.parent / "models"
REPORTS_DIR = SCRIPT_DIR.parent.parent / "reports"
MODEL_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003

FEATURE_NAMES = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "log_ret_1d", "overnight_gap",
    "sma_5", "price_vs_sma_5", "sma_10", "price_vs_sma_10",
    "sma_21", "price_vs_sma_21", "sma_50", "price_vs_sma_50",
    "atr_14",
    "volume_sma_5", "volume_sma_21", "relative_volume",
    "realized_vol_5d", "realized_vol_10d", "realized_vol_21d", "realized_vol_60d",
    "rsi_14", "rsi_overbought", "rsi_oversold",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_position",
    "vol_ratio_5_21", "vol_ratio_5_60",
    "sma_5_21_diff", "sma_5_21_cross", "sma_10_50_diff",
    "ret_momentum", "ret_accel",
    "vol_spike", "gap_abs", "gap_large",
    "is_month_end", "is_month_start",
]


def compute_features(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Download yfinance data and compute 44 technical features + 3-class target."""
    log.info("Downloading %s (period=%s)...", ticker, period)
    data = yf.download(ticker, period=period, progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data.copy()
    df = df.dropna(subset=["Close"])
    if len(df) < 100:
        raise ValueError(f"Only {len(df)} rows for {ticker}")

    close = df["Close"].astype(float)
    high = df["High"].astype(float) if "High" in df.columns else close
    low = df["Low"].astype(float) if "Low" in df.columns else close
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(1.0, index=df.index)
    open_p = df["Open"].astype(float) if "Open" in df.columns else close

    f = pd.DataFrame(index=df.index)

    for h, name in [(1,"ret_1d"),(3,"ret_3d"),(5,"ret_5d"),(10,"ret_10d"),(21,"ret_21d")]:
        f[name] = close.pct_change(h)
    f["log_ret_1d"] = np.log(close / close.shift(1))
    f["overnight_gap"] = open_p / close.shift(1) - 1.0

    for w in [5,10,21,50]:
        sma = close.rolling(w, min_periods=w).mean()
        f[f"sma_{w}"] = sma
        f[f"price_vs_sma_{w}"] = close / sma - 1.0

    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    f["atr_14"] = tr.rolling(14, min_periods=14).mean()

    v5 = volume.rolling(5, min_periods=5).mean()
    v21 = volume.rolling(21, min_periods=21).mean()
    v60 = volume.rolling(60, min_periods=60).mean()
    f["volume_sma_5"] = v5
    f["volume_sma_21"] = v21
    f["relative_volume"] = volume / v21
    f["vol_ratio_5_21"] = v5 / (v21 + 1e-10)
    f["vol_ratio_5_60"] = v5 / (v60 + 1e-10)

    lr = f["log_ret_1d"]
    for w in [5,10,21,60]:
        f[f"realized_vol_{w}d"] = lr.rolling(w, min_periods=w).std() * np.sqrt(252)

    delta = close.diff()
    gain = delta.where(delta>0, 0.0).rolling(14, min_periods=14).mean()
    loss = (-delta.where(delta<0, 0.0)).rolling(14, min_periods=14).mean()
    rs = gain / (loss + 1e-10)
    f["rsi_14"] = 100 - (100 / (1 + rs))
    f["rsi_overbought"] = (f["rsi_14"] > 70).astype(float)
    f["rsi_oversold"] = (f["rsi_14"] < 30).astype(float)

    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    macd = e12 - e26
    f["macd"] = macd
    f["macd_signal"] = macd.ewm(span=9, adjust=False).mean()
    f["macd_hist"] = macd - f["macd_signal"]

    s20 = close.rolling(20, min_periods=20).mean()
    s20std = close.rolling(20, min_periods=20).std()
    f["bb_upper"] = s20 + 2*s20std
    f["bb_lower"] = s20 - 2*s20std
    f["bb_position"] = (close - f["bb_lower"]) / (f["bb_upper"] - f["bb_lower"] + 1e-10)

    s5 = close.rolling(5, min_periods=5).mean()
    s10 = close.rolling(10, min_periods=10).mean()
    s21 = close.rolling(21, min_periods=21).mean()
    s50 = close.rolling(50, min_periods=50).mean()
    f["sma_5_21_diff"] = s5 - s21
    f["sma_5_21_cross"] = np.sign(f["sma_5_21_diff"])
    f["sma_10_50_diff"] = s10 - s50

    f["ret_momentum"] = close.pct_change(5)
    f["ret_accel"] = close.pct_change(5).diff()
    f["vol_spike"] = lr.rolling(5, min_periods=5).std() / (lr.rolling(21, min_periods=21).std() + 1e-10)
    f["gap_abs"] = f["overnight_gap"].abs()
    f["gap_large"] = (f["gap_abs"] > 0.003).astype(float)

    dt = pd.to_datetime(f.index)
    f["is_month_end"] = dt.is_month_end.astype(float)
    f["is_month_start"] = dt.is_month_start.astype(float)

    next_ret = close.pct_change(1).shift(-1)
    target = pd.Series(1, index=df.index, dtype=int)
    target = target.where(~next_ret.gt(UP_THRESHOLD), 2)
    target = target.where(~next_ret.lt(DOWN_THRESHOLD), 0)
    f["target_3class"] = target

    f = f.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    log.info("%s: %d rows, %d features computed", ticker, len(f), len(FEATURE_NAMES))
    return f


def select_features(X, y, feature_names, max_features=25):
    """3-stage feature selection: variance -> correlation -> importance."""
    n, d = X.shape
    mask = np.ones(d, dtype=bool)
    var = np.var(X, axis=0)
    mask[var < 0.0005] = False

    idx = np.where(mask)[0]
    if len(idx) > 1:
        corr = np.corrcoef(X[:, idx], rowvar=False)
        drop = set()
        for i in range(len(idx)):
            for j in range(i+1, len(idx)):
                if abs(corr[i,j]) > 0.92:
                    drop.add(idx[j])
        for k in drop:
            mask[k] = False

    idx = np.where(mask)[0]
    if len(idx) > max_features:
        from sklearn.ensemble import RandomForestClassifier
        quick = RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42, n_jobs=-1)
        quick.fit(X[:, idx], y)
        imp = quick.feature_importances_
        top = np.argsort(imp)[-max_features:]
        new_mask = np.zeros(d, dtype=bool)
        new_mask[idx[top]] = True
        mask = new_mask

    names = [feature_names[i] for i in range(d) if mask[i]]
    return names, [i for i in range(d) if mask[i]]


def walk_forward_cv(model, X, y, n_splits=8, embargo=5):
    """Walk-forward CV with embargo. Returns dict of metrics."""
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score

    fold_size = len(X) // (n_splits + 1)
    scores, train_scores = [], []

    for fold in range(n_splits):
        train_end = fold_size * (fold + 1)
        test_start = train_end + embargo
        test_end = min(test_start + fold_size, len(X))
        if test_end > len(X) or test_start >= len(X):
            break

        m = clone(model)
        m.fit(X[:train_end], y[:train_end])
        tr = accuracy_score(y[:train_end], m.predict(X[:train_end]))
        te = accuracy_score(y[test_start:test_end], m.predict(X[test_start:test_end]))
        train_scores.append(tr)
        scores.append(te)
        log.info("  Fold %d: train=%.4f test=%.4f", fold+1, tr, te)

    return {
        "n_folds": len(scores),
        "mean_train_acc": float(np.mean(train_scores)),
        "mean_test_acc": float(np.mean(scores)),
        "std_test_acc": float(np.std(scores)),
        "mean_gap": float(np.mean(train_scores) - np.mean(scores)),
        "fold_scores": [float(s) for s in scores],
    }


def _trading_sharpe(preds, actuals):
    """Simple trading Sharpe: go long on UP, short on DOWN, flat on HOLD."""
    rets = []
    for p, a in zip(preds, actuals, strict=False):
        if p == 2:  # predicted UP
            rets.append(1.0 if a == 2 else (-1.0 if a == 0 else 0.0))
        elif p == 0:  # predicted DOWN
            rets.append(1.0 if a == 0 else (-1.0 if a == 2 else 0.0))
        else:
            rets.append(0.0)
    r = np.array(rets)
    if r.std() < 1e-10:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(252))


def train_and_save(ticker: str, period: str = "5y"):
    """Train all candidates, pick best, save production artifacts."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score
    from sklearn.preprocessing import StandardScaler

    t0 = time.time()
    df = compute_features(ticker, period)

    feat_cols = [c for c in FEATURE_NAMES if c in df.columns]
    clean = df[feat_cols + ["target_3class"]].dropna()
    clean = clean[clean["target_3class"].notna()]
    clean = clean.iloc[:-1]

    if len(clean) < 200:
        raise ValueError(f"Only {len(clean)} rows for {ticker}")

    X_all = clean[feat_cols].values.astype(float)
    y_all = clean["target_3class"].values.astype(int)

    split = int(len(X_all) * 0.8)
    X_tr, X_te = X_all[:split], X_all[split:]
    y_tr, y_te = y_all[:split], y_all[split:]

    sel_names, sel_idx = select_features(X_tr, y_tr, feat_cols)
    X_tr_s = X_tr[:, sel_idx]
    X_te_s = X_te[:, sel_idx]

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr_s)
    X_te_s = scaler.transform(X_te_s)

    candidates = {
        "rf": RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=20, max_features="sqrt", random_state=42, n_jobs=-1),
        "gbm": GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.7, min_samples_leaf=20, random_state=42),
        "logistic": LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42),
    }

    best_name, best_model, best_cv, best_score = None, None, None, -999
    for name, model in candidates.items():
        log.info("Evaluating %s %s...", ticker, name)
        cv = walk_forward_cv(model, X_tr_s, y_tr, n_splits=8, embargo=5)
        log.info("  %s: wf_acc=%.4f +/- %.4f gap=%.4f", name, cv["mean_test_acc"], cv["std_test_acc"], cv["mean_gap"])
        if cv["mean_test_acc"] > best_score:
            best_score = cv["mean_test_acc"]
            best_name, best_model, best_cv = name, model, cv

    log.info("Best for %s: %s (wf_acc=%.4f)", ticker, best_name, best_score)
    best_model.fit(X_tr_s, y_tr)

    train_acc = accuracy_score(y_tr, best_model.predict(X_tr_s))
    test_acc = accuracy_score(y_te, best_model.predict(X_te_s))
    test_preds = best_model.predict(X_te_s)

    per_class = {}
    for cls, label in [(0,"DOWN"),(1,"HOLD"),(2,"UP")]:
        mask = y_te == cls
        if mask.sum() > 0:
            per_class[label] = float(accuracy_score(y_te[mask], test_preds[mask]))

    sharpe = _trading_sharpe(test_preds, y_te)
    total_time = time.time() - t0

    log.info("Final %s %s: train=%.4f test=%.4f gap=%.4f", ticker, best_name, train_acc, test_acc, train_acc-test_acc)
    log.info("Per-class: %s", per_class)
    log.info("Test Sharpe: %.4f", total_time)

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    model_path = MODEL_DIR / f"{ticker}_rf_5y_production.joblib"
    scaler_path = MODEL_DIR / f"{ticker}_rf_5y_production_scaler.joblib"
    manifest_path = MODEL_DIR / f"{ticker}_rf_5y_production_manifest.json"

    import joblib
    joblib.dump(best_model, model_path)
    joblib.dump(scaler, scaler_path)

    manifest = {
        "ticker": ticker, "model_type": best_name, "feature_version": "v5.0",
        "target": "3class_0.3pct", "n_samples": len(X_all), "n_train": len(X_tr), "n_test": len(X_te),
        "n_features": len(sel_names), "feature_names": sel_names,
        "train_accuracy": train_acc, "test_accuracy": test_acc, "overfit_gap": train_acc - test_acc,
        "walk_forward_mean": best_cv["mean_test_acc"], "walk_forward_std": best_cv["std_test_acc"],
        "walk_forward_gap": best_cv["mean_gap"], "walk_forward_folds": best_cv["n_folds"],
        "fold_scores": best_cv["fold_scores"], "per_class_test_accuracy": per_class,
        "trading_sharpe": float(sharpe), "total_time_sec": total_time,
        "created_at": datetime.now(UTC).isoformat(),
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    report_path = REPORTS_DIR / f"training_v5_{ticker}_{ts}.json"
    with open(report_path, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info("Saved: %s", model_path.name)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "DIA", "IWM", "TLT"])
    parser.add_argument("--period", default="5y")
    args = parser.parse_args()

    results = {}
    for ticker in args.tickers:
        try:
            results[ticker] = train_and_save(ticker, period=args.period)
        except Exception as e:
            log.error("%s FAILED: %s", ticker, e)
            import traceback
            traceback.print_exc()
            results[ticker] = {"error": str(e)}

    log.info("\n" + "="*70)
    log.info("V5 TRAINING SUMMARY")
    log.info("="*70)
    for t, r in results.items():
        if "error" in r:
            log.info(f"  {t}: FAILED - {r['error']}")
        else:
            log.info(f"  {t}: {r['model_type']} wf={r['walk_forward_mean']:.3f}±{r['walk_forward_std']:.3f} test={r['test_accuracy']:.3f} sharpe={r.get('trading_sharpe',0):.3f} n={r['n_samples']}")
    return results


if __name__ == "__main__":
    main()
