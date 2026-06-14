"""
backend/scripts/register_model.py

Register a saved model artifact in the MongoDB ml_models collection.

Usage:
    python scripts/register_model.py --ticker SPY --model-file models/SPY_rf_20260524_020801.joblib
    python scripts/register_model.py --ticker SPY --model-file models/SPY_rf_20260524_020801.joblib --promote
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pymongo
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("register_model")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
COLLECTION_MODELS = "ml_models"


def register_model(model_path: str, ticker: str, promote: bool = False):
    """Register a model artifact in MongoDB."""
    path = Path(model_path)
    if not path.is_absolute():
        path = BACKEND_DIR / path

    if not path.exists():
        log.error(f"Model file not found: {path}")
        sys.exit(1)

    artifact = joblib.load(path)
    _model = artifact["model"]
    feature_names = artifact.get("feature_names", [])
    metrics = artifact.get("metrics", {})

    doc = {
        "ticker": ticker,
        "model_name": metrics.get("model_name", path.stem),
        "model_file": str(path),
        "feature_names": feature_names,
        "n_features": len(feature_names),
        "status": "active" if promote else "shadow",
        "registered_at": datetime.now(UTC).isoformat(),
        "trained_at": artifact.get("trained_at", ""),
        "metrics": {
            "avg_test_sharpe": metrics.get("avg_test_sharpe", 0),
            "avg_test_accuracy": metrics.get("avg_test_accuracy", 0),
            "folds_ship": metrics.get("folds_ship", 0),
            "folds_reject": metrics.get("folds_reject", 0),
            "n_folds": metrics.get("n_folds", 0),
        },
    }

    client = pymongo.MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Deactivate other models for this ticker if promoting
    if promote:
        result = db[COLLECTION_MODELS].update_many(
            {"ticker": ticker, "status": "active"},
            {"$set": {"status": "retired", "retired_at": datetime.now(UTC).isoformat()}},
        )
        log.info(f"Retired {result.modified_count} existing active models for {ticker}")

    # Upsert by model_file path
    result = db[COLLECTION_MODELS].update_one(
        {"model_file": str(path)},
        {"$set": doc},
        upsert=True,
    )

    client.close()

    if result.upserted_id:
        log.info(f"Registered model: {doc['model_name']} (status={doc['status']})")
    else:
        log.info(f"Updated model: {doc['model_name']} (status={doc['status']})")

    logger.info(json.dumps(doc, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--model-file", required=True)
    parser.add_argument("--promote", action="store_true", help="Promote to active, retire others")
    args = parser.parse_args()
    register_model(args.model_file, args.ticker, args.promote)
