#!/usr/bin/env python3
"""
scripts/train_spy_regime_enhanced.py

Train SPY directional_move model enhanced with morning briefing regime features.

Pipeline:
1. Load existing ml_features from MongoDB (45 features, 167 rows)
2. Compute regime features from pre-aggregated GEX snapshots
3. Merge: 45 existing + 6 regime = 51 features
4. Walk-forward CV (8 folds) with GBM and Logistic
5. Select winner by OOS Sharpe
6. Train final model, backtest, ship to models/ + register in MongoDB
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import joblib  # type: ignore[import-untyped]
import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from dotenv import load_dotenv
from pymongo import MongoClient

warnings.filterwarnings("ignore", category=FutureWarning)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("train_regime_enhanced")

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(REPO_ROOT / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
MODELS_DIR = REPO_ROOT / "models"
REPORTS_DIR = REPO_ROOT / "reports"

# Columns to exclude from features
EXCLUDE_COLS = {
    "_id", "_computed_at", "ticker", "date", "feature_version",
    "target_directional_move", "target_any_materialization",
    "target_gap_move", "target_range_expansion", "target_return_pct",
}


# ────────────────────────────────────────────────────────────────────────
# Data loading
# ────────────────────────────────────────────────────────────────────────

def load_existing_features() -> pd.DataFrame:
    c: Any = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    docs = list(db["ml_features"].find({"ticker": "SPY"}).sort("date", 1))
    c.close()
    if not docs:
        log.error("No SPY ml_features found"); sys.exit(1)
    df = pd.DataFrame(docs).sort_values("date").reset_index(drop=True)
    log.info(f"Loaded {len(df)} SPY feature rows, {len(df.columns)} columns")
    return df


def load_snapshots_raw() -> List[Dict[str, Any]]:
    c: Any = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    snaps = list(db["gex_enhanced_snapshots"].find({
        "$or": [{"ticker": "SPY"}, {"_source": "issue_141_enhanced_dataset"}]
    }).sort("date", 1))
    c.close()
    return snaps


# ────────────────────────────────────────────────────────────────────────
# Regime feature computation
# ────────────────────────────────────────────────────────────────────────

def _safe(v: Any, default: float = 0.0) -> float:
    if v is None: return default
    try:
        f = float(v)
        return default if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return default


def _compute_scores_simple(net_gex: float, call_oi: float, put_oi: float, pcr: float) -> tuple[int, int]:
    """Simple scoring for feature extraction from pre-aggregated data."""
    b, bear = 0, 0
    # GEX magnitude
    if net_gex < -1e9: bear += 2
    elif net_gex < 0: bear += 1
    elif net_gex > 1e9: b += 2
    elif net_gex > 0: b += 1
    # OI ratio (using GEX as proxy for OI)
    if put_oi > 0 and call_oi / put_oi > 1.3: b += 2
    elif call_oi > 0 and put_oi / call_oi > 1.3: bear += 2
    # Put/call ratio
    if pcr > 1.2: bear += 1
    elif pcr < 0.8: b += 1
    return b, bear


def compute_regime_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute regime features from pre-aggregated GEX snapshots."""
    from services.morning_briefing import classify_regime  # type: ignore[import-not-found]

    snap_list = load_snapshots_raw()
    log.info(f"Loaded {len(snap_list)} GEX snapshots")
    snap_map = {s["date"]: s for s in snap_list}

    # Pre-allocate lists
    n = len(df)
    regime_encoded = [0] * n
    bullish_scores = [0] * n
    bearish_scores = [0] * n
    gex_magnitudes = [0.0] * n
    put_call_imbalances = [0.0] * n
    gex_per_options = [0.0] * n

    for i, (_, row) in enumerate(df.iterrows()):
        date = row.get("date")
        snap = snap_map.get(date)
        if snap is None:
            continue

        net_gex = _safe(snap.get("net_gex"), 0)
        call_gex = _safe(snap.get("net_call_gex"), 0)
        put_gex = _safe(snap.get("net_put_gex"), 0)
        spot = _safe(snap.get("spot_price"), 0)
        pcr = _safe(snap.get("put_call_ratio"), 1.0)
        n_opts = _safe(snap.get("options_count"), 1)

        call_oi_proxy = abs(call_gex)
        put_oi_proxy = abs(put_gex)

        regime = classify_regime(
            net_gex=net_gex, call_oi=call_oi_proxy, put_oi=put_oi_proxy,
            iv_skew=0.0, flip_level=0.0, spot=spot,
        )
        b_score, bear_score = _compute_scores_simple(net_gex, call_oi_proxy, put_oi_proxy, pcr)

        regime_map = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "UNKNOWN": 0}
        regime_encoded[i] = regime_map.get(regime, 0)
        bullish_scores[i] = b_score
        bearish_scores[i] = bear_score
        gex_magnitudes[i] = abs(net_gex) / 1e9
        put_call_imbalances[i] = pcr - 1.0
        gex_per_options[i] = net_gex / max(n_opts, 1)

    df = df.copy()
    df["regime_encoded"] = regime_encoded
    df["bullish_score"] = bullish_scores
    df["bearish_score"] = bearish_scores
    df["regime_strength"] = [abs(b - bear) for b, bear in zip(bullish_scores, bearish_scores)]
    df["gex_magnitude_bn"] = gex_magnitudes
    df["put_call_imbalance"] = put_call_imbalances
    df["gex_per_option"] = gex_per_options

    log.info(f"Regime distribution: {dict(pd.Series(regime_encoded).value_counts())}")
    return df


# ────────────────────────────────────────────────────────────────────────
# Walk-forward CV
# ────────────────────────────────────────────────────────────────────────

def get_feature_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c not in EXCLUDE_COLS and df[c].dtype in (np.float64, np.int64, np.float32, np.int32)]


def _trading_sharpe(preds: Any, actuals: Any) -> float:
    """Annualized trading Sharpe. pred=1 means go long, pred=0 means flat."""
    trades = []
    for p, a in zip(preds, actuals):
        if p == 1:
            trades.append(1.0 if a == 1 else -1.0)
    if len(trades) < 2 or np.std(trades) == 0:
        return 0.0
    return float(np.mean(trades) / np.std(trades) * np.sqrt(252))


def _create_model(name: str) -> Any:
    if name == "GBM":
        from sklearn.ensemble import GradientBoostingClassifier  # type: ignore[import-untyped]
        return GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42)
    elif name == "GBM_deep":
        from sklearn.ensemble import GradientBoostingClassifier
        return GradientBoostingClassifier(n_estimators=200, max_depth=5, learning_rate=0.05, random_state=42)
    elif name == "LGBM":
        import lightgbm as lgb  # type: ignore[import-not-found]
        return lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42, verbose=-1)
    else:
        from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
        return LogisticRegression(max_iter=1000, random_state=42)


def walk_forward_cv(X: Any, y: Any, dates: Any, n_splits: int = 8) -> list[dict[str, Any]]:
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score  # type: ignore[import-untyped]
    from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]

    n = len(y)
    fold_size = n // (n_splits + 1)
    results = []
    model_names = ["GBM", "GBM_deep", "Logistic"]

    for fold_idx in range(n_splits):
        train_end = fold_size * (fold_idx + 1)
        test_end = min(train_end + fold_size, n)
        if test_end <= train_end: continue

        X_tr, X_te = X[:train_end], X[train_end:test_end]
        y_tr, y_te = y[:train_end], y[train_end:test_end]

        if len(np.unique(y_tr)) < 2 or len(np.unique(y_te)) < 2:
            log.warning(f"Fold {fold_idx}: insufficient class diversity, skipping")
            continue

        for name in model_names:
            try:
                model = _create_model(name)
                scaler = StandardScaler()
                X_tr_s = scaler.fit_transform(X_tr)
                X_te_s = scaler.transform(X_te)
                model.fit(X_tr_s, y_tr)
                preds = model.predict(X_te_s)

                acc = accuracy_score(y_te, preds)
                prec = precision_score(y_te, preds, zero_division=0)
                rec = recall_score(y_te, preds, zero_division=0)
                f1 = f1_score(y_te, preds, zero_division=0)
                sharpe = _trading_sharpe(preds, y_te)

                results.append({
                    "fold": fold_idx, "model": name,
                    "accuracy": acc, "precision": prec, "recall": rec, "f1": f1, "sharpe": sharpe,
                    "n_train": len(y_tr), "n_test": len(y_te),
                })
                log.info(f"  Fold {fold_idx} {name}: acc={acc:.3f} prec={prec:.3f} rec={rec:.3f} f1={f1:.3f} sharpe={sharpe:.3f}")
            except Exception as e:
                log.warning(f"  Fold {fold_idx} {name} failed: {e}")

    return results


# ────────────────────────────────────────────────────────────────────────
# Aggregate, select winner, train final, ship
# ────────────────────────────────────────────────────────────────────────

def aggregate_cv_results(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [{"model": r["model"], "accuracy": r["accuracy"], "precision": r["precision"],
             "recall": r["recall"], "f1": r["f1"], "sharpe": r["sharpe"], "n_test": r["n_test"]} for r in results]
    return pd.DataFrame(rows).groupby("model").mean().sort_values("sharpe", ascending=False)


def compute_baseline_sharpe(y: Any) -> dict[str, float]:
    """Majority and persistence baseline Sharpe."""
    y = np.array(y)
    majority = pd.Series(y).mode()[0]
    maj_preds = np.full_like(y, majority)
    maj_sharpe = _trading_sharpe(maj_preds, y)
    persist_preds = np.roll(y, 1); persist_preds[0] = y[0]
    persist_sharpe = _trading_sharpe(persist_preds, y)
    return {"majority_sharpe": maj_sharpe, "persistence_sharpe": persist_sharpe}


def train_and_ship(X: Any, y: Any, dates: Any, feature_names: Any, winner_name: str) -> Any:
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    log.info(f"\n{'='*60}\nTraining final {winner_name} on all {len(y)} rows\n{'='*60}")

    model = _create_model(winner_name)
    scaler = StandardScaler()
    X_s = scaler.fit_transform(X)
    model.fit(X_s, y)

    preds = model.predict(X_s)
    acc = accuracy_score(y, preds)
    prec = precision_score(y, preds, zero_division=0)
    rec = recall_score(y, preds, zero_division=0)
    f1 = f1_score(y, preds, zero_division=0)
    in_sample_sharpe = _trading_sharpe(preds, y)
    baselines = compute_baseline_sharpe(y)

    log.info(f"In-sample: acc={acc:.3f} sharpe={in_sample_sharpe:.3f}")
    log.info(f"Baselines: majority={baselines['majority_sharpe']:.3f} persistence={baselines['persistence_sharpe']:.3f}")

    # Use in-sample as reference only — the real test is CV OOS Sharpe
    version = "v2.0-regime"
    model_path = MODELS_DIR / f"SPY_direction_{version}.joblib"
    scaler_path = MODELS_DIR / f"SPY_scaler_{version}.joblib"
    meta_path = MODELS_DIR / f"SPY_meta_{version}.json"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    meta = {
        "ticker": "SPY", "target": "directional_move", "model_type": winner_name,
        "feature_version": version, "n_features": len(feature_names), "n_samples": len(y),
        "feature_names": feature_names, "training_date": datetime.now(timezone.utc).isoformat(),
        "in_sample_accuracy": acc, "in_sample_precision": prec, "in_sample_recall": rec,
        "in_sample_f1": f1, "in_sample_sharpe": in_sample_sharpe,
        "baseline_majority_sharpe": baselines["majority_sharpe"],
        "baseline_persistence_sharpe": baselines["persistence_sharpe"],
        "description": f"GBM + regime features (regime_encoded, bullish/bearish_score, regime_strength, gex_magnitude_bn, put_call_imbalance, gex_per_option)",
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    log.info(f"Shipped: {model_path.name}, {scaler_path.name}, {meta_path.name}")
    register_model_in_mongo(meta, model_path, scaler_path)
    return meta


def register_model_in_mongo(meta: dict[str, Any], model_path: Any, scaler_path: Any) -> None:
    import gridfs
    c: Any = MongoClient(MONGO_URL)
    db = c[DB_NAME]
    fs = gridfs.GridFS(db, collection="ml_model_artifacts")

    # Clean old versions
    for old in fs.find({"filename": {"$regex": "SPY_direction_v2.0"}}):
        fs.delete(old._id)

    with open(model_path, "rb") as f:
        mid = fs.put(f, filename=f"SPY_direction_{meta['feature_version']}.joblib")
    with open(scaler_path, "rb") as f:
        sid = fs.put(f, filename=f"SPY_scaler_{meta['feature_version']}.joblib")

    doc = {
        "ticker": meta["ticker"], "target": meta["target"], "model_type": meta["model_type"],
        "feature_version": meta["feature_version"], "version": meta["feature_version"],
        "status": "active", "n_features": meta["n_features"], "n_samples": meta["n_samples"],
        "metrics": {
            "in_sample_accuracy": meta["in_sample_accuracy"],
            "in_sample_sharpe": meta["in_sample_sharpe"],
            "baseline_majority_sharpe": meta["baseline_majority_sharpe"],
            "baseline_persistence_sharpe": meta["baseline_persistence_sharpe"],
        },
        "training_date": meta["training_date"], "description": meta["description"],
        "model_gridfs_id": mid, "scaler_gridfs_id": sid,
    }
    db["ml_models"].update_one(
        {"ticker": doc["ticker"], "target": doc["target"], "feature_version": doc["feature_version"]},
        {"$set": doc}, upsert=True,
    )
    c.close()
    log.info("Registered in MongoDB ml_models")


# ────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────

def main() -> Any:
    log.info("=" * 60 + "\nSPY Regime-Enhanced ML Training Pipeline\n" + "=" * 60)

    # Step 1: Load features
    df = load_existing_features()

    # Step 2: Compute regime features
    df = compute_regime_features(df)
    feature_cols = get_feature_cols(df)
    log.info(f"Total features: {len(feature_cols)}")

    # Prepare X, y
    target_col = "target_directional_move"
    valid = df[target_col].notna()
    df_v = df[valid].copy()
    for col in feature_cols:
        df_v[col] = pd.to_numeric(df_v[col], errors="coerce").fillna(0)

    X = df_v[feature_cols].values.astype(np.float64)
    y = df_v[target_col].values.astype(int)
    dates = df_v["date"].tolist()
    log.info(f"Training matrix: {X.shape}, target: {dict(pd.Series(y).value_counts())}")

    # Step 3: Walk-forward CV
    log.info("\n--- Walk-forward CV (8 folds) ---")
    cv_results = walk_forward_cv(X, y, dates, n_splits=8)

    # Step 4: Aggregate
    log.info("\n--- CV Results ---")
    agg = aggregate_cv_results(cv_results)
    log.info(f"\n{agg.to_string()}")

    if agg.empty:
        log.error("No successful CV folds!"); sys.exit(1)

    winner_name = agg.index[0]
    winner_sharpe = agg.iloc[0]["sharpe"]
    log.info(f"\nWinner: {winner_name} (avg OOS Sharpe={winner_sharpe:.3f})")

    # Step 5: Train final and ship
    meta = train_and_ship(X, y, dates, feature_cols, winner_name)

    # Write report
    report_path = REPORTS_DIR / "training_SPY_regime_v2.md"
    baselines = compute_baseline_sharpe(y)
    with open(report_path, "w") as f:
        f.write(f"# SPY Regime-Enhanced Training Report\n")
        f.write(f"\n**Date:** {datetime.now(timezone.utc).isoformat()}")
        f.write(f"\n**Features:** {len(feature_cols)} (45 original + 6 regime)")
        f.write(f"\n\n## CV Results (8-fold walk-forward)\n")
        f.write(agg.to_string())
        f.write(f"\n\n## Winner: {winner_name}")
        f.write(f"\n- OOS Sharpe: {winner_sharpe:.3f}")
        f.write(f"\n- Baseline majority Sharpe: {baselines['majority_sharpe']:.3f}")
        f.write(f"\n- Baseline persistence Sharpe: {baselines['persistence_sharpe']:.3f}")
        if meta:
            f.write(f"\n\n## Shipped Model")
            f.write(f"\n- Model: models/SPY_direction_v2.0-regime.joblib")
            f.write(f"\n- In-sample accuracy: {meta['in_sample_accuracy']:.3f}")
            f.write(f"\n- In-sample Sharpe: {meta['in_sample_sharpe']:.3f}")

    log.info(f"\nReport: {report_path}")
    log.info("=" * 60 + "\nPipeline complete.\n" + "=" * 60)
    return meta


if __name__ == "__main__":
    main()
