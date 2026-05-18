#!/usr/bin/env python3
"""
scripts/extract_code_links.py

Walk every discoveries_*.json under data/external_research/ and extract
github / gitlab / bitbucket URLs from each paper's abstract. Writes a
candidate-repos manifest that lists papers + the code repositories they
reference, suitable for selective cloning into data/github-repos/cloned/.

Usage:
    python scripts/extract_code_links.py

Output: data/external_research/code_links_<UTC-date>.json with:
    {
      "generated_at": "...",
      "scanned_files": [...],
      "candidates": [
        {
          "paper_id": "arxiv:2309.07843",
          "title": "...",
          "url": "https://arxiv.org/abs/...",
          "code_urls": ["https://github.com/asridi/DML-Calibration-Heston-Model"],
          "abstract_snippet": "..."
        },
        ...
      ]
    }

No network calls. No cloning. Pure JSON-in, JSON-out analysis.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "external_research"

# Match github.com / gitlab.com / bitbucket.org URLs that look like `<host>/<user>/<repo>`.
# Tolerates trailing punctuation (period, comma, paren) that often appears in prose.
CODE_URL_RE = re.compile(
    r"(?P<url>https?://(?:www\.)?"
    r"(?:github\.com|gitlab\.com|bitbucket\.org)"
    r"/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)"
    r"(?![a-zA-Z0-9_])",
    re.IGNORECASE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extract_code_links")


def find_discovery_files(data_dir: Path) -> List[Path]:
    """All discoveries_*.json under data/external_research/."""
    return sorted(data_dir.glob("discoveries_*.json"))


def _strip_trailing_punctuation(url: str) -> str:
    """Authors write `Code at https://github.com/x/y.` — drop the trailing period."""
    return url.rstrip(".,;:)]}>'\"")


def extract_code_urls(abstract: Optional[str]) -> List[str]:
    """Extract distinct github/gitlab/bitbucket URLs from an abstract.

    Preserves order of first appearance. Deduplicates exact matches.
    """
    if not abstract:
        return []
    seen: List[str] = []
    for m in CODE_URL_RE.finditer(abstract):
        url = _strip_trailing_punctuation(m.group("url"))
        if url not in seen:
            seen.append(url)
    return seen


def extract_candidates(
    discoveries: Iterable[Dict[str, Any]],
    snippet_chars: int = 240,
) -> List[Dict[str, Any]]:
    """For each discovery with at least one code URL, yield a candidate row.

    `snippet_chars` controls the abstract excerpt length surrounding the URL.
    """
    candidates: List[Dict[str, Any]] = []
    for d in discoveries:
        abstract = d.get("abstract") or ""
        urls = extract_code_urls(abstract)
        if not urls:
            continue
        snippet = abstract[:snippet_chars]
        if len(abstract) > snippet_chars:
            snippet += "…"
        candidates.append(
            {
                "paper_id": d.get("id"),
                "title": d.get("title"),
                "url": d.get("url"),
                "source": d.get("source"),
                "published": d.get("published"),
                "code_urls": urls,
                "abstract_snippet": snippet,
            }
        )
    return candidates


def load_discoveries(path: Path) -> List[Dict[str, Any]]:
    """Open a discoveries_*.json and return its list of discovery records."""
    data = json.loads(path.read_text())
    return list(data.get("discoveries") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract code-repository URLs from discovery files")
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Directory containing discoveries_*.json (default: data/external_research/)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output file (default: code_links_<UTC-date>.json in --data-dir)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        log.error(f"data dir missing: {data_dir}")
        return 2

    files = find_discovery_files(data_dir)
    if not files:
        log.warning(f"no discoveries_*.json in {data_dir}")
        return 0

    all_discoveries: List[Dict[str, Any]] = []
    for fp in files:
        all_discoveries.extend(load_discoveries(fp))
    log.info(f"Scanned {len(files)} file(s); {len(all_discoveries)} discoveries total")

    candidates = extract_candidates(all_discoveries)
    log.info(f"{len(candidates)} papers reference code repositories")

    out_path = (
        Path(args.out) if args.out
        else data_dir / f"code_links_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scanned_files": [str(f.relative_to(REPO_ROOT)) for f in files],
        "candidates": candidates,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    log.info(f"Wrote: {out_path}")

    # Print top candidates for human review
    if candidates:
        log.info("Top candidates:")
        for c in candidates[:10]:
            log.info(f"  [{c['paper_id']}] {c['title'][:60]}")
            for u in c["code_urls"]:
                log.info(f"      → {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
