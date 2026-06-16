#!/usr/bin/env python3
"""
scripts/acquire_hf_assets.py

HuggingFace asset acquisition for Project Oracle.
Searches, downloads, and catalogs:
  - Time-series forecasting models (PatchTST, Informer, Autoformer)
  - Anomaly detection models (1D-CNN AE, Transformer-AE)
  - LOB prediction models (DeepLOB, LiT, Neural Hawkes)
  - Benchmark datasets (FI-2010, NASDAQ LOB)

Writes provenance manifest to ./project_oracle/MANIFEST.json.

Usage:
    cd /Users/nav/Documents/GitHub/floww
    .venv/bin/python scripts/acquire_hf_assets.py [--dry-run] [--models-only] [--datasets-only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ORACLE = REPO_ROOT / "project_oracle"
MODELS_DIR = PROJECT_ORACLE / "models"
DATASETS_DIR = PROJECT_ORACLE / "datasets"
MANIFEST_PATH = PROJECT_ORACLE / "MANIFEST.json"

# ── Target assets ──────────────────────────────────────────────────────────────

TIME_SERIES_MODELS: list[dict[str, Any]] = [
    {"search": "patchts", "task": "time-series-forecasting", "family": "PatchTST", "limit": 3},
    {"search": "autoformer", "task": "time-series-forecasting", "family": "Autoformer", "limit": 3},
    {"search": "timesnet time series", "task": "time-series-forecasting", "family": "TimesNet", "limit": 3},
]

ANOMALY_MODELS: list[dict[str, Any]] = [
    {"model_id": "1D-CNN-AE", "task": "anomaly-detection", "family": "1D-CNN-AE", "search": "1D-CNN autoencoder anomaly"},
    {"model_id": "Transformer-AE", "task": "anomaly-detection", "family": "Transformer-AE", "search": "transformer autoencoder anomaly"},
]

LOB_MODELS: list[dict[str, Any]] = [
    {"model_id": "DeepLOB", "task": "lob-prediction", "family": "DeepLOB", "search": "deeplob"},
    {"model_id": "LiT", "task": "lob-prediction", "family": "LiT", "search": "limit order book transformer"},
    {"model_id": "Neural-Hawkes", "task": "lob-prediction", "family": "Neural-Hawkes", "search": "hawkes process financial"},
]

DATASETS: list[dict[str, Any]] = [
    {"dataset_id": "benchmark/fi-2010", "task": "lob-benchmark", "family": "FI-2010", "search": "fi-2010"},
    {"dataset_id": "NASDAQ-LOB", "task": "lob-snapshot", "family": "NASDAQ-LOB", "search": "NASDAQ limit order book"},
]


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size_mb(path: Path) -> float:
    """Return file size in MB."""
    return round(path.stat().st_size / (1024 * 1024), 2)


def search_models(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search HuggingFace Hub for models matching query."""
    try:
        from huggingface_hub import HfApi  # type: ignore[import-not-found]
        api = HfApi()
        results = list(api.list_models(search=query, limit=limit))
        return [
            {
                "model_id": m.id,
                "downloads": getattr(m, "downloads", 0),
                "likes": getattr(m, "likes", 0),
                "last_modified": str(getattr(m, "lastModified", "")),
                "tags": getattr(m, "tags", [])[:10],
            }
            for m in results
        ]
    except Exception as e:
        log.warning(f"Model search failed for '{query}': {e}")
        return []


def search_datasets(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search HuggingFace Hub for datasets matching query."""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        results = list(api.list_datasets(search=query, limit=limit))
        return [
            {
                "dataset_id": d.id,
                "downloads": getattr(d, "downloads", 0),
                "likes": getattr(d, "likes", 0),
                "last_modified": str(getattr(d, "lastModified", "")),
            }
            for d in results
        ]
    except Exception as e:
        log.warning(f"Dataset search failed for '{query}': {e}")
        return []


def download_model(model_id: str, target_dir: Path) -> Optional[dict[str, Any]]:
    """Download a model from HuggingFace Hub. Returns provenance dict or None."""
    try:
        from huggingface_hub import snapshot_download
        log.info(f"Downloading model: {model_id}")
        local_path = snapshot_download(
            repo_id=model_id,
            local_dir=target_dir / model_id.replace("/", "--"),
            local_dir_use_symlinks=False,
        )
        path = Path(local_path)
        # Compute total size and hash of key files
        total_size = 0
        key_files = list(path.glob("*.bin")) + list(path.glob("*.safetensors")) + list(path.glob("*.pt"))
        if not key_files:
            key_files = list(path.glob("*.json"))[:5]
        file_hashes = {}
        for f in key_files[:10]:
            total_size += f.stat().st_size
            file_hashes[f.name] = sha256_file(f)

        return {
            "model_id": model_id,
            "local_path": str(path.relative_to(REPO_ROOT)),
            "size_mb": round(total_size / (1024 * 1024), 2),
            "n_files": len(list(path.rglob("*"))),
            "key_file_hashes": file_hashes,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.error(f"Failed to download model {model_id}: {e}")
        return None


def download_dataset(dataset_id: str, target_dir: Path) -> Optional[dict[str, Any]]:
    """Download a dataset from HuggingFace Hub. Returns provenance dict or None."""
    try:
        from huggingface_hub import snapshot_download
        log.info(f"Downloading dataset: {dataset_id}")
        local_path = snapshot_download(
            repo_id=dataset_id,
            repo_type="dataset",
            local_dir=target_dir / dataset_id.replace("/", "--"),
            local_dir_use_symlinks=False,
        )
        path = Path(local_path)
        total_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return {
            "dataset_id": dataset_id,
            "local_path": str(path.relative_to(REPO_ROOT)),
            "size_mb": round(total_size / (1024 * 1024), 2),
            "n_files": len(list(path.rglob("*"))),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        log.error(f"Failed to download dataset {dataset_id}: {e}")
        return None


def build_manifest(models: list[dict[str, Any]], datasets: list[dict[str, Any]], search_results: dict[str, Any]) -> dict[str, Any]:
    """Build the provenance manifest."""
    return {
        "project": "Project Oracle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_version": "1.0",
        "models": models,
        "datasets": datasets,
        "search_results": search_results,
        "total_models_downloaded": len(models),
        "total_datasets_downloaded": len(datasets),
        "total_size_mb": round(
            sum(m.get("size_mb", 0) for m in models) +
            sum(d.get("size_mb", 0) for d in datasets), 2
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire HuggingFace assets for Project Oracle")
    parser.add_argument("--dry-run", action="store_true", help="Search only, don't download")
    parser.add_argument("--models-only", action="store_true", help="Only download models")
    parser.add_argument("--datasets-only", action="store_true", help="Only download datasets")
    parser.add_argument("--search-only", action="store_true", help="Only search, don't download")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)

    manifest_models: list[dict[str, Any]] = []
    manifest_datasets: list[dict[str, Any]] = []
    search_results: dict[str, Any] = {}

    # ── Phase 1: Search ──────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Phase 1: Searching HuggingFace Hub")
    log.info("=" * 60)

    # Search time-series models
    for m in TIME_SERIES_MODELS:
        results: list[dict[str, Any]] = search_models(str(m["search"]), limit=3)
        search_results[str(m["search"])] = results
        log.info(f"  TS model '{m['search']}': {len(results)} results")

    # Search anomaly models
    for m in ANOMALY_MODELS:
        results = search_models(str(m["search"]), limit=5)
        search_results[str(m["search"])] = results
        log.info(f"  Anomaly search '{m['search']}': {len(results)} results")

    # Search LOB models
    for m in LOB_MODELS:
        results = search_models(str(m["search"]), limit=5)
        search_results[str(m["search"])] = results
        log.info(f"  LOB search '{m['search']}': {len(results)} results")

    # Search datasets
    for d in DATASETS:
        query = str(d.get("search", d["dataset_id"]))
        results = search_datasets(query, limit=5)
        search_results[query] = results
        log.info(f"  Dataset search '{query}': {len(results)} results")

    if args.dry_run or args.search_only:
        log.info("Dry run / search-only mode — skipping downloads")
        manifest = build_manifest([], [], search_results)
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str))
        log.info(f"Search manifest written to {MANIFEST_PATH}")
        return

    # ── Phase 2: Download models ─────────────────────────────────────────────
    if not args.datasets_only:
        log.info("=" * 60)
        log.info("Phase 2: Downloading models")
        log.info("=" * 60)

        for m in TIME_SERIES_MODELS:
            search_query = str(m["search"])
            limit = int(m.get("limit", 3))
            results = search_models(search_query, limit=limit)
            if results:
                top_model = results[0]["model_id"]
                result = download_model(top_model, MODELS_DIR)
                if result:
                    result["family"] = m["family"]
                    result["task"] = m["task"]
                    manifest_models.append(result)
                    log.info(f"  Downloaded: {top_model} ({result.get('size_mb', '?')} MB)")
            time.sleep(1)

        # For anomaly/LOB models, try the top search result
        for m in ANOMALY_MODELS + LOB_MODELS:
            results = search_models(str(m["search"]), limit=1)
            if results:
                top_model = results[0]["model_id"]
                result = download_model(top_model, MODELS_DIR)
                if result:
                    result["family"] = m["family"]
                    result["task"] = m["task"]
                    manifest_models.append(result)
                    log.info(f"  Downloaded: {top_model} ({result['size_mb']} MB)")
            time.sleep(1)

    # ── Phase 3: Download datasets ───────────────────────────────────────────
    if not args.models_only:
        log.info("=" * 60)
        log.info("Phase 3: Downloading datasets")
        log.info("=" * 60)

        for d in DATASETS:
            result = download_dataset(d["dataset_id"], DATASETS_DIR)
            if result:
                result["family"] = d["family"]
                result["task"] = d["task"]
                manifest_datasets.append(result)
                log.info(f"  Downloaded: {d['dataset_id']} ({result['size_mb']} MB)")
            time.sleep(1)

    # ── Phase 4: Write manifest ──────────────────────────────────────────────
    manifest = build_manifest(manifest_models, manifest_datasets, search_results)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, default=str))
    log.info(f"Manifest written to {MANIFEST_PATH}")
    log.info(f"Total: {len(manifest_models)} models, {len(manifest_datasets)} datasets, "
             f"{manifest['total_size_mb']} MB")


if __name__ == "__main__":
    main()
