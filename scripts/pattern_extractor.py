#!/usr/bin/env python3
"""
scripts/pattern_extractor.py

For each newly cloned GitHub repo, read its README + key source files and
identify patterns worth porting into the floww project. Writes findings to
data/external_research/<date>_findings.md.

Usage:
    python scripts/pattern_extractor.py [--since-days 1]
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent
CLONED_DIR = REPO_ROOT / "data" / "github-repos" / "cloned"
MANIFEST_PATH = REPO_ROOT / "data" / "github-repos" / "cloned-manifest.json"
PROVENANCE_PATH = REPO_ROOT / "data" / "github-repos" / "clone_provenance.json"
EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pattern_extractor")

# ────────────────────────────────────────────────────────────────────────────
# Pattern signatures
# ────────────────────────────────────────────────────────────────────────────

PATTERN_SIGNATURES: Dict[str, List[str]] = {
    "GEX calculation": [
        "gamma exposure", "gex", "gamma * spot", "dealer gamma",
        "gamma imbalance", "gamma wall",
    ],
    "VPIN variant": [
        "vpin", "volume-synchronized", "flow toxicity", "toxicity",
        "volume bucket", "buy volume", "sell volume",
    ],
    "Hawkes parameterization": [
        "hawkes", "self-exciting", "branching ratio", "kernel",
        "excitation kernel", "hawkes process", "intensity",
    ],
    "Vol surface technique": [
        "vol surface", "implied volatility surface", "svi", "sabr",
        "stochastic volatility", "vol skew", "vol smile",
    ],
    "LOB feature engineering": [
        "limit order book", "order book", "lob", "bid ask",
        "order flow", "market depth", "order imbalance", "microprice",
    ],
    "Options pricing model": [
        "black scholes", "heston", "jump diffusion", "merton",
        "local volatility", "implied vol", "option greeks",
    ],
    "ML anomaly detection": [
        "autoencoder", "anomaly detection", "isolation forest",
        "reconstruction error", "1d-cnn", "conv1d",
    ],
    "Dealer positioning": [
        "dealer position", "dealer hedge", "market maker",
        "options dealer", "gamma squeeze", "pin risk", "max pain",
    ],
}

SERVICE_MAP: Dict[str, str] = {
    "GEX calculation": "backend/services/gex_aggregator.py",
    "VPIN variant": "backend/services/vpin_engine.py",
    "Hawkes parameterization": "backend/services/hawkes_process.py",
    "Vol surface technique": "backend/services/stochastic_vol.py",
    "LOB feature engineering": "backend/services/flowseeker.py",
    "Options pricing model": "backend/bs_greeks.py",
    "ML anomaly detection": "backend/services/anomaly_detector.py",
    "Dealer positioning": "backend/services/gex_aggregator.py",
}

FIND_KEYWORDS: Dict[str, List[str]] = {
    "GEX calculation": ["gamma", "gex", "exposure"],
    "VPIN variant": ["vpin", "toxicity", "bucket"],
    "Hawkes parameterization": ["hawkes", "intensity", "kernel"],
    "Vol surface technique": ["surface", "vol", "svi", "sabr", "skew"],
    "LOB feature engineering": ["order_book", "lob", "bid", "ask", "depth"],
    "Options pricing model": ["price", "greeks", "delta", "gamma", "theta", "vega"],
    "ML anomaly detection": ["autoencoder", "anomaly", "detect", "reconstruct"],
    "Dealer positioning": ["dealer", "position", "hedge", "pin"],
}


def get_recently_cloned(since_days: int = 1) -> List[Dict[str, str]]:
    """Return repos cloned within the last N days from provenance."""
    if not PROVENANCE_PATH.exists():
        log.warning("No provenance file — cannot determine recent clones")
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
                        "paper_id": entry.get("paper_id", ""),
                        "paper_title": entry.get("paper_title", ""),
                    })
            except (ValueError, TypeError):
                pass

    return recent


def read_readme(repo_path: Path) -> str:
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        fp = repo_path / name
        if fp.exists():
            return fp.read_text(errors="replace")[:8000]
    return ""


def read_key_source_files(repo_path: Path, max_files: int = 10) -> Dict[str, str]:
    result: Dict[str, str] = {}
    py_files = sorted(repo_path.rglob("*.py"))
    py_files = [
        f for f in py_files
        if "__pycache__" not in str(f)
        and not f.name.startswith("test_")
        and not f.name.startswith("conftest")
    ]
    for fp in py_files[:max_files]:
        try:
            content = fp.read_text(errors="replace")[:5000]
            rel = str(fp.relative_to(repo_path))
            result[rel] = content
        except Exception:
            pass
    return result


def detect_patterns(text: str) -> List[Tuple[str, List[str]]]:
    text_lower = text.lower()
    found: List[Tuple[str, List[str]]] = []
    for category, signatures in PATTERN_SIGNATURES.items():
        matched = [s for s in signatures if s in text_lower]
        if matched:
            found.append((category, matched))
    return found


def find_key_functions(repo_path: Path, category: str) -> List[str]:
    kw = FIND_KEYWORDS.get(category, [])
    results: List[str] = []
    for py_file in repo_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(errors="replace")
            for line in content.splitlines():
                if line.strip().startswith("def ") or line.strip().startswith("class "):
                    name = line.strip().split("(")[0].replace("def ", "").replace("class ", "")
                    if any(k in name.lower() for k in kw):
                        rel = str(py_file.relative_to(repo_path))
                        results.append(f"{rel}:{name}")
        except Exception:
            pass
    return results[:10]


def get_repo_stars(owner: str, repo: str) -> int:
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}", "--jq", ".stargazers_count"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return 0


def analyze_repo(repo_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
    repo_path = Path(repo_info["local_path"])
    if not repo_path.exists():
        log.warning(f"Repo path missing: {repo_path}")
        return None

    log.info(f"Analyzing: {repo_info['owner']}/{repo_info['repo']}")
    readme = read_readme(repo_path)
    sources = read_key_source_files(repo_path)
    all_text = readme + "\n" + "\n".join(sources.values())
    patterns = detect_patterns(all_text)

    if not patterns:
        log.info("  No relevant patterns found")
        return None

    stars = get_repo_stars(repo_info["owner"], repo_info["repo"])
    findings: Dict[str, Any] = {
        "owner": repo_info["owner"],
        "repo": repo_info["repo"],
        "stars": stars,
        "paper_id": repo_info.get("paper_id", ""),
        "paper_title": repo_info.get("paper_title", ""),
        "patterns": [],
    }

    for category, matched in patterns:
        key_fns = find_key_functions(repo_path, category)
        target = SERVICE_MAP.get(category, "unknown")
        findings["patterns"].append({
            "category": category,
            "matched_signatures": matched,
            "key_functions": key_fns,
            "target_service": target,
        })

    return findings


def write_findings_report(all_findings: List[Dict[str, Any]]) -> Path:
    EXTERNAL_RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_path = EXTERNAL_RESEARCH_DIR / f"{ts}_findings.md"

    lines = [
        f"# Research Pipeline Findings — {ts}",
        "",
        f"## Repos Analyzed: {len(all_findings)}",
        "",
    ]

    for finding in sorted(all_findings, key=lambda x: x.get("stars", 0), reverse=True):
        name = f"{finding['owner']}/{finding['repo']}"
        stars = finding.get("stars", 0)
        paper = finding.get("paper_title", "")
        paper_id = finding.get("paper_id", "")

        lines.append(f"### {name}")
        lines.append(f"- **Stars**: {stars}")
        if paper:
            lines.append(f"- **Source paper**: {paper} ({paper_id})")
        lines.append("")

        for pat in finding["patterns"]:
            cat = pat["category"]
            target = pat["target_service"]
            lines.append(f"#### {cat}")
            lines.append(f"- **Matched**: {', '.join(pat['matched_signatures'])}")
            lines.append(f"- **Target service**: `{target}`")
            if pat["key_functions"]:
                lines.append("- **Key functions**:")
                for fn in pat["key_functions"]:
                    lines.append(f"  - `{fn}`")
            lines.append("")
            lines.append(
                f"**Porting recommendation**: Review `{name}` for {cat.lower()} "
                f"implementation. Key functions above may be adaptable to "
                f"`{target}`."
            )
            lines.append("")

    out_path.write_text("\n".join(lines))
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract patterns from cloned repos")
    parser.add_argument("--since-days", type=int, default=1)
    args = parser.parse_args()

    recent = get_recently_cloned(args.since_days)
    log.info(f"Found {len(recent)} recently cloned repos to analyze")

    if not recent:
        log.info("No recent clones — nothing to analyze")
        return 0

    all_findings: List[Dict[str, Any]] = []
    for repo_info in recent:
        finding = analyze_repo(repo_info)
        if finding:
            all_findings.append(finding)

    if all_findings:
        report_path = write_findings_report(all_findings)
        log.info(f"Wrote findings: {report_path}")
        log.info(f"\nSummary: {len(all_findings)} repos with relevant patterns")
        for f in all_findings:
            cats = [p["category"] for p in f["patterns"]]
            log.info(f"  {f['owner']}/{f['repo']}: {', '.join(cats)}")
    else:
        log.info("No relevant patterns found in any recent repos")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
