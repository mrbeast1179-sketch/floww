#!/usr/bin/env python3
"""
kanban/bottleneck_detector.py — Bottleneck detector for agent swarm.

Monitors queue lengths, wait times, and blocker rates.
Alerts Nav if bottleneck persists > 1 hour.
Writes alerts to kanban/BOTTLENECK_ALERTS.md.

Usage:
  python3 kanban/bottleneck_detector.py          # single check
  python3 kanban/bottleneck_detector.py --loop   # continuous (5-min interval)
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
ALERTS_FILE = KANBAN_DIR / "BOTTLENECK_ALERTS.md"
INCIDENTS_FILE = KANBAN_DIR / "INCIDENTS.md"

# Config
BLOCKER_THRESHOLD_HOURS = 1.0  # Alert if bottleneck persists > 1 hour
IN_PROGRESS_WIP_LIMIT = 6
HIGH_LOAD_MULTIPLIER = 3  # cards_in_flight > 3× median = bottleneck
STALE_HOURS = 24


def load_cards() -> list[dict]:
    """Load all card files."""
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


def compute_metrics(cards: list[dict]) -> dict:
    """Compute per-agent metrics."""
    agents = defaultdict(lambda: {
        "cards_in_progress": 0,
        "cards_ready": 0,
        "cards_done": 0,
        "cards_blocked": 0,
        "cards_backlog": 0,
        "total_cards": 0,
        "blocker_count": 0,
        "max_stale_hours": 0.0,
        "total_wait_hours": 0.0,
    })

    now = datetime.now(timezone.utc)

    for card in cards:
        assignee = card.get("assignee", "unknown")
        status = card.get("status", "unknown")
        blockers = card.get("blockers", []) or []

        agents[assignee]["total_cards"] += 1

        if status == "in_progress":
            agents[assignee]["cards_in_progress"] += 1
        elif status == "ready":
            agents[assignee]["cards_ready"] += 1
        elif status == "done":
            agents[assignee]["cards_done"] += 1
        elif status == "blocked":
            agents[assignee]["cards_blocked"] += 1
        elif status == "backlog":
            agents[assignee]["cards_backlog"] += 1

        if blockers:
            agents[assignee]["blocker_count"] += len(blockers)

        # Staleness
        last_update = card.get("last_update", "")
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
                hours_ago = (now - dt).total_seconds() / 3600
                agents[assignee]["max_stale_hours"] = max(
                    agents[assignee]["max_stale_hours"], hours_ago
                )
                if status in ("in_progress", "ready"):
                    agents[assignee]["total_wait_hours"] += hours_ago
            except (ValueError, TypeError):
                pass

    # Derived metrics
    for agent, m in agents.items():
        total = m["total_cards"]
        m["blocker_rate"] = m["blocker_count"] / total if total > 0 else 0.0
        m["done_rate"] = m["cards_done"] / total if total > 0 else 0.0

    return dict(agents)


def detect_bottlenecks(agent_metrics: dict) -> list[dict]:
    """Identify bottleneck agents. Returns list of bottleneck dicts."""
    if not agent_metrics:
        return []

    agents = list(agent_metrics.keys())
    in_prog = [agent_metrics[a]["cards_in_progress"] for a in agents]
    blocker_rates = [agent_metrics[a]["blocker_rate"] for a in agents]

    median_in_prog = sorted(in_prog)[len(in_prog) // 2] if in_prog else 0
    median_blocker = sorted(blocker_rates)[len(blocker_rates) // 2] if blocker_rates else 0

    bottlenecks = []
    for agent in agents:
        m = agent_metrics[agent]
        reasons = []
        severity = "info"

        # High load
        if m["cards_in_progress"] > HIGH_LOAD_MULTIPLIER * max(median_in_prog, 1):
            reasons.append(
                f"Overloaded: {m['cards_in_progress']} in-progress "
                f"(>{HIGH_LOAD_MULTIPLIER}x median={median_in_prog})"
            )
            severity = "critical"

        # High blocker rate
        if m["blocker_rate"] > 2 * max(median_blocker, 0.01):
            reasons.append(
                f"High blocker rate: {m['blocker_rate']:.2f} "
                f"(>2x median={median_blocker:.2f})"
            )
            severity = max(severity, "warning", key=lambda s: {"info": 0, "warning": 1, "critical": 2}[s])

        # Stale
        if m["max_stale_hours"] > STALE_HOURS:
            reasons.append(
                f"Stale: last update {m['max_stale_hours']:.0f}h ago (>{STALE_HOURS}h)"
            )
            severity = max(severity, "warning", key=lambda s: {"info": 0, "warning": 1, "critical": 2}[s])

        # WIP limit
        if m["cards_in_progress"] > IN_PROGRESS_WIP_LIMIT:
            reasons.append(
                f"WIP limit exceeded: {m['cards_in_progress']} > {IN_PROGRESS_WIP_LIMIT}"
            )
            severity = "critical"

        # Long wait times on ready cards
        if m["cards_ready"] > 5 and m["total_wait_hours"] > BLOCKER_THRESHOLD_HOURS * m["cards_ready"]:
            reasons.append(
                f"Queue backup: {m['cards_ready']} ready cards, "
                f"avg wait {m['total_wait_hours'] / max(m['cards_ready'], 1):.1f}h"
            )
            severity = max(severity, "warning", key=lambda s: {"info": 0, "warning": 1, "critical": 2}[s])

        if reasons:
            bottlenecks.append({
                "agent": agent,
                "reasons": reasons,
                "severity": severity,
                "metrics": m,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            })

    return bottlenecks


def format_alert(bottlenecks: list[dict], agent_metrics: dict) -> str:
    """Format bottleneck alert for BOTTLENECK_ALERTS.md."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Bottleneck Alerts — {now}",
        "",
    ]

    if not bottlenecks:
        lines.append("✅ No bottlenecks detected. All agents within normal parameters.")
        lines.append("")
    else:
        lines.append(f"⚠️ **{len(bottlenecks)} bottleneck(s) detected**")
        lines.append("")
        for b in bottlenecks:
            icon = "🔴" if b["severity"] == "critical" else "🟡"
            lines.append(f"## {icon} {b['agent']} ({b['severity']})")
            for reason in b["reasons"]:
                lines.append(f"- {reason}")
            lines.append("")

    # Full metrics table
    lines.append("---")
    lines.append("## Agent Metrics Summary")
    lines.append("")
    lines.append("| Agent | In Progress | Ready | Done | Blocked | Blocker Rate | Stale (h) |")
    lines.append("|-------|-------------|-------|------|---------|--------------|-----------|")
    for agent in sorted(agent_metrics.keys()):
        m = agent_metrics[agent]
        stale = f"{m['max_stale_hours']:.0f}" if m['max_stale_hours'] else "—"
        lines.append(
            f"| {agent} | {m['cards_in_progress']} | {m['cards_ready']} | "
            f"{m['cards_done']} | {m['cards_blocked']} | "
            f"{m['blocker_rate']:.2f} | {stale} |"
        )
    lines.append("")
    lines.append(f"*Next check: {(datetime.now(timezone.utc) + timedelta(minutes=5)).strftime('%H:%M UTC')}*")

    return "\n".join(lines)


def log_incident(bottleneck: dict):
    """Append critical bottleneck to INCIDENTS.md."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"""
## {ts} — BOTTLENECK: {bottleneck['agent']}
- **Severity:** {bottleneck['severity']}
- **Symptoms:** {'; '.join(bottleneck['reasons'])}
- **Action:** Alerted Nav via BOTTLENECK_ALERTS.md
- **Resolution:** Awaiting Nav triage or auto-reassignment
"""
    with open(INCIDENTS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


def run_check() -> dict:
    """Run full bottleneck check. Returns result dict."""
    cards = load_cards()
    metrics = compute_metrics(cards)
    bottlenecks = detect_bottlenecks(metrics)
    report = format_alert(bottlenecks, metrics)

    ALERTS_FILE.write_text(report + "\n", encoding="utf-8")

    # Log critical bottlenecks as incidents
    for b in bottlenecks:
        if b["severity"] == "critical":
            log_incident(b)

    return {
        "bottlenecks": bottlenecks,
        "metrics": metrics,
        "n_cards": len(cards),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bottleneck detector")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 5 min")
    args = parser.parse_args()

    if args.loop:
        print("[bottleneck] Starting continuous loop (5-min interval)")
        while True:
            try:
                result = run_check()
                n = len(result["bottlenecks"])
                print(f"[bottleneck] {datetime.now(timezone.utc).strftime('%H:%M')} — {n} bottleneck(s)")
            except Exception as e:
                print(f"[bottleneck] ERROR: {e}", file=sys.stderr)
            time.sleep(300)
    else:
        result = run_check()
        print(f"Bottlenecks: {len(result['bottlenecks'])}")
        for b in result["bottlenecks"]:
            print(f"  {b['agent']} ({b['severity']}): {'; '.join(b['reasons'])}")
        print(f"\nFull report: {ALERTS_FILE}")


if __name__ == "__main__":
    main()
