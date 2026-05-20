#!/usr/bin/env python3
"""
start_incident.py — Create a new incident post-mortem from the template.

Usage:
    python start_incident.py --alert-id ALERT-123 --title "Database failover" --severity CRITICAL --category infra

Can also be imported:
    from start_incident import create_from_alert
    path = create_from_alert("ALERT-123")
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
INCIDENTS_DIR = REPO_ROOT / "docs" / "INCIDENTS"
TEMPLATE_PATH = INCIDENTS_DIR / "_template.md"

VALID_SEVERITIES = {"CRITICAL", "MEDIUM", "LOW"}
VALID_CATEGORIES = {"infra", "app", "security", "data", "network", "other"}

# Simple in-process registry to track created incidents (for idempotency).
# In production this would be a database or a lock file.
_created_registry: set[str] = set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert *text* to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Template not found at {TEMPLATE_PATH}. "
            "Ensure docs/INCIDENTS/_template.md exists."
        )
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _render_template(
    template: str,
    *,
    date: str,
    title: str,
    severity: str,
    alert_id: str,
    category: str,
    alert_name: str,
) -> str:
    """Replace {{PLACEHOLDER}} tokens in the template."""
    detection_details = (
        f"Agent 10 detected an anomaly via alert **{alert_id}** "
        f"(category: {category}). The alert name was '{alert_name}'."
    )
    replacements = {
        "{{DATE}}": date,
        "{{TITLE}}": title,
        "{{SEVERITY}}": severity,
        "{{SERVICES_AFFECTED}}": "_To be filled_",
        "{{ALERT_ID}}": alert_id,
        "{{CATEGORY}}": category,
        "{{ALERT_NAME}}": alert_name,
        "{{DETECTION_DETAILS}}": detection_details,
        "{{TIMESTAMP}}": _now_iso(),
        "{{ROOT_CAUSE}}": "_To be determined_",
        "{{IMMEDIATE_ACTIONS}}": "_To be filled_",
        "{{PERMANENT_FIX}}": "_To be filled_",
        "{{ACTION_ITEM_1}}": "_TBD_",
        "{{KANBAN_ID_1}}": "KANBAN-XXX",
        "{{LESSONS_LEARNED}}": "_To be filled_",
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_from_alert(
    alert_id: str,
    *,
    title: Optional[str] = None,
    severity: str = "MEDIUM",
    category: str = "other",
    alert_name: Optional[str] = None,
) -> Path:
    """
    Create a new incident post-mortem file from the template.

    Parameters
    ----------
    alert_id:
        Unique alert identifier (e.g. "ALERT-123").
    title:
        Human-readable incident title.  Defaults to *alert_id*.
    severity:
        One of CRITICAL, MEDIUM, LOW.
    category:
        One of infra, app, security, data, network, other.
    alert_name:
        Descriptive alert name.  Defaults to *title*.

    Returns
    -------
    Path
        The path to the newly-created (or already-existing) post-mortem file.

    Raises
    ------
    ValueError
        If *severity* or *category* is invalid.
    FileNotFoundError
        If the template file is missing.
    """
    # --- validation ---------------------------------------------------------
    severity = severity.upper()
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity '{severity}'. Must be one of {VALID_SEVERITIES}"
        )
    category = category.lower()
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of {VALID_CATEGORIES}"
        )

    # --- idempotency --------------------------------------------------------
    if alert_id in _created_registry:
        # Find the existing file so we can return its path.
        date_str = _today()
        slug = _slugify(title or alert_id)
        existing = INCIDENTS_DIR / f"{date_str}_{slug}.md"
        if existing.exists():
            return existing
    _created_registry.add(alert_id)

    # --- prepare ------------------------------------------------------------
    title = title or alert_id
    alert_name = alert_name or title
    date_str = _today()
    slug = _slugify(title)
    filename = f"{date_str}_{slug}.md"

    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)

    template = _load_template()
    rendered = _render_template(
        template,
        date=date_str,
        title=title,
        severity=severity,
        alert_id=alert_id,
        category=category,
        alert_name=alert_name,
    )

    output_path = INCIDENTS_DIR / filename
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new incident post-mortem from the template."
    )
    parser.add_argument(
        "--alert-id",
        required=True,
        help="Unique alert identifier (e.g. ALERT-123).",
    )
    parser.add_argument(
        "--title",
        required=True,
        help='Human-readable incident title (e.g. "Database failover").',
    )
    parser.add_argument(
        "--severity",
        default="MEDIUM",
        choices=sorted(VALID_SEVERITIES),
        help="Incident severity (default: MEDIUM).",
    )
    parser.add_argument(
        "--category",
        default="other",
        choices=sorted(VALID_CATEGORIES),
        help="Alert category (default: other).",
    )
    args = parser.parse_args()

    path = create_from_alert(
        alert_id=args.alert_id,
        title=args.title,
        severity=args.severity,
        category=args.category,
    )
    print(f"Incident post-mortem created at: {path}")


if __name__ == "__main__":
    main()
