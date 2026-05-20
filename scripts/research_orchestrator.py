#!/usr/bin/env python3
"""
scripts/research_orchestrator.py

Master pipeline orchestrator for the Autonomous Research & Asset Acquisition Protocol.
Runs the full loop: discover -> extract -> clone -> analyze -> HF search -> digest.

Designed to be called by cron every 60 minutes. Each run:
  1. Runs arxiv discovery (new papers)
  2. Extracts code links from discoveries
  3. Clones new candidate repos (with --execute --yes)
  4. Runs pattern extraction on newly cloned repos
  5. Every 2nd run: HF Hub search
  6. Every 4th run: writes a digest

Usage:
    python scripts/research_orchestrator.py [--full] [--hf-only] [--digest-only]
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent
EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"
DIGEST_DIR = REPO_ROOT / "memory"
STATE_PATH = EXTERNAL_RESEARCH_DIR / ".orchestrator_state.json"
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(EXTERNAL_RESEARCH_DIR / "orchestrator.log"),
    ],
)
log = logging.getLogger("orchestrator")


def _load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"run_count": 0, "last_run": None, "last_hf_run": None, "last_digest_run": None}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _run(cmd: List[str], cwd: Path = REPO_ROOT, timeout: int = 600) -> subprocess.CompletedProcess:
    log.info(f"Running: {' '.join(cmd[:5])}...")
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
    )


def step_discover() -> bool:
    """Step 1: Run arxiv discovery."""
    log.info("=== Step 1: Discovery ===")
    result = _run([str(VENV_PYTHON), "scripts/discover_research.py", "--sources", "arxiv"])
    if result.returncode != 0:
        log.error(f"Discovery failed: {result.stderr[:500]}")
        return False
    log.info("Discovery complete")
    return True


def step_extract_links() -> bool:
    """Step 2: Extract code links from discoveries."""
    log.info("=== Step 2: Extract code links ===")
    result = _run([str(VENV_PYTHON), "scripts/extract_code_links.py"])
    if result.returncode != 0:
        log.error(f"Link extraction failed: {result.stderr[:500]}")
        return False
    log.info("Link extraction complete")
    return True


def step_clone() -> bool:
    """Step 3: Clone new candidate repos."""
    log.info("=== Step 3: Clone repos ===")
    result = _run([
        str(VENV_PYTHON), "scripts/clone_and_extract.py",
        "--execute", "--yes",
    ])
    if result.returncode not in (0, 1):  # 0 = success, 1 = some failures but not fatal
        log.error(f"Clone failed: {result.stderr[:500]}")
        return False
    log.info("Clone step complete")
    return True


def step_pattern_extract() -> bool:
    """Step 4: Extract patterns from newly cloned repos."""
    log.info("=== Step 4: Pattern extraction ===")
    result = _run([
        str(VENV_PYTHON), "scripts/pattern_extractor.py",
        "--since-days", "1",
    ])
    if result.returncode != 0:
        log.error(f"Pattern extraction failed: {result.stderr[:500]}")
        return False
    log.info("Pattern extraction complete")
    return True


def step_hf_search() -> bool:
    """Step 5: HuggingFace Hub search (every 2 hours)."""
    log.info("=== Step 5: HF Hub search ===")
    result = _run([str(VENV_PYTHON), "scripts/hf_search.py"])
    if result.returncode != 0:
        log.error(f"HF search failed: {result.stderr[:500]}")
        return False
    log.info("HF search complete")
    return True


def step_digest(state: Dict[str, Any]) -> bool:
    """Step 6: Write a research digest (every 4 hours)."""
    log.info("=== Step 6: Research digest ===")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    digest_path = DIGEST_DIR / f"research_digest_{ts}.md"

    # Gather recent discoveries
    discoveries_files = sorted(EXTERNAL_RESEARCH_DIR.glob("discoveries_*.json"))
    recent_papers: List[Dict[str, Any]] = []
    for fp in discoveries_files[-3:]:  # Last 3 discovery files
        try:
            data = json.loads(fp.read_text())
            recent_papers.extend(data.get("discoveries", []))
        except Exception:
            pass

    # Gather recent findings
    findings_files = sorted(EXTERNAL_RESEARCH_DIR.glob("*_findings.md"))
    recent_findings = []
    for fp in findings_files[-3:]:
        try:
            recent_findings.append(fp.read_text()[:2000])
        except Exception:
            pass

    # Gather HF manifest
    hf_files = sorted(EXTERNAL_RESEARCH_DIR.glob("hf_manifest_*.json"))
    hf_summary = []
    if hf_files:
        try:
            hf_data = json.loads(hf_files[-1].read_text())
            notable = [r for r in hf_data.get("results", []) if r.get("notable")]
            hf_summary = notable[:10]
        except Exception:
            pass

    # Build digest
    lines = [
        f"# Research Digest — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"## Run #{state['run_count']} | Papers discovered: {len(recent_papers)}",
        "",
    ]

    # Top papers
    if recent_papers:
        lines.append("## Top Papers")
        lines.append("")
        # Deduplicate by ID
        seen: set = set()
        unique_papers = []
        for p in recent_papers:
            pid = p.get("id", "")
            if pid not in seen:
                seen.add(pid)
                unique_papers.append(p)
        for p in unique_papers[:10]:
            title = p.get("title", "?")
            pid = p.get("id", "")
            url = p.get("url", "")
            abstract = (p.get("abstract", "") or "")[:200]
            lines.append(f"### {title}")
            lines.append(f"- **ID**: {pid}")
            lines.append(f"- **URL**: {url}")
            lines.append(f"- **Abstract**: {abstract}")
            lines.append("")

    # Top findings
    if recent_findings:
        lines.append("## Recent Findings from Cloned Repos")
        lines.append("")
        for i, f in enumerate(recent_findings):
            lines.append(f"### Findings batch {i + 1}")
            lines.append(f[:1500])
            lines.append("")

    # HF assets
    if hf_summary:
        lines.append("## Notable HuggingFace Assets")
        lines.append("")
        for r in hf_summary:
            lines.append(f"- [{r['type']}] {r['id']} — {r['likes']} likes, {r.get('downloads', 0)} downloads")
            lines.append(f"  {r['url']}")
        lines.append("")

    lines.append(f"## State: run #{state['run_count']}")
    lines.append(f"- Last HF search: {state.get('last_hf_run', 'never')}")
    lines.append(f"- Last digest: {state.get('last_digest_run', 'never')}")
    lines.append("")

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    digest_path.write_text("\n".join(lines))
    log.info(f"Wrote digest: {digest_path}")
    return True


def run_full_pipeline(args: argparse.Namespace) -> int:
    """Run the full pipeline once."""
    state = _load_state()
    state["run_count"] = state.get("run_count", 0) + 1
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    run_num = state["run_count"]
    log.info(f"═══ Pipeline Run #{run_num} ═══")

    # Step 1: Discovery (always)
    if not args.skip_discover:
        if not step_discover():
            log.warning("Discovery step had errors — continuing")

    # Step 2: Extract code links (always)
    if not args.skip_extract:
        if not step_extract_links():
            log.warning("Link extraction had errors — continuing")

    # Step 3: Clone repos (always)
    if not args.skip_clone:
        if not step_clone():
            log.warning("Clone step had errors — continuing")

    # Step 4: Pattern extraction (always)
    if not args.skip_patterns:
        if not step_pattern_extract():
            log.warning("Pattern extraction had errors — continuing")

    # Step 5: HF search (every 2 runs = ~2 hours with 60-min interval)
    if not args.skip_hf:
        last_hf = state.get("last_hf_run")
        do_hf = True
        if last_hf:
            try:
                last_dt = datetime.fromisoformat(last_hf)
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                do_hf = elapsed > 7200  # 2 hours
            except Exception:
                pass
        if do_hf or args.force_hf:
            if step_hf_search():
                state["last_hf_run"] = datetime.now(timezone.utc).isoformat()
        else:
            log.info("Skipping HF search (last run < 2 hours ago)")

    # Step 6: Digest (every 4 runs = ~4 hours)
    if not args.skip_digest:
        last_digest = state.get("last_digest_run")
        do_digest = True
        if last_digest:
            try:
                last_dt = datetime.fromisoformat(last_digest)
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                do_digest = elapsed > 14400  # 4 hours
            except Exception:
                pass
        if do_digest or args.force_digest:
            if step_digest(state):
                state["last_digest_run"] = datetime.now(timezone.utc).isoformat()
        else:
            log.info("Skipping digest (last run < 4 hours ago)")

    _save_state(state)
    log.info(f"═══ Pipeline Run #{run_num} Complete ═══")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Research pipeline orchestrator")
    parser.add_argument("--full", action="store_true", help="Run full pipeline (default)")
    parser.add_argument("--hf-only", action="store_true", help="Only run HF search")
    parser.add_argument("--digest-only", action="store_true", help="Only write digest")
    parser.add_argument("--skip-discover", action="store_true", help="Skip discovery step")
    parser.add_argument("--skip-extract", action="store_true", help="Skip link extraction")
    parser.add_argument("--skip-clone", action="store_true", help="Skip clone step")
    parser.add_argument("--skip-patterns", action="store_true", help="Skip pattern extraction")
    parser.add_argument("--skip-hf", action="store_true", help="Skip HF search")
    parser.add_argument("--skip-digest", action="store_true", help="Skip digest")
    parser.add_argument("--force-hf", action="store_true", help="Force HF search regardless of interval")
    parser.add_argument("--force-digest", action="store_true", help="Force digest regardless of interval")
    args = parser.parse_args()

    if args.hf_only:
        return 0 if step_hf_search() else 1

    if args.digest_only:
        state = _load_state()
        return 0 if step_digest(state) else 1

    return run_full_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
