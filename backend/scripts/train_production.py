#!/usr/bin/env python3
"""
Production ML Training Script — SPY/QQQ/DIA/IWM direction prediction.

Trains GradientBoosting classifiers on 2 years of real yfinance data with:
- Walk-forward validation (8 folds, 126 train / 21 test per fold)
- Trading Sharpe computation from walk-forward predictions
- Quality gates: class balance, no overfit, walk-forward consistency
- Artifact saving: model.joblib, scaler.joblib, manifest.json
- Model registration in MongoDB ml_models collection

Usage:
    cd backend && ./venv/bin/python scripts/train_production.py --tickers SPY QQQ DIA IWM
    cd backend && ./venv/bin/python scripts/train_production.py --tickers SPY --walk-forward-only
"""

import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("train_production")

from train_real_ml import compute_features, FEATURE_NAMES
from train_with_baselines import compute_trading_sharpe

MODEL_DIR = Path(__file__).resolve().parents[1] / "models"
MODEL_DIR.mkdir(exist_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Train production ML models")
    parser.add_argument("--tickers", nargs="+", default=["SPY", "QQQ", "DIA", "IWM"])
    parser.add_argument("--period", default="2y", help="Data period for yfinance")
    args = parser.parse_args()

    results = {}
    for ticker in args.tickers:
        try:
            result = train_production_model(ticker, period=args.period)
            results[ticker] = result
        except Exception as e:
            log.error(f"[{ticker}] Training failed: {e}")
            results[ticker] = {"error": str(e)}

    # Summary
    log.info("\n" + "=" * 60)
    log.info("TRAINING SUMMARY")
    log.info("=" * 60)
    for ticker, result in results.items():
        if "error" in result:
            log.info(f"  {ticker}: FAILED — {result['error']}")
        else:
            log.info(
                f"  {ticker}: {result['verdict']} — "
                f"acc={result['metrics']['overall_accuracy']:.4f} "
                f"wf={result['metrics']['avg_fold_accuracy']:.4f}±{result['metrics']['std_fold_accuracy']:.4f} "
                f"sharpe={result['metrics']['overall_sharpe']:.4f}"
            )

    return results


if __name__ == "__main__":
    main()
