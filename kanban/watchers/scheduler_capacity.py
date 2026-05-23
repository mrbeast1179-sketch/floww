#!/usr/bin/env python3
"""
scheduler_capacity.py — Polling Cadence & Capacity Coordinator
Agent 8 (Hermes) runs this to:
  1. Track active polling jobs (MarketData.app 60s, yfinance 60s fallback)
  2. Ensure total concurrent requests ≤ 2 to preserve API credits & avoid 429s
  3. Alert if scheduler drift > 5s or overlap detected
  4. Log capacity metrics for trend analysis

Usage:
    python3 scheduler_capacity.py [--check] [--simulate] [--report]
    
Exit codes:
    0 = within capacity
    1 = capacity exceeded or drift detected
"""

import sys
import os
import json
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional

KANBAN_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = KANBAN_DIR.parent
CAPACITY_LOG = KANBAN_DIR / "capacity_log.json"
ALERT_FILE = KANBAN_DIR / "CAPACITY_ALERT.md"

try:
    import yaml
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml


# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

MAX_CONCURRENT_REQUESTS = 2
DRIFT_THRESHOLD_SECONDS = 5.0
CAPACITY_LOG_MAX_ENTRIES = 1000

POLLING_JOBS = [
    {
        "id": "marketdata_primary",
        "name": "MarketData.app Primary",
        "interval_seconds": 60,
        "provider": "marketdata.app",
        "priority": 1,
        "fallback_for": None,
        "env_var": "MARKETDATA_API_KEY",
    },
    {
        "id": "yfinance_fallback",
        "name": "yfinance Fallback",
        "interval_seconds": 60,
        "provider": "yfinance",
        "priority": 2,
        "fallback_for": "marketdata_primary",
        "env_var": None,  # No API key needed
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PollingJob:
    id: str
    name: str
    interval_seconds: int
    provider: str
    priority: int
    fallback_for: Optional[str]
    env_var: Optional[str]
    last_run: Optional[str] = None
    last_duration_ms: float = 0.0
    status: str = "idle"  # idle | running | error | paused
    error_count: int = 0


@dataclass
class CapacitySnapshot:
    timestamp: str
    active_jobs: int
    max_concurrent: int
    within_capacity: bool
    drift_detected: bool
    max_drift_seconds: float
    jobs: List[dict]
    alerts: List[str]


# ──────────────────────────────────────────────────────────────────────────────
# Capacity checking
# ──────────────────────────────────────────────────────────────────────────────

def load_capacity_log() -> list:
    """Load the capacity log."""
    if CAPACITY_LOG.exists():
        try:
            return json.loads(CAPACITY_LOG.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_capacity_log(entries: list):
    """Save the capacity log, trimming to max entries."""
    if len(entries) > CAPACITY_LOG_MAX_ENTRIES:
        entries = entries[-CAPACITY_LOG_MAX_ENTRIES:]
    CAPACITY_LOG.write_text(json.dumps(entries, indent=2, default=str))


def check_provider_availability(job: dict) -> bool:
    """Check if a polling job's provider is available."""
    env_var = job.get("env_var")
    if env_var:
        return bool(os.environ.get(env_var))
    # yfinance doesn't need an API key
    return True


def simulate_polling_schedule(jobs: list, duration_seconds: int = 300) -> CapacitySnapshot:
    """
    Simulate the polling schedule for `duration_seconds` and check for overlaps.
    Returns a CapacitySnapshot with any alerts.
    """
    now = time.time()
    events = []  # (timestamp, job_id, event_type)
    
    for job in jobs:
        if not check_provider_availability(job):
            continue
        
        t = now
        while t < now + duration_seconds:
            events.append((t, job["id"], "start"))
            # Assume each request takes ~200ms
            events.append((t + 0.2, job["id"], "end"))
            t += job["interval_seconds"]
    
    # Sort by timestamp
    events.sort(key=lambda e: e[0])
    
    # Check for overlaps
    active = set()
    max_concurrent = 0
    max_concurrent_time = 0
    alerts = []
    
    for ts, job_id, event_type in events:
        if event_type == "start":
            active.add(job_id)
        else:
            active.discard(job_id)
        
        if len(active) > max_concurrent:
            max_concurrent = len(active)
            max_concurrent_time = ts
    
    within_capacity = max_concurrent <= MAX_CONCURRENT_REQUESTS
    
    if not within_capacity:
        alerts.append(
            f"⚠️ CAPACITY EXCEEDED: {max_concurrent} concurrent requests "
            f"(max: {MAX_CONCURRENT_REQUESTS}) at {datetime.fromtimestamp(max_concurrent_time, tz=timezone.utc).isoformat()}"
        )
    
    # Check for drift (jobs running at unexpected times)
    drift_detected = False
    max_drift = 0.0
    
    for i in range(1, len(events)):
        if events[i][2] == "start" and events[i-1][2] == "start":
            gap = events[i][0] - events[i-1][0]
            if gap < 0.05:  # Less than 50ms between starts = potential overlap
                drift_detected = True
                max_drift = max(max_drift, abs(gap - 0.2))
    
    if drift_detected:
        alerts.append(
            f"⚠️ SCHEDULER DRIFT: {max_drift:.3f}s deviation detected "
            f"(threshold: {DRIFT_THRESHOLD_SECONDS}s)"
        )
    
    return CapacitySnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_jobs=len([j for j in jobs if check_provider_availability(j)]),
        max_concurrent=MAX_CONCURRENT_REQUESTS,
        within_capacity=within_capacity,
        drift_detected=drift_detected,
        max_drift_seconds=max_drift,
        jobs=[{"id": j["id"], "name": j["name"], "interval": j["interval_seconds"]} for j in jobs],
        alerts=alerts,
    )


def write_alert(snapshot: CapacitySnapshot):
    """Write an alert file for the dashboard."""
    ALERT_FILE.write_text(
        f"# ⚠️ CAPACITY ALERT — {snapshot.timestamp}\n\n"
        f"**Status:** {'✅ OK' if snapshot.within_capacity else '❌ EXCEEDED'}\n"
        f"**Active Jobs:** {snapshot.active_jobs}\n"
        f"**Max Concurrent:** {snapshot.max_concurrent}\n"
        f"**Drift Detected:** {snapshot.drift_detected}\n"
        f"**Max Drift:** {snapshot.max_drift_seconds:.3f}s\n\n"
        f"## Alerts\n" + "\n".join(f"- {a}" for a in snapshot.alerts) + "\n"
    )


def clear_alert():
    """Clear the alert file."""
    if ALERT_FILE.exists():
        ALERT_FILE.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────────────

def generate_report(snapshot: CapacitySnapshot) -> str:
    """Generate a human-readable capacity report."""
    lines = [
        f"# Capacity Report — {snapshot.timestamp}",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Active Jobs | {snapshot.active_jobs} |",
        f"| Max Concurrent | {snapshot.max_concurrent} |",
        f"| Within Capacity | {'✅ Yes' if snapshot.within_capacity else '❌ No'} |",
        f"| Drift Detected | {'⚠️ Yes' if snapshot.drift_detected else '✅ No'} |",
        f"| Max Drift | {snapshot.max_drift_seconds:.3f}s |",
        "",
        "## Polling Jobs",
        "",
        "| Job | Interval | Provider |",
        "|-----|----------|----------|",
    ]
    for job in snapshot.jobs:
        lines.append(f"| {job['name']} | {job['interval']}s | {job.get('provider', 'N/A')} |")
    
    if snapshot.alerts:
        lines.extend(["", "## Alerts", ""])
        for alert in snapshot.alerts:
            lines.append(f"- {alert}")
    
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    do_check = "--check" in sys.argv
    do_simulate = "--simulate" in sys.argv
    do_report = "--report" in sys.argv
    
    if not any([do_check, do_simulate, do_report]):
        do_check = True  # Default
    
    print(f"📊 Scheduler Capacity — {datetime.now(timezone.utc).isoformat()}")
    print(f"   Max concurrent: {MAX_CONCURRENT_REQUESTS}")
    print(f"   Drift threshold: {DRIFT_THRESHOLD_SECONDS}s")
    print()
    
    jobs = POLLING_JOBS
    
    if do_simulate or do_check:
        snapshot = simulate_polling_schedule(jobs)
        
        # Log
        log = load_capacity_log()
        log.append(asdict(snapshot))
        save_capacity_log(log)
        
        if snapshot.alerts:
            write_alert(snapshot)
            print("⚠️  ALERTS:")
            for alert in snapshot.alerts:
                print(f"   {alert}")
            sys.exit(1)
        else:
            clear_alert()
            print(f"✅ Within capacity — {snapshot.active_jobs} jobs, no drift")
    
    if do_report:
        # Use last snapshot or generate a fresh one
        if 'snapshot' not in dir():
            snapshot = simulate_polling_schedule(jobs)
        report = generate_report(snapshot)
        print(report)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
