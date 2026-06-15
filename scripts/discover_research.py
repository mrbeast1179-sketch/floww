#!/usr/bin/env python3
"""
scripts/discover_research.py

Run the research-discovery pipeline against the curated sources in
`data/external_research/sources.yaml`. Writes a manifest of discoveries
to `data/external_research/discoveries_<UTC-date>.json`.

Usage:
    python scripts/discover_research.py [--sources arxiv,huggingface]
    python scripts/discover_research.py --dry-run

Discoveries are NEVER auto-ingested into training pipelines. They land in
the JSON manifest for human/LLM vetting. See `data/external_research/README.md`
for the workflow.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.research.discovery import (  # type: ignore[import-not-found]  # noqa: E402
    ArxivSource,
    DiscoverySource,
    HuggingFaceSource,
    GitHubTopicSource,
    SSRNSource,
    NBERSource,
    QuantocracySource,
    AQRSource,
    RobotWealthSource,
    ResearchGateSource,
    discover_all,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discover_research")

SOURCES_YAML = REPO_ROOT / "data" / "external_research" / "sources.yaml"
OUTPUT_DIR = REPO_ROOT / "data" / "external_research"


def load_sources_yaml(path: Path) -> Dict[str, Any]:
    """Minimal YAML loader so we don't add a dependency for one config file.

    Supports the subset of YAML used in sources.yaml: top-level keys with
    nested `queries:` / `topics:` lists.
    """
    try:
        import yaml  # type: ignore
    except ImportError:
        log.warning("PyYAML not installed; using fallback parser (limited)")
        return _fallback_yaml_parse(path.read_text())
    return yaml.safe_load(path.read_text()) or {}


def _fallback_yaml_parse(text: str) -> Dict[str, Any]:
    """Tiny YAML subset parser. Handles `key:` and `  - "item"` only.
    Used when PyYAML is not installed; sufficient for sources.yaml.
    """
    result: Dict[str, Any] = {}
    current_top: str = ""
    current_sub: str = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent == 0 and stripped.endswith(":"):
            current_top = stripped[:-1].strip()
            result[current_top] = {}
            current_sub = ""
        elif indent == 2 and stripped.endswith(":") and current_top:
            current_sub = stripped[:-1].strip()
            result[current_top][current_sub] = []
        elif stripped.startswith("- ") and current_top and current_sub:
            val = stripped[2:].strip().strip('"').strip("'")
            result[current_top][current_sub].append(val)
    return result


def build_sources(names: List[str]) -> List[DiscoverySource]:
    """Construct DiscoverySource instances for the requested names."""
    available = {
        "arxiv": ArxivSource,
        "huggingface": HuggingFaceSource,
        "github_topic": GitHubTopicSource,
        "ssrn": SSRNSource,
        "nber": NBERSource,
        "quantocracy": QuantocracySource,
        "aqr": AQRSource,
        "robot_wealth": RobotWealthSource,
        "researchgate": ResearchGateSource,
    }
    sources: List[DiscoverySource] = []
    for name in names:
        cls = available.get(name)
        if cls is None:
            log.warning(f"unknown source '{name}'; skipping")
            continue
        sources.append(cls())
    return sources


def collect_queries(yaml_data: Dict[str, Any], source_names: List[str]) -> Dict[str, List[str]]:
    """Pull `queries` (or `topics`, for github_topic) per source from yaml."""
    out: Dict[str, List[str]] = {}
    for name in source_names:
        cfg = yaml_data.get(name, {}) or {}
        queries = cfg.get("queries") or cfg.get("topics") or []
        out[name] = [str(q) for q in queries]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover open-source quant research")
    parser.add_argument(
        "--sources",
        default="arxiv",
        help="Comma-separated source names (default: arxiv). Use 'all' for every wired source.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load config, list what would be searched, but don't fetch.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=10,
        help="Max queries per run (default: 10). Rotates through full set across runs.",
    )
    args = parser.parse_args()

    if not SOURCES_YAML.exists():
        log.error(f"sources file missing: {SOURCES_YAML}")
        return 2

    yaml_data = load_sources_yaml(SOURCES_YAML)

    if args.sources == "all":
        source_names = ["arxiv", "huggingface", "github_topic"]
    else:
        source_names = [s.strip() for s in args.sources.split(",") if s.strip()]

    queries = collect_queries(yaml_data, source_names)

    # Rotate queries: use a state file to track offset, limit to max-queries per run
    state_path = OUTPUT_DIR / ".discover_state.json"
    offset = 0
    if state_path.exists():
        try:
            d = json.loads(state_path.read_text())
            offset = d.get("offset", 0)
        except Exception:
            pass

    # Rotate queries for each source
    rotated_queries: Dict[str, List[str]] = {}
    for name, qs in queries.items():
        if not qs:
            rotated_queries[name] = []
            continue
        n = min(args.max_queries, len(qs))
        start = offset % max(len(qs), 1)
        selected = []
        for i in range(n):
            selected.append(qs[(start + i) % len(qs)])
        rotated_queries[name] = selected

    total_queries = sum(len(v) for v in rotated_queries.values())
    log.info(f"Sources: {source_names}; queries this run: {total_queries} (offset={offset})")

    # Save next offset
    state_path.write_text(json.dumps({"offset": offset + total_queries}))

    if args.dry_run:
        for name, qs in rotated_queries.items():
            log.info(f"  {name}: {len(qs)} queries")
            for q in qs[:3]:
                log.info(f"    - {q}")
            if len(qs) > 3:
                log.info(f"    ... and {len(qs) - 3} more")
        return 0

    sources = build_sources(source_names)
    log.info(f"Running discovery against {len(sources)} source(s)...")
    discoveries, errors = discover_all(sources, rotated_queries)
    log.info(f"Got {len(discoveries)} discoveries; errors: {len(errors)}")
    for name, err in errors.items():
        log.warning(f"  {name}: {err}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = OUTPUT_DIR / f"discoveries_{ts}.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources_run": source_names,
        "queries_per_source": rotated_queries,
        "errors": errors,
        "discoveries": [d.to_dict() for d in discoveries],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    log.info(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
