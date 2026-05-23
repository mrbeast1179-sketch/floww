#!/usr/bin/env python3
"""
todo_extractor.py — Auto-Spawn Follow-Up Kanban Cards
Agent 8 (Hermes) runs this every 5 minutes to:
  1. Scan commit bodies + code comments for TODO/FIXME/follow-up/XXX
  2. Deduplicate by content hash
  3. Create kanban cards for new items
  4. Assign to appropriate agent based on file path

Usage:
    python3 todo_extractor.py [--dry-run] [--verbose]
    
Exit codes:
    0 = success
    1 = error
"""

import sys
import os
import re
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

KANBAN_DIR = Path(__file__).resolve().parent.parent
CARD_DIR = KANBAN_DIR / "cards"
EXTRACTED_DIR = KANBAN_DIR / "extracted_todos"
EXTRACTED_DIR.mkdir(exist_ok=True)

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Agent routing — file path → assignee
# ──────────────────────────────────────────────────────────────────────────────

AGENT_ROUTING = [
    (r"backend/services/ingestion_pipeline|backend/services/mock_schwab|backend/routes/market_data", "Agent 1"),
    (r"backend/services/anomaly_detector|backend/services/gex_aggregator|backend/services/bs_calculator|backend/services/cpr_calculator|backend/services/ml/", "Agent 2"),
    (r"backend/services/dash_ui|frontend/|frontend/serve\.js", "Agent 3"),
    (r"backend/tests/", "Agent 4"),
    (r"backend/services/risk/", "Agent 8"),
    (r"backend/services/observability|backend/services/alert", "Agent 10"),
    (r"backend/services/memory|backend/services/code_suggester", "Agent 9"),
    (r"backend/services/research|data/external_research", "Agent 6"),
    (r"SECURITY|backend/middleware|backend/services/audit", "Agent 7"),
]

DEFAULT_AGENT = "Agent 8"  # Orchestrator gets unrecognized paths


def route_to_agent(file_path: str) -> str:
    """Determine which agent owns a file path."""
    for pattern, agent in AGENT_ROUTING:
        if re.search(pattern, file_path):
            return agent
    return DEFAULT_AGENT


# ──────────────────────────────────────────────────────────────────────────────
# TODO extraction
# ──────────────────────────────────────────────────────────────────────────────

TODO_PATTERNS = [
    re.compile(r"#\s*(TODO|FIXME|follow-up|XXX)\s*[:\s]\s*(.+)", re.IGNORECASE),
    re.compile(r"//\s*(TODO|FIXME|follow-up|XXX)\s*[:\s]\s*(.+)", re.IGNORECASE),
    re.compile(r"/\*\s*(TODO|FIXME|follow-up|XXX)\s*[:\s]\s*(.+)", re.IGNORECASE),
    re.compile(r'"""\s*(TODO|FIXME|follow-up|XXX)\s*[:\s]\s*(.+)', re.IGNORECASE),
]

COMMIT_PATTERN = re.compile(r"(TODO|FIXME|follow-up|XXX)\s*[:\s]\s*(.+)", re.IGNORECASE)


def scan_code_comments(repo_root: Path) -> list[dict]:
    """Scan all Python/JS files for TODO/FIXME/XXX comments."""
    items = []
    extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh", ".yaml", ".yml"}
    
    for fpath in repo_root.rglob("*"):
        if fpath.suffix not in extensions:
            continue
        if ".venv" in str(fpath) or "node_modules" in str(fpath) or "__pycache__" in str(fpath):
            continue
        
        try:
            content = fpath.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        
        for line_num, line in enumerate(content.split("\n"), 1):
            for pattern in TODO_PATTERNS:
                match = pattern.search(line)
                if match:
                    tag = match.group(1).upper()
                    text = match.group(2).strip()
                    items.append({
                        "file": str(fpath.relative_to(repo_root)),
                        "line": line_num,
                        "tag": tag,
                        "text": text,
                        "source": "code_comment",
                    })
    
    return items


def scan_commit_bodies(repo_root: Path, since_hours: int = 24) -> list[dict]:
    """Scan recent commit bodies for TODO/FIXME references."""
    items = []
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since_hours} hours ago", "--format=%H %s%n%b"],
            capture_output=True, text=True, cwd=str(repo_root), timeout=10
        )
        if result.returncode != 0:
            return items
        
        for block in result.stdout.split("\n\n"):
            lines = block.strip().split("\n")
            if not lines:
                continue
            # First line is "HASH subject"
            for line in lines[1:]:  # Body lines
                match = COMMIT_PATTERN.search(line)
                if match:
                    tag = match.group(1).upper()
                    text = match.group(2).strip()
                    items.append({
                        "file": "commit",
                        "line": 0,
                        "tag": tag,
                        "text": text,
                        "source": "commit_body",
                        "commit": lines[0][:8],
                    })
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Deduplication
# ──────────────────────────────────────────────────────────────────────────────

def content_hash(item: dict) -> str:
    """Generate a unique hash for a TODO item."""
    key = f"{item['file']}:{item['line']}:{item['text']}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def is_already_extracted(h: str) -> bool:
    """Check if a TODO with this hash has already been extracted."""
    return (EXTRACTED_DIR / f"{h}.sentinel").exists()


def mark_extracted(h: str):
    """Mark a TODO as extracted."""
    (EXTRACTED_DIR / f"{h}.sentinel").write_text(
        datetime.now(timezone.utc).isoformat()
    )


from typing import Optional


def create_card(item: dict, dry_run: bool = False) -> Optional[str]:
    """Create a kanban card for a TODO item. Returns card_id or None."""
    h = content_hash(item)
    
    if is_already_extracted(h):
        return None
    
    tag = item["tag"]
    text = item["text"]
    file_path = item["file"]
    agent = route_to_agent(file_path)
    
    # Generate card ID
    card_id = f"AUTO-{h[:8]}"
    card_file = CARD_DIR / f"{card_id}.md"
    
    if card_file.exists():
        mark_extracted(h)
        return None
    
    title = f"[{tag}] {text[:60]}"
    if len(text) > 60:
        title += "..."
    
    body = f"""# {title}

## Source
- **File:** `{file_path}`
- **Line:** {item.get('line', 'N/A')}
- **Tag:** {tag}
- **Extracted:** {datetime.now(timezone.utc).isoformat()}

## Context
{text}

## Acceptance Criteria
- [ ] {text}
- [ ] Verify fix doesn't break existing tests
- [ ] Commit with conventional message: `fix({file_path.split('/')[0]}): {text[:40]}`
"""
    
    if not dry_run:
        card_file.write_text(
            f"---\n"
            f"id: {card_id}\n"
            f"title: {title}\n"
            f"assignee: {agent}\n"
            f"source: todo_extractor.py\n"
            f"auto: true\n"
            f"status: ready\n"
            f"created: {datetime.now(timezone.utc).isoformat()}\n"
            f"file: {file_path}\n"
            f"line: {item.get('line', 0)}\n"
            f"tag: {tag}\n"
            f"---\n\n"
            f"{body}\n"
        )
        mark_extracted(h)
    
    return card_id


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    repo_root = KANBAN_DIR.parent
    
    print(f"🔍 TODO Extractor — {datetime.now(timezone.utc).isoformat()}")
    print(f"   Repo: {repo_root}")
    print(f"   Dry run: {dry_run}")
    print()
    
    # Scan
    code_items = scan_code_comments(repo_root)
    commit_items = scan_commit_bodies(repo_root)
    all_items = code_items + commit_items
    
    if verbose:
        print(f"   Found {len(code_items)} code comments, {len(commit_items)} commit refs")
    
    # Deduplicate and create cards
    created = 0
    skipped = 0
    
    for item in all_items:
        h = content_hash(item)
        if is_already_extracted(h):
            skipped += 1
            continue
        
        card_id = create_card(item, dry_run=dry_run)
        if card_id:
            created += 1
            agent = route_to_agent(item["file"])
            print(f"   ✅ Created {card_id} → {agent}: {item['text'][:50]}")
        else:
            skipped += 1
    
    print(f"\n   Created: {created} | Skipped (dupes): {skipped} | Total found: {len(all_items)}")
    
    if created > 0:
        print(f"   📋 {len(all_items)} TODO items → {created} new kanban cards")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
