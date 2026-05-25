"""
backend/routes/predictive.py

Predictive alerting and chaos forecasting API routes.

Endpoints:
  GET  /api/predictive/forecasts     — Current forecasts for all metrics
  GET  /api/predictive/alerts        — Active predictive alerts
  GET  /api/predictive/chaos         — List chaos scenarios
  POST /api/predictive/chaos/run     — Run a chaos scenario simulation
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictive", tags=["predictive"])


@router.get("/forecasts")
async def get_forecasts():
    """Return current forecasts for all tracked metrics."""
    from services.predictive_alerting import predictive_engine
    forecasts = predictive_engine.forecast_all()
    return {
        "forecasts": [
            {
                "metric": f.metric_name,
                "current": f.current_value,
                "forecast": f.forecast_value,
                "horizon_seconds": f.horizon_seconds,
                "confidence": f.confidence,
                "will_breach": f.will_breach,
                "breach_threshold": f.breach_threshold,
                "breach_eta_seconds": f.breach_eta_seconds,
            }
            for f in forecasts
        ],
        "count": len(forecasts),
    }


@router.get("/alerts")
async def get_predictive_alerts():
    """Return active predictive alerts (metrics forecast to breach)."""
    from services.predictive_alerting import predictive_engine
    alerts = predictive_engine.get_predictive_alerts()
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/chaos")
async def list_chaos_scenarios():
    """List all available chaos scenarios."""
    from services.predictive_alerting import ChaosForecaster
    scenarios = ChaosForecaster.get_scenarios()
    return {
        "scenarios": [
            {
                "name": s.name,
                "description": s.description,
                "max_severity": s.max_severity,
                "cascade_count": len(s.cascade_predictions),
            }
            for s in scenarios
        ],
        "count": len(scenarios),
    }


@router.post("/chaos/run")
async def run_chaos_scenario(scenario_name: str = Query(...)):
    """Run a chaos scenario simulation against current metrics."""
    from services.predictive_alerting import ChaosForecaster, predictive_engine
    # Get current metric values from the forecasters
    current_metrics = {}
    for name, forecaster in predictive_engine._forecasters.items():
        if forecaster._history:
            current_metrics[name] = forecaster._history[-1]

    result = ChaosForecaster.run_scenario(scenario_name, current_metrics)
    if result is None:
        return {"error": f"Scenario '{scenario_name}' not found"}, 404
    return result
