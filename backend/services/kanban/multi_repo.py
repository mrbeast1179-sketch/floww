#!/usr/bin/env python3
"""
backend/services/kanban/multi_repo.py — Multi-repo coordination.

Nav has multiple projects (floww, gflows, baby-billy-dvt).
Some kanban cards span repos. Schema extension: cards can declare
`affects_repos: [floww, gflows]`; watcher monitors all listed repos.
Cross-repo SWARM_STATUS.md aggregates state from all.
"""

import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)

# Known project repos
PROJECT_REPOS = {
    "floww": REPO_ROOT,
    "gflows": Path.home() / "Documents" / "GitHub" / "gflows",
    "baby-billy-dvt": Path.home() / "Documents" / "GitHub" / "baby-billy-dvt",
}


if __name__ == "__main__":
    logger.info(generate_multi_repo_status())
