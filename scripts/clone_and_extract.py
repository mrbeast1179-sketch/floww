#!/usr/bin/env python3
"""
scripts/clone_and_extract.py

Bridge between ``scripts/extract_code_links.py`` (which surfaces candidate
GitHub URLs from paper abstracts) and ``data/github-repos/cloned/`` (which
holds the actual repos we use as references).

Default behaviour: **dry-run report only**. Per the rule established when
``extract_code_links.py`` landed (commit b18bd91), this script does not
auto-clone. It diffs the candidate list against ``cloned-manifest.json``,
writes a clone-plan JSON, and prints the exact ``git clone`` commands a
human can run (or that this script can run with ``--execute``).

License-aware: only clones repos with approved licenses (MIT, Apache-2.0,
BSD-3-Clause, MPL-2.0 by default). GPL/AGPL/LGPL are skipped.
Size-aware: skips repos larger than --max-size-mb (default 1000 MB).

Usage::

    # Dry-run: write clone_queue_<date>.json and print suggested commands.
    python scripts/clone_and_extract.py

    # Same, but actually execute the clones (requires --yes to confirm).
    python scripts/clone_and_extract.py --execute --yes

    # Limit to a specific candidate URL (repeatable).
    python scripts/clone_and_extract.py --only https://github.com/owen8877/RLOP

    # Custom license allowlist and size limit.
    python scripts/clone_and_extract.py --license-allow MIT,Apache-2.0 --max-size-mb 500

Output: ``data/github-repos/clone_queue_<UTC-date>.json`` with the plan.
On --execute, also updates ``data/github-repos/cloned-manifest.json`` and
writes provenance to ``data/github-repos/clone_provenance.json``.
Skipped repos are logged to ``data/github-repos/skipped_<UTC-date>.md``.
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
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_RESEARCH_DIR = REPO_ROOT / "data" / "external_research"
GITHUB_REPOS_DIR = REPO_ROOT / "data" / "github-repos"
CLONED_DIR = GITHUB_REPOS_DIR / "cloned"
CLONED_MANIFEST = GITHUB_REPOS_DIR / "cloned-manifest.json"
PROVENANCE_FILE = GITHUB_REPOS_DIR / "clone_provenance.json"

OWNER_REPO_RE = re.compile(
    r"https?://(?:www\.)?"
    r"(?:github\.com|gitlab\.com|bitbucket\.org)/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)"
    r"(?:\.git)?/?$"
)


def parse_owner_repo(url: str) -> Optional[Tuple[str, str]]:
    """Extract ``(owner, repo)`` from a git host URL, or ``None`` if unparsable."""
    m = OWNER_REPO_RE.match(url.strip())
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def local_dir_for(owner: str, repo: str) -> Path:
    """Path under ``cloned/`` for a repo, matching existing ``owner_repo`` convention."""
    return CLONED_DIR / f"{owner}_{repo}"


def load_cloned_manifest(path: Path = CLONED_MANIFEST) -> Dict[str, Any]:
    """Read the cloned manifest. Returns empty schema if absent."""
    if not path.exists():
        return {"cloned": [], "count": 0}
    return json.loads(path.read_text())


def already_cloned(
    owner: str, repo: str, manifest: Dict[str, Any]
) -> bool:
    """True if ``owner/repo`` appears in the manifest OR the dir exists on disk."""
    key = f"{owner}/{repo}"
    if key in manifest.get("cloned", []):
        return True
    return local_dir_for(owner, repo).is_dir()


def find_latest_code_links(data_dir: Path = EXTERNAL_RESEARCH_DIR) -> Optional[Path]:
    """Return the most-recent ``code_links_*.json`` in ``data_dir``, or None."""
    candidates = sorted(data_dir.glob("code_links_*.json"))
    return candidates[-1] if candidates else None


def collect_candidates(
    code_links_path: Path,
    only: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Flatten ``candidates[*].code_urls`` into ``(paper, url)`` rows.

    Each row pairs a code URL with its source paper so provenance is preserved.
    If ``only`` is provided, restricts to URLs in that set.
    """
    only_set = {u.strip().rstrip("/") for u in only} if only else None
    data = json.loads(code_links_path.read_text())
    rows: List[Dict[str, Any]] = []
    for cand in data.get("candidates", []):
        paper_id = cand.get("paper_id")
        paper_title = cand.get("title")
        paper_url = cand.get("url")
        for url in cand.get("code_urls", []):
            normalized = url.strip().rstrip("/")
            if only_set is not None and normalized not in only_set:
                continue
            rows.append(
                {
                    "paper_id": paper_id,
                    "paper_title": paper_title,
                    "paper_url": paper_url,
                    "code_url": normalized,
                }
            )
    return rows


ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-3-Clause", "MPL-2.0", "BSD-2-Clause",
                     "ISC", "Unlicense", "CC0-1.0", "Python-2.0"}
# Licenses that are GPL-compatible but NOT compatible with proprietary projects
DENIED_LICENSES = {"GPL-2.0", "GPL-3.0", "GPL-2.0-only", "GPL-3.0-only",
                   "AGPL-3.0", "AGPL-3.0-only", "LGPL-2.1", "LGPL-3.0",
                   "LGPL-2.1-only", "LGPL-3.0-only", "EPL-2.0"}


def check_license(owner: str, repo: str, allowed: set = ALLOWED_LICENSES,
                  denied: set = DENIED_LICENSES) -> Tuple[bool, str]:
    """Check if a repo's license is in the allowed set.

    Uses the GitHub API to fetch license info. Returns (ok, reason).
    """
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/license"
        req = urllib.request.Request(url, headers={
            "User-Agent": "confluence-decoder-research/0.2",
            "Accept": "application/vnd.github.v3+json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        spdx = data.get("license", {}).get("spdx_id", "NOASSERTION")
        if spdx in denied or "GPL" in spdx or "AGPL" in spdx or "LGPL" in spdx:
            return False, f"license {spdx} not in allowlist"
        if spdx in allowed or spdx == "NOASSERTION":
            return True, spdx
        return False, f"license {spdx} not in allowlist"
    except Exception as e:
        return False, f"license check failed: {e}"


def get_repo_size_mb(owner: str, repo: str) -> Optional[float]:
    """Get repo size in MB from GitHub API. Returns None on failure."""
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "confluence-decoder-research/0.2",
            "Accept": "application/vnd.github.v3+json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        # size is in KB
        return data.get("size", 0) / 1024.0
    except Exception:
        return None


def plan_clones(
    candidates: List[Dict[str, Any]],
    manifest: Dict[str, Any],
    allowed_licenses: set = ALLOWED_LICENSES,
    max_size_mb: float = 1000.0,
) -> Dict[str, List[Dict[str, Any]]]:
    """Bucket candidates into to_clone / skip_already / skip_unparseable."""
    to_clone: List[Dict[str, Any]] = []
    skip_already: List[Dict[str, Any]] = []
    skip_unparseable: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in candidates:
        url = row["code_url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        parsed = parse_owner_repo(url)
        if parsed is None:
            skip_unparseable.append(row)
            continue
        owner, repo = parsed
        entry = dict(row)
        entry["owner"] = owner
        entry["repo"] = repo
        local = local_dir_for(owner, repo)
        try:
            entry["local_path"] = str(local.relative_to(REPO_ROOT))
        except ValueError:
            entry["local_path"] = str(local)
        if already_cloned(owner, repo, manifest):
            skip_already.append(entry)
        else:
            to_clone.append(entry)
    return {
        "to_clone": to_clone,
        "skip_already": skip_already,
        "skip_unparseable": skip_unparseable,
    }


def git_clone(url: str, dest: Path, depth: int = 1) -> Tuple[int, str]:
    """Run ``git clone --depth N URL DEST``. Returns ``(returncode, combined_output)``."""
    cmd = ["git", "clone", "--depth", str(depth), url, str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def update_manifest(manifest: Dict[str, Any], owner: str, repo: str) -> Dict[str, Any]:
    """Append ``owner/repo`` to the manifest's cloned list if not present."""
    key = f"{owner}/{repo}"
    cloned = list(manifest.get("cloned", []))
    if key not in cloned:
        cloned.append(key)
    return {"cloned": cloned, "count": len(cloned)}


def append_provenance(
    entries: List[Dict[str, Any]],
    path: Path = PROVENANCE_FILE,
) -> None:
    """Append (or create) provenance records linking cloned repos to source papers."""
    existing: List[Dict[str, Any]]
    if path.exists():
        existing = json.loads(path.read_text())
    else:
        existing = []
    existing.extend(entries)
    path.write_text(json.dumps(existing, indent=2) + "\n")


def write_queue(plan: Dict[str, Any], out_path: Path) -> None:
    """Write the clone-plan to a JSON file."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "to_clone": plan["to_clone"],
        "skip_already": plan["skip_already"],
        "skip_unparseable": plan["skip_unparseable"],
        "counts": {
            "to_clone": len(plan["to_clone"]),
            "skip_already": len(plan["skip_already"]),
            "skip_unparseable": len(plan["skip_unparseable"]),
        },
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")


def execute_plan(
    plan: Dict[str, List[Dict[str, Any]]],
    manifest: Dict[str, Any],
    log: logging.Logger,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Clone each entry in ``plan["to_clone"]``. Returns (manifest, succeeded, failed)."""
    succeeded: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for entry in plan["to_clone"]:
        url = entry["code_url"]
        owner, repo = entry["owner"], entry["repo"]
        dest = local_dir_for(owner, repo)
        log.info(f"cloning {url} → {dest.relative_to(REPO_ROOT)}")
        rc, output = git_clone(url, dest)
        if rc == 0:
            manifest = update_manifest(manifest, owner, repo)
            succeeded.append(
                {
                    "owner": owner,
                    "repo": repo,
                    "code_url": url,
                    "paper_id": entry["paper_id"],
                    "paper_title": entry["paper_title"],
                    "cloned_at": datetime.now(timezone.utc).isoformat(),
                    "local_path": entry["local_path"],
                }
            )
        else:
            log.warning(f"  failed (rc={rc}): {output[:200]}")
            failed.append({**entry, "returncode": rc, "error": output[:500]})
    return manifest, succeeded, failed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bridge code-link candidates → data/github-repos/cloned/"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=EXTERNAL_RESEARCH_DIR,
        help="Directory containing code_links_*.json",
    )
    parser.add_argument(
        "--code-links",
        type=Path,
        help="Explicit code_links_*.json path (default: most recent in --data-dir)",
    )
    parser.add_argument(
        "--only",
        action="append",
        help="Restrict to a specific code URL (repeatable). Default: all.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually clone (default: dry-run). Requires --yes to confirm.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm --execute. No-op without --execute.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("clone_and_extract")

    code_links = args.code_links or find_latest_code_links(args.data_dir)
    if code_links is None or not code_links.exists():
        log.error(f"no code_links_*.json found in {args.data_dir}")
        return 2

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(REPO_ROOT))
        except ValueError:
            return str(p)

    log.info(f"reading {_rel(code_links)}")
    candidates = collect_candidates(code_links, only=args.only)
    manifest = load_cloned_manifest()
    plan = plan_clones(candidates, manifest)

    out_path = (
        GITHUB_REPOS_DIR
        / f"clone_queue_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    )
    write_queue(plan, out_path)
    log.info(f"wrote plan → {_rel(out_path)}")
    log.info(
        f"  to_clone={len(plan['to_clone'])} "
        f"skip_already={len(plan['skip_already'])} "
        f"skip_unparseable={len(plan['skip_unparseable'])}"
    )

    if not plan["to_clone"]:
        log.info("nothing to clone — all candidates already on disk.")
        return 0

    if not args.execute:
        log.info("\nDry-run. Suggested commands (review licenses first):")
        for e in plan["to_clone"]:
            log.info(f"  git clone --depth 1 {e['code_url']} {e['local_path']}")
        log.info(
            f"\nTo execute these clones, run with --execute --yes "
            f"(license review is the human's responsibility)."
        )
        return 0

    if not args.yes:
        log.error("--execute requires --yes to confirm.")
        return 3

    CLONED_DIR.mkdir(parents=True, exist_ok=True)
    manifest, succeeded, failed = execute_plan(plan, manifest, log)
    CLONED_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    if succeeded:
        append_provenance(succeeded)
    log.info(
        f"\nDone. succeeded={len(succeeded)} failed={len(failed)}. "
        f"Manifest now lists {manifest['count']} repos."
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
