#!/usr/bin/env python3
"""
ML Training Pipeline Runner.

Can be run as:
- A cron job: python ml_pipeline.py --mode train
- A one-shot: python ml_pipeline.py --mode predict --ticker SPY
- A full pipeline: python ml_pipeline.py --mode full

Every model save in this file is gated by services.ml.quality. If any gate
fails (class imbalance, constant features, degenerate predictions, future
leakage, ...) the save is refused and DegenerateModelError propagates up.
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/ml_pipeline.log"),
    ]
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)


# ---------------------------------------------------------------------------
# Gated persistence
# ---------------------------------------------------------------------------

def _save_with_gates(
    *,
    model: Any,
    scaler: Any,
    model_path: str,
    scaler_path: str,
    X_train: Any,
    y_train: Any,
    y_test: Optional[Any] = None,
    y_pred_proba: Any,
    feature_names: Optional[List[str]] = None,
    feature_dates: Optional[List[Any]] = None,
    target_dates: Optional[List[Any]] = None,
    train_dates: Optional[List[Any]] = None,
    test_dates: Optional[List[Any]] = None,
    ticker: str = "?",
) -> Dict[str, bool]:
    """Run all applicable quality gates, then save model + scaler with joblib.

    Every joblib.dump in this file goes through this helper. On any gate
    failure, the save is refused and DegenerateModelError propagates up.

    Args:
        model: Trained sklearn estimator.
        scaler: Fitted feature scaler.
        model_path: Destination path for the model.
        scaler_path: Destination path for the scaler.
        X_train: Training feature matrix (for feature-variance gate).
        y_train: Training labels (for class-balance gate).
        y_test: Optional test labels (also gated for balance if provided).
        y_pred_proba: Predicted probabilities on held-out data
            (for prediction-distribution gate).
        feature_names: Optional names for variance-gate error messages.
        feature_dates / target_dates: Optional for the no-future-leakage gate.
        train_dates / test_dates: Optional for the train/test temporal-split gate.
        ticker: Symbol label for log lines.

    Returns:
        Dict[str, bool] reporting which gates ran and passed.

    Raises:
        DegenerateModelError: If any gate fails. The save is refused.
    """
    import joblib
    from services.ml.quality import (
        assert_class_balance,
        assert_feature_variance,
        assert_prediction_distribution,
        assert_temporal_ordering,
        assert_no_future_leakage,
        assert_train_test_temporal_split,
    )
    from services.ml import DegenerateModelError

    gate_results: Dict[str, bool] = {}

    try:
        # Gate 1: class balance on training labels (catches 99/1 splits)
        assert_class_balance(y_train, label=f"{ticker} y_train")
        gate_results["class_balance_train"] = True

        # Gate 1b: class balance on test labels too (when provided)
        if y_test is not None and len(np.asarray(y_test)) > 0:
            assert_class_balance(y_test, label=f"{ticker} y_test")
            gate_results["class_balance_test"] = True

        # Gate 2: feature variance (catches all-constant feature columns)
        assert_feature_variance(X_train, feature_names=feature_names)
        gate_results["feature_variance"] = True

        # Gate 3: prediction distribution (catches always-predict-X models)
        assert_prediction_distribution(y_pred_proba, label=f"{ticker} predictions")
        gate_results["prediction_distribution"] = True

        # Gate 4: temporal ordering of feature timestamps (when provided)
        if feature_dates is not None:
            assert_temporal_ordering(feature_dates, label=f"{ticker} feature_dates")
            gate_results["temporal_ordering"] = True

        # Gate 5: no future leakage from features into targets (when provided)
        if feature_dates is not None and target_dates is not None:
            assert_no_future_leakage(feature_dates, target_dates, label=f"{ticker} features")
            gate_results["no_future_leakage"] = True

        # Gate 6: train/test temporal split (when provided)
        if train_dates is not None and test_dates is not None:
            assert_train_test_temporal_split(train_dates, test_dates)
            gate_results["train_test_temporal_split"] = True

    except DegenerateModelError as e:
        logger.error(f"REFUSED TO SAVE {ticker} — degenerate model: {e}")
        raise

    # All gates passed — persist.
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    logger.info(
        f"{ticker}: saved model and scaler after {len(gate_results)} quality gates"
    )
    return gate_results


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

async def collect_data():
    """Step 1: Collect fresh data."""
    from data_collector import collect_multiple_tickers

    tickers = os.environ.get("COLLECT_TICKERS", "SPY,QQQ,IWM,DIA,AAPL,TSLA,NVDA,MSFT").split(",")
    results = await collect_multiple_tickers(tickers)

    success = sum(1 for r in results if r.get("status") == "stored")
    logger.info(f"Data collection: {success}/{len(tickers)} tickers stored")
    return results


async def _build_dataset_from_snapshots(ticker: str, min_samples: int):
    """Load snapshots from Mongo and build (X, y, feature_names, timestamps).

    Returns a tuple (status_dict, X, y, feature_names, timestamps).
    When the dataset is unusable, status_dict is non-None and the other
    return values are None. Otherwise status_dict is None.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    from ml_price_prediction import extract_features

    load_dotenv()
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    cursor = db.snapshots.find({"ticker": ticker}).sort("ts", 1)
    snapshots = await cursor.to_list(length=10000)
    client.close()

    if len(snapshots) < min_samples:
        return (
            {"status": "insufficient_data", "samples": len(snapshots), "required": min_samples},
            None, None, None, None,
        )

    X: List[List[float]] = []
    y: List[float] = []
    timestamps: List[Any] = []
    for i in range(len(snapshots) - 1):
        features = extract_features(snapshots, i)
        if not features:
            continue
        current_spot = snapshots[i].get("spot", 0)
        next_spot = snapshots[i + 1].get("spot", 0)
        if current_spot <= 0 or next_spot <= 0:
            continue
        y.append(1.0 if next_spot > current_spot else 0.0)
        X.append(list(features.values()))
        timestamps.append(snapshots[i].get("ts"))

    if len(X) < min_samples:
        return (
            {"status": "insufficient_training_data", "samples": len(X), "required": min_samples},
            None, None, None, None,
        )

    feature_names = list(extract_features(snapshots, 0).keys())
    return None, np.array(X), np.array(y), feature_names, timestamps


async def train_one_ticker(ticker: str, min_samples: int = 20) -> Dict[str, Any]:
    """Train one ticker end-to-end with quality gates *before* save.

    Pipeline: load snapshots → build (X, y) → time-split → scale → fit →
    predict → run gates → joblib.dump only on pass. Any DegenerateModelError
    is logged as REFUSED TO SAVE and re-raised.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score

    status, X, y, feature_names, timestamps = await _build_dataset_from_snapshots(
        ticker, min_samples
    )
    if status is not None:
        return status

    # Time-ordered train/test split (we sorted by ts, so this is chronological).
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    train_dates = timestamps[:split_idx]
    test_dates = timestamps[split_idx:]

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = GradientBoostingClassifier(
        n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
    )
    model.fit(X_train_scaled, y_train)
    y_pred = model.predict(X_test_scaled)
    y_pred_proba = model.predict_proba(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred) if len(y_test) else 0.0

    model_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    model_path = os.path.join(model_dir, f"price_model_{ticker}.joblib")
    scaler_path = os.path.join(model_dir, f"price_scaler_{ticker}.joblib")

    # GATES RUN HERE, BEFORE SAVE. _save_with_gates raises DegenerateModelError
    # on failure and the save is refused.
    gate_results = _save_with_gates(
        model=model,
        scaler=scaler,
        model_path=model_path,
        scaler_path=scaler_path,
        X_train=X_train,
        y_train=y_train,
        y_test=y_test,
        y_pred_proba=y_pred_proba,
        feature_names=feature_names,
        feature_dates=train_dates if all(t is not None for t in train_dates) else None,
        target_dates=test_dates if all(t is not None for t in test_dates) else None,
        train_dates=train_dates if all(t is not None for t in train_dates) else None,
        test_dates=test_dates if all(t is not None for t in test_dates) else None,
        ticker=ticker,
    )

    return {
        "status": "trained",
        "ticker": ticker,
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)),
        "accuracy": round(float(accuracy), 4),
        "feature_names": feature_names,
        "model_path": model_path,
        "scaler_path": scaler_path,
        "quality_gates": gate_results,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }


async def train_models():
    """Step 2: Train ML models with pre-save quality gates."""
    from services.ml import DegenerateModelError

    tickers = os.environ.get("ML_TICKERS", "SPY,QQQ").split(",")
    results: Dict[str, Any] = {}

    for ticker in tickers:
        try:
            result = await train_one_ticker(ticker)
            results[ticker] = result
            status = result.get("status", "unknown")
            accuracy = result.get("accuracy", 0)
            logger.info(f"Model training {ticker}: {status}, accuracy={accuracy}")
        except DegenerateModelError as e:
            logger.warning(f"  {ticker}: quality gate FAILED, save refused: {e}")
            results[ticker] = {
                "status": "rejected",
                "rejection_reason": str(e),
                "ticker": ticker,
            }
        except Exception as e:
            logger.error(f"Model training {ticker} failed: {e}")
            results[ticker] = {"status": "error", "message": str(e)}

    return results


async def evaluate_models():
    """Step 3: Evaluate trained models."""
    from ml_price_prediction import predict_price_direction

    tickers = os.environ.get("ML_TICKERS", "SPY,QQQ").split(",")
    results: Dict[str, Any] = {}

    for ticker in tickers:
        try:
            result = await predict_price_direction(ticker)
            results[ticker] = result
            prediction = result.get("prediction", "unknown")
            confidence = result.get("confidence", 0)
            logger.info(f"Prediction {ticker}: {prediction} (confidence={confidence})")
        except Exception as e:
            logger.error(f"Prediction {ticker} failed: {e}")
            results[ticker] = {"status": "error", "message": str(e)}

    return results


async def full_pipeline():
    """Run the full ML pipeline: collect -> train -> evaluate."""
    logger.info("=" * 60)
    logger.info("Starting ML Pipeline")
    logger.info("=" * 60)

    start = datetime.now(timezone.utc)

    logger.info("Step 1: Collecting data...")
    collect_results = await collect_data()

    logger.info("Step 2: Training models...")
    train_results = await train_models()

    logger.info("Step 3: Evaluating models...")
    eval_results = await evaluate_models()

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": elapsed,
        "collection": str(collect_results),
        "training": {t: r.get("status") for t, r in train_results.items()},
        "evaluation": {t: r.get("status") for t, r in eval_results.items()},
    }

    logger.info(f"Pipeline complete in {elapsed:.1f}s")
    logger.info(f"Training results: {json.dumps(train_results, indent=2, default=str)}")
    logger.info(f"Evaluation results: {json.dumps(eval_results, indent=2, default=str)}")

    summary_path = os.path.join(
        "logs", f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    return summary


async def main():
    mode = "full"
    ticker = "SPY"

    # Parse args
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--mode" and i + 1 < len(sys.argv[1:]):
            mode = sys.argv[i + 2]
        elif arg == "--ticker" and i + 1 < len(sys.argv[1:]):
            ticker = sys.argv[i + 2]

    if mode == "collect":
        await collect_data()
    elif mode == "train":
        await train_models()
    elif mode == "predict":
        from ml_price_prediction import predict_price_direction
        result = await predict_price_direction(ticker)
        logger.info(json.dumps(result, indent=2))
    elif mode == "evaluate":
        await evaluate_models()
    elif mode == "full":
        await full_pipeline()
    else:
        logger.info(f"Unknown mode: {mode}")
        logger.info("Available modes: collect, train, predict, evaluate, full")


if __name__ == "__main__":
    asyncio.run(main())