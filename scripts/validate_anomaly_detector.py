#!/usr/bin/env python3
"""
scripts/validate_anomaly_detector.py

Inject-anomaly validation for the 1D-CNN Autoencoder.
Generates "toxic flow" scenarios and verifies the trained model detects them.

Toxic flow scenarios:
  - VPIN spike to 0.9+ (extreme toxicity)
  - QI z-score > 3 (severe quote imbalance)
  - Sustained 10+ ticks of elevated VPIN

Reports:
  - Recall on injected anomalies (target >95%)
  - False positive rate on held-out normal data
  - Confusion matrix

Usage:
    cd /Users/nav/Documents/GitHub/floww
    .venv/bin/python scripts/validate_anomaly_detector.py [--model-path ...] [--n-normal 2000] [--n-anomaly 500]
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
BACKEND = REPO_ROOT / "backend"
MODELS_DIR = REPO_ROOT / "project_oracle" / "models"
QC_DIR = REPO_ROOT / "project_oracle" / "qc"

sys.path.insert(0, str(BACKEND))


def generate_normal_data(n_samples: int, seq_len: int, seed: int = 100) -> np.ndarray:
    """Generate normal market data (low toxicity)."""
    rng = np.random.RandomState(seed)
    data = np.zeros((n_samples, 2), dtype=np.float32)

    # VPIN: normal range 0.3-0.6
    vpin = np.zeros(n_samples)
    vpin[0] = 0.45
    for t in range(1, n_samples):
        vpin[t] = np.clip(vpin[t - 1] + 0.05 * (0.45 - vpin[t - 1]) + rng.normal(0, 0.02), 0.2, 0.7)

    # QI: normal range -0.3 to 0.3
    qi = np.zeros(n_samples)
    for t in range(1, n_samples):
        qi[t] = np.clip(qi[t - 1] + 0.1 * (0.0 - qi[t - 1]) + rng.normal(0, 0.05), -0.5, 0.5)

    data[:, 0] = vpin
    data[:, 1] = qi
    return data


def generate_toxic_data(n_samples: int, seq_len: int, seed: int = 200) -> np.ndarray:
    """Generate toxic flow data with injected anomalies."""
    rng = np.random.RandomState(seed)
    data = np.zeros((n_samples, 2), dtype=np.float32)

    # VPIN: spike to 0.8-0.95 (extreme toxicity)
    vpin = np.zeros(n_samples)
    vpin[0] = 0.45
    for t in range(1, n_samples):
        # Mean-revert to high toxicity (0.85) instead of normal (0.45)
        target = rng.choice([0.45, 0.85], p=[0.2, 0.8])  # 80% toxic
        vpin[t] = np.clip(vpin[t - 1] + 0.15 * (target - vpin[t - 1]) + rng.normal(0, 0.04), 0.3, 0.99)

    # QI: extreme imbalance, z-score > 3
    qi = np.zeros(n_samples)
    for t in range(1, n_samples):
        target = rng.choice([0.0, rng.uniform(0.6, 0.9)], p=[0.3, 0.7])
        qi[t] = np.clip(qi[t - 1] + 0.2 * (target - qi[t - 1]) + rng.normal(0, 0.08), -1.0, 1.0)

    data[:, 0] = vpin
    data[:, 1] = qi
    return data


def create_sequences(data: np.ndarray, seq_len: int) -> np.ndarray:
    """Create sliding window sequences."""
    n = len(data) - seq_len + 1
    sequences = np.zeros((n, seq_len, data.shape[1]), dtype=np.float32)
    for i in range(n):
        sequences[i] = data[i:i + seq_len]
    return sequences


def validate_model(model_path: str, seq_len: int = 50, device: str = "cpu",
                   n_normal: int = 2000, n_anomaly: int = 500) -> dict:
    """Run inject-anomaly validation.

    Returns dict with recall, FPR, confusion matrix, and per-scenario results.
    """
    import torch
    import torch.nn.functional as F

    # Load model
    from services.anomaly_detector import Conv1DAutoencoder

    checkpoint = torch.load(model_path, map_location=device)
    config = checkpoint["config"]
    threshold_info = checkpoint["threshold"]
    threshold = threshold_info["threshold"]

    model = Conv1DAutoencoder(
        input_channels=config["input_channels"],
        seq_len=config["seq_len"],
        latent_dim=config["latent_dim"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    log.info(f"Loaded model from {model_path}")
    log.info(f"Threshold: {threshold:.8f}")

    # Generate data
    normal_data = generate_normal_data(n_normal, seq_len)
    toxic_data = generate_toxic_data(n_anomaly, seq_len)

    normal_seq = create_sequences(normal_data, seq_len)
    toxic_seq = create_sequences(toxic_data, seq_len)

    log.info(f"Normal sequences: {len(normal_seq)}, Toxic sequences: {len(toxic_seq)}")

    # Compute reconstruction errors
    def compute_errors(sequences):
        errors = []
        x = torch.tensor(sequences, dtype=torch.float32).permute(0, 2, 1).to(device)
        with torch.no_grad():
            for i in range(0, len(x), 256):
                batch = x[i:i + 256]
                recon, _ = model(batch)
                batch_errors = torch.mean((batch - recon) ** 2, dim=(1, 2)).cpu().numpy()
                errors.extend(batch_errors.tolist())
        return np.array(errors)

    log.info("Computing reconstruction errors on normal data...")
    normal_errors = compute_errors(normal_seq)
    log.info("Computing reconstruction errors on toxic data...")
    toxic_errors = compute_errors(toxic_seq)

    # Classify
    normal_predictions = (normal_errors > threshold).astype(int)
    toxic_predictions = (toxic_errors > threshold).astype(int)

    # Metrics
    tp = int(np.sum(toxic_predictions == 1))
    fn = int(np.sum(toxic_predictions == 0))
    fp = int(np.sum(normal_predictions == 1))
    tn = int(np.sum(normal_predictions == 0))

    recall = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    precision = tp / max(tp + fp, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)

    results = {
        "model_path": model_path,
        "threshold": threshold,
        "n_normal": len(normal_errors),
        "n_toxic": len(toxic_errors),
        "true_positives": tp,
        "false_negatives": fn,
        "false_positives": fp,
        "true_negatives": tn,
        "recall": round(recall, 4),
        "false_positive_rate": round(fpr, 4),
        "precision": round(precision, 4),
        "f1_score": round(f1, 4),
        "normal_error_mean": round(float(np.mean(normal_errors)), 8),
        "normal_error_std": round(float(np.std(normal_errors)), 8),
        "toxic_error_mean": round(float(np.mean(toxic_errors)), 8),
        "toxic_error_std": round(float(np.std(toxic_errors)), 8),
        "recall_target_met": recall >= 0.95,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    return results


def print_confusion_matrix(results: dict):
    """Print a formatted confusion matrix."""
    tp = results["true_positives"]
    fn = results["false_negatives"]
    fp = results["false_positives"]
    tn = results["true_negatives"]

    print("\n" + "=" * 50)
    print("CONFUSION MATRIX")
    print("=" * 50)
    print(f"                    Predicted")
    print(f"                 Normal  |  Anomaly")
    print(f"  Actual Normal   {tn:5d}   |  {fp:5d}   (FPR={results['false_positive_rate']:.4f})")
    print(f"  Actual Anomaly  {fn:5d}   |  {tp:5d}   (Recall={results['recall']:.4f})")
    print("=" * 50)
    print(f"  Precision: {results['precision']:.4f}")
    print(f"  F1 Score:  {results['f1_score']:.4f}")
    print(f"  Recall target (≥95%): {'✓ MET' if results['recall_target_met'] else '✗ NOT MET'}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Validate anomaly detector with injected anomalies")
    parser.add_argument("--model-path", type=str, default=str(MODELS_DIR / "anomaly_detector_v1.pt"))
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--n-normal", type=int, default=2000)
    parser.add_argument("--n-anomaly", type=int, default=500)
    args = parser.parse_args()

    QC_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info("Inject-Anomaly Validation")
    log.info("=" * 60)

    results = validate_model(
        model_path=args.model_path,
        seq_len=args.seq_len,
        device=args.device,
        n_normal=args.n_normal,
        n_anomaly=args.n_anomaly,
    )

    # Print results
    print_confusion_matrix(results)

    log.info(f"\nNormal data — mean error: {results['normal_error_mean']:.8f}, std: {results['normal_error_std']:.8f}")
    log.info(f"Toxic data  — mean error: {results['toxic_error_mean']:.8f}, std: {results['toxic_error_std']:.8f}")
    log.info(f"Recall: {results['recall']:.4f} (target ≥0.95)")
    log.info(f"FPR:    {results['false_positive_rate']:.4f}")

    # Save results
    results_path = QC_DIR / "anomaly_validation_v1.json"
    results_path.write_text(json.dumps(results, indent=2))
    log.info(f"\nResults saved to {results_path}")

    if not results["recall_target_met"]:
        log.warning("WARNING: Recall target (≥95%) NOT MET — consider retraining with more epochs")
        sys.exit(1)
    else:
        log.info("✓ All validation targets met")


if __name__ == "__main__":
    main()
