"""API routes for the alert system."""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Global alert engine instance
_alert_engine = None

def get_alert_engine():
    """Get or create the global alert engine."""
    global _alert_engine
    if _alert_engine is None:
        from alert_engine import AlertEngine
        _alert_engine = AlertEngine()
    return _alert_engine


@router.get("/{ticker}")
async def get_alerts(ticker: str, momentum_score: int = Query(50, ge=0, le=100)):
    """Get current alerts for a ticker."""
    try:
        engine = get_alert_engine()
        summary = engine.get_alert_summary(ticker.upper())
        return summary
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}


@router.post("/snapshot")
async def add_snapshot(snapshot: Dict[str, Any]):
    """Add a GEX snapshot for alert detection."""
    try:
        from alert_engine import GEXSnapshot, AlertEngine
        engine = get_alert_engine()
        
        snap = GEXSnapshot(
            ticker=snapshot.get("ticker", "UNKNOWN").upper(),
            spot_price=snapshot.get("spot_price", 0),
            gamma_flip=snapshot.get("gamma_flip", 0),
            call_wall=snapshot.get("call_wall", 0),
            put_wall=snapshot.get("put_wall", 0),
            max_pain=snapshot.get("max_pain", 0),
            max_gamma_strike=snapshot.get("max_gamma_strike", 0),
            total_gex=snapshot.get("total_gex", 0),
            net_gex=snapshot.get("net_gex", 0),
            regime=snapshot.get("regime", "UNKNOWN"),
            gex_by_strike=snapshot.get("gex_by_strike", {}),
        )
        
        engine.add_snapshot(snap)
        
        # Detect alerts
        alerts = engine.detect_alerts(snap.ticker)
        
        return {
            "status": "ok",
            "snapshot_stored": True,
            "alerts_detected": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/status")
async def get_alert_status():
    """Get alert system status."""
    try:
        engine = get_alert_engine()
        tickers = list(engine._snapshots.keys())
        return {
            "status": "active",
            "monitored_tickers": tickers,
            "snapshot_counts": {t: len(s) for t, s in engine._snapshots.items()},
        }
    except Exception as e:
        return {"error": str(e)}
