"""API routes for the alert system."""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# Global alert engine instance
_alert_engine = None

# Connected WebSocket clients for signal streaming
_signal_clients: List[WebSocket] = []


async def broadcast_signal(signal: Dict[str, Any]):
    """Broadcast a trading signal to all connected WebSocket clients."""
    disconnected = []
    for ws in _signal_clients:
        try:
            await ws.send_json(signal)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _signal_clients.remove(ws)


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket endpoint for real-time trading signal streaming.

    Clients connect here to receive BUY/SELL signals pushed from
    trading_signals.py or the alert engine.
    """
    await websocket.accept()
    _signal_clients.append(websocket)
    logger.info(f"Signal client connected. Total: {len(_signal_clients)}")
    try:
        while True:
            # Keep connection alive, handle pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        _signal_clients.remove(websocket)
        logger.info(f"Signal client disconnected. Total: {len(_signal_clients)}")
    except Exception as e:
        logger.error(f"Signal WebSocket error: {e}")
        if websocket in _signal_clients:
            _signal_clients.remove(websocket)

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
        from alert_engine import GEXSnapshot
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
