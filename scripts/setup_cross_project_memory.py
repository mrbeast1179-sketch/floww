#!/usr/bin/env python3
"""
scripts/setup_cross_project_memory.py — Configure mem0 for multi-project mode.

Tags every existing memory entry with its project, and updates the mem0 config
to support project-scoped queries.

Projects:
  floww          — /Users/nav/Documents/GitHub/floww (main trading terminal)
  gflows         — Gflows project (if exists)
  baby-billy-dvt — Baby Billy DVT project (if exists)
  personal       — Personal notes, preferences, non-project items

Usage:
    python3 scripts/setup_cross_project_memory.py          # live run
    python3 scripts/setup_cross_project_memory.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

CONFIG_PATH = Path.home() / ".mem0" / "config.json"
REPO_ROOT = Path(__file__).resolve().parent.parent

# Project detection rules: path substring → project tag
PROJECT_RULES = [
    ("/floww/", "floww"),
    ("/gflows/", "gflows"),
    ("/baby-billy-dvt/", "baby-billy-dvt"),
    # Default for anything not matching
    (None, "personal"),
]

# Source-based project mapping
SOURCE_PROJECT = {
    "claude-code": "floww",   # Claude Code memory is floww-specific
    "plur": "floww",          # PLUR engrams are floww-specific
    "obsidian": "floww",      # Obsidian vault is floww-specific
}


def get_api_key():
    cfg = json.load(open(CONFIG_PATH))
    return cfg["platform"]["api_key"]


def detect_project(metadata: dict, memory_text: str) -> str:
    """Detect which project a memory entry belongs to."""
    # Check explicit project in metadata
    if "project" in metadata:
        return metadata["project"]

    # Check source
    source = metadata.get("source", "")
    if source in SOURCE_PROJECT:
        return SOURCE_PROJECT[source]

    # Check file references in memory text
    for path_substr, project in PROJECT_RULES:
        if path_substr and path_substr in memory_text:
            return project

    # Check metadata file field
    file_field = metadata.get("file", "")
    for path_substr, project in PROJECT_RULES:
        if path_substr and path_substr in file_field:
            return project

    return "floww"  # Default to floww for this setup


def main():
    parser = argparse.ArgumentParser(description="Setup cross-project memory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = get_api_key()
    from mem0 import MemoryClient
    client = MemoryClient(api_key=api_key)
    user_id = "user_c778280e23af"

    print(f"[cross_project] {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"[cross_project] Fetching all entries for {user_id}...")

    # Fetch all entries
    all_entries = []
    page = 1
    while True:
        result = client.get_all(filters={"user_id": user_id}, page=page, page_size=50)
        if isinstance(result, list):
            all_entries.extend(result)
            if len(result) < 50:
                break
        elif isinstance(result, dict):
            entries = result.get("results", result.get("data", []))
            all_entries.extend(entries)
            if not result.get("next"):
                break
        else:
            break
        page += 1

    print(f"[cross_project] Total entries: {len(all_entries)}")

    # Analyze and tag
    project_counts = {}
    to_update = []

    for entry in all_entries:
        memory_id = entry.get("id")
        memory_text = entry.get("memory", "")
        metadata = entry.get("metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}

        project = detect_project(metadata, memory_text)
        project_counts[project] = project_counts.get(project, 0) + 1

        # Check if already tagged
        existing_tags = entry.get("categories", []) or []
        if isinstance(existing_tags, str):
            existing_tags = [existing_tags]

        needs_update = False
        project_tag = f"project:{project}"
        if project_tag not in existing_tags:
            needs_update = True

        if needs_update:
            to_update.append({
                "id": memory_id,
                "project": project,
                "project_tag": project_tag,
                "existing_tags": existing_tags,
            })

    print(f"\n[cross_project] Project distribution:")
    for proj, count in sorted(project_counts.items()):
        print(f"  {proj}: {count}")

    print(f"\n[cross_project] Entries needing project tag: {len(to_update)}")

    if args.dry_run:
        for entry in to_update[:10]:
            print(f"  Would tag {entry['id'][:8]} → {entry['project_tag']}")
        if len(to_update) > 10:
            print(f"  ... and {len(to_update) - 10} more")
        return

    # Apply tags
    updated = 0
    errors = 0
    for i, entry in enumerate(to_update):
        try:
            new_tags = list(set(entry["existing_tags"] + [entry["project_tag"]]))
            client.update(memory_id=entry["id"], metadata={"project": entry["project"], "tags": new_tags})
            updated += 1
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i+1}/{len(to_update)}")
            time.sleep(0.05)  # reduced from 0.2s
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  WARN: Failed to update {entry['id'][:8]}: {e}")

    print(f"\n[cross_project] Updated {updated}/{len(to_update)} entries ({errors} errors)")

    # Update mem0 config with multi-project settings
    cfg = json.load(open(CONFIG_PATH))
    cfg["multi_project"] = {
        "enabled": True,
        "default_project": "floww",
        "projects": {
            "floww": {"path": str(REPO_ROOT), "description": "Floww trading terminal"},
            "gflows": {"path": "~/Documents/GitHub/gflows", "description": "Gflows project"},
            "baby-billy-dvt": {"path": "~/Documents/GitHub/baby-billy-dvt", "description": "Baby Billy DVT"},
            "personal": {"path": "~", "description": "Personal notes and preferences"},
        },
        "cross_pollination_guard": {
            "financial_queries_default_project_only": True,
            "trading_keywords": ["GEX", "VEX", "options", "trading", "SPY", "QQQ", "floww"],
        },
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[cross_project] Config updated: multi-project mode enabled")


if __name__ == "__main__":
    main()
