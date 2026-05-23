#!/usr/bin/env python3
"""
kanban_watcher.py — Agent 8 background loop for Project Oracle.

Every 5 minutes:
  1. git pull --rebase origin main
  2. For each in_progress card: scan git log for new commits referencing card_id
  3. If no commit in 30min → mark blocked, log to INCIDENTS.md
  4. Regenerate SWARM_STATUS.md
  5. Auto-archive done cards older than 24h

Usage:
  python3 kanban_watcher.py          # single pass
  python3 kanban_watcher.py --loop   # continuous loop (background)
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
CLOSED_DIR = KANBAN_DIR / "closed"
BOARD_FILE = KANBAN_DIR / "board.yaml"
STATUS_FILE = KANBAN_DIR / "SWARM_STATUS.md"
INCIDENTS_FILE = KANBAN_DIR / "INCIDENTS.md"

BLOCKER_THRESHOLD = timedelta(minutes=30)
ARCHIVE_AFTER = timedelta(hours=24)


def git_pull():
    """Pull latest from origin."""
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def git_log_for_card(card_id: str, since: str = None) -> list[str]:
    """Return commit SHAs referencing card_id since last check."""
    cmd = ["git", "log", "--oneline", f"--grep={card_id}"]
    if since:
        cmd.append(f"--since={since}")
    try:
        result = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return []
        return [line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def parse_card(card_path: Path) -> dict:
    """Parse a card .md file, returning frontmatter dict + body."""
    text = card_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        frontmatter = {}
    if "id" not in frontmatter:
        frontmatter["id"] = card_path.stem
    frontmatter["_body"] = parts[2]
    frontmatter["_file"] = str(card_path)
    return frontmatter


def write_card(card_path: Path, frontmatter: dict, body: str):
    """Write card frontmatter + body back to file."""
    # Remove internal keys
    fm = {k: v for k, v in frontmatter.items() if not k.startswith("_")}
    yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    content = f"---\n{yaml_str}---\n{body}"
    card_path.write_text(content, encoding="utf-8")


def load_board() -> dict:
    """Load board.yaml."""
    if not BOARD_FILE.exists():
        return {}
    return yaml.safe_load(BOARD_FILE.read_text()) or {}


def all_cards() -> list[dict]:
    """Load all card files."""
    cards = []
    for f in sorted(CARDS_DIR.glob("*.md")):
        card = parse_card(f)
        if card:
            cards.append(card)
    return cards


def cards_by_status(cards: list[dict], status: str) -> list[dict]:
    return [c for c in cards if c.get("status") == status]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def update_card_commits(card: dict) -> bool:
    """Check git log for new commits on this card. Returns True if new commits found."""
    card_id = card.get("id", "")
    existing = card.get("commits", [])
    if not isinstance(existing, list):
        existing = []

    new_shas = git_log_for_card(card_id)
    fresh = [sha for sha in new_shas if sha not in existing]
    if fresh:
        card["commits"] = existing + fresh
        card["last_update"] = now_iso()
        return True
    return False


def check_blocker(card: dict) -> bool:
    """Return True if card should be marked blocked (no update in 30min)."""
    last = card.get("last_update")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt > BLOCKER_THRESHOLD
    except (ValueError, TypeError):
        return True


def log_incident(card: dict, reason: str):
    """Append an incident entry to INCIDENTS.md."""
    card_id = card.get("id", "unknown")
    assignee = card.get("assignee", "unknown")
    ts = now_iso()
    entry = f"""
## {ts} — {card_id}
- **Assignee:** {assignee}
- **Symptoms:** {reason}
- **Root Cause:** Agent may be stuck or waiting on external resource
- **Resolution:** Marked BLOCKED; awaiting architect (Nav) triage
- **Prevention:** Agent-hardening: add timeout retry + state checkpointing
"""
    with open(INCIDENTS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def enforce_wip_limit(cards: list[dict], board: dict) -> list[dict]:
    """If in_progress exceeds WIP limit, move excess back to ready."""
    in_prog = cards_by_status(cards, "in_progress")
    wip_limit = 6
    for col in board.get("columns", []):
        if col["id"] == "in_progress":
            wip_limit = col.get("wip_limit", 6)
            break

    if len(in_prog) <= wip_limit:
        return cards

    # Sort by last_update (oldest first), keep the newest wip_limit
    in_prog.sort(key=lambda c: c.get("last_update", ""))
    excess = in_prog[:len(in_prog) - wip_limit]
    for card in excess:
        card["status"] = "ready"
        card["blockers"] = card.get("blockers", []) + [
            f"WIP limit enforcement: moved from in_progress to ready at {now_iso()}"
        ]
    return cards


def auto_archive(cards: list[dict]) -> list[dict]:
    """Move done cards older than 24h to closed/."""
    done = cards_by_status(cards, "done")
    remaining = [c for c in cards if c.get("status") != "done"]

    for card in done:
        last = card.get("last_update", "")
        try:
            last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - last_dt > ARCHIVE_AFTER:
                # Move to closed
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                closed_subdir = CLOSED_DIR / date_str
                closed_subdir.mkdir(parents=True, exist_ok=True)
                src = Path(card["_file"])
                dst = closed_subdir / src.name
                src.rename(dst)
                continue  # Don't add back to remaining
        except (ValueError, TypeError):
            pass
        remaining.append(card)

    return remaining


def render_status(cards: list[dict]):
    """Write SWARM_STATUS.md."""
    backlog = cards_by_status(cards, "backlog")
    ready = cards_by_status(cards, "ready")
    in_prog = cards_by_status(cards, "in_progress")
    review = cards_by_status(cards, "review")
    done = cards_by_status(cards, "done")
    blocked = [c for c in cards if "blocked" in str(c.get("status", "")) or c.get("blockers")]

    ts = now_iso()

    lines = [
        "# SWARM STATUS — Project Oracle Kanban",
        f"# Generated: {ts} by Agent 8 (Hermes)",
        "# This file IS the 30-minute report. Nav can `cat` it anytime.",
        "",
        "## Board Summary",
        "",
        "| Column | Count | WIP Limit |",
        "|--------|-------|-----------|",
        f"| Backlog | {len(backlog)} | - |",
        f"| Ready | {len(ready)} | 20 |",
        f"| In Progress | {len(in_prog)} | 6 |",
        f"| Review | {len(review)} | 4 |",
        f"| Done | {len(done)} | 20 |",
        "",
    ]

    # In Progress table
    lines.append("## In Progress")
    lines.append("")
    if in_prog:
        lines.append("| Card | Assignee | Last Update | Commits | Blockers |")
        lines.append("|------|----------|-------------|---------|----------|")
        for c in in_prog:
            cid = c.get("id", "")
            assignee = c.get("assignee", "")
            last = c.get("last_update", "")
            n_commits = len(c.get("commits", []))
            blockers = ", ".join(c.get("blockers", [])) or "-"
            lines.append(f"| {cid} | {assignee} | {last} | {n_commits} | {blockers} |")
    else:
        lines.append("None.")
    lines.append("")

    # Ready table
    lines.append("## Ready (dispatch order)")
    lines.append("")
    if ready:
        lines.append("| Card | Assignee | Est. Hours | Skills |")
        lines.append("|------|----------|------------|--------|")
        for c in ready:
            cid = c.get("id", "")
            assignee = c.get("assignee", "")
            est = c.get("estimate_hours", "?")
            skills = c.get("skill", "").split(" + ")[0][:40]
            lines.append(f"| {cid} | {assignee} | {est}h | {skills} |")
    else:
        lines.append("None.")
    lines.append("")

    # Blocked
    lines.append("## Blocked")
    lines.append("")
    if blocked:
        for c in blocked:
            cid = c.get("id", "")
            blockers = c.get("blockers", [])
            lines.append(f"- **{cid}**: {', '.join(blockers)}")
    else:
        lines.append("None.")
    lines.append("")

    # Recent incidents
    lines.append("## Recent Incidents")
    lines.append("")
    if INCIDENTS_FILE.exists():
        inc_text = INCIDENTS_FILE.read_text()
        # Show last incident block
        blocks = inc_text.split("## ")
        if len(blocks) > 1:
            lines.append(f"```\n## {blocks[-1].strip()}\n```")
        else:
            lines.append("None.")
    else:
        lines.append("None.")
    lines.append("")

    next_run = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"---")
    lines.append(f"*Next watcher run: {next_run}*")
    lines.append(f"*See kanban/INCIDENTS.md for full incident log*")

    STATUS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def single_pass():
    """Execute one watcher pass."""
    git_pull()

    board = load_board()
    cards = all_cards()

    # Check each in_progress card
    for card in cards:
        if card.get("status") == "in_progress":
            updated = update_card_commits(card)
            if not updated and check_blocker(card):
                card["status"] = "blocked"
                card["blockers"] = card.get("blockers", []) + [
                    f"No commit in 30min — agent may be stuck (detected at {now_iso()})"
                ]
                log_incident(card, "No commit activity for 30+ minutes")

    # WIP limit enforcement
    cards = enforce_wip_limit(cards, board)

    # Auto-archive old done cards
    cards = auto_archive(cards)

    # Write updated cards back
    for card in cards:
        if "_file" in card:
            write_card(Path(card["_file"]), card, card.get("_body", ""))

    # Render status
    render_status(cards)


def main():
    parser = argparse.ArgumentParser(description="Project Oracle Kanban Watcher")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 5 minutes")
    args = parser.parse_args()

    if args.loop:
        print(f"[kanban_watcher] Starting continuous loop (5-min interval)")
        while True:
            try:
                single_pass()
                print(f"[kanban_watcher] Pass complete at {now_iso()}")
            except Exception as e:
                print(f"[kanban_watcher] ERROR: {e}", file=sys.stderr)
            time.sleep(300)
    else:
        single_pass()
        print(f"[kanban_watcher] Single pass complete at {now_iso()}")


if __name__ == "__main__":
    main()
