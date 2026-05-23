#!/usr/bin/env python3
"""
scripts/start_incident.py

Create an incident post-mortem skeleton from a CRITICAL alert.
Pre-fills detection + timeline from logs/metrics.

Usage:
    python scripts/start_incident.py --title "SPY chain stall" --severity CRITICAL
    python scripts/start_incident.py --title "API burn" --severity CRITICAL --alert-name credit_burn_95
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# Add backend to path for DuckDB/Prometheus access
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

INCIDENT_DIR = REPO_ROOT / "docs" / "INCIDENTS"
INCIDENTS_DIR = INCIDENT_DIR  # alias for tests/external callers
TEMPLATE_PATH = INCIDENT_DIR / "_template.md"

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", str(REPO_ROOT / "data" / "floww.duckdb"))

# Validation sets — keep aligned with alert taxonomy in credit_monitor / staleness_alerts
VALID_SEVERITIES = {"CRITICAL", "MEDIUM", "LOW"}
VALID_CATEGORIES = {"infra", "app", "data"}

# In-process idempotency registry: alert_id -> Path
_created_registry: Dict[str, Path] = {}


def _today() -> str:
    """Return today's date in YYYY-MM-DD (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug.

    Rules:
    - Lowercase
    - Strip anything that isn't [a-z0-9\\s-]
    - Collapse runs of whitespace to a single hyphen
    """
    s = text.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


def fetch_prometheus_metric(query: str, default: str = "N/A") -> str:
    """Query Prometheus for a metric value."""
    try:
        url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            results = data.get("data", {}).get("result", [])
            if results:
                return results[0].get("value", [None, default])[1]
    except Exception:
        pass
    return default


def fetch_duckdb_metric(query: str, db_path: str = DUCKDB_PATH, default: str = "N/A") -> str:
    """Query DuckDB for a metric value."""
    try:
        import duckdb
        conn = duckdb.connect(db_path, read_only=True)
        result = conn.execute(query).fetchone()
        conn.close()
        if result and result[0] is not None:
            return str(result[0])
    except Exception:
        pass
    return default


def generate_incident(
    title: str,
    severity: str = "CRITICAL",
    alert_name: str = "",
    detection_source: str = "automated alert",
) -> str:
    """Generate a filled-in incident post-mortem from the template."""
    template = TEMPLATE_PATH.read_text()
    now = datetime.now(timezone.utc)

    # Gather metrics
    p99 = fetch_prometheus_metric(
        'floww_api_request_duration_seconds{quantile="0.99"}',
        default="N/A"
    )
    queue_depth = fetch_prometheus_metric(
        "floww_duckdb_queue_depth",
        default="N/A"
    )
    max_delay = fetch_duckdb_metric(
        "SELECT MAX(delay_seconds) FROM ticks",
        default="N/A"
    )

    # Build replacements
    replacements = {
        "{{TITLE}}": title,
        "{{DATE}}": now.strftime("%Y-%m-%d"),
        "{{SEVERITY}}": severity,
        "{{DURATION}}": "TBD",
        "{{DETECTION_SOURCE}}": detection_source,
        "{{ALERT_NAME}}": alert_name or "N/A",
        "{{ALERT_TIME}}": now.isoformat(),
        "{{INITIAL_SYMPTOM}}": f"CRITICAL alert: {alert_name}" if alert_name else "TBD",
        "{{AFFECTED_SYSTEMS}}": "TBD",
        "{{T1}}": now.strftime("%H:%M:%S"),
        "{{T2}}": "TBD",
        "{{T3}}": "TBD",
        "{{T4}}": "TBD",
        "{{T5}}": "TBD",
        "{{ROOT_CAUSE_SUMMARY}}": "TBD",
        "{{FACTOR_1}}": "TBD",
        "{{FACTOR_2}}": "TBD",
        "{{FIX_COMMAND}}": "# TBD",
        "{{VERIFICATION_STEP}}": "TBD",
        "{{ACTION_1}}": "Root cause analysis",
        "{{OWNER_1}}": "TBD",
        "{{KANBAN_URL_1}}": "#",
        "{{DUE_1}}": "TBD",
        "{{ACTION_2}}": "Add regression test",
        "{{OWNER_2}}": "TBD",
        "{{KANBAN_URL_2}}": "#",
        "{{DUE_2}}": "TBD",
        "{{P99_PEAK}}": p99,
        "{{QUEUE_MAX}}": queue_depth,
        "{{CACHE_STALE_MAX}}": f"{float(max_delay)/60:.1f}" if max_delay != "N/A" else "N/A",
        "{{CREDIT_BURN}}": "TBD",
        "{{429_COUNT}}": "TBD",
        "{{LESSON_1}}": "TBD",
        "{{LESSON_2}}": "TBD",
        "{{GENERATION_TIME}}": now.isoformat(),
    }

    content = template
    for key, value in replacements.items():
        content = content.replace(key, value)

    return content


def create_from_alert(
    alert_id: str,
    title: str,
    severity: str = "CRITICAL",
    category: str = "app",
    alert_name: str = "",
    detection_details: str = "",
) -> Path:
    """Create an incident skeleton from an alert, with idempotency by alert_id.

    Calling twice with the same alert_id returns the same Path without
    creating a second file. The in-process registry can be cleared via
    ``_created_registry.clear()`` (used by tests).

    Raises:
        ValueError: if severity or category is not in the allowed taxonomy.
    """
    if severity not in VALID_SEVERITIES:
        raise ValueError(
            f"Invalid severity {severity!r}. Must be one of {sorted(VALID_SEVERITIES)}"
        )
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. Must be one of {sorted(VALID_CATEGORIES)}"
        )

    if alert_id in _created_registry:
        existing = _created_registry[alert_id]
        if existing.exists():
            return existing

    INCIDENTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = INCIDENTS_DIR / f"{_today()}_{_slugify(title)}.md"

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc)

    replacements = {
        # Tests' minimal template set
        "{{DATE}}": _today(),
        "{{TITLE}}": title,
        "{{SEVERITY}}": severity,
        "{{ALERT_ID}}": alert_id,
        "{{CATEGORY}}": category,
        "{{ALERT_NAME}}": alert_name or "N/A",
        "{{DETECTION_DETAILS}}": detection_details or f"Alert {alert_id} fired at {now.isoformat()}",
        "{{TIMESTAMP}}": now.isoformat(),
        "{{ROOT_CAUSE}}": "TBD",
        "{{IMMEDIATE_ACTIONS}}": "TBD",
        "{{PERMANENT_FIX}}": "TBD",
        "{{ACTION_ITEM_1}}": "Root cause analysis",
        "{{KANBAN_ID_1}}": "TBD",
        "{{LESSONS_LEARNED}}": "TBD",
        # Backwards-compat with the richer real template
        "{{DURATION}}": "TBD",
        "{{DETECTION_SOURCE}}": "automated alert",
        "{{ALERT_TIME}}": now.isoformat(),
        "{{INITIAL_SYMPTOM}}": f"CRITICAL alert: {alert_name}" if alert_name else "TBD",
        "{{AFFECTED_SYSTEMS}}": "TBD",
        "{{T1}}": now.strftime("%H:%M:%S"),
        "{{T2}}": "TBD",
        "{{T3}}": "TBD",
        "{{T4}}": "TBD",
        "{{T5}}": "TBD",
        "{{ROOT_CAUSE_SUMMARY}}": "TBD",
        "{{FACTOR_1}}": "TBD",
        "{{FACTOR_2}}": "TBD",
        "{{FIX_COMMAND}}": "# TBD",
        "{{VERIFICATION_STEP}}": "TBD",
        "{{ACTION_1}}": "Root cause analysis",
        "{{OWNER_1}}": "TBD",
        "{{KANBAN_URL_1}}": "#",
        "{{DUE_1}}": "TBD",
        "{{ACTION_2}}": "Add regression test",
        "{{OWNER_2}}": "TBD",
        "{{KANBAN_URL_2}}": "#",
        "{{DUE_2}}": "TBD",
        "{{P99_PEAK}}": "TBD",
        "{{QUEUE_MAX}}": "TBD",
        "{{CACHE_STALE_MAX}}": "TBD",
        "{{CREDIT_BURN}}": "TBD",
        "{{429_COUNT}}": "TBD",
        "{{LESSON_1}}": "TBD",
        "{{LESSON_2}}": "TBD",
        "{{GENERATION_TIME}}": now.isoformat(),
    }

    content = template
    for key, value in replacements.items():
        content = content.replace(key, str(value))

    output_path.write_text(content, encoding="utf-8")
    _created_registry[alert_id] = output_path
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Create incident post-mortem skeleton")
    parser.add_argument("--title", required=True, help="Incident title")
    parser.add_argument("--severity", default="CRITICAL", help="Severity level")
    parser.add_argument("--alert-name", default="", help="Alert that triggered this incident")
    parser.add_argument("--detection-source", default="automated alert", help="How it was detected")
    parser.add_argument("--output", default=None, help="Output path (default: docs/INCIDENTS/YYYY-MM-DD_title.md)")
    args = parser.parse_args()

    INCIDENT_DIR.mkdir(parents=True, exist_ok=True)

    if args.output:
        output_path = Path(args.output)
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe_title = args.title.lower().replace(" ", "_").replace("/", "_")[:40]
        output_path = INCIDENT_DIR / f"{date_str}_{safe_title}.md"

    if output_path.exists():
        print(f"[WARN] {output_path} already exists. Overwriting.")

    content = generate_incident(
        title=args.title,
        severity=args.severity,
        alert_name=args.alert_name,
        detection_source=args.detection_source,
    )

    output_path.write_text(content)
    print(f"[INCIDENT] Post-mortem skeleton created: {output_path}")
    return str(output_path)


if __name__ == "__main__":
    main()
