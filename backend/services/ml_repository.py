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
