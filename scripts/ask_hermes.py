#!/usr/bin/env python3
"""
scripts/ask_hermes.py — "ask Hermes" CLI for querying memory + commits + kanban.

Usage:
  ask-hermes "what did agent 7 find in the audit?"
  ask-hermes "trinity confluence" --json
  ask-hermes --project=floww "GEX"
  ask-hermes --all-projects "memory system"

Backend: semantic search over mem0 + git log --grep + kanban cards
Returns: top 3 results with source attribution + one-paragraph synthesis
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
MEMORY_DIR = REPO_ROOT / "memory"
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-nav-Documents-GitHub-floww" / "memory"
CONFIG_PATH = Path.home() / ".mem0" / "config.json"


def get_mem0_client():
    """Initialize mem0 MemoryClient from config."""
    if not CONFIG_PATH.exists():
        return None
    cfg = json.load(open(CONFIG_PATH))
    api_key = cfg.get("platform", {}).get("api_key")
    if not api_key:
        return None
    try:
        from mem0 import MemoryClient
        return MemoryClient(api_key=api_key)
    except Exception:
        return None


def search_mem0(client, query: str, user_id: str = "user_c778280e23af",
                project: str = None, limit: int = 5) -> list[dict]:
    """Search mem0 for relevant memories."""
    if not client:
        return []

    filters = {"user_id": user_id}
    if project:
        filters["metadata"] = {"project": project}

    try:
        results = client.search(
            query=query,
            filters=filters,
            limit=limit,
        )
        if isinstance(results, dict):
            return results.get("results", [])
        return results if isinstance(results, list) else []
    except Exception as e:
        return []


def search_git_log(query: str, limit: int = 5) -> list[dict]:
    """Search git log for relevant commits."""
    try:
        # Build grep pattern from query words
        words = [w for w in query.split() if len(w) > 2]
        if not words:
            return []

        cmd = ["git", "log", "--oneline", "--all", f"--grep={words[0]}"]
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return []

        commits = []
        for line in result.stdout.strip().splitlines()[:limit]:
            if line.strip():
                parts = line.split(None, 1)
                if len(parts) == 2:
                    commits.append({
                        "sha": parts[0],
                        "message": parts[1],
                        "source": "git",
                    })
        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def search_kanban(query: str, limit: int = 5) -> list[dict]:
    """Search kanban cards for relevant content."""
    results = []
    if not KANBAN_DIR.exists():
        return results

    query_lower = query.lower()
    for card_file in KANBAN_DIR.glob("cards/*.md"):
        try:
            content = card_file.read_text()
            # Simple keyword match
            if query_lower in content.lower():
                # Extract title from frontmatter
                title = card_file.stem
                if content.startswith("---"):
                    for line in content.split("\n"):
                        if line.startswith("title:"):
                            title = line.split(":", 1)[1].strip().strip('"')
                            break
                results.append({
                    "title": title,
                    "file": str(card_file.relative_to(REPO_ROOT)),
                    "source": "kanban",
                    "snippet": content[:200],
                })
        except Exception:
            continue

    return results[:limit]


def search_memory_files(query: str, limit: int = 5) -> list[dict]:
    """Search local memory .md files."""
    results = []
    if not CLAUDE_MEMORY_DIR.exists():
        return results

    query_lower = query.lower()
    for mem_file in CLAUDE_MEMORY_DIR.glob("*.md"):
        try:
            content = mem_file.read_text()
            if query_lower in content.lower():
                results.append({
                    "title": mem_file.stem,
                    "file": str(mem_file),
                    "source": "memory_file",
                    "snippet": content[:300],
                })
        except Exception:
            continue

    return results[:limit]


def synthesize_results(mem0_results: list, git_results: list,
                       kanban_results: list, memory_results: list,
                       query: str) -> str:
    """Generate a one-paragraph synthesis of all results."""
    parts = []

    if mem0_results:
        mem_count = len(mem0_results)
        top_mem = mem0_results[0].get("memory", "")[:100] if mem0_results else ""
        parts.append(f"Found {mem_count} memory entries. Top: {top_mem}")

    if git_results:
        commit_count = len(git_results)
        top_commit = git_results[0].get("message", "")[:80] if git_results else ""
        parts.append(f"{commit_count} git commits reference this. Latest: {top_commit}")

    if kanban_results:
        cards = [r["title"] for r in kanban_results[:3]]
        parts.append(f"Kanban cards: {', '.join(cards)}")

    if memory_results:
        files = [r["title"] for r in memory_results[:3]]
        parts.append(f"Memory files: {', '.join(files)}")

    if not parts:
        return f"No results found for '{query}'."

    return " ".join(parts)


def main():
    parser = argparse.ArgumentParser(
        description="Ask Hermes — query memory, commits, and kanban",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ask-hermes "what did agent 7 find in the audit?"
  ask-hermes "trinity confluence" --json
  ask-hermes --project=floww "GEX"
  ask-hermes --all-projects "memory system"
        """
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--project", default=None, help="Filter by project tag")
    parser.add_argument("--all-projects", action="store_true", help="Search all projects (default: current only)")
    parser.add_argument("--limit", type=int, default=3, help="Max results per source")
    parser.add_argument("--user-id", default="user_c778280e23af", help="mem0 user ID")
    args = parser.parse_args()

    # Initialize mem0 client
    client = get_mem0_client()

    # Determine project filter
    project = args.project
    if not project and not args.all_projects:
        # Default to floww for financial/trading queries
        project = "floww"

    # Search all sources
    mem0_results = search_mem0(client, args.query, args.user_id, project, args.limit)
    git_results = search_git_log(args.query, args.limit)
    kanban_results = search_kanban(args.query, args.limit)
    memory_results = search_memory_files(args.query, args.limit)

    # Combine and rank
    all_results = []
    for r in mem0_results:
        r["source_type"] = "mem0"
        all_results.append(r)
    for r in git_results:
        r["source_type"] = "git"
        all_results.append(r)
    for r in kanban_results:
        r["source_type"] = "kanban"
        all_results.append(r)
    for r in memory_results:
        r["source_type"] = "memory_file"
        all_results.append(r)

    # Synthesize
    synthesis = synthesize_results(mem0_results, git_results, kanban_results, memory_results, args.query)

    if args.json:
        output = {
            "query": args.query,
            "project": project,
            "synthesis": synthesis,
            "results": {
                "mem0": mem0_results,
                "git": git_results,
                "kanban": kanban_results,
                "memory_files": memory_results,
            },
            "total": len(all_results),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"Query: {args.query}")
        print(f"Project: {project or 'all'}")
        print(f"Results: {len(all_results)}")
        print()
        print(f"Synthesis: {synthesis}")
        print()

        if mem0_results:
            print("## Memory (mem0)")
            for r in mem0_results[:args.limit]:
                mem = r.get("memory", "")[:120]
                print(f"  - {mem}")
            print()

        if git_results:
            print("## Git Commits")
            for r in git_results[:args.limit]:
                print(f"  - {r['sha'][:8]}: {r['message']}")
            print()

        if kanban_results:
            print("## Kanban Cards")
            for r in kanban_results[:args.limit]:
                print(f"  - {r['title']} ({r['file']})")
            print()

        if memory_results:
            print("## Memory Files")
            for r in memory_results[:args.limit]:
                print(f"  - {r['title']}: {r['file']}")


if __name__ == "__main__":
    main()
