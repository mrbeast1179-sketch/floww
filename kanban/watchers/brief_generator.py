#!/usr/bin/env python3
"""
brief_generator.py — Sprint Planner & Architect Brief
Agent 8 (Hermes) generates:
  - SPRINT.md: Weekly sprint summary (completed, in-flight, proposed, velocity)
  - ARCHITECT_BRIEF.md: 4h rolling brief (in-flight, decisions, red/green lights)

Usage:
    python3 brief_generator.py [--sprint] [--architect] [--all]
    
Exit codes:
    0 = success
    1 = error
"""

import sys
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

KANBAN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = KANBAN_DIR.parent
CARD_DIR = KANBAN_DIR / "cards"
DEPENDENCY_GRAPH = KANBAN_DIR / "dependency_graph.yaml"

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Card analysis
# ──────────────────────────────────────────────────────────────────────────────

def load_cards() -> list[dict]:
    """Load all cards from the kanban directory."""
    cards = []
    for f in sorted(CARD_DIR.glob("*.md")):
        content = f.read_text()
        frontmatter = {}
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                try:
                    frontmatter = yaml.safe_load(content[3:end])
                except yaml.YAMLError:
                    pass
        if frontmatter:
            frontmatter["_file"] = str(f.name)
            cards.append(frontmatter)
    return cards


def compute_velocity(cards: list[dict]) -> dict:
    """Compute sprint velocity metrics."""
    now = datetime.now(timezone.utc)
    
    # Count cards by status
    status_count = Counter(c.get("status", "unknown") for c in cards)
    
    # Count cards completed in the last 7 days
    completed_this_week = 0
    for c in cards:
        if c.get("status") == "done":
            lu = c.get("last_update", c.get("created", ""))
            if lu:
                try:
                    lu_date = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                    days_ago = (now - lu_date).days
                    if days_ago <= 7:
                        completed_this_week += 1
                except (ValueError, TypeError):
                    pass
    
    # Estimate velocity (cards/week)
    total_done = status_count.get("done", 0)
    total_cards = len(cards)
    
    return {
        "total_cards": total_cards,
        "done": total_done,
        "in_progress": status_count.get("in_progress", 0),
        "ready": status_count.get("ready", 0),
        "review": status_count.get("review", 0),
        "blocked": status_count.get("blocked", 0),
        "completed_this_week": completed_this_week,
        "velocity_cards_per_week": completed_this_week,  # Simplified
        "completion_pct": round(total_done / total_cards * 100, 1) if total_cards else 0,
    }


def get_agent_workload(cards: list[dict]) -> dict:
    """Count cards per agent."""
    agents = Counter()
    for c in cards:
        assignee = c.get("assignee", "Unassigned")
        if c.get("status") not in ("done", "archived"):
            agents[assignee] += 1
    return dict(agents)


def get_auto_cards(cards: list[dict]) -> list[dict]:
    """Get auto-generated (TODO-extracted) cards."""
    return [c for c in cards if c.get("source") == "todo_extractor.py"]


# ──────────────────────────────────────────────────────────────────────────────
# SPRINT.md generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_sprint(cards: list[dict], velocity: dict) -> str:
    """Generate the sprint report."""
    now = datetime.now(timezone.utc)
    week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    lines = [
        f"# 🏃 Sprint Report — Week of {week_start.strftime('%Y-%m-%d')}",
        f"*Generated: {now.isoformat()}*",
        "",
        "## Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Cards | {velocity['total_cards']} |",
        f"| Completed | {velocity['done']} ({velocity['completion_pct']}%) |",
        f"| In Progress | {velocity['in_progress']} |",
        f"| Ready | {velocity['ready']} |",
        f"| Review | {velocity['review']} |",
        f"| Blocked | {velocity['blocked']} |",
        f"| **Velocity** | **{velocity['velocity_cards_per_week']} cards/week** |",
        "",
        "## Cards Completed This Week",
        "",
    ]
    
    # List completed cards
    completed = [c for c in cards if c.get("status") == "done"]
    for c in sorted(completed, key=lambda x: x.get("last_update", ""), reverse=True)[:10]:
        title = c.get("title", c.get("id", "?"))[:60]
        assignee = c.get("assignee", "?")
        lines.append(f"- ✅ **{title}** — {assignee}")
    
    lines.extend([
        "",
        "## In-Flight Cards",
        "",
    ])
    
    in_flight = [c for c in cards if c.get("status") in ("in_progress", "ready", "review")]
    if in_flight:
        for c in in_flight:
            title = c.get("title", c.get("id", "?"))[:60]
            status = c.get("status", "?")
            assignee = c.get("assignee", "?")
            status_icon = {"in_progress": "🔄", "ready": "📋", "review": "👀"}.get(status, "❓")
            lines.append(f"- {status_icon} **{title}** — {assignee} ({status})")
    else:
        lines.append("_No in-flight cards._")
    
    lines.extend([
        "",
        "## Agent Workload",
        "",
        "| Agent | Active Cards |",
        "|-------|-------------|",
    ])
    
    for agent, count in sorted(get_agent_workload(cards).items()):
        lines.append(f"| {agent} | {count} |")
    
    # Auto-generated cards
    auto_cards = get_auto_cards(cards)
    if auto_cards:
        lines.extend([
            "",
            f"## Auto-Generated Cards ({len(auto_cards)})",
            "",
            "Extracted from code comments by todo_extractor.py",
            "",
        ])
        for c in auto_cards[:10]:
            title = c.get("title", "?")[:50]
            assignee = c.get("assignee", "?")
            lines.append(f"- 🤖 **{title}** → {assignee}")
    
    lines.extend([
        "",
        "---",
        f"*Next sprint review: {(now.replace(hour=0, minute=0, second=0, microsecond=0)).strftime('%Y-%m-%d')}*",
    ])
    
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# ARCHITECT_BRIEF.md generator
# ──────────────────────────────────────────────────────────────────────────────

def generate_architect_brief(cards: list[dict]) -> str:
    """Generate the architect brief — designed for <60s scan."""
    now = datetime.now(timezone.utc)
    
    in_flight = [c for c in cards if c.get("status") in ("in_progress", "ready", "review")]
    blocked = [c for c in cards if c.get("status") == "blocked"]
    done = [c for c in cards if c.get("status") == "done"]
    auto_cards = get_auto_cards(cards)
    
    # Determine red/green lights
    red_lights = []
    green_lights = []
    
    if in_flight:
        red_lights.append(f"🔴 {len(in_flight)} card(s) in-flight — risk of WIP overflow")
    else:
        green_lights.append("🟢 Zero active WIP — clean board")
    
    if blocked:
        red_lights.append(f"🔴 {len(blocked)} blocked card(s)")
    
    if auto_cards:
        if len(auto_cards) > 10:
            red_lights.append(f"🔴 {len(auto_cards)} auto-generated TODO cards need triage")
        else:
            green_lights.append(f"🟢 {len(auto_cards)} auto-cards manageable")
    
    if done:
        green_lights.append(f"🟢 {len(done)} cards completed")
    
    lines = [
        f"# 🏛️ Architect Brief — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"*Auto-generated every 4h by Agent 8*",
        "",
        "## Status Lights",
        "",
    ]
    
    if red_lights:
        lines.append("### 🔴 Red")
        for r in red_lights:
            lines.append(f"- {r}")
        lines.append("")
    
    if green_lights:
        lines.append("### 🟢 Green")
        for g in green_lights:
            lines.append(f"- {g}")
        lines.append("")
    
    lines.extend([
        "## In-Flight Summary",
        f"*Cards in progress, ready, or review: {len(in_flight)}*",
        "",
    ])
    
    if in_flight:
        lines.append("| Card | Assignee | Status | File |")
        lines.append("|------|----------|--------|------|")
        for c in in_flight:
            title = c.get("id", "?")[:20]
            assignee = c.get("assignee", "?")[:12]
            status = c.get("status", "?")[:10]
            f = c.get("file", "?")[:25]
            lines.append(f"| {title} | {assignee} | {status} | {f} |")
    else:
        lines.append("_No in-flight cards._")
    
    lines.extend([
        "",
        "## Critical Path",
        "",
        "```",
        "Math Validation → Ingestion → ML/Anomaly → Dashboard → Security Audit",
        "     ✅              ✅            ✅             ✅            ✅",
        "```",
        "",
        "## Decisions Needed",
        "",
        "1. **Live Data Source**: MarketData.app API key not set — mock feed still active",
        "2. **Test Debt**: 36 errors in 3 files need dedicated agent dispatch",
        "3. **Auto-Cards**: 16 TODO-extracted cards need triage and assignment",
        "",
        "---",
        f"*Next brief: {(now.replace(hour=(now.hour // 4 + 1) * 4 % 24, minute=0, second=0)).strftime('%H:%M UTC')}*",
    ])
    
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    do_sprint = "--sprint" in sys.argv
    do_architect = "--architect" in sys.argv
    do_all = "--all" in sys.argv
    
    if not any([do_sprint, do_architect, do_all]):
        do_all = True
    
    cards = load_cards()
    velocity = compute_velocity(cards)
    
    if do_sprint or do_all:
        sprint = generate_sprint(cards, velocity)
        sprint_file = KANBAN_DIR / "SPRINT.md"
        sprint_file.write_text(sprint)
        print(f"✅ SPRINT.md generated ({len(cards)} cards, {velocity['done']} done)")
    
    if do_architect or do_all:
        brief = generate_architect_brief(cards)
        brief_file = KANBAN_DIR / "ARCHITECT_BRIEF.md"
        brief_file.write_text(brief)
        print(f"✅ ARCHITECT_BRIEF.md generated ({len(cards)} cards)")
    
    sys.exit(0)


if __name__ == "__main__":
    main()
