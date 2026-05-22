#!/usr/bin/env python3
"""
kanban/reassigner.py — Dynamic task reassignment engine.

If an agent is overloaded or blocked, reassigns low-priority tasks to idle agents.
Respects skill constraints (TF-IDF matching).
Writes proposals to kanban/REASSIGN_PROPOSAL.md.

Usage:
  python3 kanban/reassigner.py --check    # check & propose reassignments
  python3 kanban/reassigner.py --apply    # apply proposals
  python3 kanban/reassigner.py --dry-run  # show what would change without writing
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
PROPOSAL_FILE = KANBAN_DIR / "REASSIGN_PROPOSAL.md"
APPLIED_LOG = KANBAN_DIR / "reassign_applied.json"

SKILL_KEYWORDS = [
    "coding-agent", "api-builder", "architecture-diagram", "dspy",
    "evaluating-llms", "academic-verify", "jupyter", "arxiv",
    "duckduckgo", "arxiv-watcher", "godmode", "agent-hardening",
    "obsidian", "mem0", "honcho-memory", "kanban-orchestrator",
    "kanban-codex", "confluence-decoder", "debugging", "test-runner",
    "spike", "writing-plans", "requesting-code-review", "nano-pdf",
    "security-auditor", "data-analyst", "diagram-maker",
]


def load_cards() -> list[dict]:
    cards = []
    for f in sorted(CARDS_DIR.glob("*.md")):
        if f.name.startswith("tagging_") or f.name.startswith("folder_") or f.name.startswith("agent9_"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            fm["_file"] = str(f)
            fm["_body"] = parts[2] if len(parts) > 2 else ""
            cards.append(fm)
        except Exception:
            continue
    return cards


def extract_skills(text: str) -> list[str]:
    text_lower = text.lower()
    return [s for s in SKILL_KEYWORDS if s in text_lower]


def cosine_similarity(text_a: str, text_b: str) -> float:
    words_a = text_a.lower().split()
    words_b = text_b.lower().split()
    if not words_a or not words_b:
        return 0.0
    tf_a = Counter(words_a)
    tf_b = Counter(words_b)
    vocab = set(words_a) | set(words_b)
    vec_a = [tf_a.get(w, 0) / len(words_a) for w in vocab]
    vec_b = [tf_b.get(w, 0) / len(words_b) for w in vocab]
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def compute_agent_load(cards: list[dict]) -> dict:
    load = defaultdict(lambda: {"in_progress": 0, "ready": 0, "total_active": 0, "done": 0})
    for card in cards:
        assignee = card.get("assignee", "unknown")
        status = card.get("status", "unknown")
        if status == "in_progress":
            load[assignee]["in_progress"] += 1
            load[assignee]["total_active"] += 1
        elif status == "ready":
            load[assignee]["ready"] += 1
            load[assignee]["total_active"] += 1
        elif status == "done":
            load[assignee]["done"] += 1
    return dict(load)


def find_reassignments(bottleneck_agent: str, cards: list[dict], agent_load: dict, max_reassign: int = 3) -> list[dict]:
    eligible = [
        c for c in cards
        if c.get("assignee") == bottleneck_agent
        and c.get("status") in ("ready", "in_progress")
        and c.get("priority", "medium") != "high"
    ]
    if not eligible:
        return []

    active_counts = [v["total_active"] for v in agent_load.values()]
    median_load = sorted(active_counts)[len(active_counts) // 2] if active_counts else 1

    candidates = [a for a, s in agent_load.items() if a != bottleneck_agent and s["total_active"] <= median_load]
    if not candidates:
        candidates = [a for a in agent_load if a != bottleneck_agent]

    reassignments = []
    for card in eligible[:max_reassign]:
        card_text = f"{card.get('title', '')} {card.get('skill', '')} {card.get('_body', '')}"
        card_skills = extract_skills(card_text)

        best_agent = None
        best_score = -1

        for a in candidates:
            agent_cards = [c for c in cards if c.get("assignee") == a]
            agent_text = " ".join(f"{c.get('title', '')} {c.get('skill', '')} {c.get('_body', '')}" for c in agent_cards)
            agent_skills = extract_skills(agent_text)

            if card_skills and agent_skills:
                overlap = len(set(card_skills) & set(agent_skills))
                skill_score = overlap / max(len(card_skills), 1)
            else:
                skill_score = 0

            text_score = cosine_similarity(card_text, agent_text)
            load_score = 1.0 / (1 + agent_load.get(a, {}).get("total_active", 0))
            score = skill_score * 0.5 + text_score * 0.3 + load_score * 0.2

            if score > best_score:
                best_score = score
                best_agent = a

        if best_agent and best_score > 0.05:
            reassignments.append({
                "card_id": card.get("id", "unknown"),
                "card_title": card.get("title", ""),
                "from_agent": bottleneck_agent,
                "to_agent": best_agent,
                "confidence": round(best_score, 3),
                "reasoning": f"Skill match + low load ({agent_load.get(best_agent, {}).get('total_active', 0)} active)",
                "card_path": card.get("_file", ""),
            })

    return reassignments


def format_proposal(bottleneck_agents: list, reassignments: list) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Reassignment Proposal — {now}",
        f"**Bottleneck agents:** {', '.join(bottleneck_agents)}",
        f"**Proposed reassignments:** {len(reassignments)}",
        "",
    ]
    if not reassignments:
        lines.append("No reassignments proposed at this time.")
        return "\n".join(lines)

    for i, rec in enumerate(reassignments, 1):
        lines.append(f"### {i}. {rec['card_title']} (`{rec['card_id']}`)")
        lines.append(f"- **From:** {rec['from_agent']} -> **To:** {rec['to_agent']}")
        lines.append(f"- **Confidence:** {rec['confidence']}")
        lines.append(f"- **Reasoning:** {rec['reasoning']}")
        lines.append(f"- **File:** `{rec.get('card_path', 'N/A')}`")
        lines.append("")

    lines.append("---")
    lines.append("*Proposed by kanban/reassigner.py. Review and apply with `--apply`.*")
    return "\n".join(lines)


def apply_reassignment(reassignment: dict) -> bool:
    card_id = reassignment["card_id"]
    to_agent = reassignment["to_agent"]
    for f in CARDS_DIR.glob("*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            if fm.get("id") == card_id:
                fm["assignee"] = to_agent
                fm["reassigned_from"] = reassignment["from_agent"]
                fm["reassigned_at"] = datetime.now(timezone.utc).isoformat()
                yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
                f.write_text(f"---\n{yaml_str}---\n{parts[2]}", encoding="utf-8")
                return True
        except Exception:
            continue
    return False


def log_applied(reassignments: list):
    log = []
    if APPLIED_LOG.exists():
        try:
            log = json.loads(APPLIED_LOG.read_text())
        except json.JSONDecodeError:
            pass
    for r in reassignments:
        entry = dict(r)
        entry["applied_at"] = datetime.now(timezone.utc).isoformat()
        log.append(entry)
    APPLIED_LOG.write_text(json.dumps(log, indent=2))


def run_check(dry_run: bool = False) -> dict:
    cards = load_cards()
    agent_load = compute_agent_load(cards)
    all_reassignments = []
    bottleneck_agents = []

    for agent, stats in agent_load.items():
        if stats["total_active"] > 3:
            bottleneck_agents.append(agent)
            recs = find_reassignments(agent, cards, agent_load)
            all_reassignments.extend(recs)

    bottleneck_agents = list(dict.fromkeys(bottleneck_agents))
    proposal = format_proposal(bottleneck_agents, all_reassignments)

    if not dry_run:
        if all_reassignments:
            PROPOSAL_FILE.write_text(proposal + "\n")
        elif PROPOSAL_FILE.exists():
            PROPOSAL_FILE.unlink()

    return {
        "bottlenecks": bottleneck_agents,
        "reassignments": all_reassignments,
        "proposal_file": str(PROPOSAL_FILE) if all_reassignments else None,
        "agent_load": agent_load,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Dynamic task reassigner")
    parser.add_argument("--check", action="store_true", help="Check and propose")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    parser.add_argument("--apply", action="store_true", help="Apply pending proposals")
    args = parser.parse_args()

    dry_run = args.dry_run or (not args.apply)

    if args.apply:
        if not PROPOSAL_FILE.exists():
            print("[reassigner] No proposal file found. Run --check first.")
            sys.exit(1)
        result = run_check(dry_run=False)
        if result["reassignments"]:
            applied = 0
            for rec in result["reassignments"]:
                ok = apply_reassignment(rec)
                if ok:
                    applied += 1
                    print(f"  {rec['card_id']}: {rec['from_agent']} -> {rec['to_agent']}")
            log_applied(result["reassignments"])
            print(f"[reassigner] Applied {applied}/{len(result['reassignments'])} reassignments.")
        else:
            print("[reassigner] No reassignments to apply.")
    else:
        result = run_check(dry_run=dry_run)
        print(f"Agents: {len(result['agent_load'])}")
        print(f"Bottlenecks: {len(result['bottlenecks'])}")
        for b in result["bottlenecks"]:
            print(f"  {b}")
        print(f"Reassignments proposed: {len(result['reassignments'])}")
        for r in result["reassignments"]:
            print(f"  {r['card_id']}: {r['from_agent']} -> {r['to_agent']} ({r['confidence']})")
        if result["proposal_file"]:
            print(f"\nProposal: {result['proposal_file']}")


if __name__ == "__main__":
    main()
