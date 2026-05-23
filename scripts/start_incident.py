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
import sys
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path for DuckDB/Prometheus access
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

INCIDENT_DIR = REPO_ROOT / "docs" / "INCIDENTS"
TEMPLATE_PATH = INCIDENT_DIR / "_template.md"

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", str(REPO_ROOT / "data" / "floww.duckdb"))


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
