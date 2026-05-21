#!/usr/bin/env python3
"""
scripts/build_kg.py

Populate the knowledge graph from existing data:
- data/external_research/discoveries_*.json → paper nodes
- data/external_research/code_links_*.json → paper→repo edges
- data/github-repos/cloned-manifest.json → repo nodes
- data/external_research/*_findings.md → function nodes + edges
- backend/services/*.py → service nodes

Usage:
    python scripts/build_kg.py [--reset]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.research.knowledge_graph import KnowledgeGraph

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_kg")

EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"
CLONED_MANIFEST = REPO_ROOT / "data" / "github-repos" / "cloned-manifest.json"
SERVICES_DIR = REPO_ROOT / "backend" / "services"
KG_DB_PATH = REPO_ROOT / "data" / "research_kg.duckdb"

# Concept extraction patterns
CONCEPT_PATTERNS = {
    "gamma_exposure": ["gamma exposure", "gex", "dealer gamma", "gamma positioning"],
    "vpin": ["vpin", "volume-synchronized", "flow toxicity", "order flow toxicity"],
    "hawkes_process": ["hawkes", "self-exciting", "branching ratio", "excitation kernel"],
    "vol_surface": ["vol surface", "implied volatility surface", "svi", "sabr", "vol skew", "vol smile"],
    "lob_dynamics": ["limit order book", "order book", "lob", "bid ask spread", "market depth"],
    "options_pricing": ["black scholes", "heston", "jump diffusion", "merton", "local volatility"],
    "market_making": ["market making", "market maker", "inventory risk", "avellaneda-stoikov"],
    "options_greeks": ["delta", "gamma", "theta", "vega", "rho", "greeks", "vanna", "charm"],
    "anomaly_detection": ["anomaly detection", "autoencoder", "reconstruction error", "1d-cnn"],
    "dealer_positioning": ["dealer position", "dealer hedge", "gamma squeeze", "pin risk", "max pain"],
    "stochastic_volatility": ["stochastic volatility", "heston model", "rough volatility", "quadratic rough"],
    "machine_learning_finance": ["machine learning", "deep learning", "neural network", "transformer", "lstm"],
    "reinforcement_learning": ["reinforcement learning", "q-learning", "policy gradient", "rl agent"],
    "high_frequency_trading": ["high frequency", "hft", "latency", "market microstructure"],
    "risk_management": ["risk management", "value at risk", "var", "expected shortfall", "drawdown"],
}


def extract_concepts(text: str) -> List[tuple]:
    """Extract concepts from text. Returns list of (concept_id, relevance)."""
    text_lower = text.lower()
    found = []
    for concept_id, patterns in CONCEPT_PATTERNS.items():
        matches = sum(1 for p in patterns if p in text_lower)
        if matches > 0:
            relevance = min(matches / len(patterns), 1.0)
            found.append((concept_id, relevance))
    return found


def load_discoveries() -> List[Dict]:
    """Load all discovery records from JSON files."""
    papers = []
    seen_ids: Set[str] = set()
    for fp in sorted(EXTERNAL_RESEARCH_DIR.glob("discoveries_*.json")):
        try:
            data = json.loads(fp.read_text())
            for d in data.get("discoveries", []):
                if d.get("id") not in seen_ids:
                    papers.append(d)
                    seen_ids.add(d.get("id"))
        except Exception as exc:
            log.warning(f"Failed to load {fp}: {exc}")
    return papers


def load_code_links() -> List[Dict]:
    """Load all code link records."""
    links = []
    for fp in sorted(EXTERNAL_RESEARCH_DIR.glob("code_links_*.json")):
        try:
            data = json.loads(fp.read_text())
            for c in data.get("candidates", []):
                links.append(c)
        except Exception as exc:
            log.warning(f"Failed to load {fp}: {exc}")
    return links


def load_cloned_repos() -> List[Dict]:
    """Load cloned repo manifest."""
    if not CLONED_MANIFEST.exists():
        return []
    try:
        data = json.loads(CLONED_MANIFEST.read_text())
        repos = []
        for name in data.get("cloned", []):
            parts = name.split("/")
            if len(parts) == 2:
                repos.append({
                    "id": name,
                    "owner": parts[0],
                    "repo": parts[1],
                    "cloned_path": str(REPO_ROOT / "data" / "github-repos" / "cloned" / f"{parts[0]}_{parts[1]}"),
                })
        return repos
    except Exception as exc:
        log.warning(f"Failed to load cloned manifest: {exc}")
        return []


def load_findings() -> List[Dict]:
    """Load pattern extraction findings."""
    findings = []
    for fp in sorted(EXTERNAL_RESEARCH_DIR.glob("*_findings.md")):
        try:
            content = fp.read_text()
            # Parse findings markdown
            current_repo = None
            category = ""
            for line in content.splitlines():
                if line.startswith("### ") and not line.startswith("####"):
                    current_repo = line[4:].strip()
                elif line.startswith("#### "):
                    category = line[5:].strip()
                elif "**Key functions**:" in line:
                    pass
                elif line.strip().startswith("- `") and current_repo:
                    fn = line.strip().lstrip("- `").rstrip("`")
                    if ":" in fn:
                        file_path, fn_name = fn.split(":", 1)
                        findings.append({
                            "repo_name": current_repo,
                            "category": category if 'category' in locals() else "",
                            "file_path": file_path,
                            "function_name": fn_name,
                        })
        except Exception as exc:
            log.warning(f"Failed to parse {fp}: {exc}")
    return findings


def discover_services() -> List[Dict]:
    """Discover Hermes service files."""
    services = []
    if SERVICES_DIR.exists():
        for py_file in SERVICES_DIR.rglob("*.py"):
            if py_file.name.startswith("__"):
                continue
            rel_path = str(py_file.relative_to(REPO_ROOT))
            service_id = rel_path.replace("/", ".").replace(".py", "")
            # Extract docstring
            try:
                content = py_file.read_text(errors="replace")
                docstring = ""
                if '"""' in content:
                    match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                    if match:
                        docstring = match.group(1).strip()[:200]
            except Exception:
                docstring = ""
            services.append({
                "id": service_id,
                "file_path": rel_path,
                "description": docstring,
            })
    return services


def build_graph(kg: KnowledgeGraph, reset: bool = False) -> Dict[str, int]:
    """Build the knowledge graph from all data sources."""
    stats = {"papers": 0, "repos": 0, "functions": 0, "services": 0, "concepts": 0, "edges": 0}

    # 1. Insert concepts
    log.info("Inserting concepts...")
    for concept_id, patterns in CONCEPT_PATTERNS.items():
        kg.upsert_concept(concept_id, concept_id.replace("_", " ").title(), "research_concept",
                          f"Patterns: {', '.join(patterns[:3])}")
        stats["concepts"] += 1

    # 2. Insert papers
    log.info("Loading discoveries...")
    papers = load_discoveries()
    log.info(f"  {len(papers)} papers")
    for paper in papers:
        kg.upsert_paper(paper)
        stats["papers"] += 1

        # Extract concepts from title + abstract
        text = f"{paper.get('title', '')} {paper.get('abstract', '')}"
        for concept_id, relevance in extract_concepts(text):
            kg.add_paper_concept_edge(paper["id"], concept_id, relevance)
            stats["edges"] += 1

    # 3. Insert repos
    log.info("Loading cloned repos...")
    repos = load_cloned_repos()
    log.info(f"  {len(repos)} repos")
    for repo in repos:
        kg.upsert_repo(repo)
        stats["repos"] += 1

    # 4. Paper → Repo edges from code links
    log.info("Loading code links...")
    code_links = load_code_links()
    log.info(f"  {len(code_links)} code link candidates")
    for link in code_links:
        paper_id = link.get("paper_id", "")
        for url in link.get("code_urls", []):
            # Extract owner/repo from URL
            match = re.search(r"github\.com/([^/]+)/([^/]+)", url)
            if match:
                repo_id = f"{match.group(1)}/{match.group(2)}"
                kg.add_paper_repo_edge(paper_id, repo_id)
                stats["edges"] += 1

    # 5. Insert services
    log.info("Discovering services...")
    services = discover_services()
    log.info(f"  {len(services)} services")
    for svc in services:
        kg.upsert_service(svc["id"], svc["file_path"], svc["description"])
        stats["services"] += 1

        # Extract concepts from service file
        try:
            content = (REPO_ROOT / svc["file_path"]).read_text(errors="replace")
            for concept_id, relevance in extract_concepts(content):
                kg.add_service_concept_edge(svc["id"], concept_id)
                stats["edges"] += 1
        except Exception:
            pass

    # 6. Insert functions from findings
    log.info("Loading function findings...")
    findings = load_findings()
    log.info(f"  {len(findings)} function findings")
    for fn in findings:
        repo_name = fn.get("repo_name", "")
        fn_name = fn.get("function_name", "")
        file_path = fn.get("file_path", "")
        category = fn.get("category", "")

        if not fn_name or not repo_name:
            continue

        fn_id = f"{repo_name}/{file_path}:{fn_name}"
        kg.upsert_function({
            "id": fn_id,
            "name": fn_name,
            "file_path": file_path,
            "repo_id": repo_name,
            "category": category,
        })
        stats["functions"] += 1

        kg.add_repo_function_edge(repo_name, fn_id)
        stats["edges"] += 1

        # Map category to concept
        for concept_id in CONCEPT_PATTERNS:
            if concept_id.lower() in category.lower():
                kg.add_function_concept_edge(fn_id, concept_id)
                stats["edges"] += 1

    # 7. Compute paper similarity
    log.info("Computing paper similarity...")
    sim_count = kg.compute_paper_similarity()
    stats["edges"] += sim_count

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Build knowledge graph from research data")
    parser.add_argument("--reset", action="store_true", help="Reset the database")
    parser.add_argument("--stats-only", action="store_true", help="Only show stats")
    args = parser.parse_args()

    if args.reset and KG_DB_PATH.exists():
        KG_DB_PATH.unlink()
        log.info(f"Removed existing KG: {KG_DB_PATH}")

    kg = KnowledgeGraph(str(KG_DB_PATH))
    kg.ensure_schema()

    if args.stats_only:
        stats = kg.get_stats()
        log.info("Knowledge Graph Stats:")
        for k, v in stats.items():
            log.info(f"  {k}: {v}")
        kg.close()
        return 0

    log.info("Building knowledge graph...")
    stats = build_graph(kg, reset=args.reset)

    log.info("Final stats:")
    for k, v in stats.items():
        log.info(f"  {k}: {v}")

    # Show concept summary
    log.info("\nTop concepts:")
    for c in kg.get_concept_summary(10):
        log.info(f"  {c['name']}: {c['paper_count']} papers")

    # Show port candidates
    ports = kg.find_port_candidates(5)
    if ports:
        log.info(f"\nTop port candidates:")
        for p in ports:
            log.info(f"  {p['name']} ({p['repo_id']}) → {p['target_service']} | "
                     f"LOC={p['loc']} benchmark={p['has_benchmark']} stars={p['stars']}")

    kg.close()
    log.info(f"Knowledge graph saved to: {KG_DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
