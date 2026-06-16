#!/usr/bin/env python3
"""
scripts/kg_query.py

LLM-augmented research query engine.

Uses the knowledge graph to answer research questions, then augments
with LLM reasoning to synthesize answers.

Usage:
    python scripts/kg_query.py "What are the best implementations of GEX calculation?"
    python scripts/kg_query.py "Find repos related to Hawkes process"
    python scripts/kg_query.py "What papers mention both gamma exposure and VPIN?"
    python scripts/kg_query.py --stats
    python scripts/kg_query.py --port-candidates
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from services.research.knowledge_graph import KnowledgeGraph  # type: ignore[import-not-found]

KG_DB_PATH = REPO_ROOT / "data" / "research_kg.duckdb"


def format_paper_list(papers: List[Dict[str, Any]]) -> str:
    lines = []
    for p in papers[:10]:
        lines.append(f"  [{p['id']}] {p['title'][:80]}")
        if p.get("url"):
            lines.append(f"    {p['url']}")
    return "\n".join(lines)


def format_repo_list(repos: List[Dict[str, Any]]) -> str:
    lines = []
    for r in repos[:10]:
        stars = r.get("stars", 0)
        lines.append(f"  {r['id']} ({stars} stars) — {r.get('license', 'unknown license')}")
        if r.get("cloned_path"):
            lines.append(f"    Path: {r['cloned_path']}")
    return "\n".join(lines)


def format_port_candidates(candidates: List[Dict[str, Any]]) -> str:
    lines = []
    for c in candidates[:10]:
        bench = "✓ benchmark" if c["has_benchmark"] else "✗ no benchmark"
        numba = "✓ Numba" if c["numba_compatible"] else "✗ no Numba"
        target = c.get("target_service", "TBD")
        lines.append(
            f"  {c['name']} ({c['repo_id']}) → {target}\n"
            f"    LOC={c['loc']} | {bench} | {numba} | stars={c.get('stars', 0)}"
        )
    return "\n".join(lines)


def query_concept(kg: KnowledgeGraph, concept: str) -> str:
    """Query papers and repos related to a concept."""
    papers = kg.find_papers_by_concept(concept, limit=15)
    repos = kg.find_repos_by_category(concept, limit=10)

    output = [f"# Research Query: {concept}\n"]
    output.append(f"## Papers ({len(papers)} found)\n")
    output.append(format_paper_list(papers))
    output.append(f"\n## Repos ({len(repos)} found)\n")
    output.append(format_repo_list(repos))
    return "\n".join(output)


def query_port_candidates(kg: KnowledgeGraph) -> str:
    """Find all port candidates."""
    candidates = kg.find_port_candidates(limit=50)
    output = [f"# Port Candidates ({len(candidates)} found)\n"]
    output.append(format_port_candidates(candidates))
    return "\n".join(output)


def query_stats(kg: KnowledgeGraph) -> str:
    """Show KG statistics."""
    stats = kg.get_stats()
    output = ["# Knowledge Graph Statistics\n"]
    for k, v in stats.items():
        output.append(f"  {k}: {v}")

    output.append("\n## Top Concepts\n")
    for c in kg.get_concept_summary(15):
        output.append(f"  {c['name']}: {c['paper_count']} papers")

    return "\n".join(output)


def query_related(kg: KnowledgeGraph, paper_id: str) -> str:
    """Find papers related to a given paper."""
    related = kg.find_related_papers(paper_id, limit=10)
    output = [f"# Papers Related to {paper_id}\n"]
    for r in related:
        output.append(f"  [{r['id']}] {r['title'][:80]}")
        output.append(f"    Shared concepts: {r['shared_concepts']} | Similarity: {r['similarity']:.2f}")
        output.append(f"    {r['url']}")
    return "\n".join(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Knowledge graph query engine")
    parser.add_argument("query", nargs="?", help="Research query (concept name or paper ID)")
    parser.add_argument("--stats", action="store_true", help="Show KG statistics")
    parser.add_argument("--port-candidates", action="store_true", help="Show port candidates")
    parser.add_argument("--related", type=str, help="Find papers related to given paper ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not KG_DB_PATH.exists():
        print(f"Knowledge graph not found at {KG_DB_PATH}")
        print("Run: python scripts/build_kg.py")
        return 1

    kg = KnowledgeGraph(str(KG_DB_PATH))

    if args.stats:
        result = query_stats(kg)
        print(result)
    elif args.port_candidates:
        result = query_port_candidates(kg)
        print(result)
    elif args.related:
        result = query_related(kg, args.related)
        print(result)
    elif args.query:
        result = query_concept(kg, args.query)
        print(result)
    else:
        parser.print_help()

    kg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
