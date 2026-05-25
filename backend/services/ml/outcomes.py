"""
Realized outcome attachment for ML predictions.

Computes next-day realized outcomes (return, directional label) for predictions
in ml_predictions that don't have realized_outcome yet. Enables rolling accuracy
tracking in the dashboard.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger("ml.outcomes")

COLLECTION_PREDICTIONS = "ml_predictions"


async def fetch_next_day_outcome(ticker: str, prediction_date: str) -> Optional[Dict[str, Any]]:
    """Fetch the realized next-day outcome for a prediction via yfinance.

    Returns dict with realized_label, realized_return_pct, range_pct, etc.
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

        if data is None or (hasattr(data, "empty") and data.empty):
            return None

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        mask = data.index > pred_dt
        next_bars = data[mask]
        if next_bars is None or next_bars.empty:
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
        range_pct = (high_price - low_price) / open_price * 100.0 if open_price > 0 else 0.0

        return {
            "realized_label": 1 if close_price > open_price else 0,
            "realized_return_pct": round(realized_return_pct, 4),
            "gap_pct": 0.0,
            "range_pct": round(range_pct, 4),
            "abs_return_pct": round(abs_return_pct, 4),
            "directional_move": abs_return_pct > 0.5,
            "data_source": "yfinance",
            "bars_used": 1,
        }
    except Exception as e:
        log.debug(f"fetch_next_day_outcome failed for {ticker}@{prediction_date}: {e}")
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
            if isinstance(ts, str):
                pred_dt = pd.Timestamp(ts)
            else:
                pred_dt = ts
            if hasattr(pred_dt, "tzinfo") and pred_dt.tzinfo is None:
                pred_dt = pred_dt.tz_localize("UTC")
            cutoff_check = datetime.now(timezone.utc) - timedelta(hours=25)
            if pred_dt > cutoff_check:
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
                    "outcome_computed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            updated += 1

    if updated > 0:
        log.info(f"Attached outcomes for {updated}/{len(pending)} predictions")
    return updated


async def _try_underlying_bars(db: Any, ticker: str, prediction_ts: Any) -> Optional[Dict[str, Any]]:
    """Fallback: compute outcome from underlying_bars collection."""
    try:
        bars_col = db["underlying_bars"]
        if isinstance(prediction_ts, str):
            pred_str = prediction_ts
        elif hasattr(prediction_ts, "isoformat"):
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
        range_pct = (high_price - low_price) / open_price * 100.0 if open_price > 0 else 0.0

        return {
            "realized_label": 1 if close_price > open_price else 0,
            "realized_return_pct": round(realized_return_pct, 4),
            "gap_pct": 0.0,
            "range_pct": round(range_pct, 4),
            "abs_return_pct": round(abs_return_pct, 4),
            "directional_move": abs_return_pct > 0.5,
            "data_source": "underlying_bars",
            "bars_used": 1,
        }
    except Exception:
        return None


async def compute_rolling_accuracy(
    db: Any, ticker: str, window_days: int = 30,
) -> Dict[str, Any]:
    """Compute rolling accuracy for a ticker over the given window.

    Returns dict with:
      - ticker, window_days
      - n_predictions, n_with_outcomes
      - accuracy (fraction correct), avg_return_pct
    """
    predictions_col = db[COLLECTION_PREDICTIONS]
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=window_days)
    cutoff = cutoff_dt.isoformat()

    pipeline = [
        {"$match": {
            "ticker": ticker,
            "ts": {"$gte": cutoff},
        }},
        {"$group": {
            "_id": None,
            "n_total": {"$sum": 1},
            "n_with_outcome": {
                "$sum": {"$cond": [{"$ne": ["$realized_outcome", None]}, 1, 0]}
            },
            "n_correct": {
                "$sum": {"$cond": [{"$eq": ["$prediction", "$realized_outcome"]}, 1, 0]}
            },
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
