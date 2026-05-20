#!/usr/bin/env python3
"""
migrate_memory.py — Migrate Claude Code memory + PLUR engrams to mem0.

Usage:
    python migrate_memory.py [--dry-run] [--verbose]

Environment:
    MEM0_API_KEY — mem0 Platform API key (required)
"""

import os
import sys
import json
import re
import yaml
import time
import argparse
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────

CLAUDE_MEMORY_DIR = Path.home() / ".claude/projects/-Users-nav-Documents-GitHub-floww/memory"
PLUR_ENGRAMS_FILE = Path.home() / "Documents/GitHub/plur/.plur/engrams.yaml"
OBSIDIAN_VAULT = Path.home() / "Documents/GitHub/Hermes"
MEM0_CONFIG = Path.home() / ".mem0/config.json"
LOG_FILE = CLAUDE_MEMORY_DIR / "_migration_log_2026-05-20.md"

# ── Helpers ────────────────────────────────────────────────────────────────

def get_api_key():
    """Read MEM0_API_KEY from config or env."""
    key = os.environ.get("MEM0_API_KEY", "")
    if not key:
        if MEM0_CONFIG.exists():
            with open(MEM0_CONFIG) as f:
                cfg = json.load(f)
            key = cfg.get("platform", {}).get("api_key", "")
    if not key:
        print("ERROR: MEM0_API_KEY not found. Set it in ~/.mem0/config.json or environment.")
        sys.exit(1)
    return key


def get_user_id():
    """Read default user_id from mem0 config."""
    if MEM0_CONFIG.exists():
        with open(MEM0_CONFIG) as f:
            cfg = json.load(f)
        return cfg.get("defaults", {}).get("user_id", "user_c778280e23af")
    return "user_c778280e23af"


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if m:
        try:
            return yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return {}
    return {}


def extract_body(content: str) -> str:
    """Extract body text after frontmatter."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
    if m:
        return content[m.end():].strip()
    return content.strip()


def mem0_add(text: str, user_id: str, tags: list, metadata: dict, api_key: str, dry_run=False) -> dict:
    """Add a memory entry via mem0 CLI."""
    if dry_run:
        print(f"  [DRY-RUN] Would add: {text[:80]}...")
        return {"status": "dry_run"}

    import subprocess
    cmd = [
        "mem0", "add", text,
        "--user-id", user_id,
        "--tags", ",".join(tags) if tags else "",
        "--metadata", json.dumps(metadata) if metadata else "{}",
        "--agent", "--json"
    ]
    env = {**os.environ, "MEM0_API_KEY": api_key}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"  ERROR: {result.stderr[:200]}")
            return {"status": "error", "error": result.stderr[:200]}
    except Exception as e:
        print(f"  ERROR: {e}")
        return {"status": "error", "error": str(e)}


def mem0_search(query: str, user_id: str, api_key: str, limit=3) -> list:
    """Search mem0 for existing entries."""
    import subprocess
    cmd = [
        "mem0", "search", query,
        "--user-id", user_id,
        "--limit", str(limit),
        "--agent", "--json"
    ]
    env = {**os.environ, "MEM0_API_KEY": api_key}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("data", [])
        return []
    except Exception:
        return []


def is_duplicate(text: str, user_id: str, api_key: str, threshold=0.85) -> bool:
    """Check if a semantically equivalent memory already exists."""
    results = mem0_search(text[:100], user_id, api_key, limit=3)
    for r in results:
        score = r.get("score", 0)
        if score >= threshold:
            return True
    return False


# ── Migration Logic ────────────────────────────────────────────────────────

def migrate_claude_memory(api_key: str, user_id: str, dry_run=False) -> dict:
    """Migrate all Claude Code memory files to mem0."""
    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0, "files": []}

    md_files = sorted(CLAUDE_MEMORY_DIR.glob("*.md"))
    # Skip audit/log files
    skip_files = {"_migration_audit_2026-05-20.md", "_migration_log_2026-05-20.md"}

    for md_file in md_files:
        if md_file.name in skip_files:
            continue
        if md_file.name.startswith("_"):
            continue

        stats["total"] += 1
        content = md_file.read_text()
        fm = parse_frontmatter(content)
        body = extract_body(content)

        name = fm.get("name", md_file.stem)
        mem_type = fm.get("type", "unknown")
        description = fm.get("description", "")

        # Build the memory text
        memory_text = f"{name}: {description}\n\n{body}" if description else f"{name}\n\n{body}"

        # Build tags
        tags = ["claude-code", mem_type]
        if "project" in mem_type:
            tags.append("project")
        if "reference" in mem_type:
            tags.append("reference")

        # Build metadata
        metadata = {
            "source": "claude-code",
            "file": md_file.name,
            "type": mem_type,
            "origin_session": fm.get("originSessionId", ""),
            "migrated_at": datetime.now().isoformat()
        }

        print(f"[{stats['total']}] Migrating: {md_file.name} ({mem_type})")

        # Check for duplicates
        if not dry_run:
            existing = mem0_search(name, user_id, api_key, limit=2)
            if existing and existing[0].get("score", 0) > 0.9:
                print(f"  SKIP: Already exists (score={existing[0].get('score', 0):.2f})")
                stats["skipped"] += 1
                stats["files"].append({"file": md_file.name, "status": "skipped", "reason": "duplicate"})
                continue

        result = mem0_add(memory_text, user_id, tags, metadata, api_key, dry_run)

        if result.get("status") in ("success", "dry_run", "PENDING"):
            stats["added"] += 1
            stats["files"].append({"file": md_file.name, "status": "added"})
            print(f"  OK: {result.get('status', 'ok')}")
        else:
            stats["errors"] += 1
            stats["files"].append({"file": md_file.name, "status": "error", "error": result.get("error", "")})
            print(f"  FAIL: {result.get('error', 'unknown')}")

        # Rate limit: be nice to the API
        if not dry_run:
            time.sleep(1)

    return stats


def migrate_plur_engrams(api_key: str, user_id: str, dry_run=False) -> dict:
    """Migrate PLUR engrams to mem0 with deduplication."""
    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0, "duplicates": 0}

    if not PLUR_ENGRAMS_FILE.exists():
        print("WARNING: PLUR engrams file not found, skipping.")
        return stats

    with open(PLUR_ENGRAMS_FILE) as f:
        data = yaml.safe_load(f)

    engrams = data.get("engrams", [])
    stats["total"] = len(engrams)

    print(f"\nMigrating {len(engrams)} PLUR engrams...")

    for i, eng in enumerate(engrams):
        eng_id = eng.get("id", f"unknown-{i}")
        abstract = eng.get("abstract", "") or ""
        content = eng.get("content", "") or ""
        tags_list = eng.get("tags", []) or []
        created_at = eng.get("created_at", "")
        updated_at = eng.get("updated_at", "")

        # Skip engrams with no meaningful text
        memory_text = abstract or content
        if not memory_text or len(memory_text.strip()) < 10:
            stats["skipped"] += 1
            continue

        # Build tags
        tags = ["plur"] + [str(t) for t in tags_list[:5]]

        # Build metadata
        metadata = {
            "source": "plur",
            "engram_id": eng_id,
            "created_at": created_at,
            "updated_at": updated_at,
            "activation": eng.get("activation", {}),
            "migrated_at": datetime.now().isoformat()
        }

        # Check for duplicates
        if not dry_run:
            if is_duplicate(memory_text, user_id, api_key, threshold=0.85):
                stats["duplicates"] += 1
                if i % 10 == 0:
                    print(f"  [{i+1}/{len(engrams)}] SKIP duplicate: {eng_id}")
                continue

        result = mem0_add(memory_text, user_id, tags, metadata, api_key, dry_run)

        if result.get("status") in ("success", "dry_run", "PENDING"):
            stats["added"] += 1
            if i % 10 == 0 or dry_run:
                print(f"  [{i+1}/{len(engrams)}] Added: {eng_id}")
        else:
            stats["errors"] += 1
            print(f"  [{i+1}/{len(engrams)}] ERROR: {eng_id} - {result.get('error', '')}")

        # Rate limit
        if not dry_run and i % 5 == 0:
            time.sleep(0.5)

    return stats


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrate memory systems to mem0")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--source", choices=["claude", "plur", "all"], default="all",
                        help="Which source to migrate")
    args = parser.parse_args()

    api_key = get_api_key()
    user_id = get_user_id()

    print(f"Migration starting — user_id: {user_id}")
    print(f"Dry run: {args.dry_run}")
    print(f"Source: {args.source}")
    print()

    log_lines = ["# Migration Log — 2026-05-20\n"]

    # Migrate Claude Code memory
    if args.source in ("claude", "all"):
        print("=" * 60)
        print("PHASE 1: Claude Code Memory → mem0")
        print("=" * 60)
        claude_stats = migrate_claude_memory(api_key, user_id, args.dry_run)
        print(f"\nClaude Code: {claude_stats['total']} files, {claude_stats['added']} added, "
              f"{claude_stats['skipped']} skipped, {claude_stats['errors']} errors")
        log_lines.append(f"\n## Claude Code Memory\n")
        log_lines.append(f"- Total: {claude_stats['total']}")
        log_lines.append(f"- Added: {claude_stats['added']}")
        log_lines.append(f"- Skipped: {claude_stats['skipped']}")
        log_lines.append(f"- Errors: {claude_stats['errors']}")

    # Migrate PLUR engrams
    if args.source in ("plur", "all"):
        print("\n" + "=" * 60)
        print("PHASE 2: PLUR Engrams → mem0")
        print("=" * 60)
        plur_stats = migrate_plur_engrams(api_key, user_id, args.dry_run)
        print(f"\nPLUR: {plur_stats['total']} engrams, {plur_stats['added']} added, "
              f"{plur_stats['duplicates']} duplicates, {plur_stats['skipped']} skipped, "
              f"{plur_stats['errors']} errors")
        log_lines.append(f"\n## PLUR Engrams\n")
        log_lines.append(f"- Total: {plur_stats['total']}")
        log_lines.append(f"- Added: {plur_stats['added']}")
        log_lines.append(f"- Duplicates: {plur_stats['duplicates']}")
        log_lines.append(f"- Skipped: {plur_stats['skipped']}")
        log_lines.append(f"- Errors: {plur_stats['errors']}")

    # Write log
    if not args.dry_run:
        LOG_FILE.write_text("\n".join(log_lines))
        print(f"\nLog written to: {LOG_FILE}")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
