#!/usr/bin/env python3
"""
scripts/generate_retro.py — Sprint retrospective generator.

End of each sprint (weekly): aggregate completed cards + close-time stats + blockers.
Generate retrospective with: what went well, what didn't, action items.
LLM-augmented via OpenRouter Claude (DSPy pipeline).

Usage:
  python3 scripts/generate_retro.py              # generate retro for current sprint
  python3 scripts/generate_retro.py --week 1     # generate for specific week
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
RETRO_DIR = KANBAN_DIR / "retros"
CONFIG_PATH = Path.home() / ".mem0" / "config.json"


def get_sprint_cards(sprint_start: datetime, sprint_end: datetime) -> list[dict]:
    """Get cards completed during the sprint period."""
    import yaml
    cards = []

    for f in sorted(CARDS_DIR.glob("*.md")):
        if f.name.startswith("tagging_"):
            continue
        try:
            content = f.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}

            # Check if card was completed during sprint
            last_update = fm.get("last_update", "")
            if last_update:
                try:
                    dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
                    if sprint_start <= dt <= sprint_end and fm.get("status") == "done":
                        cards.append(fm)
                except (ValueError, TypeError):
                    pass
        except Exception:
            continue

    return cards


def get_sprint_commits(sprint_start: datetime, sprint_end: datetime) -> list[str]:
    """Get commits during the sprint period."""
    try:
        since = sprint_start.strftime("%Y-%m-%dT%H:%M:%S")
        until = sprint_end.strftime("%Y-%m-%dT%H:%M:%S")
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={since}", f"--until={until}"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return [line for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def get_blockers() -> list[dict]:
    """Get blockers from INCIDENTS.md."""
    incidents_file = KANBAN_DIR / "INCIDENTS.md"
    if not incidents_file.exists():
        return []

    content = incidents_file.read_text()
    blockers = []

    # Parse incident blocks
    for block in content.split("## ")[1:]:
        lines = block.strip().split("\n")
        if lines:
            blockers.append({
                "title": lines[0].strip(),
                "details": "\n".join(lines[1:]).strip()[:200],
            })

    return blockers


def compute_sprint_stats(cards: list[dict], commits: list[str]) -> dict:
    """Compute sprint statistics."""
    stats = {
        "cards_completed": len(cards),
        "total_commits": len(commits),
        "agents": defaultdict(int),
        "total_estimate_hours": 0,
        "avg_estimate_hours": 0,
    }

    for card in cards:
        agent = card.get("assignee", "unknown")
        stats["agents"][agent] += 1
        est = card.get("estimate_hours", 0)
        if isinstance(est, (int, float)) and est > 0:
            stats["total_estimate_hours"] += est

    if cards:
        stats["avg_estimate_hours"] = round(stats["total_estimate_hours"] / len(cards), 1)

    stats["agents"] = dict(stats["agents"])
    return stats


def generate_retro_with_llm(sprint_stats: dict, cards: list[dict],
                            commits: list[str], blockers: list[dict]) -> str:
    """Generate retrospective using LLM synthesis."""
    # Build context for LLM
    context = f"""
Sprint Retrospective Data:
- Cards completed: {sprint_stats['cards_completed']}
- Total commits: {sprint_stats['total_commits']}
- Agent contributions: {json.dumps(sprint_stats['agents'])}
- Total estimated hours: {sprint_stats['total_estimate_hours']}
- Average card estimate: {sprint_stats['avg_estimate_hours']}h

Completed cards:
"""
    for card in cards[:10]:
        context += f"- {card.get('title', 'unknown')} ({card.get('assignee', 'unknown')})\n"

    if blockers:
        context += "\nBlockers encountered:\n"
        for b in blockers[:5]:
            context += f"- {b['title']}\n"

    context += """
Generate a sprint retrospective with:
1. **What went well** (3+ items, cite specific cards/agents)
2. **What didn't go well** (2+ items, cite specific issues)
3. **Action items** (3+ concrete improvements, each as a kanban card suggestion)

Format in markdown. Every claim must reference a specific card ID or agent.
"""

    # Try LLM via OpenRouter
    try:
        import urllib.request
        import urllib.parse

        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            # Try to load from config
            hermes_env = Path.home() / ".hermes" / ".env"
            if hermes_env.exists():
                for line in hermes_env.read_text().splitlines():
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break

        if api_key:
            payload = json.dumps({
                "model": "anthropic/claude-sonnet-4",
                "messages": [
                    {"role": "system", "content": "You are a sprint retrospective facilitator. Be specific and cite evidence."},
                    {"role": "user", "content": context},
                ],
                "max_tokens": 1000,
            }).encode()

            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        pass

    # Fallback: template-based retro
    return generate_template_retro(sprint_stats, cards, blockers)


def generate_template_retro(stats: dict, cards: list[dict], blockers: list[dict]) -> str:
    """Generate retrospective without LLM (fallback)."""
    lines = [
        f"# Sprint Retrospective",
        f"**Period:** {stats.get('sprint_start', 'N/A')} → {stats.get('sprint_end', 'N/A')}",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        f"- Cards completed: {stats['cards_completed']}",
        f"- Total commits: {stats['total_commits']}",
        f"- Total estimated hours: {stats['total_estimate_hours']}h",
        "",
        "## Agent Contributions",
    ]

    for agent, count in sorted(stats.get("agents", {}).items(), key=lambda x: -x[1]):
        lines.append(f"- {agent}: {count} cards")

    lines.extend(["", "## What Went Well"])
    if stats["cards_completed"] > 0:
        lines.append(f"- {stats['cards_completed']} cards completed across {len(stats.get('agents', {}))} agents")
    if stats["total_commits"] > 0:
        lines.append(f"- {stats['total_commits']} commits pushed")

    lines.extend(["", "## What Didn't Go Well"])
    if blockers:
        for b in blockers[:3]:
            lines.append(f"- {b['title']}")
    else:
        lines.append("- No major blockers recorded")

    lines.extend(["", "## Action Items"])
    lines.append("- [ ] Review bottleneck patterns in agent throughput")
    lines.append("- [ ] Update kanban WIP limits based on actual throughput")
    lines.append("- [ ] Follow up on stale cards (>7 days in_progress)")

    return "\n".join(lines)


def spawn_action_items(retro: str):
    """Spawn action items as kanban cards."""
    action_items = []
    in_actions = False
    for line in retro.split("\n"):
        if "## Action Items" in line:
            in_actions = True
            continue
        if in_actions and line.strip().startswith("- [ ]"):
            action_items.append(line.strip()[6:].strip())

    if action_items:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        retro_cards_file = CARDS_DIR / f"retro_actions_{date_str}.md"
        content = f"""---
id: RETRO-ACTIONS-{date_str}
title: Sprint Retro Action Items
assignee: Agent 8
skill: kanban-orchestrator
estimate_hours: 1
dependencies: []
status: ready
last_update: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
commits: []
blockers: []
---

## Action Items from Sprint Retrospective

"""
        for item in action_items:
            content += f"- {item}\n"

        retro_cards_file.write_text(content)


def main():
    parser = argparse.ArgumentParser(description="Generate sprint retrospective")
    parser.add_argument("--week", type=int, default=None, help="Sprint week number")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = parser.parse_args()

    # Determine sprint period (weekly, ending now)
    now = datetime.now(timezone.utc)
    if args.week:
        # Approximate: week 1 = May 19-25, etc.
        sprint_start = datetime(2026, 5, 19, tzinfo=timezone.utc) + timedelta(weeks=args.week - 1)
        sprint_end = sprint_start + timedelta(weeks=1)
    else:
        # Default: last 7 days
        sprint_start = now - timedelta(weeks=1)
        sprint_end = now

    print(f"[retro] Sprint period: {sprint_start.strftime('%Y-%m-%d')} → {sprint_end.strftime('%Y-%m-%d')}")

    # Gather data
    cards = get_sprint_cards(sprint_start, sprint_end)
    commits = get_sprint_commits(sprint_start, sprint_end)
    blockers = get_blockers()
    stats = compute_sprint_stats(cards, commits)
    stats["sprint_start"] = sprint_start.strftime("%Y-%m-%d")
    stats["sprint_end"] = sprint_end.strftime("%Y-%m-%d")

    print(f"[retro] Cards: {stats['cards_completed']}, Commits: {stats['total_commits']}, Blockers: {len(blockers)}")

    # Generate retro
    retro = generate_retro_with_llm(stats, cards, commits, blockers)

    # Write retro
    RETRO_DIR.mkdir(parents=True, exist_ok=True)
    retro_file = RETRO_DIR / f"retro_{sprint_start.strftime('%Y-%m-%d')}.md"

    if not args.dry_run:
        retro_file.write_text(retro + "\n")
        print(f"[retro] Written to {retro_file}")

        # Spawn action items
        spawn_action_items(retro)
        print(f"[retro] Action items spawned")

    print()
    print(retro)


if __name__ == "__main__":
    main()
