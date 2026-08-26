"""Repository layer for ML prediction persistence (MongoDB).

GSD Phase 3.2 — routes no longer touch `db["collection"]` directly.
All ml_predictions / ml_models / ml_retrain access goes through these
functions, so the storage backend can change (or gain caching/validation)
in one place.

Usage:
    from services.ml_repository import record_prediction, retrain_history
    await record_prediction(doc)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# NOTE: access server.db lazily via a function, NOT `from server import db` —
# tests patch server.db per-test; a module-level import would bind the real
# client before the mock applies (the exact bug this avoids).


def _col(name: str):
    from server import db

    return db[name]



async def record_prediction(doc: dict[str, Any]) -> None:
    """Insert one prediction outcome-tracking document."""
    await _col("ml_predictions").insert_one(doc)


async def predictions_for(ticker: str, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent predictions for a ticker, newest first."""
    cursor = (
        _col("ml_predictions")
        .find({"ticker": ticker.upper()}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def update_outcome(ticker: str, asof: str, fields: dict[str, Any]) -> int:
    """Set realized-outcome fields on a matching prediction. Returns modified count."""
    res = await _col("ml_predictions").update_many(
        {"ticker": ticker.upper(), "asof_date": asof}, {"$set": fields}
    )
    return res.modified_count


async def latest_prediction(ticker: str) -> dict[str, Any] | None:
    """Most recent prediction document for a ticker (any outcome state)."""
    return await _col("ml_predictions").find_one(
        {"ticker": ticker.upper()},
        sort=[("ts", -1)],
    )


async def predictions_with_outcomes(ticker: str, limit: int = 30) -> list[dict[str, Any]]:
    """Recent predictions that have realized outcomes + confidence (calibration)."""
    cursor = (
        _col("ml_predictions")
        .find({
            "ticker": ticker.upper(),
            "realized_outcome": {"$ne": None},
            "confidence": {"$ne": None},
        })
        .sort("ts", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def active_model_summary(ticker: str) -> dict[str, Any] | None:
    """Active model manifest with promotion metadata for a ticker."""
    return await _col("ml_models").find_one(
        {"ticker": ticker.upper(), "status": "active"},
        {"_id": 0, "model_id": 1, "created_at": 1, "promoted_at": 1},
    )


async def latest_model_doc(ticker: str) -> dict[str, Any] | None:
    """The active model manifest for a ticker."""
    return await _col("ml_models").find_one(
        {"ticker": ticker.upper(), "active": True}, {"_id": 0}
    )


async def all_active_models() -> list[dict[str, Any]]:
    """All active model manifests."""
    cursor = _col("ml_models").find({"active": True}, {"_id": 0})
    return await cursor.to_list(length=20)


async def retrain_history(ticker: str, limit: int = 10) -> list[dict[str, Any]]:
    """Retrain runs for a ticker, newest first."""
    cursor = (
        _col("ml_retrain")
        .find({"ticker": ticker.upper()}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def record_retrain(doc: dict[str, Any]) -> None:
    """Insert one retrain-run record."""
    await _col("ml_retrain").insert_one(doc)


# ── Outcome-tracking queries (ml_outcome_api) ─────────────────────────


async def predictions_due_for_outcome(now: datetime, limit: int = 100) -> list[dict[str, Any]]:
    """Predictions whose outcome_date has passed but have no realized outcome."""
    cursor = (
        _col("ml_predictions")
        .find({"outcome_date": {"$lte": now}, "realized_outcome": None})
        .sort("predicted_at", -1)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def set_outcome(doc_id: Any, fields: dict[str, Any]) -> None:
    """Fill realized-outcome fields on one prediction by _id."""
    await _col("ml_predictions").update_one({"_id": doc_id}, {"$set": fields})


async def accuracy_stats(
    match: dict[str, Any], per_class_match: dict[str, Any] | None = None
) -> tuple[dict[str, Any] | None, dict[str, dict], dict[int, dict]]:
    """Overall + per-ticker + per-class accuracy aggregation for /accuracy.

    Returns (overall_stats, by_ticker, by_class keyed on prediction int).
    """
    col = _col("ml_predictions")

    overall = None
    cursor = col.aggregate([
        {"$match": match},
        {"$group": {
            "_id": None,
            "total": {"$sum": 1},
            "correct": {"$sum": {"$cond": ["$accurate", 1, 0]}},
            "avg_confidence": {"$avg": "$confidence"},
            "avg_return_when_correct": {"$avg": {"$cond": ["$accurate", "$realized_return_pct", None]}},
            "avg_return_when_wrong": {"$avg": {"$cond": [{"$not": ["$accurate"]}, "$realized_return_pct", None]}},
        }},
    ])
    async for doc in cursor:
        overall = doc
        break

    by_ticker: dict[str, dict] = {}
    cursor2 = col.aggregate([
        {"$match": match},
        {"$group": {
            "_id": "$ticker",
            "total": {"$sum": 1},
            "correct": {"$sum": {"$cond": ["$accurate", 1, 0]}},
            "avg_confidence": {"$avg": "$confidence"},
        }},
    ])
    async for doc in cursor2:
        by_ticker[doc["_id"]] = {
            "total": doc["total"],
            "correct": doc["correct"],
            "accuracy": round(doc["correct"] / doc["total"], 4) if doc["total"] > 0 else 0,
            "avg_confidence": round(doc.get("avg_confidence", 0), 4),
        }

    by_class: dict[int, dict] = {}
    for cls in (0, 1, 2):
        cls_match = {**match, "prediction": cls}
        cursor3 = col.aggregate([
            {"$match": cls_match},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "correct": {"$sum": {"$cond": ["$accurate", 1, 0]}},
            }},
        ])
        async for doc in cursor3:
            by_class[cls] = {
                "total": doc["total"],
                "correct": doc["correct"],
                "accuracy": round(doc["correct"] / doc["total"], 4) if doc["total"] > 0 else 0,
            }
    return overall, by_ticker, by_class


async def calibration_buckets(match: dict[str, Any]) -> list[dict[str, Any]]:
    """Confidence-bucket calibration curve (bucket, count, accuracy)."""
    cursor = _col("ml_predictions").aggregate([
        {"$match": match},
        {"$bucket": {
            "groupBy": "$confidence",
            "boundaries": [0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "default": "other",
            "output": {
                "count": {"$sum": 1},
                "accuracy": {"$avg": {"$cond": ["$accurate", 1.0, 0.0]}},
            },
        }},
    ])
    return [
        {
            "confidence_bucket": doc["_id"],
            "count": doc["count"],
            "accuracy": round(doc["accuracy"], 4),
        }
        async for doc in cursor
    ]


async def recent_predictions(
    ticker: str | None = None,
    limit: int = 20,
    with_outcomes_only: bool = False,
) -> list[dict[str, Any]]:
    """Recent predictions (stringified _id), optionally outcome-only."""
    query: dict[str, Any] = {}
    if ticker:
        query["ticker"] = ticker.upper()
    if with_outcomes_only:
        query["realized_outcome"] = {"$ne": None}
    cursor = (
        _col("ml_predictions")
        .find(query)
        .sort("predicted_at", -1)
        .limit(limit)
    )
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results
