"""
backend/services/meta_observability.py

Meta-anomaly detection on Prometheus metrics themselves.
Trains an Isolation Forest on rolling metrics to detect deviations from
"time-of-day" baselines — e.g., Tuesday 2pm now vs Tuesday 2pm average.

Inputs (from Prometheus scrape):
    - ingestion_rate per symbol
    - duckdb_queue_depth
    - vpin_current per ticker
    - p99 API latency
    - websocket_connections

Output: LOW-severity warnings surfaced before they become incidents.

Model: sklearn.ensemble.IsolationForest
Persistence: ./project_oracle/models/meta_anomaly_v1.pt (joblib)
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

# Model path
MODEL_DIR = Path(__file__).resolve().parents[2] / "project_oracle" / "models"
MODEL_PATH = MODEL_DIR / "meta_anomaly_v1.pt"

# Feature names (must match training order)
FEATURES = [
    "ingestion_rate_spy",
    "ingestion_rate_qqq",
    "queue_depth",
    "vpin_spy",
    "vpin_qqq",
    "p99_latency",
    "ws_connections",
    "hour_of_day",      # cyclical encoding
    "day_of_week",      # cyclical encoding
]

# Anomaly threshold (Isolation Forest decision_function score)
ANOMALY_THRESHOLD = -0.15


class MetaAnomalyDetector:
    """Detects anomalies in the metrics themselves using Isolation Forest."""

    def __init__(self):
        self._model: Any = None
        self._scaler: Any = None
        self._last_score: float = 0.0
        self._last_anomaly: bool = False
        self._training_data: List[List[float]] = []
        self._training_max = 10080  # 7 days of 1-min samples
        self._load_model()

    # ------------------------------------------------------------------
    # Model persistence
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load trained model from disk."""
        try:
            import joblib
            if MODEL_PATH.exists():
                data = joblib.load(MODEL_PATH)
                self._model = data["model"]
                self._scaler = data["scaler"]
                log.info(f"Meta-anomaly model loaded from {MODEL_PATH}")
            else:
                log.info("No saved meta-anomaly model — will train on first data")
        except ImportError:
            log.warning("joblib not available — meta-anomaly detection disabled")
        except Exception as e:
            log.warning(f"Failed to load meta-anomaly model: {e}")

    def _save_model(self):
        """Save trained model to disk."""
        try:
            import joblib
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            joblib.dump({"model": self._model, "scaler": self._scaler}, MODEL_PATH)
            log.info(f"Meta-anomaly model saved to {MODEL_PATH}")
        except Exception as e:
            log.error(f"Failed to save meta-anomaly model: {e}")

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_features(self, metrics_snapshot: Dict[str, float]) -> List[float]:
        """Extract feature vector from a Prometheus metrics snapshot.

        metrics_snapshot keys:
            ingestion_rate_spy, ingestion_rate_qqq, queue_depth,
            vpin_spy, vpin_qqq, p99_latency, ws_connections
        """
        now = datetime.now(timezone.utc)
        hour = now.hour + now.minute / 60.0
        dow = now.weekday()

        # Cyclical encoding for time features
        hour_sin = np.sin(2 * np.pi * hour / 24.0)
        hour_cos = np.cos(2 * np.pi * hour / 24.0)
        dow_sin = np.sin(2 * np.pi * dow / 7.0)
        dow_cos = np.cos(2 * np.pi * dow / 7.0)

        return [
            metrics_snapshot.get("ingestion_rate_spy", 0.0),
            metrics_snapshot.get("ingestion_rate_qqq", 0.0),
            metrics_snapshot.get("queue_depth", 0.0),
            metrics_snapshot.get("vpin_spy", 0.0),
            metrics_snapshot.get("vpin_qqq", 0.0),
            metrics_snapshot.get("p99_latency", 0.0),
            metrics_snapshot.get("ws_connections", 0.0),
            hour_sin * 0.5 + hour_cos * 0.5,  # combined cyclical
            dow_sin * 0.5 + dow_cos * 0.5,
        ]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def add_training_sample(self, metrics_snapshot: Dict[str, float]):
        """Add a sample to the training buffer. Triggers training when buffer is full."""
        features = self._extract_features(metrics_snapshot)
        self._training_data.append(features)

        if len(self._training_data) > self._training_max:
            self._training_data = self._training_data[-self._training_max:]

        # Auto-train every 1440 samples (1 day of 1-min data)
        if len(self._training_data) % 1440 == 0 and len(self._training_data) >= 2880:
            self.train()

    def train(self):
        """Train the Isolation Forest on collected training data."""
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            log.warning("sklearn not available — cannot train meta-anomaly model")
            return

        if len(self._training_data) < 100:
            log.info(f"Not enough training data ({len(self._training_data)} samples)")
            return

        X = np.array(self._training_data)
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        self._model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X_scaled)
        self._save_model()
        log.info(f"Meta-anomaly model trained on {len(self._training_data)} samples")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def score(self, metrics_snapshot: Dict[str, float]) -> Dict[str, Any]:
        """Score a metrics snapshot for anomaly detection.

        Returns:
            {
                "anomaly_score": float,  # Isolation Forest decision_function
                "is_anomaly": bool,      # True if score < threshold
                "model_loaded": bool,
                "training_samples": int,
            }
        """
        features = self._extract_features(metrics_snapshot)

        # Always add to training buffer
        self.add_training_sample(metrics_snapshot)

        if self._model is None or self._scaler is None:
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "model_loaded": False,
                "training_samples": len(self._training_data),
            }

        try:
            X = np.array([features])
            X_scaled = self._scaler.transform(X)
            score = float(self._model.decision_function(X_scaled)[0])
            is_anomaly = score < ANOMALY_THRESHOLD

            self._last_score = score
            self._last_anomaly = is_anomaly

            if is_anomaly:
                log.warning(
                    f"[META-ANOMALY] score={score:.4f} — deviation from time-of-day baseline"
                )

            return {
                "anomaly_score": round(score, 4),
                "is_anomaly": is_anomaly,
                "model_loaded": True,
                "training_samples": len(self._training_data),
            }
        except Exception as e:
            log.error(f"Meta-anomaly scoring failed: {e}")
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "model_loaded": True,
                "training_samples": len(self._training_data),
            }

    def get_state(self) -> Dict[str, Any]:
        """Return current detector state."""
        return {
            "model_loaded": self._model is not None,
            "training_samples": len(self._training_data),
            "last_score": self._last_score,
            "last_anomaly": self._last_anomaly,
            "threshold": ANOMALY_THRESHOLD,
            "model_path": str(MODEL_PATH),
        }


# Global singleton
meta_detector = MetaAnomalyDetector()
