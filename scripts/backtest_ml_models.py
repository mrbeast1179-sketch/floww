#!/usr/bin/env python3
"""
scripts/backtest_ml_models.py

Walk-forward backtest for trained ML models.
Tests anomaly detection on historical data with injected synthetic toxic-flow events.

Usage:
    cd /Users/nav/Documents/GitHub/floww
    .venv/bin/python scripts/backtest_ml_models.py [--n-inject 50] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = REPO_ROOT / "reports"

sys.path.insert(0, str(REPO_ROOT / "backend"))


def generate_backtest_data(n_normal: int = 5000, n_anomaly: int = 50, seed: int = 42):
    """Generate backtest data with injected anomalies."""
    rng = np.random.RandomState(seed)

    # Normal VPIN + QI
    vpin = np.zeros(n_normal, dtype=np.float32)
    vpin[0] = 0.45
    for t in range(1, n_normal):
        vpin[t] = np.clip(vpin[t - 1] + 0.05 * (0.45 - vpin[t - 1]) + rng.normal(0, 0.02), 0.05, 0.99)

    qi = np.zeros(n_normal, dtype=np.float32)
    for t in range(1, n_normal):
        qi[t] = np.clip(qi[t - 1] + 0.1 * (0.0 - qi[t - 1]) + rng.normal(0, 0.05), -1.0, 1.0)

    normal_data = np.stack([vpin, qi], axis=1)

    # Inject anomalies at random positions
    anomaly_indices = sorted(rng.choice(n_normal, size=n_anomaly, replace=False))
    labels = np.zeros(n_normal, dtype=int)
    for idx in anomaly_indices:
        # Toxic flow: high VPIN + extreme QI
        normal_data[idx, 0] = rng.uniform(0.80, 0.99)  # VPIN spike
        normal_data[idx, 1] = rng.choice([-1, 1]) * rng.uniform(0.6, 0.95)  # QI extreme
        labels[idx] = 1

    return normal_data, labels, anomaly_indices


def run_backtest(data: np.ndarray, labels: np.ndarray, seq_len: int = 50) -> dict:
    """Run walk-forward backtest."""
    from services.anomaly_detector import FlowAnomalyDetector

    detector = FlowAnomalyDetector(seq_len=seq_len, latent_dim=8)
    predictions = []
    scores = []

    for i in range(len(data)):
        result = detector.update(float(data[i, 0]), float(data[i, 1]))
        predictions.append(1 if result.get("is_anomaly", False) else 0)
        scores.append(result.get("anomaly_score", 0.0))

    predictions = np.array(predictions)
    scores = np.array(scores)

    # Metrics (only on data after warmup)
    warmup = seq_len + 20
    tp = int(np.sum((predictions[warmup:] == 1) & (labels[warmup:] == 1)))
    fn = int(np.sum((predictions[warmup:] == 0) & (labels[warmup:] == 1)))
    fp = int(np.sum((predictions[warmup:] == 1) & (labels[warmup:] == 0)))
    tn = int(np.sum((predictions[warmup:] == 0) & (labels[warmup:] == 0)))

    recall = tp / max(tp + fn, 1)
    precision = tp / max(tp + fp, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    fpr = fp / max(fp + tn, 1)

    return {
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "recall": round(recall, 4),
        "precision": round(precision, 4),
        "f1_score": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "n_total": len(data) - warmup,
        "n_anomalies": int(np.sum(labels[warmup:])),
    }


def main():
    parser = argparse.ArgumentParser(description="Backtest ML anomaly models")
    parser.add_argument("--n-normal", type=int, default=5000)
    parser.add_argument("--n-inject", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seq-len", type=int, default=50)
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("ML Model Backtest")
    log.info("=" * 60)

    data, labels, anomaly_indices = generate_backtest_data(
        n_normal=args.n_normal, n_anomaly=args.n_inject, seed=args.seed
    )
    log.info(f"Data: {len(data)} samples, {len(anomaly_indices)} injected anomalies")

    results = run_backtest(data, labels, seq_len=args.seq_len)

    log.info(f"\nResults:")
    log.info(f"  TP={results['true_positives']} FN={results['false_negatives']} "
             f"FP={results['false_positives']} TN={results['true_negatives']}")
    log.info(f"  Recall:    {results['recall']:.4f}")
    log.info(f"  Precision: {results['precision']:.4f}")
    log.info(f"  F1:        {results['f1_score']:.4f}")
    log.info(f"  FPR:       {results['false_positive_rate']:.4f}")

    # Save report
    report = {
        "results": results,
        "config": {
            "n_normal": args.n_normal,
            "n_inject": args.n_inject,
            "seed": args.seed,
            "seq_len": args.seq_len,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    report_path = REPORTS_DIR / f"backtest_ml_{datetime.now().strftime('%Y%m%d')}.json"
    report_path.write_text(json.dumps(report, indent=2))
    log.info(f"\nReport saved to {report_path}")

    if results["f1_score"] > 0.6:
        log.info("✓ F1 > 0.6 threshold met")
    else:
        log.warning("✗ F1 < 0.6 — model needs more training")


if __name__ == "__main__":
    main()
