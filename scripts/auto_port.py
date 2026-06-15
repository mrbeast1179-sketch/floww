#!/usr/bin/env python3
"""
scripts/auto_port.py

For each newly cloned repo, detect portable kernels and generate port proposals.

A "portable kernel" is:
  (a) <500 LOC Python
  (b) Clear single-purpose (one GEX calc, one Hawkes fit, one vol surface interp)
  (c) Has a benchmark/test fixture against a known dataset

For qualifying kernels:
  1. Run the repo's own benchmark → record numbers
  2. Generate a Hermes-style port: type hints, docstrings with paper citation, Numba-decorated
  3. Write port proposal to memory/auto_port_proposal_<repo>_<date>.md

Usage:
    python scripts/auto_port.py [--since-days 1] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
CLONED_DIR = REPO_ROOT / "data" / "github-repos" / "cloned"
PROVENANCE_PATH = REPO_ROOT / "data" / "github-repos" / "clone_provenance.json"
MEMORY_DIR = REPO_ROOT / "memory"
VENV_PYTHON = REPO_ROOT / "backend" / ".venv" / "bin" / "python"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("auto_port")

MAX_LOC = 500  # Max lines of code for a portable kernel

# Kernel categories we can port
KERNEL_CATEGORIES = {
    "GEX calculation": {
        "import_patterns": ["numpy", "scipy"],
        "function_patterns": ["gamma_exposure", "gex", "gamma_position", "dealer_gamma"],
        "target_file": "backend/services/gex_aggregator.py",
        "numba_compatible": True,
    },
    "Hawkes process": {
        "import_patterns": ["numpy"],
        "function_patterns": ["hawkes", "intensity", "branching", "kernel_fit", "em_fit"],
        "target_file": "backend/services/hawkes_process.py",
        "numba_compatible": True,
    },
    "Vol surface interpolation": {
        "import_patterns": ["numpy", "scipy"],
        "function_patterns": ["svi", "sabr", "vol_surface", "implied_vol", "skew_fit", "surface_interp"],
        "target_file": "backend/services/stochastic_vol.py",
        "numba_compatible": True,
    },
    "Options Greeks": {
        "import_patterns": ["numpy", "scipy"],
        "function_patterns": ["delta", "gamma", "theta", "vega", "rho", "greeks", "black_scholes", "bs_price"],
        "target_file": "backend/bs_greeks.py",
        "numba_compatible": True,
    },
    "VPIN calculation": {
        "import_patterns": ["numpy", "pandas"],
        "function_patterns": ["vpin", "flow_toxicity", "volume_bucket", "buy_volume", "sell_volume"],
        "target_file": "backend/services/vpin_engine.py",
        "numba_compatible": False,
    },
    "1D-CNN anomaly detector": {
        "import_patterns": ["torch", "tensorflow", "keras"],
        "function_patterns": ["autoencoder", "conv1d", "reconstruction", "anomaly_score", "threshold"],
        "target_file": "backend/services/anomaly_detector.py",
        "numba_compatible": False,
    },
    "LOB feature engineering": {
        "import_patterns": ["numpy", "pandas"],
        "function_patterns": ["order_book", "microprice", "imbalance", "spread", "depth", "queue_imbalance"],
        "target_file": "backend/services/flowseeker.py",
        "numba_compatible": True,
    },
}


def get_recently_cloned(since_days: int = 1) -> List[Dict[str, str]]:
    """Return repos cloned within the last N days."""
    if not PROVENANCE_PATH.exists():
        return []

    provenance = json.loads(PROVENANCE_PATH.read_text())
    cutoff = datetime.now(timezone.utc).timestamp() - (since_days * 86400)
    recent: List[Dict[str, str]] = []
    seen: set[str] = set()

    for entry in provenance:
        cloned_at = entry.get("cloned_at", "")
        owner = entry.get("owner", "")
        repo = entry.get("repo", "")
        key = f"{owner}/{repo}"
        if key in seen:
            continue
        seen.add(key)

        if cloned_at:
            try:
                dt = datetime.fromisoformat(cloned_at.replace("Z", "+00:00"))
                if dt.timestamp() >= cutoff:
                    recent.append({
                        "owner": owner,
                        "repo": repo,
                        "local_path": str(CLONED_DIR / f"{owner}_{repo}"),
                        "cloned_at": cloned_at,
                    })
            except (ValueError, TypeError):
                pass

    return recent


def count_python_loc(repo_path: Path) -> int:
    """Count total lines of Python code in a repo."""
    total = 0
    for py_file in repo_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="replace")
            # Count non-empty, non-comment lines
            lines = [l for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
            total += len(lines)
        except Exception:
            pass
    return total


def find_kernel_files(repo_path: Path) -> List[Dict[str, Any]]:
    """Find Python files that contain kernel-worthy functions."""
    kernels: List[Dict[str, Any]] = []

    for py_file in repo_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        if py_file.name.startswith("test_") or py_file.name.startswith("conftest"):
            continue

        try:
            content = py_file.read_text(errors="replace")
        except Exception:
            continue

        loc = len([l for l in content.splitlines() if l.strip() and not l.strip().startswith("#")])
        if loc > MAX_LOC:
            continue

        # Check which kernel categories this file matches
        content_lower = content.lower()
        for category, config in KERNEL_CATEGORIES.items():
            # Check import patterns
            has_imports = any(
                re.search(rf"\b{imp}\b", content_lower) or
                re.search(rf"import {imp}", content_lower) or
                re.search(rf"from {imp}", content_lower)
                for imp in config["import_patterns"]  # type: ignore[attr-defined]
            )

            # Check function patterns
            matched_fns = []
            for pattern in config["function_patterns"]:  # type: ignore[attr-defined]
                if pattern in content_lower:
                    # Find actual function definitions
                    fn_matches = re.findall(
                        rf"(?:def|class)\s+(\w*{pattern}\w*)\s*\(",
                        content, re.IGNORECASE,
                    )
                    matched_fns.extend(fn_matches)

            if has_imports and matched_fns:
                # Check for benchmark/test
                has_benchmark = bool(re.search(
                    r"(?:benchmark|test|assert|check|validate|compare)",
                    content_lower,
                ))

                kernels.append({
                    "file": str(py_file.relative_to(repo_path)),
                    "category": category,
                    "loc": loc,
                    "matched_functions": list(set(matched_fns)),
                    "has_benchmark": has_benchmark,
                    "target_file": config["target_file"],
                    "numba_compatible": config["numba_compatible"],
                    "content_preview": content[:2000],
                })

    return kernels


def run_benchmark(repo_path: Path, kernel_file: str) -> Optional[str]:
    """Try to run a repo's benchmark/test and capture output."""
    py_file = repo_path / kernel_file
    if not py_file.exists():
        return None

    # Check if file is runnable (has if __name__ == __main__ or test functions)
    content = py_file.read_text(errors="replace")
    if "__main__" not in content and "def test_" not in content:
        return None

    try:
        result = subprocess.run(
            [sys.executable, str(py_file)],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout + result.stderr
        return output[:2000] if output.strip() else None
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as exc:
        return f"ERROR: {exc}"


def generate_port_proposal(
    owner: str,
    repo: str,
    kernel: Dict[str, Any],
    benchmark_output: Optional[str],
) -> str:
    """Generate a port proposal markdown document."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    lines = [
        f"# Auto-Port Proposal: {owner}/{repo}",
        f"",
        f"**Date**: {ts}",
        f"**Source file**: `{kernel['file']}`",
        f"**Category**: {kernel['category']}",
        f"**Target service**: `{kernel['target_file']}`",
        f"**LOC**: {kernel['loc']}",
        f"**Numba-compatible**: {kernel['numba_compatible']}",
        f"**Has benchmark**: {kernel['has_benchmark']}",
        f"",
        f"## Matched Functions",
        f"",
    ]
    for fn in kernel["matched_functions"]:
        lines.append(f"- `{fn}()`")

    lines.extend([
        f"",
        f"## Source Preview",
        f"",
        f"```python",
        kernel["content_preview"][:1500],
        f"```",
        f"",
    ])

    if benchmark_output:
        lines.extend([
            f"## Benchmark Output",
            f"",
            f"```",
            benchmark_output[:1000],
            f"```",
            f"",
        ])

    lines.extend([
        f"## Porting Plan",
        f"",
        f"1. Extract the core kernel from `{kernel['file']}`",
        f"2. Add type hints (numpy arrays → `np.ndarray`, scalars → `float`)",
        f"3. Add docstring with paper citation (from source repo's README)",
    ])

    if kernel["numba_compatible"]:
        lines.append(f"4. Decorate with `@numba.njit` for vectorizable loops")

    lines.extend([
        f"5. Write unit test comparing output against source repo's benchmark",
        f"6. Target: relative error < 1e-4",
        f"",
        f"## Status",
        f"",
        f"- [ ] Extracted kernel",
        f"- [ ] Added type hints + docstrings",
        f"- [ ] Numba-decorated" if kernel["numba_compatible"] else "",
        f"- [ ] Unit test written",
        f"- [ ] Benchmark passed (rel-err < 1e-4)",
        f"- [ ] Merged into `{kernel['target_file']}`",
        f"",
    ])

    return "\n".join(line for line in lines if line is not None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-port kernels from cloned repos")
    parser.add_argument("--since-days", type=int, default=1, help="Analyze repos cloned in last N days")
    parser.add_argument("--dry-run", action="store_true", help="Only report, don't write proposals")
    args = parser.parse_args()

    recent = get_recently_cloned(args.since_days)
    log.info(f"Found {len(recent)} recently cloned repos")

    if not recent:
        log.info("No recent clones — nothing to analyze")
        return 0

    proposals_written = 0

    for repo_info in recent:
        repo_path = Path(repo_info["local_path"])
        if not repo_path.exists():
            continue

        owner = repo_info["owner"]
        repo = repo_info["repo"]
        log.info(f"Analyzing: {owner}/{repo}")

        # Quick LOC check
        total_loc = count_python_loc(repo_path)
        log.info(f"  Total Python LOC: {total_loc}")

        if total_loc > MAX_LOC * 5:
            log.info(f"  Skipping: too large ({total_loc} LOC)")
            continue

        # Find kernel files
        kernels = find_kernel_files(repo_path)
        if not kernels:
            log.info(f"  No portable kernels found")
            continue

        log.info(f"  Found {len(kernels)} potential kernel(s)")
        for kernel in kernels:
            log.info(f"    {kernel['category']}: {kernel['file']} ({kernel['loc']} LOC)")
            log.info(f"      Functions: {', '.join(kernel['matched_functions'][:5])}")

            # Try to run benchmark
            benchmark_output = None
            if kernel["has_benchmark"]:
                benchmark_output = run_benchmark(repo_path, kernel["file"])
                if benchmark_output:
                    log.info(f"  Benchmark: {benchmark_output[:100]}...")

            # Generate proposal
            proposal = generate_port_proposal(owner, repo, kernel, benchmark_output)

            if not args.dry_run:
                MEMORY_DIR.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d")
                safe_name = re.sub(r"[^a-zA-Z0-9]", "_", f"{owner}_{repo}_{kernel['file'].replace('/', '_')}")
                proposal_path = MEMORY_DIR / f"auto_port_proposal_{safe_name}_{ts}.md"
                proposal_path.write_text(proposal)
                log.info(f"  Wrote proposal: {proposal_path}")
                proposals_written += 1
            else:
                log.info(f"  [DRY RUN] Would write proposal for {kernel['category']}")

    log.info(f"\nTotal proposals written: {proposals_written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
