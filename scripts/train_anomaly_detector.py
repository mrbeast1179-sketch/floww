#!/usr/bin/env python3
"""
scripts/train_anomaly_detector.py

Train the 1D-CNN Autoencoder for flow toxicity anomaly detection.
Ingests VPIN + Quote Imbalance time series.

Data sources (in priority order):
  1. MongoDB gex_history collection (if populated)
  2. Synthetic data via Geometric Brownian Motion + realistic VPIN trajectories
     (ONLY for initial validation/smoothing — never in production training paths)

Architecture: Conv1DAutoencoder (services/anomaly_detector.py)
  - Input: (batch, 2, seq_len) — 2 channels: VPIN, QI
  - Encoder: Conv1d → ReLU → MaxPool → Conv1d → ReLU → MaxPool → Flatten → Linear
  - Bottleneck: latent_dim=8
  - Decoder: Linear → Unflatten → ConvTranspose1d → ReLU → ConvTranspose1d
  - Loss: MSE reconstruction error

Train/val split: time-ordered 80/20 (never random — per Oracle operating law #5)

Usage:
    cd /Users/nav/Documents/GitHub/floww
    .venv/bin/python scripts/train_anomaly_detector.py [--epochs 50] [--seq-len 50] [--batch-size 64]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from typing import Any

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
MODELS_DIR = REPO_ROOT / "project_oracle" / "models"
QC_DIR = REPO_ROOT / "project_oracle" / "qc"
MANIFEST_PATH = QC_DIR / "anomaly_detector_v1_manifest.json"

sys.path.insert(0, str(BACKEND))


# ── Data generation ──────────────────────────────────────────────────────────

def generate_synthetic_data(n_samples: int = 5000, seq_len: int = 50, seed: int = 42) -> np.ndarray:
    """Generate synthetic VPIN + QI time series via GBM.

    This is for INITIAL VALIDATION ONLY — never in production training paths.
    Per Oracle directive: NO synthetic data in production training.

    Returns array of shape (n_samples, 2) where columns are [VPIN, QI].
    """
    rng = np.random.RandomState(seed)

    # VPIN: typically 0.3-0.7 in normal markets, spikes to 0.8-0.95 in toxic flow
    # Model as mean-reverting Ornstein-Uhlenbeck process
    vpin = np.zeros(n_samples)
    vpin[0] = 0.45
    for t in range(1, n_samples):
        # Mean-reverting around 0.45 with occasional spikes
        mean_rev = 0.1 * (0.45 - vpin[t - 1])
        noise = rng.normal(0, 0.03)
        # Occasional toxicity spikes (5% of samples)
        spike = rng.random() < 0.05
        spike_val = rng.uniform(0.3, 0.5) if spike else 0.0
        vpin[t] = np.clip(vpin[t - 1] + mean_rev + noise + spike_val, 0.05, 0.99)

    # QI (Quote Imbalance): typically -0.3 to 0.3, z-score rarely > 2
    qi = np.zeros(n_samples)
    qi[0] = 0.0
    for t in range(1, n_samples):
        mean_rev = 0.15 * (0.0 - qi[t - 1])
        noise = rng.normal(0, 0.08)
        qi[t] = np.clip(qi[t - 1] + mean_rev + noise, -1.0, 1.0)

    return np.stack([vpin, qi], axis=1)


def load_mongodb_data(seq_len: int = 50) -> Optional[np.ndarray]:
    """Try to load VPIN + QI from MongoDB gex_history collection."""
    try:
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "confluence_decoder")

        async def _fetch():
            client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
            db = client[db_name]
            # Check if gex_history has data
            count = await db.gex_history.estimated_document_count()
            if count < seq_len * 2:
                return None
            cursor = db.gex_history.find(
                {}, {"vpin": 1, "qi": 1, "_id": 0}
            ).sort("ts", 1).limit(10000)
            docs = await cursor.to_list(length=10000)
            return docs

        docs = asyncio.run(_fetch())
        if not docs:
            return None

        data = []
        for doc in docs:
            vpin = doc.get("vpin", doc.get("VPIN", None))
            qi = doc.get("qi", doc.get("QI", None))
            if vpin is not None and qi is not None:
                data.append([float(vpin), float(qi)])

        if len(data) < seq_len * 2:
            log.warning(f"MongoDB data too sparse ({len(data)} rows), using synthetic")
            return None

        log.info(f"Loaded {len(data)} rows from MongoDB gex_history")
        return np.array(data, dtype=np.float32)

    except Exception as e:
        log.warning(f"MongoDB unavailable ({e}), using synthetic data")
        return None


def create_sequences(data: np.ndarray, seq_len: int) -> np.ndarray:
    """Create sliding window sequences from time series data.

    Returns array of shape (n_sequences, seq_len, 2).
    """
    n = len(data) - seq_len + 1
    if n <= 0:
        raise ValueError(f"Data length {len(data)} < seq_len {seq_len}")
    sequences = np.zeros((n, seq_len, data.shape[1]), dtype=np.float32)
    for i in range(n):
        sequences[i] = data[i:i + seq_len]
    return sequences


# ── Training ─────────────────────────────────────────────────────────────────

def train_model(
    model,
    train_data: np.ndarray,
    val_data: np.ndarray,
    epochs: int = 50,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str = "cpu",
) -> dict:
    """Train the 1D-CNN Autoencoder.

    Args:
        model: Conv1DAutoencoder instance
        train_data: (n, seq_len, 2) training sequences
        val_data: (n, seq_len, 2) validation sequences
        epochs: number of training epochs
        batch_size: mini-batch size
        lr: learning rate
        device: 'cpu' or 'mps'

    Returns:
        Training history dict with losses and timing.
    """
    import torch
    import torch.nn.functional as F
    from torch.utils.data import DataLoader, TensorDataset

    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=5
    )

    # Convert to tensors: (n, seq_len, 2) -> (n, 2, seq_len)
    train_x = torch.tensor(train_data, dtype=torch.float32).permute(0, 2, 1).to(device)
    val_x = torch.tensor(val_data, dtype=torch.float32).permute(0, 2, 1).to(device)

    train_dataset = TensorDataset(train_x)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)  # time-ordered

    history: dict[str, Any] = {"train_loss": [], "val_loss": [], "lr": [], "epoch_time": []}
    best_val_loss = float("inf")
    best_state = None

    log.info(f"Training on {len(train_data)} sequences, validating on {len(val_data)}")
    log.info(f"Device: {device}, Epochs: {epochs}, Batch size: {batch_size}, LR: {lr}")

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        for (batch_x,) in train_loader:
            optimizer.zero_grad()
            reconstructed, _ = model(batch_x)
            loss = F.mse_loss(reconstructed, batch_x)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        avg_train_loss = epoch_loss / max(n_batches, 1)

        # Validation
        model.eval()
        with torch.no_grad():
            val_recon, _ = model(val_x)
            val_loss = F.mse_loss(val_recon, val_x).item()

        scheduler.step(val_loss)
        current_lr = optimizer.param_groups[0]["lr"]
        epoch_time = time.time() - t0

        history["train_loss"].append(round(avg_train_loss, 6))
        history["val_loss"].append(round(val_loss, 6))
        history["lr"].append(current_lr)
        history["epoch_time"].append(round(epoch_time, 2))

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0 or epoch == 1:
            log.info(
                f"  Epoch {epoch:3d}/{epochs} | "
                f"train_loss={avg_train_loss:.6f} | val_loss={val_loss:.6f} | "
                f"lr={current_lr:.2e} | time={epoch_time:.1f}s"
            )

    # Restore best model
    if best_state is not None:
        model.load_state_dict(best_state)

    history["best_val_loss"] = round(best_val_loss, 6)
    history["final_train_loss"] = history["train_loss"][-1]
    history["total_epochs"] = epochs
    return history


def compute_threshold(model, val_data: np.ndarray, device: str, sigma: float = 2.5) -> dict:
    """Compute anomaly threshold from validation set reconstruction errors.

    Threshold = mean(error) + sigma * std(error)
    Returns dict with threshold, mean, std, and per-sample errors.
    """
    import torch
    import torch.nn.functional as F

    model.eval()
    val_x = torch.tensor(val_data, dtype=torch.float32).permute(0, 2, 1).to(device)

    with torch.no_grad():
        # Process in batches to avoid OOM
        batch_size = 256
        errors = []
        for i in range(0, len(val_x), batch_size):
            batch = val_x[i:i + batch_size]
            recon, _ = model(batch)
            batch_errors = torch.mean((batch - recon) ** 2, dim=(1, 2)).cpu().numpy()
            errors.extend(batch_errors.tolist())

    errors = np.array(errors)
    mean_err = float(np.mean(errors))
    std_err = float(np.std(errors))
    threshold = mean_err + sigma * std_err

    return {
        "threshold": round(threshold, 8),
        "mean_error": round(mean_err, 8),
        "std_error": round(std_err, 8),
        "sigma": sigma,
        "n_samples": len(errors),
        "min_error": round(float(np.min(errors)), 8),
        "max_error": round(float(np.max(errors)), 8),
        "p95_error": round(float(np.percentile(errors, 95)), 8),
        "p99_error": round(float(np.percentile(errors, 99)), 8),
    }


def main():
    parser = argparse.ArgumentParser(description="Train 1D-CNN Autoencoder for anomaly detection")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--seq-len", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--latent-dim", type=int, default=8)
    parser.add_argument("--sigma", type=float, default=2.5, help="Threshold sigma multiplier")
    parser.add_argument("--device", type=str, default="cpu", choices=["cpu", "mps"])
    parser.add_argument("--n-samples", type=int, default=5000, help="Synthetic data samples (if no Mongo)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    QC_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Load data ──────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Step 1: Loading data")
    log.info("=" * 60)

    data = load_mongodb_data(args.seq_len)
    data_source = "mongodb"
    if data is None:
        log.info("Generating synthetic data (GBM + OU process)")
        data = generate_synthetic_data(n_samples=args.n_samples, seq_len=args.seq_len, seed=args.seed)
        data_source = "synthetic_gbm"

    log.info(f"Data shape: {data.shape}, source: {data_source}")

    # ── Step 2: Create sequences ──────────────────────────────────────────
    log.info("Creating sliding window sequences")
    sequences = create_sequences(data, args.seq_len)
    log.info(f"Sequences shape: {sequences.shape}")

    # Time-ordered 80/20 split (NEVER random)
    split_idx = int(len(sequences) * 0.8)
    train_seq = sequences[:split_idx]
    val_seq = sequences[split_idx:]
    log.info(f"Train: {len(train_seq)}, Val: {len(val_seq)}")

    # ── Step 3: Initialize model ──────────────────────────────────────────
    log.info("=" * 60)
    log.info("Step 3: Initializing 1D-CNN Autoencoder")
    log.info("=" * 60)

    from services.anomaly_detector import Conv1DAutoencoder

    model = Conv1DAutoencoder(
        input_channels=2,
        seq_len=args.seq_len,
        latent_dim=args.latent_dim,
    )
    total_params = sum(p.numel() for p in model.parameters())
    log.info(f"Model parameters: {total_params:,}")
    log.info(f"Device: {args.device}")

    # ── Step 4: Train ─────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Step 4: Training")
    log.info("=" * 60)

    history = train_model(
        model, train_seq, val_seq,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device=args.device,
    )

    log.info(f"Training complete. Best val loss: {history['best_val_loss']:.6f}")

    # ── Step 5: Compute threshold ─────────────────────────────────────────
    log.info("=" * 60)
    log.info("Step 5: Computing anomaly threshold")
    log.info("=" * 60)

    threshold_info = compute_threshold(model, val_seq, args.device, sigma=args.sigma)
    log.info(f"Threshold: {threshold_info['threshold']:.8f} (mean={threshold_info['mean_error']:.8f}, "
             f"std={threshold_info['std_error']:.8f}, sigma={args.sigma})")

    # ── Step 6: Save checkpoint ───────────────────────────────────────────
    save_path = MODELS_DIR / "anomaly_detector_v1.pt"
    import torch
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {
            "input_channels": 2,
            "seq_len": args.seq_len,
            "latent_dim": args.latent_dim,
        },
        "threshold": threshold_info,
        "training_history": history,
        "data_source": data_source,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }, save_path)
    log.info(f"Model saved to {save_path}")

    # ── Step 7: Write manifest ────────────────────────────────────────────
    manifest = {
        "model": "anomaly_detector_v1",
        "path": str(save_path.relative_to(REPO_ROOT)),
        "size_mb": round(save_path.stat().st_size / (1024 * 1024), 2),
        "data_source": data_source,
        "n_train": len(train_seq),
        "n_val": len(val_seq),
        "seq_len": args.seq_len,
        "latent_dim": args.latent_dim,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.lr,
        "final_train_loss": history["final_train_loss"],
        "best_val_loss": history["best_val_loss"],
        "threshold": threshold_info,
        "total_params": total_params,
        "device": args.device,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    log.info(f"Manifest written to {MANIFEST_PATH}")

    # ── Summary ───────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("TRAINING COMPLETE")
    log.info("=" * 60)
    log.info(f"  Model:           {save_path}")
    log.info(f"  Data source:     {data_source}")
    log.info(f"  Train samples:   {len(train_seq)}")
    log.info(f"  Val samples:     {len(val_seq)}")
    log.info(f"  Best val loss:   {history['best_val_loss']:.6f}")
    log.info(f"  Threshold:       {threshold_info['threshold']:.8f}")
    log.info(f"  Total params:    {total_params:,}")


if __name__ == "__main__":
    main()
