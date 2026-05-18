#!/usr/bin/env python3
"""
ML Training Pipeline Runner.

Can be run as:
- A cron job: python ml_pipeline.py --mode train
- A one-shot: python ml_pipeline.py --mode predict --ticker SPY
- A full pipeline: python ml_pipeline.py --mode full
"""

import asyncio
import sys
import os
import json
import logging
from datetime import datetime, timezone

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


async def collect_data():
    """Step 1: Collect fresh data."""
    from data_collector import collect_multiple_tickers
    
    tickers = os.environ.get("COLLECT_TICKERS", "SPY,QQQ,IWM,DIA,AAPL,TSLA,NVDA,MSFT").split(",")
    results = await collect_multiple_tickers(tickers)
    
    success = sum(1 for r in results if r.get("status") == "stored")
    logger.info(f"Data collection: {success}/{len(tickers)} tickers stored")
    return results


async def train_models():
    """Step 2: Train ML models with quality gates."""
    from ml_price_prediction import train_price_direction_model
    from services.ml.quality import run_all_gates, DegenerateModelError

    tickers = os.environ.get("ML_TICKERS", "SPY,QQQ").split(",")
    results = {}

    for ticker in tickers:
        try:
            result = await train_price_direction_model(ticker)

            # Quality gate: validate training data and predictions
            if result.get("status") == "ok" and result.get("X_train") is not None:
                try:
                    gate_results = run_all_gates(
                        X=result["X_train"],
                        y=result["y_train"],
                        y_pred_proba=result.get("y_train_proba", result["y_train"]),
                    )
                    result["quality_gates"] = gate_results
                    logger.info(f"  {ticker}: quality gates passed: {len(gate_results)}")
                except DegenerateModelError as e:
                    logger.warning(f"  {ticker}: quality gate FAILED: {e}")
                    result["status"] = "rejected"
                    result["rejection_reason"] = str(e)

            results[ticker] = result
            status = result.get("status", "unknown")
            accuracy = result.get("accuracy", 0)
            logger.info(f"Model training {ticker}: {status}, accuracy={accuracy}")
        except Exception as e:
            logger.error(f"Model training {ticker} failed: {e}")
            results[ticker] = {"status": "error", "message": str(e)}

    return results


async def evaluate_models():
    """Step 3: Evaluate trained models."""
    from ml_price_prediction import predict_price_direction
    
    tickers = os.environ.get("ML_TICKERS", "SPY,QQQ").split(",")
    results = {}
    
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
    """Run the full ML pipeline: collect → train → evaluate."""
    logger.info("=" * 60)
    logger.info("Starting ML Pipeline")
    logger.info("=" * 60)
    
    start = datetime.now(timezone.utc)
    
    # Step 1: Collect data
    logger.info("Step 1: Collecting data...")
    collect_results = await collect_data()
    
    # Step 2: Train models
    logger.info("Step 2: Training models...")
    train_results = await train_models()
    
    # Step 3: Evaluate
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
    
    # Save summary
    summary_path = os.path.join("logs", f"pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
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
        print(json.dumps(result, indent=2))
    elif mode == "evaluate":
        await evaluate_models()
    elif mode == "full":
        await full_pipeline()
    else:
        print(f"Unknown mode: {mode}")
        print("Available modes: collect, train, predict, evaluate, full")


if __name__ == "__main__":
    asyncio.run(main())