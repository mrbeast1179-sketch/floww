#!/usr/bin/env python3
"""
scripts/train_v5_production.py — Production ML training with GEX features.

2-class ensemble (GBM+RF+Logistic) with feature selection, walk-forward CV,
and confidence-threshold backtest. Trains SPY/QQQ/DIA/IWM/TLT on 5y data.

Usage:
    cd backend && .venv/bin/python3 -m scripts.train_v5_production --ticker SPY
    cd backend && .venv/bin/python3 -m scripts.train_v5_production --all
"""
from __future__ import annotations

import argparse, json, logging, math, sys, time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm, skew as sp_skew, kurtosis as sp_kurtosis
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("train_v5")

TICKERS = ["SPY", "QQQ", "DIA", "IWM", "TLT"]
UP_THRESH, DOWN_THRESH, EMBARGO = 0.003, -0.003, 5

def bs_gamma(S, K, T, r=0.05, sigma=0.2):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.0
    try:
        d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
        return float(norm.pdf(d1) / (S*sigma*math.sqrt(T)))
    except: return 0.0

def compute_gex_for_date(date, spot, ticker="SPY"):
    result = dict(net_gex=0.0, total_gex=0.0, gamma_flip=spot, put_call_ratio=1.0,
                  gex_n_strikes=0.0, gex_wall_density=float("nan"), gex_herfindahl=float("nan"),
                  net_gex_oi_weighted=0.0, implied_vol_avg=0.2, gex_skew=0.0, gex_kurtosis=0.0, call_put_gex_ratio=1.0)
    try:
        t = yf.Ticker(ticker)
        try: exps = list(t.options)
        except: return result
        if not exps: return result
        best_exp, best_dte = None, 999
        for e in exps:
            try:
                dte = (pd.Timestamp(e) - pd.Timestamp(date)).days
                if 7 <= dte <= 45 and dte < best_dte: best_dte, best_exp = dte, e
            except: continue
        if not best_exp: return result
        try: chain = t.option_chain(best_exp)
        except: return result
        T = max(best_dte/365.0, 1/365.0)
        gex_by_strike, tc_oi, tp_oi, cg, pg, ivs = {}, 0, 0, 0.0, 0.0, []
        for _, row in chain.calls.iterrows():
            s, oi = float(row.get("strike",0)), int(row.get("openInterest",0) or 0)
            iv = float(row.get("impliedVolatility",0) or 0)
            if s <= 0 or oi <= 0: continue
            sig = iv if 0.01 < iv < 5.0 else 0.2
            g = bs_gamma(spot, s, T, sigma=sig) * oi * 100.0 * spot**2 * 0.01
            gex_by_strike[s] = gex_by_strike.get(s, 0.0) + g; cg += g; tc_oi += oi
            if iv > 0: ivs.append(iv)
        for _, row in chain.puts.iterrows():
            s, oi = float(row.get("strike",0)), int(row.get("openInterest",0) or 0)
            iv = float(row.get("impliedVolatility",0) or 0)
            if s <= 0 or oi <= 0: continue
            sig = iv if 0.01 < iv < 5.0 else 0.2
            g = -bs_gamma(spot, s, T, sigma=sig) * oi * 100.0 * spot**2 * 0.01
            gex_by_strike[s] = gex_by_strike.get(s, 0.0) + g; pg += g; tp_oi += oi
            if iv > 0: ivs.append(iv)
        if not gex_by_strike: return result
        gv = list(gex_by_strike.values())
        net_gex, total_gex = sum(gv), sum(abs(v) for v in gv)
        gamma_flip = min(gex_by_strike.keys(), key=lambda s: abs(gex_by_strike[s]))
        low_b, high_b = spot*0.99, spot*1.01
        band = sum(abs(g) for s,g in gex_by_strike.items() if low_b <= s <= high_b)
        wall = band/total_gex if total_gex > 0 else float("nan")
        hhi = sum((abs(g)/total_gex)**2 for g in gv) if total_gex > 0 else float("nan")
        ga = np.array(gv)
        result.update(net_gex=net_gex, total_gex=total_gex, gamma_flip=gamma_flip,
                      put_call_ratio=tp_oi/max(tc_oi,1), gex_n_strikes=float(len(gex_by_strike)),
                      gex_wall_density=wall, gex_herfindahl=hhi,
                      net_gex_oi_weighted=net_gex/max(tc_oi+tp_oi,1),
                      implied_vol_avg=float(np.mean(ivs)) if ivs else 0.2,
                      gex_skew=float(sp_skew(ga)) if len(ga)>2 else 0.0,
                      gex_kurtosis=float(sp_kurtosis(ga)) if len(ga)>3 else 0.0,
                      call_put_gex_ratio=abs(cg/pg) if abs(pg)>1e-10 else 1.0)
    except: pass
    return result

def compute_technical_features(data):
    c = data["Close"].values.astype(float); h = data["High"].values.astype(float)
    l = data["Low"].values.astype(float); v = data["Volume"].values.astype(float)
    o = data["Open"].values.astype(float); n = len(c)
    f = pd.DataFrame(index=data.index)
    for hr, name in [(1,"ret_1d"),(3,"ret_3d"),(5,"ret_5d"),(10,"ret_10d"),(21,"ret_21d")]:
        r = np.zeros(n)
        for i in range(hr, n):
            if c[i-hr] > 0: r[i] = (c[i]-c[i-hr])/c[i-hr]
        f[name] = r
    lr = np.zeros(n)
    for i in range(1, n):
        if c[i-1] > 0 and c[i] > 0: lr[i] = np.log(c[i]/c[i-1])
    f["log_ret_1d"] = lr
    og = np.zeros(n)
    for i in range(1, n):
        if c[i-1] > 0: og[i] = (o[i]-c[i-1])/c[i-1]
    f["overnight_gap"] = og
    for w, name in [(5,"sma_5"),(10,"sma_10"),(21,"sma_21"),(50,"sma_50")]:
        sma = pd.Series(c).rolling(w, min_periods=w).mean()
        f[name] = sma.values
        f[f"price_vs_sma_{w}"] = (pd.Series(c)/sma.replace(0,np.nan)-1.0).fillna(0.0).values
    tr = np.zeros(n)
    for i in range(1, n): tr[i] = max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1]))
    f["atr_14"] = pd.Series(tr).rolling(14, min_periods=1).mean().values
    v5 = pd.Series(v).rolling(5, min_periods=1).mean(); v21 = pd.Series(v).rolling(21, min_periods=1).mean()
    f["volume_sma_5"] = v5.values; f["volume_sma_21"] = v21.values
    f["relative_volume"] = (pd.Series(v)/v21.replace(0,np.nan)).fillna(0.0).values
    for w, name in [(5,"realized_vol_5d"),(10,"realized_vol_10d"),(21,"realized_vol_21d"),(60,"realized_vol_60d")]:
        f[name] = pd.Series(lr).rolling(w, min_periods=w).std().values * np.sqrt(252)
    delta = pd.Series(c).diff()
    gain = delta.where(delta>0,0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta<0,0)).rolling(14, min_periods=1).mean()
    rs = gain/(loss+1e-10); rsi = (100-100/(1+rs)).values
    f["rsi_14"] = rsi; f["rsi_overbought"] = (rsi>70).astype(float); f["rsi_oversold"] = (rsi<30).astype(float)
    e12 = pd.Series(c).ewm(12, adjust=False).mean(); e26 = pd.Series(c).ewm(26, adjust=False).mean()
    macd = e12 - e26; sig = macd.ewm(9, adjust=False).mean()
    f["macd"] = macd.values; f["macd_signal"] = sig.values; f["macd_hist"] = (macd-sig).values
    s20 = pd.Series(c).rolling(20, min_periods=1).mean(); s20std = pd.Series(c).rolling(20, min_periods=1).std()
    bw = s20 + 2*s20std - (s20 - 2*s20std)
    f["bb_position"] = ((pd.Series(c)-(s20-2*s20std))/bw.replace(0,np.nan)).fillna(0.5).values
    v60 = pd.Series(v).rolling(60, min_periods=1).mean()
    f["vol_ratio_5_21"] = (v5/v21.replace(0,np.nan)).fillna(0.0).values
    f["vol_ratio_5_60"] = (v5/v60.replace(0,np.nan)).fillna(0.0).values
    f["ret_momentum"] = pd.Series(c).pct_change(5).values
    f["ret_accel"] = pd.Series(c).pct_change(5).diff().values
    f["vol_spike"] = (pd.Series(lr).rolling(5,min_periods=1).std()/(pd.Series(lr).rolling(21,min_periods=1).std()+1e-10)).values
    f["gap_abs"] = np.abs(og); f["gap_large"] = (np.abs(og)>0.003).astype(float)
    dt = pd.to_datetime(data.index)
    f["is_month_end"] = pd.Series(dt.is_month_end, index=data.index).astype(float).values
    f["is_month_start"] = pd.Series(dt.is_month_start, index=data.index).astype(float).values
    return f.replace([np.inf, -np.inf], np.nan).fillna(0.0)

def compute_gex_series(data, ticker):
    n = len(data); c = data["Close"].values.astype(float)
    cols = {k: np.zeros(n) for k in ["net_gex","total_gex","gamma_flip","put_call_ratio","gex_n_strikes",
            "gex_wall_density","gex_herfindahl","net_gex_oi_weighted","implied_vol_avg","gex_skew","gex_kurtosis","call_put_gex_ratio"]}
    cols["put_call_ratio"][:] = 1.0; cols["implied_vol_avg"][:] = 0.2
    cols["gex_wall_density"][:] = np.nan; cols["gex_herfindahl"][:] = np.nan
    start = max(0, n-252)
    log.info(f"GEX for {n-start} recent dates...")
    t0 = time.time()
    for i in range(start, n):
        spot = c[i]
        if spot <= 0: continue
        g = compute_gex_for_date(data.index[i], spot, ticker)
        for k, v in g.items():
            if k in cols: cols[k][i] = v
        if (i-start) % 50 == 0: log.info(f"  GEX: {i-start}/{n-start}")
    log.info(f"GEX: {time.time()-t0:.1f}s")
    if start > 0:
        rn = cols["net_gex"][start:]; rs = c[start:]; valid = rn != 0
        if valid.sum() > 10:
            lr2 = np.log(np.abs(rn[valid])+1); ls = np.log(rs[valid])
            A = np.column_stack([np.ones(len(ls)), ls])
            coeffs = np.linalg.lstsq(A, lr2, rcond=None)[0]
            for i in range(start):
                if c[i] > 0:
                    lp = coeffs[0] + coeffs[1]*np.log(c[i])
                    cols["net_gex"][i] = np.exp(lp)*np.sign(coeffs[1])
                    cols["total_gex"][i] = abs(cols["net_gex"][i])*1.5
                cols["gamma_flip"][i] = c[i]*1.005; cols["put_call_ratio"][i] = 1.0
                cols["gex_n_strikes"][i] = 50.0; cols["implied_vol_avg"][i] = 0.2
    gdf = pd.DataFrame(cols, index=data.index)
    gdf["net_gex_zscore_60d"] = (gdf["net_gex"]-gdf["net_gex"].rolling(60,min_periods=1).mean())/(gdf["net_gex"].rolling(60,min_periods=1).std()+1e-9)
    for hh in [1,5,10]:
        prev = gdf["net_gex"].shift(hh)
        gdf[f"net_gex_roc_{hh}d"] = (gdf["net_gex"]-prev)/(prev.abs()+1e-9)
    gdf["gex_regime_pos"] = (gdf["net_gex"]>0).astype(float)
    gdf["dist_to_flip_norm"] = (c - gdf["gamma_flip"])/c
    return gdf

def select_features(X, y, fnames, min_var=1e-6, max_corr=0.95, max_feat=30):
    n, p = X.shape; mask = np.ones(p, dtype=bool)
    mask &= np.var(X, axis=0) > min_var
    rem = np.where(mask)[0]
    if len(rem) > 1:
        corr = np.corrcoef(X[:, rem], rowvar=False)
        to_drop = set()
        for i in range(len(rem)):
            for j in range(i+1, len(rem)):
                if abs(corr[i,j]) > max_corr: to_drop.add(rem[j])
        for idx in to_drop: mask[idx] = False
    rem = np.where(mask)[0]
    if len(rem) > max_feat:
        rf = RandomForestClassifier(n_estimators=50, max_depth=3, random_state=42, n_jobs=-1)
        rf.fit(X[:, rem], y)
        top = np.argsort(rf.feature_importances_)[-max_feat:]
        nm = np.zeros(p, dtype=bool); nm[rem[top]] = True; mask = nm
    sel = [fnames[i] for i in range(p) if mask[i]]
    log.info(f"Selected {len(sel)} from {p}")
    return sel, np.where(mask)[0]

def compute_target(c, up=UP_THRESH, down=DOWN_THRESH):
    n = len(c); t = np.zeros(n, dtype=int)
    for i in range(n-1):
        if c[i] > 0:
            r = (c[i+1]-c[i])/c[i]
            if r > up: t[i] = 1
            elif r < down: t[i] = 0
            else: t[i] = -1
    return t

def walk_forward_cv(model, X, y, n_splits=5, embargo=EMBARGO):
    from sklearn.base import clone
    fs = len(X) // (n_splits+1); scores, ts = [], []
    for fold in range(n_splits):
        te = fs*(fold+1); ts_start = te+embargo; te_end = min(ts_start+fs, len(X))
        if te_end > len(X) or ts_start >= len(X): break
        m = clone(model); m.fit(X[:te], y[:te])
        ta = accuracy_score(y[:te], m.predict(X[:te]))
        t2 = accuracy_score(y[ts_start:te_end], m.predict(X[ts_start:te_end]))
        ts.append(ta); scores.append(t2)
        log.info(f"  Fold {fold+1}: train={ta:.4f} test={t2:.4f} gap={ta-t2:.4f}")
    return {"n_folds": len(scores), "mean_train": float(np.mean(ts)) if ts else 0,
            "mean_test": float(np.mean(scores)) if scores else 0, "std_test": float(np.std(scores)) if scores else 0}

def backtest(model, X, y, close, embargo=EMBARGO, conf_thresh=0.55):
    split = len(X)*7//10; te = split+embargo
    model.fit(X[:split], y[:split])
    tX, ty, tc = X[te:], y[te:], close[te:]
    preds = model.predict(tX)
    proba = model.predict_proba(tX) if hasattr(model, "predict_proba") else None
    sr = []
    for i in range(len(preds)-1):
        if proba is not None and max(proba[i]) < conf_thresh: sr.append(0.0); continue
        r = (tc[i+1]-tc[i])/tc[i]
        sr.append(r if preds[i]==1 else -r)
    sr = np.array(sr); n = min(len(sr), len(tc)-1)
    bnr = np.diff(tc[:n])/tc[:n-1]; sr2 = sr[:n-1]
    std_s = np.std(sr2) if len(sr2)>1 else 1e-10
    std_b = np.std(bnr) if len(bnr)>1 else 1e-10
    ss = float(np.mean(sr2)/std_s*np.sqrt(252)) if std_s > 0 else 0
    bs = float(np.mean(bnr)/std_b*np.sqrt(252)) if std_b > 0 else 0
    cum = np.cumsum(sr2); peak = np.maximum.accumulate(cum)
    return {"accuracy": float(np.mean(preds[:len(ty)]==ty[:len(preds)])),
            "strat_sharpe": ss, "bnh_sharpe": bs,
            "total_return": float(np.sum(sr2)), "bnh_total_return": float(np.sum(bnr)),
            "max_drawdown": float(np.min(cum-peak)), "n_days": len(sr2),
            "n_trades": sum(1 for r in sr if r!=0), "confidence_threshold": conf_thresh}

def train_ticker(ticker, period="5y"):
    log.info(f"{'='*60}\n{ticker} v5 ({period})\n{'='*60}")
    data = yf.download(ticker, period=period, progress=False)
    if data.empty: raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
    data = data.dropna(subset=["Close"])
    close = data["Close"].values.astype(float)
    log.info(f"Data: {data.shape}, {data.index[0].date()} -> {data.index[-1].date()}")
    tech = compute_technical_features(data)
    gex = compute_gex_series(data, ticker)
    all_f = pd.concat([tech, gex], axis=1)
    all_f = all_f.loc[:, ~all_f.columns.duplicated()].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    target = compute_target(close)
    all_f["target"] = target
    all_f = all_f.iloc[60:-1]; all_f = all_f[all_f["target"] >= 0]
    fc = [c for c in all_f.columns if c != "target"]
    X_full = all_f[fc].values.astype(float); y = all_f["target"].values.astype(int)
    cc = close[60:len(all_f)+60]
    log.info(f"Raw: {X_full.shape[1]} features, {X_full.shape[0]} samples")
    for cls, lbl in [(0,"DOWN"),(1,"UP")]: log.info(f"  {lbl}: {(y==cls).mean()*100:.1f}%")
    s70 = int(len(X_full)*0.7)
    sel_names, sel_idx = select_features(X_full[:s70], y[:s70], fc, min_var=1e-6, max_corr=0.95, max_feat=30)
    X_full = X_full[:, sel_idx]
    s70 = int(len(X_full)*0.7); s85 = int(len(X_full)*0.85)
    X_tr, y_tr = X_full[:s70], y[:s70]
    _X_val, _y_val = X_full[s70:s85], y[s70:s85]  # validation set (unused in current pipeline)
    X_te, y_te = X_full[s85:], y[s85:]
    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    _X_val_s = scaler.transform(_X_val)
    X_te_s = scaler.transform(X_te)
    gbm = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.7, min_samples_leaf=20, random_state=42)
    rf = RandomForestClassifier(n_estimators=200, max_depth=4, min_samples_leaf=15, max_features="sqrt", random_state=42, n_jobs=-1)
    lr = LogisticRegression(C=0.1, max_iter=1000, solver="lbfgs", random_state=42)
    ens = VotingClassifier(estimators=[("gbm",gbm),("rf",rf),("lr",lr)], voting="soft", weights=[2,1,1])
    log.info("Walk-forward CV...")
    cv = walk_forward_cv(ens, X_tr_s, y_tr, n_splits=5, embargo=EMBARGO)
    log.info(f"CV: {cv['mean_test']:.4f} ± {cv['std_test']:.4f}")
    X_tv_s = scaler.fit_transform(X_full[:s85]); y_tv = y[:s85]
    ens.fit(X_tv_s, y_tv)
    tp = ens.predict(X_te_s)
    te_acc = accuracy_score(y_te, tp)
    te_prec = precision_score(y_te, tp, zero_division=0)
    te_rec = recall_score(y_te, tp, zero_division=0)
    te_f1 = f1_score(y_te, tp, zero_division=0)
    log.info(f"Test: acc={te_acc:.4f} prec={te_prec:.4f} rec={te_rec:.4f} f1={te_f1:.4f}")
    bt = backtest(ens, X_full, y, cc)
    log.info(f"BT: sharpe={bt['strat_sharpe']:.2f} vs B&H={bt['bnh_sharpe']:.2f}")
    log.info(f"    return={bt['total_return']*100:.1f}% vs B&H={bt['bnh_total_return']*100:.1f}%")
    log.info(f"    max_dd={bt['max_drawdown']*100:.1f}% trades={bt['n_trades']}/{bt['n_days']}")
    rf.fit(X_tr_s, y_tr); imp = rf.feature_importances_
    ti = np.argsort(imp)[-10:][::-1]
    log.info("Top 10 features:")
    for i in ti: log.info(f"  {sel_names[i]}: {imp[i]:.4f}")
    import joblib
    od = SCRIPT_DIR.parent / "models"; od.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    fn = f"{ticker}_ensemble_v5_{ts}"
    mp = od/f"{fn}.joblib"; sp = od/f"{fn}_scaler.joblib"; mnp = od/f"{fn}_manifest.json"
    joblib.dump(ens, mp); joblib.dump(scaler, sp)
    manifest = {"ticker": ticker, "model_type": "ensemble_v5",
                "n_samples": len(X_full), "n_train": len(X_tr), "n_val": len(X_val), "n_test": len(X_te),
                "n_features": len(sel_names), "feature_names": sel_names,
                "test_accuracy": te_acc, "test_precision": te_prec, "test_recall": te_rec, "test_f1": te_f1,
                "walk_forward_mean": cv["mean_test"], "walk_forward_std": cv["std_test"],
                "n_folds": cv["n_folds"], "backtest": bt,
                "data_period": period, "data_range": f"{data.index[0].date()} to {data.index[-1].date()}",
                "n_raw_data_rows": len(data),
                "top_features": [(sel_names[i], float(imp[i])) for i in ti],
                "trained_at": datetime.now(UTC).isoformat()}
    with open(mnp, "w") as f: json.dump(manifest, f, indent=2, default=str)
    log.info(f"Saved: {mp.name}")
    return manifest

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--period", default="5y")
    args = parser.parse_args()
    tickers = TICKERS if args.all else [args.ticker]
    results = {}
    for t in tickers:
        try: results[t] = train_ticker(t, args.period)
        except Exception as e:
            log.error(f"Failed {t}: {e}"); results[t] = {"error": str(e)}
    print(f"\n{'='*70}")
    print(f"{'Ticker':<8} {'Test Acc':>10} {'WF CV':>10} {'Sharpe':>10} {'B&H':>10} {'Ret%':>10} {'MaxDD%':>10}")
    print(f"{'-'*70}")
    for t, m in results.items():
        if "error" in m: print(f"{t:<8} ERROR: {m['error'][:50]}")
        else:
            bt = m["backtest"]
            print(f"{t:<8} {m['test_accuracy']:>10.4f} {m['walk_forward_mean']:>10.4f} "
                  f"{bt['strat_sharpe']:>10.2f} {bt['bnh_sharpe']:>10.2f} "
                  f"{bt['total_return']*100:>9.1f}% {bt['max_drawdown']*100:>9.1f}%")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
