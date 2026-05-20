#!/usr/bin/env python3
"""
scripts/expanded_sources.py

Non-arxiv research source discovery. Scrapes/searches:
  - SSRN (ssrn.com) — quant finance preprints
  - NBER (nber.org) — working papers
  - Quantocracy (quantocracy.com) — aggregator RSS
  - AQR (aqr.com) — Cliff Asness blog RSS
  - Robot Wealth (robotwealth.com) — blog RSS

Results are appended to data/external_research/discoveries_<date>.json
with source tags: ssrn, nber, quantocracy, aqr, robot_wealth.

Usage:
    python scripts/expanded_sources.py [--sources ssrn,nber,quantocracy,aqr,robot_wealth]
    python scripts/expanded_sources.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"
SOURCES_YAML = EXTERNAL_RESEARCH_DIR / "sources.yaml"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("expanded_sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ────────────────────────────────────────────────────────────────────────────
# SSRN scraper
# ────────────────────────────────────────────────────────────────────────────

def fetch_ssrn(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Search SSRN for papers matching query."""
    results = []
    try:
        # SSRN search URL
        params = urllib.parse.urlencode({"q": query, "page": 1})
        url = f"https://papers.ssrn.com/sol3/DisplayJournalBrowse.cfm?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Extract paper links and titles from search results
        # SSRN search results have pattern: /abstract=XXXXX">Title</a>
        paper_pattern = re.compile(
            r'href="(/sol3/papers\.cfm\?abstract_id=\d+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE,
        )
        for match in paper_pattern.finditer(html):
            paper_url_path, title = match.groups()
            title = title.strip()
            if len(title) < 10 or len(title) > 300:
                continue
            abstract_id = re.search(r"abstract_id=(\d+)", paper_url_path)
            if not abstract_id:
                continue
            paper_id = f"ssrn:{abstract_id.group(1)}"
            results.append({
                "id": paper_id,
                "title": title,
                "url": f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={abstract_id.group(1)}",
                "source": "ssrn",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "authors": [],
                "published": None,
                "abstract": None,
                "tags": ["ssrn", "preprint"],
                "license": None,
                "relevance_score": None,
                "query": query,
            })
            if len(results) >= max_results:
                break

    except Exception as exc:
        log.warning(f"SSRN search failed for '{query}': {exc}")

    return results[:max_results]


# ────────────────────────────────────────────────────────────────────────────
# NBER scraper
# ────────────────────────────────────────────────────────────────────────────

def fetch_nber(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Search NBER working papers."""
    results = []
    try:
        params = urllib.parse.urlencode({"q": query, "page": 1, "perPage": max_results})
        url = f"https://www.nber.org/papers?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # NBER paper links: /papers/wXXXXX">Title
        paper_pattern = re.compile(
            r'href="(/papers/w\d+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE,
        )
        seen_ids = set()
        for match in paper_pattern.finditer(html):
            paper_path, title = match.groups()
            title = title.strip()
            paper_id_match = re.search(r"w(\d+)", paper_path)
            if not paper_id_match:
                continue
            paper_id = f"nber:w{paper_id_match.group(1)}"
            if paper_id in seen_ids:
                continue
            seen_ids.add(paper_id)
            if len(title) < 10:
                continue
            results.append({
                "id": paper_id,
                "title": title,
                "url": f"https://www.nber.org{paper_path}",
                "source": "nber",
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "authors": [],
                "published": None,
                "abstract": None,
                "tags": ["nber", "working-paper"],
                "license": None,
                "relevance_score": None,
                "query": query,
            })
            if len(results) >= max_results:
                break

    except Exception as exc:
        log.warning(f"NBER search failed for '{query}': {exc}")

    return results[:max_results]


# ────────────────────────────────────────────────────────────────────────────
# RSS feed parser (Quantocracy, AQR, Robot Wealth)
# ────────────────────────────────────────────────────────────────────────────

RSS_FEEDS = {
    "quantocracy": {
        "url": "https://quantocracy.com/feed/",
        "tags": ["quantocracy", "aggregator"],
    },
    "aqr": {
        "url": "https://www.aqr.com/Insights/RSS",
        "tags": ["aqr", "commentary"],
    },
    "robot_wealth": {
        "url": "https://robotwealth.com/feed/",
        "tags": ["robot-wealth", "blog"],
    },
}


def fetch_rss_feed(source_name: str, feed_url: str, keywords: List[str], tags: List[str]) -> List[Dict[str, Any]]:
    """Fetch an RSS feed and filter items by keywords."""
    results = []
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        root = ET.fromstring(content)
        # RSS 2.0: channel/item, Atom: feed/entry
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items[:50]:
            title_elem = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
            link_elem = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
            desc_elem = item.find("description") or item.find("{http://www.w3.org/2005/Atom}summary")
            date_elem = item.find("pubDate") or item.find("{http://www.w3.org/2005/Atom}published")

            title = (title_elem.text or "").strip() if title_elem is not None else ""
            link = ""
            if link_elem is not None:
                link = link_elem.text or link_elem.get("href", "")
            desc = (desc_elem.text or "").strip() if desc_elem is not None else ""
            pub_date = (date_elem.text or "").strip() if date_elem is not None else ""

            if not title or not link:
                continue

            # Filter by keywords
            combined = f"{title} {desc}".lower()
            if not any(kw.lower() in combined for kw in keywords):
                continue

            # Clean HTML from description
            desc_clean = re.sub(r"<[^>]+>", "", desc)[:500]

            item_id = f"{source_name}:{re.sub(r'[^a-zA-Z0-9]', '_', title[:60])}"
            results.append({
                "id": item_id,
                "title": title,
                "url": link.strip(),
                "source": source_name,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "authors": [],
                "published": pub_date or None,
                "abstract": desc_clean or None,
                "tags": tags,
                "license": None,
                "relevance_score": None,
            })

    except Exception as exc:
        log.warning(f"RSS fetch failed for {source_name}: {exc}")

    return results


def fetch_all_rss(keywords_per_source: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Fetch all configured RSS feeds."""
    all_results = []
    for source_name, feed_config in RSS_FEEDS.items():
        keywords = keywords_per_source.get(source_name, ["options", "volatility", "quantitative"])
        log.info(f"Fetching RSS: {source_name} ({feed_config['url']})")
        results = fetch_rss_feed(
            source_name, feed_config["url"], keywords, feed_config["tags"]
        )
        all_results.extend(results)
        log.info(f"  {source_name}: {len(results)} matching items")
        time.sleep(2.0)  # Be polite
    return all_results


# ────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ────────────────────────────────────────────────────────────────────────────

def load_sources_yaml() -> Dict[str, Any]:
    try:
        import yaml
        return yaml.safe_load(SOURCES_YAML.read_text()) or {}
    except ImportError:
        return {}


def append_discoveries(new_results: List[Dict[str, Any]]) -> Path:
    """Append new discoveries to the daily discoveries file."""
    EXTERNAL_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = EXTERNAL_RESEARCH_DIR / f"discoveries_{ts}.json"

    existing = {"generated_at": None, "sources_run": [], "queries_per_source": {}, "errors": {}, "discoveries": []}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
        except Exception:
            pass

    # Merge, dedup by ID
    existing_ids = {d.get("id") for d in existing.get("discoveries", [])}
    added = 0
    for r in new_results:
        if r.get("id") not in existing_ids:
            existing["discoveries"].append(r)
            existing_ids.add(r.get("id"))
            added += 1

    existing["generated_at"] = datetime.now(timezone.utc).isoformat()
    existing["sources_run"] = list(set(existing.get("sources_run", []) + ["ssrn", "nber", "quantocracy", "aqr", "robot_wealth"]))

    out_path.write_text(json.dumps(existing, indent=2))
    log.info(f"Appended {added} new discoveries to {out_path}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Expanded research source discovery")
    parser.add_argument(
        "--sources",
        default="quantocracy,aqr,robot_wealth",
        help="Comma-separated source names (default: RSS sources only)",
    )
    parser.add_argument("--all", action="store_true", help="Run all sources")
    parser.add_argument("--max-per-query", type=int, default=10, help="Max results per query")
    args = parser.parse_args()

    if args.all:
        source_names = ["ssrn", "nber", "quantocracy", "aqr", "robot_wealth"]
    else:
        source_names = [s.strip() for s in args.sources.split(",") if s.strip()]

    yaml_data = load_sources_yaml()
    all_results: List[Dict[str, Any]] = []

    for source_name in source_names:
        log.info(f"--- Source: {source_name} ---")
        source_cfg = yaml_data.get(source_name, {})
        queries = source_cfg.get("queries", ["options volatility"])

        if source_name in ("quantocracy", "aqr", "robot_wealth"):
            # RSS-based
            keywords = {source_name: queries}
            results = fetch_all_rss(keywords)
            all_results.extend(results)
        elif source_name == "ssrn":
            for query in queries[:3]:  # Limit to 3 queries per run
                results = fetch_ssrn(query, max_results=args.max_per_query)
                all_results.extend(results)
                log.info(f"  SSRN '{query}': {len(results)} results")
                time.sleep(3.0)
        elif source_name == "nber":
            for query in queries[:3]:
                results = fetch_nber(query, max_results=args.max_per_query)
                all_results.extend(results)
                log.info(f"  NBER '{query}': {len(results)} results")
                time.sleep(3.0)
        else:
            log.warning(f"Unknown source: {source_name}")

    if all_results:
        out_path = append_discoveries(all_results)
        log.info(f"Total new discoveries: {len(all_results)}")
    else:
        log.info("No new discoveries from expanded sources")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
