"""
backend/routes/ml_api.py

FastAPI routes for ML model management.

Endpoints:
    GET  /api/ml/models           - List all models
    POST /api/ml/promote/{model_id} - Promote shadow -> active
    POST /api/ml/predict/{ticker}  - Get prediction from active model
    GET  /api/ml/drift/{ticker}    - Get drift report
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from services.ml.registry import ModelRegistry
from services.ml import DegenerateModelError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])


async def _get_registry() -> ModelRegistry:
    """Resolve the ModelRegistry singleton from the server's db handle."""
    # Local import so the routes module remains import-safe before app is constructed.
    from server import db  # noqa: F401
    return ModelRegistry(db)


# ── GET /api/ml/models ────────────────────────────────────────────────────


@router.get("/models")
async def list_models(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List all models, optionally filtered by ticker and/or status.

    Query params:
        ticker: Filter by ticker symbol (e.g. SPY)
        status: Filter by lifecycle status (shadow, active, retired)
    """
    registry = await _get_registry()
    models = await registry.list_models(ticker=ticker, status=status)
    return {"models": models, "count": len(models)}


# ── POST /api/ml/promote/{model_id} ───────────────────────────────────────


@router.post("/promote/{model_id}")
async def promote_model(model_id: str) -> Dict[str, Any]:
    """Promote a shadow model to active.

    Promotion gate criteria (all must hold):
        - beats_baselines == True
        - holdout_sharpe > prior_active.holdout_sharpe
        - calibration_error < 0.05

    Returns 200 on success, 400 on gate failure, 404 if model not found.
    """
    registry = await _get_registry()
    result = await registry.promote_model(model_id)

    if not result["success"]:
        if "not found" in result["reason"]:
            raise HTTPException(status_code=404, detail=result["reason"])
        raise HTTPException(status_code=400, detail=result["reason"])

    return result


# ── POST /api/ml/predict/{ticker} ─────────────────────────────────────────


@router.post("/predict/{ticker}")
async def predict(ticker: str) -> Dict[str, Any]:
    """Get a prediction from the active model for a ticker.

    Loads the active model, computes features from the latest data,
    runs inference, logs the prediction, and returns the result.
    """
    registry = await _get_registry()
    try:
        result = await registry.predict(ticker)
        return result
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Model artifact missing: {e}")
    except Exception as e:
        logger.error(f"Prediction failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


# ── GET /api/ml/drift/{ticker} ────────────────────────────────────────────


@router.get("/drift/{ticker}")
async def drift_report(ticker: str) -> Dict[str, Any]:
    """Get the PSI drift report for a ticker's active model.

    Compares the rolling 24h feature distribution against the
    training distribution. Returns per-feature PSI values and
    any drift alerts (PSI >= 0.2).
    """
    registry = await _get_registry()
    report = await registry.compute_drift(ticker)
    return report
