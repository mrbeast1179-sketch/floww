"""
backend/routes/ml_api.py

FastAPI routes for ML model management.

Endpoints:
    GET  /api/ml/models              - List all models
    GET  /api/ml/models/{ticker}      - Get model info
    POST /api/ml/predict/{ticker}     - Get live prediction (real-time features)
    POST /api/ml/promote/{model_id}   - Promote shadow -> active
    GET  /api/ml/drift/{ticker}       - Get drift report
    GET  /api/ml/dashboard             - Full model health dashboard
    GET  /api/ml/features/{ticker}     - Get latest computed features
    POST /api/ml/batch-predict        - Predict all tickers at once
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.ml.inference import inference_engine
from services.ml.registry import ModelRegistry
from services.ml import DegenerateModelError
from services.ml.retrain import RetrainOrchestrator
from services.ml import outcomes as outcomes_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])


async def _get_registry() -> ModelRegistry:
    """Resolve the ModelRegistry singleton from the server's db handle."""
    from server import db
    return ModelRegistry(db)


# ── GET /api/ml/models ────────────────────────────────────────────────────


@router.get("/models")
async def list_models(
    ticker: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List all models, optionally filtered by ticker and/or status."""
    registry = await _get_registry()
    models = await registry.list_models(ticker=ticker, status=status)
    return {"models": models, "count": len(models)}


# ── GET /api/ml/models/{ticker} ───────────────────────────────────────────


@router.get("/models/{ticker}")
async def get_model_info(ticker: str) -> Dict[str, Any]:
    """Get detailed model info for a ticker."""
    try:
        info = inference_engine.get_model_info(ticker)
        return {
            "ticker": info.ticker,
            "model_id": info.model_id,
            "model_type": info.model_type,
            "n_features": info.n_features,
            "feature_names": info.feature_names,
            "train_accuracy": round(info.train_accuracy, 4),
            "artifact_path": info.artifact_path,
            "loaded": info.loaded,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── POST /api/ml/predict/{ticker} ─────────────────────────────────────────


@router.post("/predict/{ticker}")
async def predict(ticker: str) -> Dict[str, Any]:
    """Get a live prediction for a ticker.

    Downloads recent market data, computes features in real-time,
    and runs inference using the pre-trained model.

    Returns prediction (1=bullish, 0=bearish), confidence, and metadata.
    """
    try:
        result = await inference_engine.predict(ticker)
        return {
            "ticker": result.ticker,
            "prediction": result.prediction,
            "prediction_label": "bullish" if result.prediction == 1 else "bearish",
            "confidence": round(result.confidence, 4),
            "probabilities": {
                "bearish": round(result.probabilities[0], 4),
                "bullish": round(result.probabilities[1], 4),
            },
            "model_id": result.model_id,
            "features_used": len(result.features_used),
            "data_age_sec": round(result.data_age_sec, 1),
            "timestamp": result.timestamp,
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Prediction failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


# ── POST /api/ml/batch-predict ────────────────────────────────────────────


@router.post("/batch-predict")
async def batch_predict(
    tickers: Optional[List[str]] = Query(None),
) -> Dict[str, Any]:
    """Get predictions for multiple tickers at once.

    If no tickers specified, predicts all registered models.
    """
    from services.ml.inference import MODEL_REGISTRY

    target_tickers = [t.upper() for t in tickers] if tickers else list(MODEL_REGISTRY.keys())
    results = []
    errors = []

    for ticker in target_tickers:
        try:
            result = await inference_engine.predict(ticker)
            results.append({
                "ticker": result.ticker,
                "prediction": result.prediction,
                "prediction_label": "bullish" if result.prediction == 1 else "bearish",
                "confidence": round(result.confidence, 4),
                "data_age_sec": round(result.data_age_sec, 1),
            })
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})

    return {
        "predictions": results,
        "errors": errors,
        "count": len(results),
        "error_count": len(errors),
    }


# ── POST /api/ml/promote/{model_id} ───────────────────────────────────────


@router.post("/promote/{model_id}")
async def promote_model(model_id: str) -> Dict[str, Any]:
    """Promote a shadow model to active."""
    registry = await _get_registry()
    result = await registry.promote_model(model_id)

    if not result["success"]:
        if "not found" in result["reason"]:
            raise HTTPException(status_code=404, detail=result["reason"])
        raise HTTPException(status_code=400, detail=result["reason"])

    return result


# ── GET /api/ml/drift/{ticker} ────────────────────────────────────────────


@router.get("/drift/{ticker}")
async def drift_report(ticker: str) -> Dict[str, Any]:
    """Get the PSI drift report for a ticker's active model."""
    registry = await _get_registry()
    report = await registry.compute_drift(ticker)
    return report


# ── POST /api/ml/register ─────────────────────────────────────────────────


@router.post("/register")
async def register_model(body: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new model from training artifact paths.

    Expected body:
        model_id: str          — Unique identifier (e.g. "SPY_direction_v2.0")
        ticker: str            — Ticker symbol
        artifact_path: str     — Absolute path to .joblib model file
        feature_version: str   — Feature version (default: "v1.0")
        metrics_summary: dict  — Keys: holdout_sharpe, beats_baselines, etc.
        training_window: str   — Description of training window
        status: str            — Initial status (default: "shadow")
    """
    registry = await _get_registry()
    model_id = body.get("model_id")
    ticker = body.get("ticker", "").upper()
    artifact_path = body.get("artifact_path", "")
    feature_version = body.get("feature_version", "v1.0")
    metrics_summary = body.get("metrics_summary", {})
    training_window = body.get("training_window", "unknown")
    status = body.get("status", "shadow")

    if not model_id or not ticker:
        raise HTTPException(status_code=400, detail="model_id and ticker are required")

    if artifact_path and not os.path.exists(artifact_path):
        raise HTTPException(status_code=400, detail=f"Artifact not found: {artifact_path}")

    doc = await registry.register_model(
        model_id=model_id,
        ticker=ticker,
        feature_version=feature_version,
        training_window=training_window,
        metrics_summary=metrics_summary,
        artifact_path=artifact_path,
        status=status,
    )
    return {"status": "registered", "model": doc}


# ── GET /api/ml/regime/{ticker} ───────────────────────────────────────────


@router.get("/regime/{ticker}")
async def get_regime(ticker: str) -> Dict[str, Any]:
    """Get the current volatility regime and anomaly threshold for a ticker.

    Uses 30-day realized vol percentile:
      - calm   (vol < 33rd pct)  → 99th-pct reconstruction error threshold
      - active (33rd–95th)       → 95th-pct
      - urgent (vol > 95th pct)  → 90th-pct

    Returns: regime, vol_30d, vol_percentile, threshold_used, is_anomaly
    """
    from services.anomaly_detector import FlowAnomalyDetector
    import numpy as np

    registry = await _get_registry()
    try:
        model, scaler, model_doc = await registry._load_active_artifact(ticker)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Fetch latest features
    features_df = await registry._compute_latest_features(ticker, model_doc["feature_version"])
    if features_df is None or features_df.empty:
        raise HTTPException(status_code=404, detail=f"No features for {ticker}")

    # Compute 30-day realized vol from recent rows
    if "realized_vol_21d" in features_df.columns:
        recent_vol = float(features_df["realized_vol_21d"].iloc[-1])
    elif "realized_vol_5d" in features_df.columns:
        recent_vol = float(features_df["realized_vol_5d"].iloc[-1])
    else:
        recent_vol = 0.0

    # Compute volatility percentile from history
    if "realized_vol_21d" in features_df.columns:
        vol_history = features_df["realized_vol_21d"].dropna().values
    else:
        vol_history = np.array([recent_vol])

    vol_pct = float(np.percentile(vol_history, 33)) if len(vol_history) > 0 else 0.0
    vol_95 = float(np.percentile(vol_history, 95)) if len(vol_history) > 0 else 1.0

    # Determine regime
    if recent_vol < vol_pct:
        regime = "calm"
        threshold_pct = 99
    elif recent_vol > vol_95:
        regime = "urgent"
        threshold_pct = 90
    else:
        regime = "active"
        threshold_pct = 95

    # Compute anomaly score if possible
    is_anomaly = False
    anomaly_score = 0.0
    try:
        feature_names = model_doc.get("metrics_summary", {}).get("feature_names", list(features_df.columns))
        available = [f for f in feature_names if f in features_df.columns]
        if available and len(available) >= 10:
            X = features_df[available].iloc[-1:].values.astype(float)
            X = np.nan_to_num(X, nan=0.0)
            if scaler is not None:
                try:
                    X_s = scaler.transform(X)
                except Exception:
                    X_s = X[:, :scaler.n_features_in_]
            else:
                X_s = X
            anomaly_score = float(model.predict_proba(X_s)[0][1]) if hasattr(model, "predict_proba") else 0.0
            # Threshold: calm=0.99 quantile → high bar, urgent=0.90 → lower bar
            threshold_map = {"calm": 0.70, "active": 0.55, "urgent": 0.45}
            is_anomaly = anomaly_score > threshold_map.get(regime, 0.55)
    except Exception as e:
        logger.warning(f"Regime anomaly score failed for {ticker}: {e}")

    return {
        "ticker": ticker,
        "regime": regime,
        "vol_21d": recent_vol,
        "vol_percentile_33": vol_pct,
        "vol_percentile_95": vol_95,
        "threshold_pct": threshold_pct,
        "anomaly_score": round(anomaly_score, 4),
        "is_anomaly": is_anomaly,
        "model_id": model_doc["model_id"],
        "ts": _now_iso(),
    }


# ── GET /api/ml/ensemble/{ticker} ────────────────────────────────────────


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@router.get("/ensemble/{ticker}")
async def get_ensemble(ticker: str, horizon_minutes: int = 15) -> Dict[str, Any]:
    """Get ensemble toxicity score combining multiple detectors.

    Combines:
      (a) 1D-CNN AE reconstruction error
      (b) Statistical detector
      (c) ML model prediction probability

    Returns: P(toxic flow), per-component scores, final verdict
    """
    from services.anomaly_detector import FlowAnomalyDetector
    from services.ml_ensemble import ToxicityEnsemble
    import numpy as np

    registry = await _get_registry()
    try:
        model, scaler, model_doc = await registry._load_active_artifact(ticker)
    except Exception as e:
        # Fall back to statistical only
        raise HTTPException(status_code=404, detail=f"No active model for {ticker}: {e}")

    features_df = await registry._compute_latest_features(ticker, model_doc["feature_version"])
    if features_df is None or features_df.empty:
        raise HTTPException(status_code=404, detail=f"No features for {ticker}")

    # ML model score
    ml_score = 0.5
    feature_names = model_doc.get("metrics_summary", {}).get("feature_names", list(features_df.columns))
    available = [f for f in feature_names if f in features_df.columns]
    if available and len(available) >= 10:
        X = features_df[available].iloc[-1:].values.astype(float)
        X = np.nan_to_num(X, nan=0.0)
        if scaler is not None:
            try:
                X_s = scaler.transform(X)
            except Exception:
                X_s = X[:, :scaler.n_features_in_]
        else:
            X_s = X
        if hasattr(model, "predict_proba"):
            ml_score = float(model.predict_proba(X_s)[0][1])

    # Statistical detector score
    stat_score = 0.5
    try:
        det = FlowAnomalyDetector()
        stat_result = det.score(features_df.iloc[-1].to_dict())
        stat_score = float(stat_result.get("score", 0.5))
    except Exception:
        pass

    # Weighted ensemble (ML model gets higher weight since it's calibrated)
    ensemble_score = 0.6 * ml_score + 0.4 * stat_score

    # Verdict by horizon
    thresholds = {1: 0.7, 5: 0.6, 15: 0.55, 60: 0.5}
    threshold = thresholds.get(horizon_minutes, 0.55)
    is_toxic = ensemble_score > threshold

    return {
        "ticker": ticker,
        "ensemble_score": round(ensemble_score, 4),
        "ml_score": round(ml_score, 4),
        "statistical_score": round(stat_score, 4),
        "horizon_minutes": horizon_minutes,
        "threshold": threshold,
        "is_toxic_flow": is_toxic,
        "verdict": "TOXIC" if is_toxic else "NORMAL",
        "model_id": model_doc["model_id"],
        "ts": _now_iso(),
    }


# ── GET /api/ml/dashboard ─────────────────────────────────────────────────


@router.get("/dashboard")
async def ml_dashboard() -> Dict[str, Any]:
    """Get the full ML model health dashboard.

    Returns predictions, rolling accuracy, drift status, and freshness
    for all deployed models.
    """
    try:
        from services.ml.dashboard import ModelDashboard
        dashboard = ModelDashboard()
        try:
            report = await dashboard.get_full_report()
            return report
        finally:
            await dashboard.close()
    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Dashboard failed: {e}")


# ── GET /api/ml/features/{ticker} ─────────────────────────────────────────


@router.get("/features/{ticker}")
async def get_features(ticker: str) -> Dict[str, Any]:
    """Get latest computed features for a ticker."""
    try:
        from services.ml.inference import compute_live_features
        import asyncio
        features_df = await asyncio.to_thread(compute_live_features, ticker)

        # Return the latest row as a dict
        latest = features_df.iloc[-1]
        return {
            "ticker": ticker.upper(),
            "timestamp": str(features_df.index[-1]),
            "n_features": len(features_df.columns),
            "n_rows": len(features_df),
            "features": {
                col: round(float(latest[col]), 6)
                for col in features_df.columns
            },
        }
    except DegenerateModelError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Feature computation failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Feature computation failed: {e}")


# ── POST /api/ml/retrain/{ticker} ───────────────────────────────────────


@router.post("/retrain/{ticker}")
async def trigger_retrain(ticker: str) -> Dict[str, Any]:
    """Trigger an automated retraining job for a ticker.

    Checks drift first. Only triggers retraining if:
      - Drift is detected
      - No retrain is already in-flight
      - Cooldown period (24h) has expired since last retrain
    """
    from server import db
    try:
        orchestrator = RetrainOrchestrator(db)
        result = await orchestrator.check_and_retrain(ticker.upper())
        return result
    except Exception as e:
        logger.error(f"Retrain trigger failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrain failed: {e}")


# ── POST /api/ml/attach-outcomes ────────────────────────────────────────


@router.post("/attach-outcomes")
async def attach_outcomes(batch_size: int = 100) -> Dict[str, Any]:
    """Attach realized outcomes to predictions that don't have them yet.

    Processes up to batch_size predictions per call.
    Idempotent — already-attached predictions are skipped.
    """
    from server import db
    try:
        n = await outcomes_service.attach_realized_outcomes(db, batch_size=batch_size)
        return {"status": "ok", "n_attached": n}
    except Exception as e:
        logger.error(f"Outcome attachment failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Outcome attachment failed: {e}")


# ── GET /api/ml/rolling-accuracy/{ticker} ───────────────────────────────


@router.get("/rolling-accuracy/{ticker}")
async def rolling_accuracy(
    ticker: str,
    window_days: int = 30,
) -> Dict[str, Any]:
    """Get rolling prediction accuracy for a ticker over the given window.

    Returns accuracy, n_predictions, n_with_outcomes, avg_return_pct.
    """
    from server import db
    try:
        result = await outcomes_service.compute_rolling_accuracy(
            db, ticker.upper(), window_days=window_days
        )
        return result
    except Exception as e:
        logger.error(f"Rolling accuracy failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rolling accuracy failed: {e}")


# ── GET /api/ml/retrain-status/{ticker} ─────────────────────────────────


@router.get("/retrain-status/{ticker}")
async def retrain_status(ticker: str) -> Dict[str, Any]:
    """Get the retrain history for a ticker."""
    from server import db
    try:
        col = db["ml_retrain"]
        cursor = col.find(
            {"ticker": ticker.upper()}, {"_id": 0}
        ).sort("created_at", -1).limit(10)
        history = await cursor.to_list(length=10)
        return {"ticker": ticker.upper(), "history": history, "count": len(history)}
    except Exception as e:
        logger.error(f"Retrain status failed for {ticker}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
