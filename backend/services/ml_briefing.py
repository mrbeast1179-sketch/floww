"""
backend/services/ml_briefing.py

ML-powered briefing integrator.

Combines deterministic morning briefing with ML model predictions
to produce a unified trading signal with confidence scoring.

Usage:
    from services.ml_briefing import MlBriefingIntegrator
    integrator = MlBriefingIntegrator()
    briefing = await integrator.generate_briefing("SPY")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from services.ml import DegenerateModelError

log = logging.getLogger("ml_briefing")


@dataclass
class MlBriefingIntegrator:
    """Combines morning briefing with ML predictions."""

    def __init__(self):
        self._inference_engine = None
        self._briefing_engine = None

    def _get_inference_engine(self):
        """Lazy-load inference engine."""
        if self._inference_engine is None:
            try:
                from services.ml.inference import InferenceEngine
                self._inference_engine = InferenceEngine()
            except Exception as e:
                log.warning(f"Could not load inference engine: {e}")
        return self._inference_engine

    def _get_briefing_engine(self):
        """Lazy-load morning briefing engine."""
        if self._briefing_engine is None:
            try:
                from services.morning_briefing import build_briefing
                self._briefing_engine = build_briefing
            except Exception as e:
                log.warning(f"Could not load briefing engine: {e}")
        return self._briefing_engine

    async def generate_briefing(self, ticker: str) -> dict[str, Any]:
        """Generate a unified ML + deterministic briefing.

        Args:
            ticker: Ticker symbol

        Returns:
            Dict with regime, ML prediction, combined signal, and supporting data
        """
        ticker = ticker.upper()
        now_str = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

        # --- Deterministic briefing ---
        regime = "NEUTRAL"
        regime_confidence = 0.5
        spot_price = None
        net_gex = None
        gex_regime = None
        top_movers = []
        alerts = []

        briefing = self._get_briefing_engine()
        if briefing:
            try:
                result = await briefing(ticker)
                if result:
                    regime = result.regime or "NEUTRAL"
                    regime_confidence = 0.7 if regime != "NEUTRAL" else 0.5
                    metrics = result.metrics or {}
                    spot_price = metrics.get("spot_price")
                    net_gex = metrics.get("net_gex")
                    gex_regime = metrics.get("gex_regime")
                    top_movers = metrics.get("top_movers", [])
                    alerts = metrics.get("alerts", [])
            except Exception as e:
                log.warning(f"Briefing engine failed for {ticker}: {e}")

        # --- ML prediction ---
        ml_prediction = None
        ml_confidence = None
        ml_model_id = None
        feature_values = {}

        engine = self._get_inference_engine()
        if engine:
            try:
                result = await engine.predict(ticker)
                ml_prediction = result.prediction
                ml_confidence = result.confidence
                ml_model_id = result.model_id
                feature_values = result.feature_values
            except DegenerateModelError as e:
                log.info(f"No ML model for {ticker}: {e}")
            except Exception as e:
                log.warning(f"ML prediction failed for {ticker}: {e}")

        # --- Combine signals ---
        combined_signal, combined_confidence = self._combine_signals(
            regime, regime_confidence, ml_prediction, ml_confidence
        )

        return {
            "ticker": ticker,
            "timestamp": now_str,
            "regime": regime,
            "regime_confidence": regime_confidence,
            "ml_prediction": ml_prediction,
            "ml_confidence": ml_confidence,
            "ml_model_id": ml_model_id,
            "combined_signal": combined_signal,
            "combined_confidence": combined_confidence,
            "spot_price": spot_price,
            "net_gex": net_gex,
            "gex_regime": gex_regime,
            "top_movers": top_movers,
            "feature_values": feature_values,
            "alerts": alerts,
        }

    def _combine_signals(
        self,
        regime: str,
        regime_confidence: float,
        ml_prediction: int | None,
        ml_confidence: float | None,
    ) -> tuple:
        """Combine deterministic regime + ML prediction into unified signal.

        Returns (signal, confidence).
        """
        # Regime score: -1 (bearish) to +1 (bullish)
        regime_score = 0.0
        if regime == "BULLISH":
            regime_score = regime_confidence
        elif regime == "BEARISH":
            regime_score = -regime_confidence

        # ML score: -1 (bearish) to +1 (bullish)
        ml_score = 0.0
        if ml_prediction is not None and ml_confidence is not None:
            ml_score = (2 * ml_prediction - 1) * ml_confidence  # 1->+conf, 0->-conf

        # Weighted average (weight by confidence)
        total_weight = 0.0
        weighted_score = 0.0

        if regime_confidence > 0:
            weighted_score += regime_score * regime_confidence
            total_weight += regime_confidence

        if ml_confidence is not None and ml_confidence > 0:
            weighted_score += ml_score * ml_confidence
            total_weight += ml_confidence

        combined = weighted_score / total_weight if total_weight > 0 else 0.0

        # Map to signal label
        if combined > 0.5:
            signal = "STRONG_BULLISH"
        elif combined > 0.2:
            signal = "BULLISH"
        elif combined < -0.5:
            signal = "STRONG_BEARISH"
        elif combined < -0.2:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        confidence = abs(combined)
        return signal, confidence

    async def get_model_status(self, ticker: str) -> dict[str, Any]:
        """Get ML model status for a ticker."""
        engine = self._get_inference_engine()
        if not engine:
            return {"ticker": ticker, "status": "unavailable", "reason": "Inference engine not loaded"}

        ticker = ticker.upper()
        try:
            info = engine.get_model_info(ticker)
            return {
                "ticker": ticker,
                "status": "loaded",
                "model_id": info.model_id,
                "model_type": info.model_type,
                "n_features": info.n_features,
                "train_accuracy": info.train_accuracy,
            }
        except DegenerateModelError as e:
            return {"ticker": ticker, "status": "not_found", "reason": str(e)}
        except Exception as e:
            return {"ticker": ticker, "status": "error", "reason": str(e)}

    async def list_available_models(self) -> list[dict[str, Any]]:
        """List all available ML models."""
        engine = self._get_inference_engine()
        if not engine:
            return []

        models = []
        for info in engine.list_models():
            models.append({
                "ticker": info.ticker,
                "model_id": info.model_id,
                "model_type": info.model_type,
                "n_features": info.n_features,
                "train_accuracy": info.train_accuracy,
                "loaded": info.loaded,
            })
        return models


# Singleton
ml_briefing = MlBriefingIntegrator()
