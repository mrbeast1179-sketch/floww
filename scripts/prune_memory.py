#!/usr/bin/env python3
"""
scripts/prune_memory.py — Nightly memory pruning policy.

Runs nightly via cron:
  - type=session entries older than 30d → move to memory/_archive/<year>/<month>/
  - Maintain memory/_archive/INDEX.md as a searchable index
  - Durable types (project_*, reference_*, feedback_*) never pruned

Usage:
  python3 scripts/prune_memory.py          # live run
  python3 scripts/prune_memory.py --dry-run  # show what would be archived
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-nav-Documents-GitHub-floww" / "memory"
ARCHIVE_DIR = CLAUDE_MEMORY_DIR / "_archive"
INDEX_FILE = ARCHIVE_DIR / "INDEX.md"

# Types that are NEVER pruned
DURABLE_TYPES = {"project", "reference", "feedback", "decision", "config"}
# Types that CAN be pruned after 30 days
PRUNABLE_TYPES = {"session"}
MAX_ACTIVE_FILES = 50
PRUNE_AFTER_DAYS = 30


def get_memory_type(filename: str) -> str:
    """Extract memory type from filename (e.g., 'session_2026-05-18_final.md' -> 'session')."""
    stem = Path(filename).stem
    # Remove date suffixes
    parts = stem.replace("_final", "").replace("_handoff", "").split("_")
    if parts:
        return parts[0]
    return "unknown"


def is_prunable(filename: str, modified_time: datetime) -> bool:
    """Check if a memory file should be pruned."""
    mem_type = get_memory_type(filename)

    # Never prune durable types
    if mem_type in DURABLE_TYPES:
        return False

    # Only prune session types
    if mem_type not in PRUNABLE_TYPES:
        return False

    # Check age
    age = datetime.now(timezone.utc) - modified_time
    return age > timedelta(days=PRUNE_AFTER_DAYS)


def archive_file(src: Path, archive_dir: Path) -> Path:
    """Move a file to the archive directory."""
    dst = archive_dir / src.name
    shutil.move(str(src), str(dst))
    return dst


def update_index(index_file: Path, entries: list[dict]):
    """Update the archive INDEX.md."""
    lines = [
        "# Memory Archive Index",
        f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "| File | Type | Archived | Original Path |",
        "|------|------|----------|---------------|",
    ]
    for entry in entries:
        lines.append(
            f"| {entry['filename']} | {entry['type']} | {entry['archived']} | {entry['original']} |"
        )

    index_file.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Nightly memory pruning")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived")
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"[prune] Starting {mode}")

    if not CLAUDE_MEMORY_DIR.exists():
        print(f"[prune] Memory dir not found: {CLAUDE_MEMORY_DIR}")
        return

    # Count current files
    all_files = list(CLAUDE_MEMORY_DIR.glob("*.md"))
    print(f"[prune] Active memory files: {len(all_files)}")

    # Find prunable files
    prunable = []
    kept = []

    for f in all_files:
        if f.name.startswith("_"):
            kept.append(f)
            continue

        stat = f.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        if is_prunable(f.name, mtime):
            prunable.append((f, mtime))
        else:
            kept.append(f)

    print(f"[prune] Prunable: {len(prunable)}, Kept: {len(kept)}")

    if not prunable:
        print("[prune] Nothing to prune.")
        return

    # Archive files
    archived_entries = []
    for f, mtime in prunable:
        year = mtime.strftime("%Y")
        month = mtime.strftime("%m")
        archive_subdir = ARCHIVE_DIR / year / month

        if not args.dry_run:
            archive_subdir.mkdir(parents=True, exist_ok=True)
            dst = archive_file(f, archive_subdir)
            print(f"  Archived: {f.name} -> {dst}")
        else:
            print(f"  [DRY RUN] Would archive: {f.name} -> {archive_subdir / f.name}")

        archived_entries.append({
            "filename": f.name,
            "type": get_memory_type(f.name),
            "archived": mtime.strftime("%Y-%m-%d"),
            "original": str(f.relative_to(REPO_ROOT)),
        })

    # Update index
    if not args.dry_run and archived_entries:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        # Load existing index entries
        existing = []
        if INDEX_FILE.exists():
            # Parse existing entries (simple approach: just append)
            pass
        update_index(INDEX_FILE, archived_entries)
        print(f"[prune] Index updated: {INDEX_FILE}")

    # Summary
    remaining = len(kept)
    print(f"\n[prune] Summary:")
    print(f"  Archived: {len(archived_entries)}")
    print(f"  Remaining active: {remaining}")
    if remaining > MAX_ACTIVE_FILES:
        print(f"  WARNING: Active files ({remaining}) exceeds target ({MAX_ACTIVE_FILES})")


if __name__ == "__main__":
    main()
