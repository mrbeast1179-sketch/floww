#!/usr/bin/env python3
"""
scripts/consolidate_memory_daily.py — Daily memory consolidation for mem0.

Runs daily @ 4am local via cron:
  - Pull all mem0 entries added in last 24h
  - Detect duplicates via embedding cosine-similarity (threshold > 0.95)
  - Merge duplicates: keep richer entry, redirect ID
  - Flag stale references (memory points to deleted file)
  - Write diff to memory/_consolidation_log_<date>.md

Usage:
  python3 scripts/consolidate_memory_daily.py          # live run
  python3 scripts/consolidate_memory_daily.py --dry-run  # print proposed merges
"""

import argparse
import json
import os
import sys
import difflib
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MEMORY_DIR = REPO_ROOT / "memory"
LOG_DIR = MEMORY_DIR / "_consolidation_logs"
CONFIG_PATH = Path.home() / ".mem0" / "config.json"

# Cosine similarity threshold for duplicate detection
DUPLICATE_THRESHOLD = 0.95


def get_mem0_client():
    """Initialize mem0 MemoryClient from config."""
    if not CONFIG_PATH.exists():
        print("ERROR: ~/.mem0/config.json not found. Run mem0 init first.")
        sys.exit(1)

    cfg = json.load(open(CONFIG_PATH))
    api_key = cfg.get("platform", {}).get("api_key")
    if not api_key:
        print("ERROR: No mem0 platform API key in config.")
        sys.exit(1)

    from mem0 import MemoryClient
    return MemoryClient(api_key=api_key)


def get_recent_entries(client, user_id: str, hours: int = 24) -> list[dict]:
    """Fetch entries added in the last N hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%S-00:00")

    all_entries = []
    page = 1
    while True:
        result = client.get_all(
            filters={"user_id": f"{user_id} AND created_at >= '{since_str}'"},
            page=page,
            page_size=50,
        )
        if isinstance(result, dict):
            entries = result.get("results", [])
            all_entries.extend(entries)
            if not result.get("next"):
                break
            page += 1
        elif isinstance(result, list):
            all_entries.extend(result)
            break
        else:
            break
    return all_entries


def get_all_entries(client, user_id: str) -> list[dict]:
    """Fetch all entries for a user."""
    all_entries = []
    page = 1
    while True:
        result = client.get_all(
            filters={"user_id": user_id},
            page=page,
            page_size=50,
        )
        if isinstance(result, dict):
            entries = result.get("results", [])
            all_entries.extend(entries)
            if not result.get("next"):
                break
            page += 1
        elif isinstance(result, list):
            all_entries.extend(result)
            break
        else:
            break
    return all_entries


def text_similarity(a: str, b: str) -> float:
    """Simple text similarity using SequenceMatcher (no embedding needed for consolidation)."""
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_duplicates(entries: list[dict]) -> list[tuple[int, int, float]]:
    """Find duplicate pairs above threshold. Returns list of (i, j, score)."""
    duplicates = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            mem_i = entries[i].get("memory", "")
            mem_j = entries[j].get("memory", "")
            score = text_similarity(mem_i, mem_j)
            if score > DUPLICATE_THRESHOLD:
                duplicates.append((i, j, score))
    return duplicates


def check_stale_references(entry: dict, repo_root: Path) -> list[str]:
    """Check if a memory references files that no longer exist."""
    stale = []
    memory_text = entry.get("memory", "")

    # Look for file path patterns in memory text
    import re
    # Match common file path patterns
    path_patterns = [
        r'`([^`]+\.(?:py|md|yaml|yml|json|txt|sh|js|ts|tsx|jsx))`',
        r'([a-zA-Z0-9_/\-]+\.(?:py|md|yaml|yml|json|txt|sh|js|ts|tsx|jsx))',
    ]
    for pattern in path_patterns:
        for match in re.finditer(pattern, memory_text):
            path_str = match.group(1)
            if path_str.startswith("/"):
                full_path = Path(path_str)
            else:
                full_path = repo_root / path_str
            if not full_path.exists():
                stale.append(path_str)

    return stale


def merge_entries(client, keep: dict, remove: dict) -> bool:
    """Merge two entries: update keep with combined info, delete remove."""
    try:
        # Update the kept entry with combined memory
        combined = keep.get("memory", "")
        if remove.get("memory", "") not in combined:
            combined += f" [Merged: {remove['memory']}]"

        client.update(memory_id=keep["id"], text=combined)
        client.delete(memory_id=remove["id"])
        return True
    except Exception as e:
        print(f"  WARN: merge failed: {e}")
        return False


def write_log(log_path: Path, entries: list[dict], duplicates: list[tuple],
              stale: dict, merged: list, dry_run: bool):
    """Write consolidation log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Memory Consolidation Log — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"",
        f"**Mode:** {'DRY RUN' if dry_run else 'LIVE'}",
        f"**Entries scanned:** {len(entries)}",
        f"**Duplicates found:** {len(duplicates)}",
        f"**Stale references:** {len(stale)}",
        f"**Merged:** {len(merged)}",
        f"",
    ]

    if duplicates:
        lines.append("## Duplicates Detected")
        lines.append("")
        for i, j, score in duplicates:
            ei = entries[i]
            ej = entries[j]
            lines.append(f"- `{ei['id'][:8]}` <-> `{ej['id'][:8]}` (score: {score:.2f})")
            lines.append(f"  - A: {ei.get('memory', '')[:100]}")
            lines.append(f"  - B: {ej.get('memory', '')[:100]}")
        lines.append("")

    if stale:
        lines.append("## Stale References")
        lines.append("")
        for entry_id, refs in stale.items():
            lines.append(f"- `{entry_id[:8]}`: {', '.join(refs)}")
        lines.append("")

    if merged:
        lines.append("## Merged Entries")
        lines.append("")
        for keep_id, remove_id in merged:
            lines.append(f"- Kept `{keep_id[:8]}`, removed `{remove_id[:8]}`")
        lines.append("")

    log_path.write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Daily memory consolidation")
    parser.add_argument("--dry-run", action="store_true", help="Print proposed merges without executing")
    parser.add_argument("--user-id", default="user_c778280e23af", help="mem0 user ID")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back")
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"[consolidate] Starting {mode} for user {args.user_id}")

    client = get_mem0_client()

    # Get recent entries
    recent = get_recent_entries(client, args.user_id, args.hours)
    print(f"[consolidate] Found {len(recent)} entries in last {args.hours}h")

    if not recent:
        print("[consolidate] No recent entries to consolidate.")
        return

    # Get all entries for duplicate detection
    all_entries = get_all_entries(client, args.user_id)
    print(f"[consolidate] Total entries: {len(all_entries)}")

    # Find duplicates among recent entries
    duplicates = find_duplicates(recent)
    print(f"[consolidate] Duplicates found: {len(duplicates)}")

    # Check stale references
    stale = {}
    for entry in recent:
        refs = check_stale_references(entry, REPO_ROOT)
        if refs:
            stale[entry["id"]] = refs
    print(f"[consolidate] Stale references: {len(stale)}")

    # Execute merges
    merged = []
    if not args.dry_run:
        for i, j, score in duplicates:
            # Keep the richer (longer) entry
            ei = recent[i]
            ej = recent[j]
            if len(ei.get("memory", "")) >= len(ej.get("memory", "")):
                keep, remove = ei, ej
            else:
                keep, remove = ej, ei

            print(f"  Merging {remove['id'][:8]} -> {keep['id'][:8]} (score: {score:.2f})")
            if merge_entries(client, keep, remove):
                merged.append((keep["id"], remove["id"]))
    else:
        for i, j, score in duplicates:
            ei = recent[i]
            ej = recent[j]
            print(f"  [DRY RUN] Would merge: {ei['id'][:8]} <-> {ej['id'][:8]} (score: {score:.2f})")
            print(f"    A: {ei.get('memory', '')[:80]}")
            print(f"    B: {ej.get('memory', '')[:80]}")

    # Write log
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_path = LOG_DIR / f"consolidation_{date_str}.md"
    write_log(log_path, recent, duplicates, stale, merged, args.dry_run)
    print(f"[consolidate] Log written to {log_path}")

    # Print summary
    print(f"\n[consolidate] Summary:")
    print(f"  Entries scanned: {len(recent)}")
    print(f"  Duplicates: {len(duplicates)}")
    print(f"  Merged: {len(merged)}")
    print(f"  Stale refs: {len(stale)}")
    print(f"  Total entries: {len(all_entries)}")


if __name__ == "__main__":
    main()
