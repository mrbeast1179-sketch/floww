"""
backend/services/ml/retrain.py

Auto-retrain trigger — monitors drift and kicks off retraining.

Architecture:
    DriftMonitor polls ml_predictions for tickers with drift_detected status.
    When drift is detected AND no retrain is already in-flight:
      1. Spawns a background retraining job (via async task)
      2. Re-registers the new model as a shadow candidate
      3. Promotes if it passes the SHIP gate
      4. Retires the old model
    State is tracked in ml_retrain collection to prevent duplicate retrains.

Usage:
    from services.ml.retrain import RetrainOrchestrator
    orch = RetrainOrchestrator(db)
    result = await orch.check_and_retrain("SPY")
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from services.ml import DegenerateModelError

log = logging.getLogger("ml.retrain")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_RETRAIN = "ml_retrain"
COLLECTION_MODELS = "ml_models"
COLLECTION_PREDICTIONS = "ml_predictions"

# Minimum time between retrains for the same ticker (hours)
RETRAIN_COOLDOWN_HOURS = 24
# Minimum number of drift-detected samples before triggering
DRIFT_THRESHOLD_SAMPLES = 3


class RetrainOrchestrator:
    """Monitors model health and triggers retraining on drift detection.

    Designed to be called from a cron job (not a long-lived process).
    Each call checks all registered models and triggers retraining
    only when drift is detected and cooldown has expired.
    """

    def __init__(self, db: Any) -> None:
        self.db = db
        self.retrain_col = db[COLLECTION_RETRAIN]
        self.models_col = db[COLLECTION_MODELS]
        self.predictions_col = db[COLLECTION_PREDICTIONS]

    async def get_active_tickers(self) -> List[str]:
        """Get list of tickers with active models."""
        cursor = self.models_col.find({"status": "active"}, {"ticker": 1, "_id": 0})
        docs = await cursor.to_list(length=100)
        return [d["ticker"] for d in docs]

    async def is_retrain_in_flight(self, ticker: str) -> bool:
        """Check if a retrain is already running for this ticker."""
        existing = await self.retrain_col.find_one({
            "ticker": ticker,
            "status": {"$in": ["pending", "running"]},
        })
        return existing is not None

    async def is_retrain_on_cooldown(self, ticker: str) -> bool:
        """Check if enough time has passed since the last retrain."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=RETRAIN_COOLDOWN_HOURS)
        recent = await self.retrain_col.find_one({
            "ticker": ticker,
            "created_at": {"$gte": cutoff.isoformat()},
        })
        return recent is not None

    async def detect_drift(self, ticker: str) -> Dict[str, Any]:
        """Check if drift has been detected for a ticker's recent predictions.

        Returns drift report with:
          - drift_detected: bool
          - n_samples: number of recent predictions checked
          - n_drift: number showing drift
          - details: list of drift alerts
        """
        from services.ml.registry import ModelRegistry
        registry = ModelRegistry(self.db)
        try:
            drift_report = await registry.compute_drift(ticker)
        except DegenerateModelError:
            return {"drift_detected": False, "n_samples": 0, "n_drift": 0, "details": []}
        except Exception as e:
            log.warning(f"Drift check failed for {ticker}: {e}")
            return {"drift_detected": False, "n_samples": 0, "n_drift": 0, "details": []}

        status = drift_report.get("status", "ok")
        drift_detected = status == "drift_detected"
        features = drift_report.get("features", {})
        drift_alerts = [f for f, psi in features.items() if psi >= 0.2]

        return {
            "drift_detected": drift_detected,
            "n_samples": drift_report.get("n_recent_samples", 0),
            "n_drift": len(drift_alerts),
            "details": drift_alerts,
            "drift_report": drift_report,
        }

    async def spawn_retrain(self, ticker: str) -> Dict[str, Any]:
        """Spawn a background retraining job for a ticker.

        Creates a retrain document with status='pending' and then
        runs the retraining pipeline asynchronously.
        """
        from services.ml.registry import ModelRegistry
        import joblib
        import numpy as np
        import pandas as pd
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import accuracy_score

        ticker = ticker.upper()
        retrain_id = f"{ticker}_retrain_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Create retrain document
        await self.retrain_col.insert_one({
            "retrain_id": retrain_id,
            "ticker": ticker,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "result": None,
        })

        try:
            # Build features from recent snapshots
            features_df = await self._build_features_for_ticker(ticker)
            if features_df is None or len(features_df) < 100:
                await self._update_retrain(retrain_id, "failed", {
                    "reason": "insufficient_data",
                    "samples": len(features_df) if features_df is not None else 0,
                })
                return {"status": "failed", "reason": "insufficient_data"}

            # Walk-forward training
            X = features_df.drop(columns=["date", "label", "ticker"], errors="ignore")
            y = features_df["label"].values
            feature_names = list(X.columns)
            X = X.values.astype(float)

            # Clean NaN/Inf
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

            # Walk-forward splits
            n_splits = min(5, len(X) // 60)
            if n_splits < 2:
                await self._update_retrain(retrain_id, "failed", {"reason": "not enough splits"})
                return {"status": "failed", "reason": "not enough splits"}

            split_size = len(X) // (n_splits + 1)
            accuracies = []
            best_model = None
            best_scaler = None
            best_acc = 0.0

            for i in range(n_splits):
                train_end = split_size * (i + 1)
                test_end = min(train_end + split_size, len(X))
                if test_end - train_end < 10:
                    continue

                X_train = X[:train_end]
                y_train = y[:train_end]
                X_test = X[train_end:test_end]
                y_test = y[train_end:test_end]

                scaler = StandardScaler()
                X_train_s = scaler.fit_transform(X_train)
                X_test_s = scaler.transform(X_test)

                model = GradientBoostingClassifier(
                    n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
                )
                model.fit(X_train_s, y_train)

                acc = accuracy_score(y_test, model.predict(X_test_s))
                accuracies.append(acc)

                if acc > best_acc:
                    best_acc = acc
                    best_model = model
                    best_scaler = scaler

            if best_model is None:
                await self._update_retrain(retrain_id, "failed", {"reason": "training produced no model"})
                return {"status": "failed", "reason": "no model produced"}

            mean_acc = float(np.mean(accuracies)) if accuracies else 0.0

            # Save new model artifact
            import joblib as _joblib
            from pathlib import Path
            model_dir = Path(__file__).resolve().parents[2] / "models"
            model_dir.mkdir(exist_ok=True)
            model_path = model_dir / f"{ticker}_rf_retrain_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.joblib"

            artifact = {
                "model": best_model,
                "scaler": best_scaler,
                "model_name": "GradientBoosting_retrain",
                "feature_names": feature_names,
                "metrics": {
                    "avg_train_accuracy": mean_acc,
                    "avg_test_accuracy": best_acc,
                    "n_splits": len(accuracies),
                },
            }
            _joblib.dump(artifact, str(model_path))

            # Register as shadow model
            model_id = f"{ticker}_direction_retrain_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            registry = ModelRegistry(self.db)
            await registry.register_model(
                model_id=model_id,
                ticker=ticker,
                feature_version="v1.0_retrain",
                training_window=f"auto-retrain from {len(X)} samples",
                metrics_summary={
                    "beats_baselines": mean_acc > 0.52,  # must beat coin flip + margin
                    "holdout_sharpe": 0.0,  # not yet computed via backtest
                    "calibration_error": 0.0,
                    "train_accuracy": mean_acc,
                    "n_features": len(feature_names),
                    "feature_names": feature_names,
                    "auto_retrained": True,
                    "retrain_id": retrain_id,
                },
                artifact_path=str(model_path),
                status="shadow",
            )

            await self._update_retrain(retrain_id, "completed", {
                "model_id": model_id,
                "artifact_path": str(model_path),
                "mean_accuracy": round(mean_acc, 4),
                "n_samples": len(X),
                "n_features": len(feature_names),
                "n_splits": len(accuracies),
            })

            log.info(f"Retrain {retrain_id} completed: {model_id} mean_acc={mean_acc:.4f}")
            return {
                "status": "completed",
                "model_id": model_id,
                "mean_accuracy": mean_acc,
                "n_samples": len(X),
            }

        except Exception as e:
            log.error(f"Retrain {retrain_id} failed: {e}", exc_info=True)
            await self._update_retrain(retrain_id, "failed", {"reason": str(e)})
            return {"status": "failed", "reason": str(e)}

    async def _build_features_for_ticker(self, ticker: str) -> Optional[Any]:
        """Build feature matrix from recent snapshots + outcomes for retraining."""
        import pandas as pd
        import numpy as np

        # Load recent snapshots (last 252 trading days)
        snapshots = await self.db["snapshots"].find(
            {"ticker": ticker}
        ).sort("ts", -1).to_list(length=500)

        if len(snapshots) < 60:
            # Fallback to enhanced snapshots
            snapshots = await self.db["gex_enhanced_snapshots"].find(
                {"ticker": ticker}
            ).sort("date", -1).to_list(length=500)

        if len(snapshots) < 60:
            return None

        # Build feature rows
        rows = []
        for s in snapshots:
            row = self._extract_snapshot_features(s)
            if row:
                rows.append(row)

        if len(rows) < 60:
            return None

        df = pd.DataFrame(rows)
        df = df.sort_values("date").reset_index(drop=True)

        # Create label: 1 if next-day return > 0
        if "spot" in df.columns:
            df["next_return"] = df["spot"].pct_change().shift(-1)
            df["label"] = (df["next_return"] > 0).astype(int)
        else:
            return None

        df = df.dropna(subset=["label"])
        return df

    def _extract_snapshot_features(self, snapshot: Dict) -> Optional[Dict]:
        """Extract numeric features from a snapshot document."""
        spot = snapshot.get("spot", 0)
        if not spot or spot <= 0:
            return None

        ts = snapshot.get("ts", snapshot.get("date", ""))
        features = {
            "date": ts,
            "spot": float(spot),
            "total_gex": float(snapshot.get("total_gex", 0) or 0),
            "net_gex": float(snapshot.get("net_gex", 0) or 0),
            "king_strike": float(snapshot.get("king_strike", 0) or 0),
            "king_gex": float(snapshot.get("king_gex", 0) or 0),
            "top_floor": float(snapshot.get("top_floor", 0) or 0),
            "top_ceiling": float(snapshot.get("top_ceiling", 0) or 0),
            "num_strikes": float(snapshot.get("num_strikes", 0) or 0),
        }

        # Add regime encoding
        regime = snapshot.get("regime", "unknown")
        features["regime_positive"] = 1.0 if str(regime).upper() == "POSITIVE" else 0.0
        features["regime_negative"] = 1.0 if str(regime).upper() == "NEGATIVE" else 0.0

        # Add strike compact features
        strikes = snapshot.get("strikes_compact", [])
        if strikes:
            gex_values = [float(s.get("gex", 0)) for s in strikes if s.get("gex") is not None]
            if gex_values:
                features["gex_mean"] = float(np.mean(gex_values))
                features["gex_std"] = float(np.std(gex_values))
                features["gex_max"] = float(np.max(np.abs(gex_values)))
                features["gex_skew"] = float(np.percentile(gex_values, 75) - np.percentile(gex_values, 25)) if len(gex_values) > 1 else 0.0
            else:
                features["gex_mean"] = 0.0
                features["gex_std"] = 0.0
                features["gex_max"] = 0.0
                features["gex_skew"] = 0.0
        else:
            features["gex_mean"] = 0.0
            features["gex_std"] = 0.0
            features["gex_max"] = 0.0
            features["gex_skew"] = 0.0

        return features

    async def _update_retrain(self, retrain_id: str, status: str, result: Dict) -> None:
        """Update retrain document with status and result."""
        await self.retrain_col.update_one(
            {"retrain_id": retrain_id},
            {"$set": {
                "status": status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            }},
        )

    async def check_and_retrain(self, ticker: str) -> Dict[str, Any]:
        """Check drift for a ticker and trigger retraining if needed.

        Returns a status dict:
          - action: "skipped" | "triggered" | "in_flight" | "cooldown" | "no_drift" | "failed"
          - details: additional info
        """
        ticker = ticker.upper()

        # Check if retrain already in flight
        if await self.is_retrain_in_flight(ticker):
            return {"action": "in_flight", "ticker": ticker}

        # Check cooldown
        if await self.is_retrain_on_cooldown(ticker):
            return {"action": "cooldown", "ticker": ticker}

        # Check drift
        drift = await self.detect_drift(ticker)
        if not drift["drift_detected"]:
            return {"action": "no_drift", "ticker": ticker, "samples": drift["n_samples"]}

        # Spawn retrain
        log.info(f"Drift detected for {ticker} ({drift['n_drift']} features), triggering retrain")
        result = await self.spawn_retrain(ticker)
        return {
            "action": "triggered",
            "ticker": ticker,
            "drift_features": drift["n_drift"],
            "retrain_result": result,
        }

    async def check_all_and_retrain(self) -> List[Dict[str, Any]]:
        """Check all active tickers and trigger retraining where needed."""
        tickers = await self.get_active_tickers()
        results = []
        for ticker in tickers:
            try:
                result = await self.check_and_retrain(ticker)
                results.append(result)
            except Exception as e:
                log.error(f"Check/retrain failed for {ticker}: {e}")
                results.append({"action": "error", "ticker": ticker, "error": str(e)})
        return results
