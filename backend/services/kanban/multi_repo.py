#!/usr/bin/env python3
"""
backend/services/kanban/multi_repo.py — Multi-repo coordination.

Nav has multiple projects (floww, gflows, baby-billy-dvt).
Some kanban cards span repos. Schema extension: cards can declare
`affects_repos: [floww, gflows]`; watcher monitors all listed repos.
Cross-repo SWARM_STATUS.md aggregates state from all.
"""

import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)

# Known project repos
PROJECT_REPOS = {
    "floww": REPO_ROOT,
    "gflows": Path.home() / "Documents" / "GitHub" / "gflows",
    "baby-billy-dvt": Path.home() / "Documents" / "GitHub" / "baby-billy-dvt",
}


def load_cards() -> list[dict]:
    """Load all card files."""
    import yaml
    cards = []
    cards_dir = REPO_ROOT / "kanban" / "cards"
    if not cards_dir.exists():
        return cards

    for f in sorted(cards_dir.glob("*.md")):
        if f.name.startswith("tagging_") or f.name.startswith("retro_"):
            continue
        try:
            content = f.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            fm["_file"] = str(f)
            cards.append(fm)
        except Exception:
            continue
    return cards


def get_commits_for_card(card_id: str, repo_path: Path, since: str = None) -> list[str]:
    """Get commits referencing a card ID in a specific repo."""
    if not repo_path.exists():
        return []

    try:
        cmd = ["git", "log", "--oneline", f"--grep={card_id}"]
        if since:
            cmd.append(f"--since={since}")
        result = subprocess.run(
            cmd, cwd=repo_path, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return [line for line in result.stdout.strip().splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def get_cross_repo_status(cards: list[dict]) -> dict:
    """Get cross-repo status for all cards."""
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repos": {},
        "cross_repo_cards": [],
    }

    # Check which repos exist
    for name, path in PROJECT_REPOS.items():
        status["repos"][name] = {
            "path": str(path),
            "exists": path.exists(),
        }

    # Find cross-repo cards
    for card in cards:
        affects_repos = card.get("affects_repos", [])
        if not affects_repos:
            # Default: card belongs to floww
            affects_repos = ["floww"]

        card_status = {
            "id": card.get("id", ""),
            "title": card.get("title", ""),
            "status": card.get("status", ""),
            "affects_repos": affects_repos,
            "commits_by_repo": {},
        }

        for repo_name in affects_repos:
            repo_path = PROJECT_REPOS.get(repo_name)
            if repo_path and repo_path.exists():
                commits = get_commits_for_card(card.get("id", ""), repo_path)
                card_status["commits_by_repo"][repo_name] = commits

        if len(affects_repos) > 1:
            status["cross_repo_cards"].append(card_status)

        status[f"card_{card.get('id', 'unknown')}"] = card_status

    return status


def generate_multi_repo_status() -> str:
    """Generate multi-repo status markdown."""
    cards = load_cards()
    status = get_cross_repo_status(cards)

    lines = [
        "# Multi-Repo Status",
        f"Generated: {status['timestamp']}",
        "",
        "## Repos",
        "",
    ]

    for name, info in status["repos"].items():
        exists = "✓" if info["exists"] else "✗"
        lines.append(f"- {exists} **{name}**: {info['path']}")

    lines.extend(["", "## Cross-Repo Cards", ""])

    if status["cross_repo_cards"]:
        for card in status["cross_repo_cards"]:
            lines.append(f"### {card['title']} (`{card['id']}`)")
            lines.append(f"- **Status:** {card['status']}")
            lines.append(f"- **Repos:** {', '.join(card['affects_repos'])}")
            for repo, commits in card["commits_by_repo"].items():
                lines.append(f"  - {repo}: {len(commits)} commits")
            lines.append("")
    else:
        lines.append("No cross-repo cards detected.")

    lines.extend(["", "## All Cards by Repo", ""])

    # Group cards by repo
    repo_cards = defaultdict(list)
    for card in cards:
        affects = card.get("affects_repos", ["floww"])
        for repo in affects:
            repo_cards[repo].append(card)

    for repo_name in sorted(repo_cards.keys()):
        lines.append(f"### {repo_name}")
        for card in repo_cards[repo_name]:
            cid = card.get("id", "?")
            title = card.get("title", "?")
            cstatus = card.get("status", "?")
            lines.append(f"- `{cid}` {title} ({cstatus})")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    logger.info(generate_multi_repo_status())
