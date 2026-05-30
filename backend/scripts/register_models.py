#!/usr/bin/env python3
"""
Register trained production models in MongoDB ml_models collection.

Reads manifest JSON files from models/ directory and registers each model
via the ModelRegistry. Promotes SHIP-verdict models to active status.

Usage:
    cd backend && ./venv/bin/python scripts/register_models.py
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("register_models")

from services.ml.registry import ModelRegistry

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")


async def register_all():
    """Load manifests and register all production models."""
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    registry = ModelRegistry(db)

    tickers = ["SPY", "QQQ", "DIA", "IWM"]
    results = {}

    for ticker in tickers:
        manifest_path = MODEL_DIR / f"{ticker}_gbm_production_manifest.json"
        if not manifest_path.exists():
            log.warning(f"[{ticker}] Manifest not found: {manifest_path}")
            continue

        with open(manifest_path) as f:
            manifest = json.load(f)

        model_id = manifest.get("model_id", f"{ticker}_direction_v1.0_gbm")
        model_path = Path(manifest["model_path"])
        _scaler_path = Path(manifest["scaler_path"])
        verdict = manifest.get("verdict", "HOLD")
        metrics = manifest.get("metrics", {})
        gate_results = manifest.get("gate_results", {})

        log.info(f"[{ticker}] Registering {model_id} (verdict={verdict})")
        log.info(f"[{ticker}]   WF acc={metrics.get('avg_fold_accuracy', 0):.4f}, sharpe={metrics.get('overall_sharpe', 0):.4f}")

        # Build metrics_summary for registry
        metrics_summary = {
            "avg_fold_accuracy": metrics.get("avg_fold_accuracy", 0),
            "std_fold_accuracy": metrics.get("std_fold_accuracy", 0),
            "overall_sharpe": metrics.get("overall_sharpe", 0),
            "overfit_gap": metrics.get("overfit_gap", 1.0),
            "verdict": verdict,
            "gates": gate_results,
        }

        status = "active" if verdict == "SHIP" else "shadow"

        doc = await registry.register_model(
            model_id=model_id,
            ticker=ticker,
            feature_version=manifest.get("feature_version", "v2.0"),
            training_window="2y_walkforward_8folds",
            metrics_summary=metrics_summary,
            artifact_path=str(model_path),
            status=status,
        )

        results[ticker] = {
            "model_id": model_id,
            "status": status,
            "verdict": verdict,
            "doc_id": str(doc.get("_id", "?")),
        }

        log.info(f"[{ticker}] Registered as {status} (doc_id={results[ticker]['doc_id']})")

        # If SHIP, also promote
        if verdict == "SHIP":
            try:
                promo = await registry.promote_model(model_id)
                log.info(f"[{ticker}] Promote result: {promo}")
                results[ticker]["promoted"] = promo.get("success", False)
            except Exception as e:
                log.warning(f"[{ticker}] Promote skipped: {e}")
                results[ticker]["promoted"] = False

    log.info("\n" + "=" * 60)
    log.info("REGISTRATION SUMMARY")
    log.info("=" * 60)
    for ticker, r in results.items():
        log.info(f"  {ticker}: {r['status']} (verdict={r['verdict']}, promoted={r.get('promoted', 'N/A')})")

    return results


if __name__ == "__main__":
    asyncio.run(register_all())
