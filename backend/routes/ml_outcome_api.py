#!/usr/bin/env python3
"""
backend/routes/ml_outcome_api.py

ML Outcome Tracking API — stores predictions and compares against realized outcomes.

Endpoints:
    POST /api/ml/outcome/record           - Record a prediction (called by scheduled job)
    GET  /api/ml/outcome/accuracy         - Get prediction accuracy stats
    GET  /api/ml/outcome/recent           - Get recent predictions with outcomes
    POST /api/ml/outcome/batch-record     - Batch record from live inference engine

MongoDB collections:
    ml_predictions: stores each prediction with features, model_id, timestamp
        After outcome_date passes, a background job fills in realized_outcome
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ml/outcome", tags=["ml-outcome"])

# ── Record Predictions ────────────────────────────────────────────────

@router.post("/record")
async def record_prediction(
    ticker: str = Query(..., description="Ticker symbol"),
    model_id: str | None = Query(None, description="Model ID"),
):
    """Record a live prediction for outcome tracking.

    Fetches current features, runs inference, stores prediction in MongoDB.
    The outcome will be filled in later when next-day return is known.
    """
    from services.ml.inference import CLASS_LABELS, inference_engine

    ticker = ticker.upper()

    try:
        result = await inference_engine.predict(ticker)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prediction failed: {e}") from e

    now = datetime.now(UTC)

    # Outcome date = next trading day (simply tomorrow for now)
    outcome_date = now + timedelta(days=1)
    # Skip weekends
    while outcome_date.weekday() >= 5:
        outcome_date += timedelta(days=1)

    doc = {
        "ticker": ticker,
        "model_id": result.model_id,
        "prediction": result.prediction,
        "prediction_label": CLASS_LABELS.get(result.prediction, "?"),
        "confidence": round(result.confidence, 4),
        "probabilities": {
            "down": round(result.probabilities[0], 4) if len(result.probabilities) > 0 else 0,
            "hold": round(result.probabilities[1], 4) if len(result.probabilities) > 1 else 0,
            "up": round(result.probabilities[2], 4) if len(result.probabilities) > 2 else 0,
        },
        "features_used": len(result.features_used),
        "feature_snapshot": {k: round(v, 6) for k, v in list(result.feature_values.items())[:10]},
        "gex_signal": result.gex_signal,
        "predicted_at": now,
        "outcome_date": outcome_date,
        "realized_outcome": None,
        "realized_return_pct": None,
        "accurate": None,
    }

    from services.ml_repository import record_prediction
    await record_prediction(doc)

    return {
        "ok": True,
        "ticker": ticker,
        "prediction": CLASS_LABELS.get(result.prediction, "?"),
        "confidence": round(result.confidence, 4),
        "model_id": result.model_id,
        "outcome_date": outcome_date.isoformat(),
    }


@router.post("/batch-record")
async def batch_record(tickers: list[str] | None = Query(None)):  # noqa: B008
    """Record predictions for multiple tickers (or all registered models)."""
    from services.ml.inference import MODEL_REGISTRY

    target = [t.upper() for t in tickers] if tickers else list(MODEL_REGISTRY.keys())
    results = []
    errors = []

    for ticker in target:
        try:
            r = await record_prediction(ticker=ticker)
            results.append(r)
        except HTTPException as e:
            errors.append({"ticker": ticker, "error": e.detail})
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})

    return {"recorded": len(results), "results": results, "errors": errors}


# ── Compute Outcomes ─────────────────────────────────────────────────

@router.post("/compute")
async def compute_outcomes():
    """Fill in realized outcomes for past predictions.

    For each prediction where outcome_date has passed:
    1. Fetch actual next-day return
    2. Compute realized 3-class outcome
    3. Mark accuracy
    """
    from services.ml.inference import compute_live_features
    from services.ml_repository import (
        predictions_due_for_outcome,
        set_outcome,
    )

    now = datetime.now(UTC)

    # Find predictions needing outcome computation
    pending = await predictions_due_for_outcome(now, limit=100)

    updated = 0
    for doc in pending:
        ticker = doc["ticker"]
        try:
            # Get the latest return data
            features_df = await asyncio.to_thread(compute_live_features, ticker, period="5d")
            if features_df.empty or len(features_df) < 2:
                continue

            # Compute actual return from prediction date to now
            latest_close = features_df["Close"].iloc[-1] if "Close" in features_df.columns else None
            if latest_close is None:
                # Use ret_1d as proxy
                actual_return = features_df["ret_1d"].iloc[-1] if "ret_1d" in features_df.columns else 0
            else:
                # Approximate: use mean of recent daily returns
                actual_return = features_df["ret_1d"].mean() if "ret_1d" in features_df.columns else 0.0

            # 3-class outcome
            if actual_return > 0.003:
                realized = 2  # UP
            elif actual_return < -0.003:
                realized = 0  # DOWN
            else:
                realized = 1  # HOLD

            # Accuracy
            accurate = (doc["prediction"] == realized)

            await set_outcome(doc["_id"], {
                "realized_outcome": realized,
                "realized_return_pct": round(float(actual_return), 6),
                "accurate": accurate,
                "computed_at": now,
            })
            updated += 1
        except Exception as e:
            logger.warning(f"Outcome compute failed for {ticker}: {e}")

    return {"updated": updated, "checked_at": now.isoformat()}


# ── Accuracy Stats ───────────────────────────────────────────────────

@router.get("/accuracy")
async def get_accuracy(
    ticker: str | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    model_id: str | None = Query(None),
):
    """Get prediction accuracy statistics.

    Overall, per-class, per-ticker, and calibration.
    """
    since = datetime.now(UTC) - timedelta(days=days)

    match = {
        "predicted_at": {"$gte": since},
        "realized_outcome": {"$ne": None},
    }
    if ticker:
        match["ticker"] = ticker.upper()
    if model_id:
        match["model_id"] = model_id

    from services.ml_repository import accuracy_stats, calibration_buckets

    stats, by_ticker, by_class_raw = await accuracy_stats(match)

    # Per-class breakdown (labeled)
    by_class = {}
    class_labels = {0: "DOWN", 1: "HOLD", 2: "UP"}
    for cls, label in class_labels.items():
        entry = by_class_raw.get(cls)
        if entry:
            by_class[label] = entry

    # Calibration: how often is confidence ≈ accuracy?
    calibration = []
    try:
        calibration = await calibration_buckets(match)
    except Exception as e:
        logger.warning(f"Calibration pipeline failed: {e}")

    if not stats:
        return {"message": "No outcomes yet. Run POST /api/ml/outcome/compute after predictions mature."}

    return {
        "period_days": days,
        "total_predictions": stats["total"],
        "correct": stats["correct"],
        "overall_accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] > 0 else 0,
        "avg_confidence": round(stats.get("avg_confidence", 0), 4),
        "by_ticker": by_ticker,
        "by_class": by_class,
        "calibration": calibration,
    }


# ── Recent Predictions ───────────────────────────────────────────────

@router.get("/recent")
async def get_recent(
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    with_outcomes_only: bool = Query(False),
):
    """Get recent predictions, optionally filtered to those with outcomes."""
    from services.ml_repository import recent_predictions

    results = await recent_predictions(
        ticker=ticker, limit=limit, with_outcomes_only=with_outcomes_only
    )

    return {"predictions": results, "count": len(results)}
