"""
backend/routes/ml_dashboard.py

ML Dashboard API — real-time predictions, model status, and feature inspection.

All routes are self-contained: they use yfinance for data and joblib for models.
No MongoDB dependency.

Endpoints:
    GET  /api/ml/dashboard/{ticker}     - Full ML briefing (regime + ML + combined)
    GET  /api/ml/predict/{ticker}       - Raw ML prediction
    GET  /api/ml/models                 - List available models
    GET  /api/ml/model-info/{ticker}    - Model metadata
    GET  /api/ml/features/{ticker}      - Latest feature values
    POST /api/ml/reload/{ticker}        - Reload model from disk
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


# ── GET /api/ml/predict/{ticker} ───────────────────────────────────────

@router.get("/predict/{ticker}")
async def ml_predict(ticker: str) -> Dict[str, Any]:
    """Get raw ML prediction for a ticker."""
    engine = await _get_inference_engine()
    try:
        result = await engine.predict(ticker.upper())
        return {
            "ticker": result.ticker,
            "prediction": result.prediction,
            "prediction_label": "BULLISH" if result.prediction == 1 else "BEARISH",
            "confidence": result.confidence,
            "probabilities": {
                "bearish": result.probabilities[0] if len(result.probabilities) > 0 else 0.5,
                "bullish": result.probabilities[1] if len(result.probabilities) > 1 else 0.5,
            },
            "model_id": result.model_id,
            "features_used": result.features_used,
            "feature_values": result.feature_values,
            "timestamp": result.timestamp,
            "data_age_sec": result.data_age_sec,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Prediction failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")


# ── GET /api/ml/models ─────────────────────────────────────────────────

@router.get("/models")
async def ml_list_models() -> Dict[str, Any]:
    """List all available ML models."""
    engine = await _get_inference_engine()
    models = engine.list_models()
    return {
        "models": [
            {
                "ticker": m.ticker,
                "model_id": m.model_id,
                "model_type": m.model_type,
                "n_features": m.n_features,
                "train_accuracy": m.train_accuracy,
                "loaded": m.loaded,
            }
            for m in models
        ],
        "count": len(models),
    }


# ── GET /api/ml/model-info/{ticker} ────────────────────────────────────

@router.get("/model-info/{ticker}")
async def ml_model_info(ticker: str) -> Dict[str, Any]:
    """Get model metadata for a ticker."""
    engine = await _get_inference_engine()
    try:
        info = engine.get_model_info(ticker.upper())
        return {
            "ticker": info.ticker,
            "model_id": info.model_id,
            "model_type": info.model_type,
            "n_features": info.n_features,
            "feature_names": info.feature_names,
            "train_accuracy": info.train_accuracy,
            "artifact_path": info.artifact_path,
            "loaded": info.loaded,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Model info failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/ml/features/{ticker} ──────────────────────────────────────

@router.get("/features/{ticker}")
async def ml_features(ticker: str) -> Dict[str, Any]:
    """Get latest computed features for a ticker."""
    from services.ml.inference import compute_live_features
    import asyncio

    try:
        df = await asyncio.to_thread(compute_live_features, ticker.upper())
        latest = df.iloc[-1]
        features = {col: float(latest[col]) for col in df.columns}
        return {
            "ticker": ticker.upper(),
            "timestamp": str(df.index[-1]),
            "n_rows": len(df),
            "n_features": len(df.columns),
            "features": features,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Feature computation failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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


# ── GET /api/ml/compare ─────────────────────────────────────────────────


@router.get("/compare")
async def compare_models(
    tickers: Optional[str] = Query(None, description="Comma-separated tickers, default=all"),
):
    """Compare all registered models on current live data.

    Runs inference for each ticker and returns a side-by-side comparison
    of predictions, confidence, model type, and data freshness.
    """
    engine = await _get_inference_engine()

    if tickers:
        ticker_list = [t.strip().upper() for t in tickers.split(",")]
    else:
        ticker_list = list(engine.MODEL_REGISTRY.keys())

    results = []
    errors = []

    for ticker in ticker_list:
        try:
            pred = await engine.predict(ticker)
            results.append({
                "ticker": ticker,
                "prediction": pred.prediction,
                "prediction_label": {0: "DOWN", 1: "HOLD", 2: "UP"}.get(pred.prediction, "UNKNOWN"),
                "confidence": round(pred.confidence, 4),
                "model_id": pred.model_id,
                "data_age_sec": round(pred.data_age_sec, 1),
                "gex_signal": pred.gex_signal,
                "timestamp": pred.timestamp,
            })
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})

    return {
        "comparison": results,
        "errors": errors,
        "count": len(results),
        "error_count": len(errors),
    }
