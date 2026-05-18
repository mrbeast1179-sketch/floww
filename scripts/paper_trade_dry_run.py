#!/usr/bin/env python3
"""
scripts/paper_trade_dry_run.py

Daily paper-trade dry-run for SPY direction model.

DRY-RUN ONLY — no Alpaca order submission. Intents are persisted to the
``orders_dry_run`` Mongo collection. Live wiring stays disabled until the
SPY v2.0 model audit returns PASS.

Schedule: 09:35 ET weekdays (via cron)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import joblib
import numpy as np
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paper_trade_dry_run")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
LIVE_TRADING_ENABLED = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"


def get_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def load_active_model(ticker: str):
    """Load the active model and scaler for a ticker."""
    models_dir = Path(__file__).resolve().parent.parent / "models"

    # Find the latest model file
    pattern = f"{ticker}_direction_*.joblib"
    model_files = sorted(models_dir.glob(pattern))
    if not model_files:
        raise FileNotFoundError(f"No model found for {ticker} matching {pattern}")

    model_path = model_files[-1]
    scaler_path = str(model_path).replace("_direction_", "_scaler_")

    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"Scaler not found: {scaler_path}")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    return model, scaler, str(model_path)


def compute_features(ticker: str, db) -> Optional[Dict[str, Any]]:
    """Compute features for today's prediction."""
    # Load latest GEX features
    gex = db["gex_features"].find_one({"ticker": ticker}, sort=[("day", -1)])
    if not gex:
        log.warning(f"No GEX features for {ticker}")
        return None

    # Load latest underlying bars (last 60 days)
    bars = list(db["underlying_bars"].find(
        {"ticker": ticker}
    ).sort("date", -1).limit(60))

    if len(bars) < 21:
        log.warning(f"Insufficient bars for {ticker}: {len(bars)}")
        return None

    bars = sorted(bars, key=lambda b: b["date"])
    closes = np.array([b["close"] for b in bars], dtype=float)

    # Compute features
    features = {}

    # GEX features
    features["net_gex"] = gex.get("net_gex", 0)
    features["call_gex"] = gex.get("call_gex", 0)
    features["put_gex"] = gex.get("put_gex", 0)
    features["total_vex"] = gex.get("total_vex", 0)
    features["total_dex"] = gex.get("total_dex", 0)
    features["total_vega"] = gex.get("total_vega", 0)
    features["gamma_flip"] = gex.get("gamma_flip", 0) or 0
    features["gex_n_strikes"] = gex.get("n_strikes", 0)
    features["spot"] = gex.get("spot", closes[-1])

    # Returns
    for h in [1, 3, 5, 10, 21]:
        if len(closes) > h:
            features[f"ret_{h}d"] = (closes[-1] / closes[-1 - h]) - 1
        else:
            features[f"ret_{h}d"] = 0.0

    # SMA
    for w in [5, 10, 21]:
        if len(closes) >= w:
            features[f"sma_{w}"] = np.mean(closes[-w:])
            features[f"price_vs_sma_{w}"] = closes[-1] / features[f"sma_{w}"] - 1
        else:
            features[f"sma_{w}"] = closes[-1]
            features[f"price_vs_sma_{w}"] = 0.0

    # Realized vol
    log_ret = np.log(closes[1:] / closes[:-1])
    for w in [5, 21]:
        if len(log_ret) >= w:
            features[f"realized_vol_{w}d"] = float(np.std(log_ret[-w:]) * np.sqrt(252))
        else:
            features[f"realized_vol_{w}d"] = 0.0

    # RSI
    if len(closes) >= 15:
        deltas = np.diff(closes[-15:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        rs = avg_gain / (avg_loss + 1e-10)
        features["rsi_14"] = 100 - (100 / (1 + rs))
    else:
        features["rsi_14"] = 50.0

    return features


async def daily_paper_trade_dry_run(ticker: str = "SPY") -> Dict[str, Any]:
    """Run daily paper-trade dry-run."""
    log.info(f"Starting paper-trade dry-run for {ticker}")

    db = get_db()

    # Load model
    try:
        model, scaler, model_path = load_active_model(ticker)
        log.info(f"Loaded model: {model_path}")
    except FileNotFoundError as e:
        log.error(f"Model not found: {e}")
        return {"status": "error", "message": str(e)}

    # Compute features
    features = compute_features(ticker, db)
    if features is None:
        return {"status": "error", "message": "Could not compute features"}

    # Get feature names from model
    if hasattr(model, "feature_names_in_"):
        feature_names = list(model.feature_names_in_)
    else:
        # Use all numeric features
        feature_names = sorted(features.keys())

    # Build feature vector
    X = np.array([[features.get(f, 0.0) for f in feature_names]])
    X = np.nan_to_num(X, nan=0.0)
    X_scaled = scaler.transform(X)

    # Predict
    prediction = int(model.predict(X_scaled)[0])
    probability = float(model.predict_proba(X_scaled)[0][1])

    # Determine action
    if probability > 0.55:
        action = "BUY"
        confidence = probability
    elif probability < 0.45:
        action = "SELL"
        confidence = 1 - probability
    else:
        action = "HOLD"
        confidence = max(probability, 1 - probability)

    # Get current price
    latest_bar = db["underlying_bars"].find_one(
        {"ticker": ticker}, sort=[("date", -1)]
    )
    current_price = latest_bar.get("close", 0) if latest_bar else 0

    # Position sizing: max 5% of $100K = $5K
    account_value = 100000.0
    max_position = account_value * 0.05
    shares = int(max_position / current_price) if current_price > 0 else 0

    # Build order intent
    order_intent = {
        "ticker": ticker,
        "date": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "confidence": round(confidence, 4),
        "prediction": prediction,
        "probability": round(probability, 4),
        "current_price": current_price,
        "shares": shares,
        "notional_usd": round(shares * current_price, 2),
        "model_path": model_path,
        "dry_run": True,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "submitted": False,
        "features_used": len(feature_names),
    }

    # Persist to MongoDB
    db["orders_dry_run"].insert_one(order_intent)

    log.info(f"Prediction: {action} (conf={confidence:.3f}, prob={probability:.3f}, price={current_price:.2f}, shares={shares})")

    return {
        "status": "ok",
        "ticker": ticker,
        "action": action,
        "confidence": confidence,
        "probability": probability,
        "current_price": current_price,
        "shares": shares,
        "dry_run": True,
    }


async def main():
    ticker = os.environ.get("PAPER_TRADE_TICKER", "SPY")
    result = await daily_paper_trade_dry_run(ticker)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
