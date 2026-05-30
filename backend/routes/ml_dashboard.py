"""
backend/routes/ml_dashboard.py

ML Dashboard API — real-time predictions, model status, and feature inspection.

All routes are self-contained: they use yfinance for data and joblib for models.
No MongoDB dependency.

Endpoints:
    GET  /api/ml/dashboard/{ticker}     - Full ML briefing (regime + ML + combined)
    POST /api/ml/reload/{ticker}        - Reload model from disk

Note: /predict/{ticker}, /models, /model-info/{ticker}, /features/{ticker},
      and /compare were removed (duplicates of ml_api.py/ml_predict_api.py).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from services.ml import DegenerateModelError

log = logging.getLogger("ml_dashboard")

router = APIRouter(prefix="/api/ml", tags=["ml-dashboard"])


# ── Helpers ─────────────────────────────────────────────────────────────

async def _get_inference_engine():
    """Lazy-load the inference engine."""
    from services.ml.inference import InferenceEngine
    return InferenceEngine()


async def _get_briefing_integrator():
    """Lazy-load the ML briefing integrator."""
    from services.ml_briefing import ml_briefing
    return ml_briefing


# ── GET /api/ml/dashboard/{ticker} ─────────────────────────────────────

@router.get("/dashboard/{ticker}")
async def ml_dashboard(ticker: str) -> Dict[str, Any]:
    """Full ML dashboard data for a ticker.

    Returns regime, ML prediction, combined signal, and supporting data.
    """
    integrator = await _get_briefing_integrator()
    try:
        result = await integrator.generate_briefing(ticker.upper())
        return result
    except Exception as e:
        log.error(f"Dashboard failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dashboard error: {e}")


# ── POST /api/ml/reload/{ticker} ───────────────────────────────────────

@router.post("/reload/{ticker}")
async def ml_reload_model(ticker: str) -> Dict[str, Any]:
    """Reload model from disk (useful after retraining)."""
    engine = await _get_inference_engine()
    ticker = ticker.upper()

    # Clear cache
    if ticker in engine._model_cache:
        del engine._model_cache[ticker]

    # Reload
    try:
        info = engine.get_model_info(ticker)
        return {"status": "reloaded", "ticker": ticker, "model_id": info.model_id}
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
