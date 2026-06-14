"""
backend/services/ml/outcomes.py

Realized outcome attachment — computes next-day outcomes for predictions.

For every prediction in ml_predictions without a realized_outcome,
this service:
  1. Fetches the next day's OHLCV bar for the ticker
  2. Computes the realized return and directional label
  3. Updates the prediction document with realized_outcome

This enables rolling accuracy tracking in the ML dashboard.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

log = logging.getLogger("ml.outcomes")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_PREDICTIONS = "ml_predictions"


async def fetch_next_day_outcome(ticker: str, prediction_date: str) -> dict[str, Any] | None:
    """Fetch the realized next-day outcome for a prediction via yfinance.

    Returns dict with:
      - realized_label: 1 if next-day close > open, 0 otherwise
      - realized_return_pct: (close - open) / open * 100
      - gap_pct: (open - prev_close) / prev_close * 100
      - range_pct: (high - low) / open * 100
      - abs_return_pct: abs(realized_return_pct)
      - directional_move: bool, True if abs_return > 0.5%
      - data_source: "yfinance"
      - bars_used: number of bars fetched
    """
    ticker = ticker.upper()

    try:
        pred_dt = pd.Timestamp(prediction_date)
        if pred_dt.tzinfo is None:
            pred_dt = pred_dt.tz_localize("UTC")
        next_day = pred_dt + timedelta(days=1)
        end = next_day + timedelta(days=5)
        start = next_day - timedelta(days=1)

        data = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
        )

        if data is None or (hasattr(data, 'empty') and data.empty):
            return None

        # Handle multi-level columns from yfinance
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        # Get the first trading day bar after the prediction date
        mask = data.index > pred_dt
        next_bars = data.loc[mask]
        if next_bars is None or (hasattr(next_bars, 'empty') and next_bars.empty):
            return None

        bar = next_bars.iloc[0]
        open_price = float(bar.get("Open", 0) or 0)
        close_price = float(bar.get("Close", 0) or 0)
        high_price = float(bar.get("High", 0) or 0)
        low_price = float(bar.get("Low", 0) or 0)

        if open_price <= 0 or close_price <= 0:
            return None

        realized_return_pct = (close_price - open_price) / open_price * 100.0
        abs_return_pct = abs(realized_return_pct)

        return {
            "realized_label": 1 if close_price > open_price else 0,
            "realized_return_pct": round(realized_return_pct, 4),
            "gap_pct": 0.0,
            "range_pct": round((high_price - low_price) / open_price * 100, 4),
            "abs_return_pct": round(abs_return_pct, 4),
            "directional_move": abs_return_pct > 0.5,
            "data_source": "yfinance",
            "bars_used": 1,
        }
    except Exception as e:
        log.debug(f"yfinance outcome fetch failed for {ticker}@{prediction_date}: {e}")
        return None


async def attach_realized_outcomes(db: Any, batch_size: int = 100) -> int:
    """Attach realized outcomes to predictions that don't have them yet.

    Args:
        db: MongoDB database handle
        batch_size: Max predictions to process per call

    Returns:
        Number of predictions updated
    """
    predictions_col = db[COLLECTION_PREDICTIONS]

    query = {"realized_outcome": {"$eq": None}}
    cursor = predictions_col.find(query).sort("ts", 1).limit(batch_size)
    pending = await cursor.to_list(length=batch_size)

    if not pending:
        return 0

    updated = 0
    for pred in pending:
        ticker = pred.get("ticker", "")
        ts = pred.get("ts", "")

        if not ticker or not ts:
            continue

        # Skip predictions from the last 25h (outcome not yet known)
        try:
            pred_dt = pd.Timestamp(ts) if isinstance(ts, str) else ts
            if hasattr(pred_dt, 'tzinfo') and pred_dt.tzinfo is None:
                pred_dt = pred_dt.tz_localize("UTC")
            cutoff = datetime.now(UTC) - timedelta(hours=25)
            if pred_dt > cutoff:
                continue
        except Exception:
            continue

        ts_str = str(ts) if not isinstance(ts, str) else ts
        outcome = await fetch_next_day_outcome(ticker, ts_str)

        # Fallback: try underlying_bars collection
        if outcome is None:
            outcome = await _try_underlying_bars(db, ticker, ts)

        if outcome is not None:
            await predictions_col.update_one(
                {"_id": pred["_id"]},
                {"$set": {
                    "realized_outcome": outcome["realized_label"],
                    "realized_return_pct": outcome["realized_return_pct"],
                    "realized_details": outcome,
                    "outcome_computed_at": datetime.now(UTC).isoformat(),
                }},
            )
            updated += 1

    if updated > 0:
        log.info(f"Attached outcomes for {updated}/{len(pending)} predictions")
    return updated


async def _try_underlying_bars(db: Any, ticker: str, prediction_ts: Any) -> dict[str, Any] | None:
    """Fallback: compute outcome from underlying_bars collection."""
    try:
        bars_col = db["underlying_bars"]
        if isinstance(prediction_ts, str):
            pred_str = prediction_ts
        elif hasattr(prediction_ts, 'isoformat'):
            pred_str = prediction_ts.isoformat()
        else:
            pred_str = str(prediction_ts)

        cursor = bars_col.find({
            "ticker": ticker,
            "date": {"$gt": pred_str},
        }).sort("date", 1).limit(1)
        bars = await cursor.to_list(length=1)
        if not bars:
            return None

        bar = bars[0]
        open_price = float(bar.get("open", 0) or 0)
        close_price = float(bar.get("close", 0) or 0)
        high_price = float(bar.get("high", 0) or 0)
        low_price = float(bar.get("low", 0) or 0)

        if open_price <= 0 or close_price <= 0:
            return None

        realized_return_pct = (close_price - open_price) / open_price * 100.0
        abs_return_pct = abs(realized_return_pct)

        return {
            "realized_label": 1 if close_price > open_price else 0,
            "realized_return_pct": round(realized_return_pct, 4),
            "gap_pct": 0.0,
            "range_pct": round((high_price - low_price) / open_price * 100, 4),
            "abs_return_pct": round(abs_return_pct, 4),
            "directional_move": abs_return_pct > 0.5,
            "data_source": "underlying_bars",
            "bars_used": 1,
        }
    except Exception:
        return None


async def compute_rolling_accuracy(db: Any, ticker: str, window_days: int = 30) -> dict[str, Any]:
    """Compute rolling accuracy for a ticker over the given window.

    Returns dict with:
      - ticker, window_days
      - n_predictions, n_with_outcomes
      - accuracy (fraction correct), avg_return_pct
    """
    predictions_col = db[COLLECTION_PREDICTIONS]
    cutoff_dt = datetime.now(UTC) - timedelta(days=window_days)
    cutoff = cutoff_dt.isoformat()

    pipeline = [
        {"$match": {
            "ticker": ticker,
            "ts": {"$gte": cutoff},
        }},
        {"$group": {
            "_id": None,
            "n_total": {"$sum": 1},
            "n_with_outcome": {"$sum": {"$cond": [{"$ne": ["$realized_outcome", None]}, 1, 0]}},
            "n_correct": {"$sum": {"$cond": [{"$eq": ["$prediction", "$realized_outcome"]}, 1, 0]}},
            "avg_return": {"$avg": "$realized_return_pct"},
        }},
    ]

    try:
        result = await predictions_col.aggregate(pipeline).to_list(length=1)
    except Exception:
        result = []

    if not result:
        return {
            "ticker": ticker,
            "window_days": window_days,
            "n_predictions": 0,
            "n_with_outcomes": 0,
            "accuracy": None,
            "avg_return_pct": None,
        }

    r = result[0]
    n_outcomes = r.get("n_with_outcome", 0)
    accuracy = r.get("n_correct", 0) / n_outcomes if n_outcomes > 0 else None

    return {
        "ticker": ticker,
        "window_days": window_days,
        "n_predictions": r.get("n_total", 0),
        "n_with_outcomes": n_outcomes,
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "avg_return_pct": round(r.get("avg_return", 0.0) or 0.0, 4),
    }
