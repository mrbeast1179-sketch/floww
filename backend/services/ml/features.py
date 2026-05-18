"""
backend/services/ml/features.py

Feature engineering on real market data from MongoDB.

Computes ~50 features per ticker per date from:
- GEX snapshots (gex_enhanced_snapshots)
- Outcomes labels (gex_llm_patterns_outcomes)
- Underlying bars (underlying_bars)

All features are computed with strict no-leakage: features at time t only use
data available at or before t.

Feature version: v1.0 (stored alongside every feature row)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

log = logging.getLogger("ml.features")

FEATURE_VERSION = "v1.0"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_FEATURES = "ml_features"


def get_async_db():
    client = AsyncIOMotorClient(MONGO_URL)
    return client[DB_NAME]


# ============================================================================
# Data loading helpers
# ============================================================================

async def load_gex_snapshots(db, ticker: str = "SPY") -> List[Dict]:
    """Load GEX snapshots sorted by date."""
    cursor = db["gex_enhanced_snapshots"].find(
        {"_source": "issue_141_enhanced_dataset"}
    ).sort("date", 1)
    return await cursor.to_list(length=10000)


async def load_outcomes(db) -> List[Dict]:
    """Load labeled outcomes sorted by date."""
    cursor = db["gex_llm_patterns_outcomes"].find(
        {"_source": "issue_145_next_day_outcomes_2024"}
    ).sort("date", 1)
    return await cursor.to_list(length=10000)


async def load_underlying_bars(db, ticker: str) -> List[Dict]:
    """Load underlying OHLCV bars sorted by date."""
    cursor = db["underlying_bars"].find(
        {"ticker": ticker}
    ).sort("date", 1)
    return await cursor.to_list(length=100000)


# ============================================================================
# Feature computation
# ============================================================================

def _safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=0):
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def compute_returns(bars: List[Dict]) -> Dict[str, List[float]]:
    """Compute return series from OHLCV bars."""
    closes = [_safe_float(b.get("close")) for b in bars]
    n = len(closes)
    returns = {}

    # Simple returns for various horizons
    for horizon, name in [(1, "ret_1d"), (3, "ret_3d"), (5, "ret_5d"), (10, "ret_10d"), (21, "ret_21d")]:
        ret = [0.0] * n
        for i in range(horizon, n):
            if closes[i - horizon] > 0:
                ret[i] = (closes[i] - closes[i - horizon]) / closes[i - horizon]
        returns[name] = ret

    # Log returns
    log_ret = [0.0] * n
    for i in range(1, n):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_ret[i] = np.log(closes[i] / closes[i - 1])
    returns["log_ret_1d"] = log_ret

    # Overnight gap (if we have open/close)
    gaps = [0.0] * n
    for i in range(1, n):
        prev_close = _safe_float(bars[i - 1].get("close"))
        curr_open = _safe_float(bars[i].get("open"))
        if prev_close > 0:
            gaps[i] = (curr_open - prev_close) / prev_close
    returns["overnight_gap"] = gaps

    return returns


def compute_realized_vol(bars: List[Dict], windows: List[int] = None) -> Dict[str, List[float]]:
    """Compute realized volatility over various windows."""
    if windows is None:
        windows = [5, 10, 21, 60]

    closes = [_safe_float(b.get("close")) for b in bars]
    n = len(closes)

    # Log returns
    log_ret = [0.0] * n
    for i in range(1, n):
        if closes[i - 1] > 0 and closes[i] > 0:
            log_ret[i] = np.log(closes[i] / closes[i - 1])

    vols = {}
    for w in windows:
        vol = [0.0] * n
        for i in range(w, n):
            window_rets = log_ret[i - w:i]
            if len(window_rets) > 1:
                vol[i] = float(np.std(window_rets) * np.sqrt(252))  # Annualized
        vols[f"realized_vol_{w}d"] = vol

    return vols


def compute_technical_features(bars: List[Dict]) -> Dict[str, List[float]]:
    """Compute technical indicators from OHLCV bars."""
    n = len(bars)
    closes = [_safe_float(b.get("close")) for b in bars]
    highs = [_safe_float(b.get("high")) for b in bars]
    lows = [_safe_float(b.get("low")) for b in bars]
    volumes = [_safe_float(b.get("volume")) for b in bars]

    features = {}

    # Simple Moving Averages
    for window in [5, 10, 21, 50]:
        sma = [0.0] * n
        for i in range(window - 1, n):
            sma[i] = np.mean(closes[i - window + 1:i + 1])
        features[f"sma_{window}"] = sma

    # Price relative to SMA
    for window in [5, 21, 50]:
        rel = [0.0] * n
        sma_key = f"sma_{window}"
        if sma_key in features:
            for i in range(n):
                if features[sma_key][i] > 0:
                    rel[i] = closes[i] / features[sma_key][i] - 1.0
        features[f"price_vs_sma_{window}"] = rel

    # ATR (Average True Range)
    atr_14 = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
    for i in range(14, n):
        atr_14[i] = np.mean(tr[i - 13:i + 1])
    features["atr_14"] = atr_14

    # Volume features
    vol_sma_5 = [0.0] * n
    vol_sma_21 = [0.0] * n
    for i in range(4, n):
        vol_sma_5[i] = np.mean(volumes[i - 4:i + 1])
    for i in range(20, n):
        vol_sma_21[i] = np.mean(volumes[i - 20:i + 1])
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21

    # Relative volume
    rel_vol = [0.0] * n
    for i in range(20, n):
        if vol_sma_21[i] > 0:
            rel_vol[i] = volumes[i] / vol_sma_21[i]
    features["relative_volume"] = rel_vol

    return features


def compute_gex_features(snapshots: List[Dict]) -> Dict[str, List[float]]:
    """Compute GEX-derived features from snapshots."""
    n = len(snapshots)
    features = {}

    # Raw GEX values
    features["net_gex"] = [_safe_float(s.get("net_gex")) for s in snapshots]
    features["net_call_gex"] = [_safe_float(s.get("net_call_gex")) for s in snapshots]
    features["net_put_gex"] = [_safe_float(s.get("net_put_gex")) for s in snapshots]
    features["spot_price"] = [_safe_float(s.get("spot_price")) for s in snapshots]
    features["put_call_ratio"] = [_safe_float(s.get("put_call_ratio")) for s in snapshots]
    features["gex_concentration"] = [_safe_float(s.get("gex_concentration")) for s in snapshots]
    features["options_count"] = [float(_safe_int(s.get("options_count"))) for s in snapshots]

    # GEX z-score (60-day rolling)
    net_gex = features["net_gex"]
    gex_zscore = [0.0] * n
    for i in range(60, n):
        window = net_gex[i - 60:i]
        mean = np.mean(window)
        std = np.std(window)
        if std > 0:
            gex_zscore[i] = (net_gex[i] - mean) / std
    features["net_gex_zscore_60d"] = gex_zscore

    # GEX rate of change
    for horizon in [1, 3, 5, 10]:
        roc = [0.0] * n
        for i in range(horizon, n):
            if abs(net_gex[i - horizon]) > 1e-10:
                roc[i] = (net_gex[i] - net_gex[i - horizon]) / abs(net_gex[i - horizon])
        features[f"net_gex_roc_{horizon}d"] = roc

    # Distance to GEX flip (from gex_concentration)
    # gex_concentration is negative when below flip, positive above
    features["dist_to_flip"] = [-_safe_float(s.get("gex_concentration")) for s in snapshots]

    # GEX regime encoding
    regime_map = {"Positive": 1.0, "Negative": -1.0, "positive": 1.0, "negative": -1.0}
    features["gex_regime_encoded"] = [regime_map.get(s.get("gex_regime", ""), 0.0) for s in snapshots]

    # Realized vol features (from snapshots)
    features["realized_vol_t1"] = [_safe_float(s.get("realized_vol_t1")) for s in snapshots]
    features["realized_vol_t3"] = [_safe_float(s.get("realized_vol_t3")) for s in snapshots]

    # Rolling realized vol
    for key in ["realized_vol_rolling_3d", "realized_vol_rolling_5d"]:
        features[key] = [_safe_float(s.get(key)) for s in snapshots]

    return features


def compute_calendar_features(dates: List[str]) -> Dict[str, List[float]]:
    """Compute calendar-based features."""
    n = len(dates)
    features = {}

    dow = [0.0] * n  # Day of week (0=Mon)
    dom = [0.0] * n  # Day of month
    month = [0.0] * n
    is_month_end = [0.0] * n
    is_month_start = [0.0] * n

    for i, d in enumerate(dates):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            dow[i] = float(dt.weekday())
            dom[i] = float(dt.day)
            month[i] = float(dt.month)
            # Month end: last 3 trading days
            is_month_end[i] = 1.0 if dt.day >= 28 else 0.0
            is_month_start[i] = 1.0 if dt.day <= 3 else 0.0
        except Exception:
            pass

    features["day_of_week"] = dow
    features["day_of_month"] = dom
    features["month"] = month
    features["is_month_end"] = is_month_end
    features["is_month_start"] = is_month_start

    return features


# ============================================================================
# Main feature computation pipeline
# ============================================================================

async def compute_features(ticker: str = "SPY", as_of: Optional[str] = None) -> Dict[str, Any]:
    """
    Compute all features for a ticker.

    Args:
        ticker: Ticker symbol
        as_of: Optional date string (YYYY-MM-DD) to compute features up to

    Returns:
        Dict with feature matrix, dates, feature names, and metadata
    """
    db = get_async_db()

    # Load data
    snapshots = await load_gex_snapshots(db, ticker)
    outcomes = await load_outcomes(db)
    bars = await load_underlying_bars(db, ticker)

    if not snapshots:
        log.warning(f"No GEX snapshots found for {ticker}")
        return {"error": "no_data", "n_rows": 0}

    log.info(f"Loaded {len(snapshots)} snapshots, {len(outcomes)} outcomes, {len(bars)} bars for {ticker}")

    # Build date-indexed lookups
    bars_by_date = {b["date"]: b for b in bars}
    outcomes_by_date = {o["date"]: o for o in outcomes}

    # Compute bar-based features
    bar_features = compute_technical_features(bars)
    bar_returns = compute_returns(bars)
    bar_vols = compute_realized_vol(bars)

    # Compute GEX features
    gex_features = compute_gex_features(snapshots)

    # Build feature matrix aligned to snapshot dates
    snapshot_dates = [s["date"] for s in snapshots]
    calendar_features = compute_calendar_features(snapshot_dates)

    # Combine all features
    all_features = {}
    all_features.update(gex_features)
    all_features.update(calendar_features)

    # Add bar-aligned features (match by date)
    bar_date_list = [b["date"] for b in bars]
    for feat_name, feat_values in {**bar_features, **bar_returns, **bar_vols}.items():
        # Align to snapshot dates
        aligned = []
        for sd in snapshot_dates:
            # Find closest bar date <= sd
            idx = None
            for bi in range(len(bar_date_list) - 1, -1, -1):
                if bar_date_list[bi] <= sd:
                    idx = bi
                    break
            if idx is not None:
                aligned.append(feat_values[idx])
            else:
                aligned.append(0.0)
        all_features[feat_name] = aligned

    # Add targets from outcomes
    targets = {
        "directional_move": [],
        "range_expansion": [],
        "gap_move": [],
        "any_materialization": [],
        "return_pct": [],
    }
    for sd in snapshot_dates:
        outcome = outcomes_by_date.get(sd, {})
        for key in targets:
            targets[key].append(float(_safe_float(outcome.get(key, 0))))

    all_features.update(targets)

    # Build feature matrix (exclude targets from features)
    target_keys = set(targets.keys())
    feature_names = sorted([k for k in all_features.keys() if k not in target_keys and k != "date"])

    n_rows = len(snapshot_dates)
    n_features = len(feature_names)

    # Filter: only include rows where we have at least some non-zero features
    # and where we have a target
    valid_rows = []
    for i in range(n_rows):
        if targets["directional_move"][i] != 0 or targets["return_pct"][i] != 0:
            valid_rows.append(i)

    # Build output documents
    feature_docs = []
    for i in valid_rows:
        if as_of and snapshot_dates[i] > as_of:
            continue

        doc = {
            "ticker": ticker,
            "date": snapshot_dates[i],
            "feature_version": FEATURE_VERSION,
            "target_directional_move": targets["directional_move"][i],
            "target_return_pct": targets["return_pct"][i],
            "target_range_expansion": targets["range_expansion"][i],
            "target_gap_move": targets["gap_move"][i],
            "target_any_materialization": targets["any_materialization"][i],
            "_computed_at": datetime.now(timezone.utc).isoformat(),
        }
        for fn in feature_names:
            doc[fn] = all_features[fn][i]

        feature_docs.append(doc)

    log.info(f"Computed {len(feature_docs)} feature rows with {n_features} features for {ticker}")

    return {
        "ticker": ticker,
        "n_rows": len(feature_docs),
        "n_features": n_features,
        "feature_names": feature_names,
        "docs": feature_docs,
    }


async def store_features(ticker: str = "SPY", as_of: Optional[str] = None) -> Dict[str, Any]:
    """Compute and store features in MongoDB."""
    db = get_async_db()

    result = await compute_features(ticker, as_of)
    if result.get("error"):
        return result

    docs = result["docs"]
    if not docs:
        return {"stored": 0, "ticker": ticker, "message": "No valid feature rows"}

    # Upsert all feature documents
    collection = db[COLLECTION_FEATURES]
    stored = 0
    for doc in docs:
        await collection.update_one(
            {"ticker": doc["ticker"], "date": doc["date"], "feature_version": FEATURE_VERSION},
            {"$set": doc},
            upsert=True,
        )
        stored += 1

    # Write manifest
    manifest = {
        "ticker": ticker,
        "feature_version": FEATURE_VERSION,
        "n_rows": stored,
        "n_features": result["n_features"],
        "feature_names": result["feature_names"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["feature_manifests"].update_one(
        {"ticker": ticker, "feature_version": FEATURE_VERSION},
        {"$set": manifest},
        upsert=True,
    )

    log.info(f"Stored {stored} feature rows for {ticker}")
    return {"stored": stored, "ticker": ticker, "n_features": result["n_features"]}


async def main():
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Compute ML features")
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()

    result = await store_features(args.ticker, args.as_of)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
