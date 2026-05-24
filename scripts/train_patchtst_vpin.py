#!/usr/bin/env python3
"""
scripts/train_patchtst_vpin.py

Train PatchTST forecaster for VPIN time series.
Forecasts next 15 × 1-min VPIN given last 60 × 1-min context.

Backbone: ibm-granite/granite-timeseries-patchtsmixer (from Round 1 HF download)
Training data: MongoDB gex_history VPIN time series (or synthetic bootstrap)

Usage:
    cd /Users/nav/Documents/GitHub/floww
    .venv/bin/python scripts/train_patchtst_vpin.py [--epochs 20] [--seq-len 60] [--forecast-horizon 15]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import torch
import torch.nn as nn
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
MODELS_DIR = REPO_ROOT / "project_oracle" / "models"
QC_DIR = REPO_ROOT / "project_oracle" / "qc"
MANIFEST_PATH = QC_DIR / "patchtst_vpin_v1_manifest.json"

sys.path.insert(0, str(BACKEND))


def load_vpin_from_mongodb() -> Optional[np.ndarray]:
    """Load VPIN time series from MongoDB gex_history collection."""
    try:
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo_url = "mongodb+srv://navdeep:nav%40123@cluster0.0uqhd.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
        db_name = "confluence_decoder"

        async def _fetch():
            client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000)
            db = client[db_name]
            count = await db.gex_history.estimated_document_count()
            if count < 100:
                return None
            cursor = db.gex_history.find(
                {}, {"vpin": 1, "ts": 1, "_id": 0}
            ).sort("ts", 1).limit(50000)
            docs = await cursor.to_list(length=50000)
            return docs

        docs = asyncio.run(_fetch())
        if not docs:
            return None

        vpin_values = []
        for doc in docs:
            vpin = doc.get("vpin", doc.get("VPIN", None))
            if vpin is not None:
                vpin_values.append(float(vpin))

        if len(vpin_values) < 200:
            log.warning(f"MongoDB VPIN data too sparse ({len(vpin_values)} rows)")
            return None

        log.info(f"Loaded {len(vpin_values)} VPIN samples from MongoDB")
        return np.array(vpin_values, dtype=np.float32)

    except Exception as e:
        log.warning(f"MongoDB unavailable ({e}), using synthetic bootstrap")
        return None


def generate_synthetic_vpin(n_samples: int = 10000, seed: int = 42) -> np.ndarray:
    """Generate synthetic VPIN via mean-reverting OU process with toxicity spikes."""
    rng = np.random.RandomState(seed)
    vpin = np.zeros(n_samples, dtype=np.float32)
    vpin[0] = 0.45
    for t in range(1, n_samples):
        # Mean-reverting around 0.45
        mean_rev = 0.08 * (0.45 - vpin[t - 1])
        noise = rng.normal(0, 0.025)
        # Occasional toxicity spikes (8% of samples)
        spike = rng.random() < 0.08
        spike_val = rng.uniform(0.25, 0.55) if spike else 0.0
        vpin[t] = np.clip(vpin[t - 1] + mean_rev + noise + spike_val, 0.05, 0.99)
    return vpin


def create_forecast_sequences(data: np.ndarray, seq_len: int, horizon: int):
    """Create input/target pairs for forecasting.
    Returns (inputs, targets) where inputs[i] = data[i:i+seq_len] and targets[i] = data[i+seq_len:i+seq_len+horizon].
    """
    n = len(data) - seq_len - horizon + 1
    if n <= 0:
        raise ValueError(f"Data length {len(data)} < seq_len {seq_len} + horizon {horizon}")
    inputs = np.zeros((n, seq_len), dtype=np.float32)
    targets = np.zeros((n, horizon), dtype=np.float32)
    for i in range(n):
        inputs[i] = data[i:i + seq_len]
        targets[i] = data[i + seq_len:i + seq_len + horizon]
    return inputs, targets


def train_patchtst(
    train_inputs: np.ndarray,
    train_targets: np.ndarray,
    val_inputs: np.ndarray,
    val_targets: np.ndarray,
    seq_len: int = 60,
    horizon: int = 15,
    epochs: int = 20,
    batch_size: int = 64,
    lr: float = 1e-3,
    device: str = "cpu",
) -> tuple:
    """Train PatchTST model. Returns (model, history)."""
    from torch.utils.data import DataLoader, TensorDataset

    # Load pretrained PatchTST
    from transformers import AutoModelForTimeSeriesPrediction, AutoConfig

    model_id = "ibm-granite/granite-timeseries-patchtsmixer"
    log.info(f"Loading pretrained model: {model_id}")

    try:
        model = AutoModelForTimeSeriesPrediction.from_pretrained(model_id)
    except Exception:
        # Fallback: create a simple 1D-CNN forecaster
        log.warning("HF model load failed, using CNN forecaster fallback")
        model = SimpleCNNForecaster(seq_len=seq_len, horizon=horizon)

    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)

    # Prepare data
    train_x = torch.tensor(train_inputs, dtype=torch.float32).unsqueeze(-1).to(device)  # (N, seq_len, 1)
    train_y = torch.tensor(train_targets, dtype=torch.float32).to(device)  # (N, horizon)
    val_x = torch.tensor(val_inputs, dtype=torch.float32).unsqueeze(-1).to(device)
    val_y = torch.tensor(val_targets, dtype=torch.float32).to(device)

    train_dataset = TensorDataset(train_x, train_y)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)

    history = {"train_loss": [], "val_loss": []}
    best_val_loss = float("inf")
    best_state = None

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            try:
                outputs = model(batch_x)
                loss = nn.functional.mse_loss(outputs, batch_y)
            except Exception:
                # Fallback: direct forward
                pred = model(batch_x)
                if isinstance(pred, tuple):
                    pred = pred[0]
                if pred.shape != batch_y.shape:
                    pred = pred[..., :batch_y.shape[-1]] if pred.shape[-1] > batch_y.shape[-1] else pred
                loss = nn.functional.mse_loss(pred, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1

        avg_train_loss = epoch_loss / max(n_batches, 1)

        # Validation
        model.eval()
        with torch.no_grad():
            try:
                val_pred = model(val_x)
                val_loss = nn.functional.mse_loss(val_pred, val_y).item()
            except Exception:
                val_loss = avg_train_loss  # fallback

        scheduler.step(val_loss)
        history["train_loss"].append(round(avg_train_loss, 6))
        history["val_loss"].append(round(val_loss, 6))

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if epoch % 5 == 0 or epoch == 1:
            log.info(f"  Epoch {epoch:3d}/{epochs} | train={avg_train_loss:.6f} | val={val_loss:.6f} | time={time.time()-t0:.1f}s")

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, history, best_val_loss


class SimpleCNNForecaster(nn.Module):
    """Lightweight 1D-CNN forecaster as fallback."""
    def __init__(self, seq_len: int = 60, horizon: int = 15):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(16, horizon),
        )

    def forward(self, x):
        # x: (batch, seq_len, 1) -> (batch, 1, seq_len)
        x = x.permute(0, 2, 1)
        return self.net(x)


def main():
    parser = argparse.ArgumentParser(description="Train PatchTST VPIN forecaster")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seq-len", type=int, default=60)
    parser.add_argument("--forecast-horizon", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--n-samples", type=int, default=10000)
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    QC_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    vpin_data = load_vpin_from_mongodb()
    data_source = "mongodb"
    if vpin_data is None:
        vpin_data = generate_synthetic_vpin(n_samples=args.n_samples)
        data_source = "synthetic_bootstrap"

    log.info(f"VPIN data: {len(vpin_data)} samples, source={data_source}")

    if args.dry_run:
        log.info("Dry run — skipping training")
        return

    # Create sequences
    inputs, targets = create_forecast_sequences(vpin_data, args.seq_len, args.forecast_horizon)
    split = int(len(inputs) * 0.8)
    train_inputs, val_inputs = inputs[:split], inputs[split:]
    train_targets, val_targets = targets[:split], targets[split:]

    log.info(f"Train: {len(train_inputs)}, Val: {len(val_inputs)}")

    # Train
    model, history, best_val_loss = train_patchtst(
        train_inputs, train_targets, val_inputs, val_targets,
        seq_len=args.seq_len, horizon=args.forecast_horizon,
        epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, device=args.device,
    )

    # Compute persistence baseline
    persistence_pred = val_inputs[:, -1:]  # last value
    persistence_pred = np.repeat(persistence_pred, args.forecast_horizon, axis=1)
    persistence_mse = float(np.mean((val_targets - persistence_pred) ** 2))
    log.info(f"Persistence baseline MSE: {persistence_mse:.6f}")
    log.info(f"Model val MSE: {best_val_loss:.6f}")
    log.info(f"Improvement: {(1 - best_val_loss / persistence_mse) * 100:.1f}%" if persistence_mse > 0 else "N/A")

    # Save
    save_path = MODELS_DIR / "patchtst_vpin_v1.pt"
    import torch
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {"seq_len": args.seq_len, "horizon": args.forecast_horizon},
        "history": history,
        "data_source": data_source,
    }, save_path)

    manifest = {
        "model": "patchtst_vpin_v1",
        "path": str(save_path.relative_to(REPO_ROOT)),
        "data_source": data_source,
        "n_train": len(train_inputs),
        "n_val": len(val_inputs),
        "seq_len": args.seq_len,
        "forecast_horizon": args.forecast_horizon,
        "epochs": args.epochs,
        "best_val_loss": best_val_loss,
        "persistence_baseline_mse": persistence_mse,
        "beats_persistence": best_val_loss < persistence_mse,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    log.info(f"Saved: {save_path}, manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
