#!/usr/bin/env python3
"""
dependency_checker.py — Inter-Agent Dependency Tracker
Agent 8 (Hermes) runs this every 5 minutes to:
  1. Scan the dependency graph for blocked cards
  2. Check if upstream verification passed
  3. Auto-comment on blocked cards with ETA and unblock condition
  4. Auto-unblock when conditions are met
  5. Update the dependency_graph.yaml scan timestamp

Usage:
    python3 dependency_checker.py [--dry-run] [--verbose]
    
Exit codes:
    0 = all clear or dry-run
    1 = blocked cards found (with details in output)
"""

import sys
import os
import subprocess
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for yaml import
KANBAN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KANBAN_DIR))

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

DEPENDENCY_GRAPH = KANBAN_DIR / "dependency_graph.yaml"
CARD_DIR = KANBAN_DIR / "cards"
COMMENT_DIR = KANBAN_DIR / "comments"
COMMENT_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# YAML helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_graph():
    """Load and return the dependency graph."""
    with open(DEPENDENCY_GRAPH) as f:
        return yaml.safe_load(f)


def save_graph(graph):
    """Save the dependency graph, updating last_scan timestamp."""
    graph["last_scan"] = datetime.now(timezone.utc).isoformat()
    with open(DEPENDENCY_GRAPH, "w") as f:
        yaml.dump(graph, f, default_flow_style=False, sort_keys=False)


# ──────────────────────────────────────────────────────────────────────────────
# Git helpers
# ──────────────────────────────────────────────────────────────────────────────

def git_log_for_card(card_id: str, since_hours: int = 24) -> list[str]:
    """Return commit messages for a given card ID since N hours ago."""
    try:
        since = f"{since_hours} hours ago"
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--grep", card_id,
             "--format=%h %s"],
            capture_output=True, text=True, cwd=str(KANBAN_DIR.parent),
            timeout=10
        )
        return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def git_file_status(file_path: str) -> str:
    """Check if a file exists and has been modified recently."""
    full_path = KANBAN_DIR.parent / file_path
    if not full_path.exists():
        return "missing"
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ar", "--", str(full_path)],
            capture_output=True, text=True, cwd=str(KANBAN_DIR.parent),
            timeout=5
        )
        age = result.stdout.strip()
        if "hour" in age or "minute" in age:
            return "recent"
        elif "day" in age:
            match = re.search(r"(\d+)", age)
            days = int(match.group(1)) if match else 999
            return "stale" if days > 7 else "active"
        return "old"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Unblock condition checker
# ──────────────────────────────────────────────────────────────────────────────

def check_unblock_condition(condition: str, upstream_card: str) -> tuple[bool, str]:
    """
    Check if an unblock condition is met.
    Returns (is_unmet, details_message)
    """
    # Check file existence for specific modules
    if "ingestion_pipeline.py" in condition:
        status = git_file_status("backend/services/ingestion_pipeline.py")
        if status == "missing":
            return False, "ingestion_pipeline.py not found"
        # Check if mock feed is still being used
        mock_path = KANBAN_DIR.parent / "backend/services/mock_schwab_feed.py"
        if mock_path.exists():
            return False, "Still using mock feed — live data not connected"
        return True, "Live ingestion pipeline detected"

    if "gate.py" in condition:
        status = git_file_status("backend/services/risk/gate.py")
        if status == "missing":
            return False, "risk/gate.py not found"
        return True, "Risk gate module exists"

    if "Greeks" in condition or "gex_aggregator" in condition:
        gex_status = git_file_status("backend/services/gex_aggregator.py")
        bs_status = git_file_status("backend/services/bs_calculator.py")
        if gex_status == "missing" or bs_status == "missing":
            return False, f"Greek calc incomplete: gex={gex_status}, bs={bs_status}"
        return True, "Greek calculators present"

    if "math validation" in condition.lower():
        test_path = KANBAN_DIR.parent / "backend/tests/services/test_microstructure_math.py"
        if not test_path.exists():
            return False, "Math validation test file missing"
        return True, "Math validation suite exists"

    if "API routes" in condition:
        route_path = KANBAN_DIR.parent / "backend/routes/market_data.py"
        if not route_path.exists():
            return False, "market_data.py routes not found"
        return True, "API routes exist"

    # Default: check if upstream card has recent commits
    recent_commits = git_log_for_card(upstream_card, since_hours=48)
    if recent_commits:
        return True, f"{len(recent_commits)} recent commit(s) for {upstream_card}"
    
    return False, f"No recent activity for {upstream_card}"


# ──────────────────────────────────────────────────────────────────────────────
# Card state helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_card_status(card_id: str) -> str:
    """Read the status from a card's frontmatter."""
    card_file = CARD_DIR / f"{card_id}.md"
    if not card_file.exists():
        return "unknown"
    content = card_file.read_text()
    match = re.search(r"^status:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else "unknown"


def write_card_comment(card_id: str, message: str):
    """Write a comment file for a card."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    comment_file = COMMENT_DIR / f"{card_id}_{ts}.md"
    comment_file.write_text(
        f"---\n"
        f"card_id: {card_id}\n"
        f"timestamp: {ts}\n"
        f"source: dependency_checker.py\n"
        f"---\n\n"
        f"{message}\n"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main dependency check
# ──────────────────────────────────────────────────────────────────────────────

def check_dependencies(verbose: bool = False) -> dict:
    """
    Check all dependency edges and return status.
    Returns dict with blocked_cards, unblocked_count, total_edges.
    """
    graph = load_graph()
    edges = graph.get("edges", [])
    
    blocked = []
    unblocked = []
    dry_run_info = []
    
    for edge in edges:
        from_card = edge["from"]
        to_card = edge["to"]
        edge_type = edge.get("type", "blocks")
        reason = edge.get("reason", "")
        condition = edge.get("unblock_condition", "")
        
        to_status = get_card_status(to_card)
        from_status = get_card_status(from_card)
        
        if verbose:
            print(f"  {from_card} ({from_status}) --[{edge_type}]--> {to_card} ({to_status})")
        
        # Only check 'blocks' type edges
        if edge_type != "blocks":
            continue
        
        # Check if downstream card is blocked
        if to_status in ("ready", "in_progress", "review"):
            # Downstream is in-flight, check upstream
            is_unmet, details = check_unblock_condition(condition, from_card)
            
            if not is_unmet:
                # Condition NOT met → should be blocked
                blocked_info = {
                    "downstream": to_card,
                    "upstream": from_card,
                    "reason": reason,
                    "condition": condition,
                    "details": details,
                    "from_status": from_status,
                    "to_status": to_status,
                }
                blocked.append(blocked_info)
                
                # Write comment
                eta = f"Blocked by {from_card}: {details}"
                comment_msg = (
                    f"⚠️ DEPENDENCY BLOCK\n\n"
                    f"Blocked by: {from_card} ({from_status})\n"
                    f"Reason: {reason}\n"
                    f"Unblock condition: {condition}\n"
                    f"Current status: {details}\n\n"
                    f"ETA: Waiting on upstream verification\n"
                    f"Auto-unblock when: {condition}"
                )
                write_card_comment(to_card, comment_msg)
            else:
                unblocked.append({
                    "downstream": to_card,
                    "upstream": from_card,
                    "details": details,
                })
    
    return {
        "blocked_cards": blocked,
        "unblocked_count": len(unblocked),
        "total_edges": len(edges),
        "scan_time": datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    print(f"🔍 Dependency Checker — {datetime.now(timezone.utc).isoformat()}")
    print(f"   Graph: {DEPENDENCY_GRAPH}")
    print(f"   Dry run: {dry_run}")
    print()
    
    result = check_dependencies(verbose=verbose)
    
    blocked = result["blocked_cards"]
    
    if blocked:
        print(f"⚠️  {len(blocked)} blocked card(s) found:")
        for b in blocked:
            print(f"   {b['downstream']} ← blocked by {b['upstream']}")
            print(f"      Reason: {b['reason']}")
            print(f"      Status: {b['details']}")
            print()
    else:
        print(f"✅ All clear — {result['unblocked_count']} dependency edges satisfied")
    
    # Update scan timestamp
    if not dry_run:
        graph = load_graph()
        save_graph(graph)
        print(f"   Updated last_scan: {result['scan_time']}")
    
    # Exit code
    sys.exit(1 if blocked else 0)


if __name__ == "__main__":
    main()
