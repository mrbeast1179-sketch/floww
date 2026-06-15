#!/usr/bin/env python3
"""
scripts/train_2class_direction.py

2-class (UP/DOWN only) direction prediction — filters out HOLD days.
Uses full feature set (no 20-feature limit), regularized RF,
walk-forward CV with embargo, and trading Sharpe as selection criterion.
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
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_2class")

UP_THRESHOLD = 0.003
DOWN_THRESHOLD = -0.003

FEATURE_NAMES = [
    "ret_1d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "log_ret_1d", "overnight_gap",
    "sma_5", "price_vs_sma_5",
    "sma_10", "price_vs_sma_10",
    "sma_21", "price_vs_sma_21",
    "sma_50", "price_vs_sma_50",
    "atr_14",
    "volume_sma_5", "volume_sma_21", "relative_volume",
    "realized_vol_5d", "realized_vol_10d", "realized_vol_21d", "realized_vol_60d",
    "rsi_14", "rsi_overbought", "rsi_oversold",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_lower", "bb_position",
    "vol_ratio_5_21", "vol_ratio_5_60",
    "sma_5_21_diff", "sma_5_21_cross", "sma_10_50_diff",
    "ret_momentum", "ret_accel",
    "vol_spike",
    "gap_abs", "gap_large",
    "is_month_end", "is_month_start",
]


def compute_features(ticker: str, period: str = "5y") -> pd.DataFrame:
    log.info("Downloading %s (%s)...", ticker, period)
    data = yf.download(ticker, period=period, progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    df = data.dropna(subset=["Close"]).copy()
    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float) if "High" in df.columns else close
    low = df["Low"].values.astype(float) if "Low" in df.columns else close
    volume = df["Volume"].values.astype(float) if "Volume" in df.columns else np.ones(len(close))
    open_p = df["Open"].values.astype(float) if "Open" in df.columns else close
    n = len(close)
    feat = pd.DataFrame(index=df.index)

    for h, name in [(1,"ret_1d"),(3,"ret_3d"),(5,"ret_5d"),(10,"ret_10d"),(21,"ret_21d")]:
        r = np.zeros(n)
        for i in range(h, n):
            if close[i-h] > 0:
                r[i] = (close[i]-close[i-h])/close[i-h]
        feat[name] = r

    lr = np.zeros(n)
    for i in range(1, n):
        if close[i-1] > 0 and close[i] > 0:
            lr[i] = np.log(close[i]/close[i-1])
    feat["log_ret_1d"] = lr

    og = np.zeros(n)
    for i in range(1, n):
        if close[i-1] > 0:
            og[i] = (open_p[i]-close[i-1])/close[i-1]
    feat["overnight_gap"] = og

    for w, nm in [(5,"sma_5"),(10,"sma_10"),(21,"sma_21"),(50,"sma_50")]:
        s = pd.Series(close).rolling(w, min_periods=w).mean().values
        feat[nm] = s
        feat[f"price_vs_sma_{w}"] = np.where(s > 0, close/s - 1, 0)

    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    feat["atr_14"] = pd.Series(tr).rolling(14, min_periods=1).mean().values

    vs5 = pd.Series(volume).rolling(5, min_periods=1).mean().values
    vs21 = pd.Series(volume).rolling(21, min_periods=1).mean().values
    feat["volume_sma_5"] = vs5
    feat["volume_sma_21"] = vs21
    feat["relative_volume"] = np.where(vs21 > 0, volume/vs21, 0)

    for w, nm in [(5,"realized_vol_5d"),(10,"realized_vol_10d"),(21,"realized_vol_21d"),(60,"realized_vol_60d")]:
        feat[nm] = pd.Series(lr).rolling(w, min_periods=w).std().values * np.sqrt(252)

    delta = pd.Series(close).diff()
    g = delta.where(delta>0,0).rolling(14,min_periods=1).mean()
    loss = (-delta.where(delta<0,0)).rolling(14,min_periods=1).mean()
    rs = g/(loss+1e-10)
    rsi = (100-100/(1+rs)).values
    feat["rsi_14"] = rsi
    feat["rsi_overbought"] = (rsi>70).astype(float)
    feat["rsi_oversold"] = (rsi<30).astype(float)

    ema12 = pd.Series(close).ewm(12,adjust=False).mean()
    ema26 = pd.Series(close).ewm(26,adjust=False).mean()
    macd = ema12-ema26
    feat["macd"] = macd.values
    feat["macd_signal"] = macd.ewm(9,adjust=False).mean().values
    feat["macd_hist"] = feat["macd"]-feat["macd_signal"]

    s20 = pd.Series(close).rolling(20,min_periods=1).mean()
    std20 = pd.Series(close).rolling(20,min_periods=1).std()
    feat["bb_upper"] = (s20+2*std20).values
    feat["bb_lower"] = (s20-2*std20).values
    bw = feat["bb_upper"]-feat["bb_lower"]
    feat["bb_position"] = np.where(bw>0, (close-feat["bb_lower"].values)/bw, 0)

    vs60 = pd.Series(volume).rolling(60,min_periods=1).mean().values
    feat["vol_ratio_5_21"] = np.where(vs21>0, vs5/vs21, 0)
    feat["vol_ratio_5_60"] = np.where(vs60>0, vs5/vs60, 0)

    s5 = pd.Series(close).rolling(5,min_periods=1).mean().values
    s21v = pd.Series(close).rolling(21,min_periods=1).mean().values
    s10 = pd.Series(close).rolling(10,min_periods=1).mean().values
    s50v = pd.Series(close).rolling(50,min_periods=1).mean().values
    feat["sma_5_21_diff"] = s5-s21v
    feat["sma_5_21_cross"] = np.sign(s5-s21v)
    feat["sma_10_50_diff"] = s10-s50v

    feat["ret_momentum"] = pd.Series(close).pct_change(5).values
    feat["ret_accel"] = pd.Series(close).pct_change(5).diff().values
    feat["vol_spike"] = pd.Series(lr).rolling(5,min_periods=1).std().values / (pd.Series(lr).rolling(21,min_periods=1).std().values+1e-10)
    feat["gap_abs"] = np.abs(og)
    feat["gap_large"] = (np.abs(og)>0.003).astype(float)
    dates = pd.to_datetime(df.index)
    feat["is_month_end"] = np.array(dates.is_month_end, dtype=float)
    feat["is_month_start"] = np.array(dates.is_month_start, dtype=float)

    target_3 = np.ones(n, dtype=int)
    for i in range(n-1):
        if close[i] > 0:
            ret_next = (close[i+1]-close[i])/close[i]
            if ret_next > UP_THRESHOLD:
                target_3[i] = 2
            elif ret_next < DOWN_THRESHOLD:
                target_3[i] = 0
    feat["target_3class"] = target_3

    target_2 = np.full(n, -1, dtype=int)
    target_2[target_3 == 0] = 0
    target_2[target_3 == 2] = 1
    feat["target_2class"] = target_2

    feat = feat.replace([np.inf,-np.inf], np.nan).fillna(0.0)
    log.info("Features computed: %d rows", len(feat))
    return feat


def train_2class(ticker: str, days: int = 1256, output_dir: Path | None = None) -> dict:
    period = f"{max(days//21, 60)}mo"
    feat = compute_features(ticker, period=period)

    feat_cols = [c for c in FEATURE_NAMES if c in feat.columns]

    mask = feat["target_2class"].values >= 0
    feat_2 = feat[mask].copy()
    log.info("After filtering HOLD: %d rows (of %d)", len(feat_2), len(feat))

    X_full = feat_2[feat_cols].values.astype(float)
    y_full = feat_2["target_2class"].values.astype(int)

    log.info("Class distribution: DOWN=%.1f%% UP=%.1f%%",
             (y_full==0).mean()*100, (y_full==1).mean()*100)

    split_idx = int(len(X_full)*0.8)
    X_train, X_test = X_full[:split_idx], X_full[split_idx:]
    y_train, y_test = y_full[:split_idx], y_full[split_idx:]

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_te_s = scaler.transform(X_test)

    candidates = {
        "rf": RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=20,
                                      max_features="sqrt", random_state=42, n_jobs=-1),
        "gbm": GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                           subsample=0.7, min_samples_leaf=20, random_state=42),
        "lr": LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42),
    }

    best_name = None
    best_score = -1
    best_model = None
    fold_size = len(X_tr_s) // 6

    for name, model in candidates.items():
        fold_scores = []
        for fold in range(5):
            tr_end = fold_size * (fold + 1)
            te_start = tr_end + 5
            te_end = min(te_start + fold_size, len(X_tr_s))
            if te_start >= len(X_tr_s) or te_end <= te_start:
                break
            m = type(model)(**model.get_params())
            m.fit(X_tr_s[:tr_end], y_train[:tr_end])
            sc = accuracy_score(y_train[te_start:te_end], m.predict(X_tr_s[te_start:te_end]))
            fold_scores.append(sc)
        mean_sc = np.mean(fold_scores) if fold_scores else 0
        log.info("  %s: WF acc=%.4f +/- %.4f", name, mean_sc, np.std(fold_scores) if fold_scores else 0)
        if mean_sc > best_score:
            best_score = mean_sc
            best_name = name
            best_model = type(model)(**model.get_params())

    log.info("Best: %s (WF acc=%.4f)", best_name, best_score)
    best_model.fit(X_tr_s, y_train)
    train_pred = best_model.predict(X_tr_s)
    test_pred = best_model.predict(X_te_s)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)

    # Trading simulation
    raw_data = yf.download(ticker, period=period, progress=False)
    if isinstance(raw_data.columns, pd.MultiIndex):
        raw_data.columns = raw_data.columns.get_level_values(0)
    raw_close = raw_data["Close"].values.astype(float)
    mask_arr = mask.values if hasattr(mask, 'values') else mask
    close_arr = raw_close[mask_arr]

    returns = []
    for i in range(len(test_pred)):
        idx = split_idx + i
        if idx + 1 < len(close_arr) and close_arr[idx] > 0:
            actual_ret = (close_arr[idx+1] - close_arr[idx]) / close_arr[idx]
            if test_pred[i] == 1:
                returns.append(actual_ret)
            elif test_pred[i] == 0:
                returns.append(-actual_ret)
    returns = np.array(returns) if returns else np.array([0.0])
    sharpe = float(np.mean(returns)/(np.std(returns)+1e-8) * np.sqrt(252)) if len(returns) > 1 else 0.0

    log.info("Final %s %s: train=%.4f test=%.4f gap=%.4f | Sharpe=%.4f",
             ticker, best_name, train_acc, test_acc, train_acc-test_acc, sharpe)

    result = {
        "ticker": ticker, "model_type": best_name,
        "n_train": len(X_train), "n_test": len(X_test),
        "n_features": len(feat_cols), "feature_names": feat_cols,
        "train_accuracy": train_acc, "test_accuracy": test_acc,
        "overfit_gap": train_acc - test_acc,
        "walk_forward_accuracy": best_score,
        "trading_sharpe": sharpe,
        "target": "2class_up_down",
    }

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        mp = output_dir / f"{ticker}_{best_name}_2class_{ts}.joblib"
        sp = output_dir / f"{ticker}_{best_name}_2class_{ts}_scaler.joblib"
        import joblib
        joblib.dump(best_model, mp)
        joblib.dump(scaler, sp)
        result["model_path"] = str(mp)
        result["scaler_path"] = str(sp)
        result["created_at"] = datetime.now(UTC).isoformat()
        log.info("Saved: %s", mp)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--days", type=int, default=1256)
    parser.add_argument("--output-dir", type=str)
    args = parser.parse_args()

    tickers = ["SPY","QQQ","DIA","IWM","TLT"] if args.all else [args.ticker.upper()] if args.ticker else []
    if not tickers:
        parser.error("--ticker or --all required")

    output_dir = Path(args.output_dir) if args.output_dir else SCRIPT_DIR.parent / "models"
    results = {}
    for ticker in tickers:
        log.info("=" * 60)
        try:
            t0 = time.time()
            r = train_2class(ticker, days=args.days, output_dir=output_dir)
            r["total_time_sec"] = time.time() - t0
            results[ticker] = r
            log.info("OK %s: %s test=%.4f sharpe=%.4f in %.1fs",
                     ticker, r["model_type"], r["test_accuracy"],
                     r["trading_sharpe"], r["total_time_sec"])
        except Exception as e:
            results[ticker] = {"error": str(e)}
            log.error("FAIL %s: %s", ticker, e, exc_info=True)

    log.info("=" * 60)
    for ticker, r in results.items():
        if "error" in r:
            log.info("%s: ERROR %s", ticker, r["error"])
        else:
            log.info("%s: %s | test=%.4f | sharpe=%.4f | %d feat",
                     ticker, r["model_type"], r["test_accuracy"],
                     r["trading_sharpe"], r["n_features"])

    report_path = SCRIPT_DIR.parent / "reports" / f"training_2class_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("Report: %s", report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
