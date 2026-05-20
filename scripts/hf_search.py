#!/usr/bin/env python3
"""
scripts/hf_search.py

Search HuggingFace Hub for models and datasets relevant to options trading,
market microstructure, and quantitative finance. Writes results to
data/external_research/hf_manifest_<date>.json and updates
project_oracle/MANIFEST.json with notable finds.

Usage:
    python scripts/hf_search.py [--queries "query1,query2"] [--top-n 10]

Rate limits: HF Hub API is public, no auth required for search.
We self-limit to ~30 queries/hour.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from huggingface_hub import HfApi, model_info, dataset_info
    HAS_HF = True
except ImportError:
    HAS_HF = False

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"
MANIFEST_PATH = REPO_ROOT / "project_oracle" / "MANIFEST.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hf_search")

DEFAULT_QUERIES = [
    "options trading",
    "dealer gamma",
    "1D CNN autoencoder financial",
    "limit order book",
    "PatchTST options",
    "financial time series",
    "volatility forecasting",
    "market microstructure",
    "options flow",
    "gamma exposure",
]

# Known labs/institutions whose work is high-priority
KNOWN_LABS = [
    "stanford", "nyu", "stern", "epfl", "imperial", "mit", "cmu",
    "berkeley", "oxford", "cambridge", "eth", "nus", "ntu",
]


def _load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text())
    return {"hf_assets": [], "last_updated": None}


def _save_manifest(data: Dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(json.dumps(data, indent=2) + "\n")


def _is_notable(info: Any) -> bool:
    """Check if a HF model/dataset is notable enough to track."""
    likes = getattr(info, 'likes', 0) or 0
    downloads = getattr(info, 'downloads', 0) or 0
    author = getattr(info, 'author', '') or ''

    if likes >= 100:
        return True
    if downloads >= 1000:
        return True
    if any(lab in author.lower() for lab in KNOWN_LABS):
        return True
    return False


def search_hf(
    queries: List[str],
    top_n: int = 10,
) -> List[Dict[str, Any]]:
    """Search HF Hub for models and datasets matching the queries."""
    if not HAS_HF:
        log.error("huggingface_hub not installed. Run: pip install huggingface_hub")
        return []

    api: HfApi = HfApi()
    results: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for query in queries:
        log.info(f"Searching HF Hub: '{query}'")
        try:
            # Search models
            models = api.list_models(search=query, limit=top_n, sort="likes")
            for m in models:
                if m.id in seen_ids:
                    continue
                seen_ids.add(m.id)
                entry = {
                    "type": "model",
                    "id": m.id,
                    "likes": m.likes or 0,
                    "downloads": m.downloads or 0,
                    "tags": m.tags or [],
                    "pipeline_tag": m.pipeline_tag,
                    "library_name": m.library_name,
                    "created_at": str(m.created_at) if m.created_at else None,
                    "last_modified": str(m.last_modified) if m.last_modified else None,
                    "author": m.author,
                    "url": f"https://huggingface.co/{m.id}",
                    "query": query,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "notable": _is_notable(m),
                }
                results.append(entry)

            # Search datasets
            datasets = api.list_datasets(search=query, limit=top_n, sort="likes")
            for d in datasets:
                if d.id in seen_ids:
                    continue
                seen_ids.add(d.id)
                entry = {
                    "type": "dataset",
                    "id": d.id,
                    "likes": d.likes or 0,
                    "downloads": d.downloads or 0,
                    "tags": d.tags or [],
                    "created_at": str(d.created_at) if d.created_at else None,
                    "last_modified": str(d.last_modified) if d.last_modified else None,
                    "author": d.author,
                    "url": f"https://huggingface.co/datasets/{d.id}",
                    "query": query,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "notable": _is_notable(d),
                }
                results.append(entry)

        except Exception as exc:
            log.warning(f"  HF search failed for '{query}': {exc}")

        time.sleep(2.0)  # Rate limit: max ~30 queries/hour

    return results


def update_manifest(new_results: List[Dict[str, Any]]) -> int:
    """Merge new HF results into project_oracle/MANIFEST.json. Returns count of new entries."""
    manifest = _load_manifest()
    existing_ids = {a["id"] for a in manifest.get("hf_assets", [])}
    added = 0
    for r in new_results:
        if r["id"] not in existing_ids and r.get("notable"):
            summary = f"{r['type']}: {r['id']} ({r['likes']} likes, {r['downloads']} downloads)"
            manifest.setdefault("hf_assets", []).append({
                "id": r["id"],
                "type": r["type"],
                "url": r["url"],
                "likes": r["likes"],
                "downloads": r["downloads"],
                "author": r["author"],
                "summary": summary,
                "discovered_at": r["discovered_at"],
            })
            existing_ids.add(r["id"])
            added += 1
            log.info(f"  New notable: {summary}")

    _save_manifest(manifest)
    return added


def main() -> int:
    parser = argparse.ArgumentParser(description="Search HuggingFace Hub for relevant assets")
    parser.add_argument(
        "--queries",
        default=",".join(DEFAULT_QUERIES),
        help="Comma-separated search queries",
    )
    parser.add_argument("--top-n", type=int, default=10, help="Results per query per type")
    parser.add_argument("--no-manifest", action="store_true", help="Skip updating MANIFEST.json")
    args = parser.parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    log.info(f"Searching HF Hub: {len(queries)} queries, top-{args.top_n} each")

    results = search_hf(queries, top_n=args.top_n)
    notable = [r for r in results if r.get("notable")]
    log.info(f"Found {len(results)} total results, {len(notable)} notable")

    # Write daily manifest
    EXTERNAL_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = EXTERNAL_RESEARCH_DIR / f"hf_manifest_{ts}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "total_results": len(results),
        "notable_count": len(notable),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    log.info(f"Wrote: {out_path}")

    # Update project_oracle/MANIFEST.json
    if not args.no_manifest:
        added = update_manifest(results)
        log.info(f"Added {added} new assets to MANIFEST.json")

    # Print notable items
    if notable:
        log.info("\nNotable HF assets:")
        for r in sorted(notable, key=lambda x: x.get("likes", 0), reverse=True)[:20]:
            log.info(f"  [{r['type']}] {r['id']} — {r['likes']} likes, {r['downloads']} downloads")
            log.info(f"    {r['url']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
