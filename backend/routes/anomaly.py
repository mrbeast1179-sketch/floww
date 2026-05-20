"""
backend/routes/anomaly.py

Anomaly Detection API routes.
Exposes the 1D-CNN Autoencoder flow toxicity anomaly detector.

Endpoints:
  GET  /api/anomaly/{ticker}        — Current anomaly state
  POST /api/anomaly/{ticker}/update — Feed new (VPIN, QI) observation
  GET  /api/anomaly/{ticker}/status — Model status and configuration
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])

# Global anomaly detector registry (ticker -> FlowAnomalyDetector)
_detectors: Dict[str, Any] = {}


def _get_detector(ticker: str, seq_len: int = 50, latent_dim: int = 8):
    """Get or create an anomaly detector for the given ticker."""
    if ticker not in _detectors:
        from services.anomaly_detector import FlowAnomalyDetector
        _detectors[ticker] = FlowAnomalyDetector(
            seq_len=seq_len, latent_dim=latent_dim, ticker=ticker
        )
    return _detectors[ticker]


@router.get("/{ticker}")
async def get_anomaly_state(ticker: str):
    """Return the current anomaly detection state."""
    t = ticker.upper()
    detector = _get_detector(t)
    return detector.get_state()


@router.post("/{ticker}/update")
async def update_anomaly(ticker: str, vpin: float, qi: float):
    """Feed a new (VPIN, QI) observation and get anomaly score."""
    t = ticker.upper()
    detector = _get_detector(t)
    result = detector.update(vpin, qi)
    return {"ticker": t, **result}


@router.get("/{ticker}/status")
async def get_detector_status(ticker: str):
    """Return model configuration and buffer status."""
    t = ticker.upper()
    detector = _get_detector(t)
    return detector.get_state()
