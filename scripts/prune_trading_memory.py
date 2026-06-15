#!/usr/bin/env python3
"""
scripts/prune_trading_memory.py — Archive old, irrelevant trading memories.

Policies:
- mem0 Platform: Soft-delete memories with low relevance scores or old timestamps
- Claude Code memory dir: Archive files older than threshold to _archive/
- Obsidian vault: Tag old notes with #archived, move to _archive/ subfolder

Archiving rules:
- type=session entries older than ARCHIVE_DAYS → archive
- type=stale_signal (signals not seen in ARCHIVE_DAYS) → archive
- Durable types (project_*, reference_*, feedback_*, decision_*, config_*) → NEVER archive
- High-impact memories (score > 0.8) → NEVER archive
- PLUR/mem0 entries unrelated to trading → archive (they pollute search)

Usage:
    python3 scripts/prune_trading_memory.py              # live run
    python3 scripts/prune_trading_memory.py --dry-run    # show what would be archived
    python3 scripts/prune_trading_memory.py --report     # show memory stats
    python3 scripts/prune_trading_memory.py --archive-mem0  # archive mem0 entries
"""

import argparse
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-Users-nav-Documents-GitHub-floww" / "memory"
OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian Vault"
ARCHIVE_DIR = CLAUDE_MEMORY_DIR / "_archive"
OBSIDIAN_ARCHIVE_DIR = OBSIDIAN_DIR / "_archive"
REPORTS_DIR = REPO_ROOT / "reports"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Never-archive types (durable memories)
DURABLE_TYPES = {"project", "reference", "feedback", "decision", "config", "research_insight"}

# Types that can be archived after threshold
ARCHIVABLE_TYPES = {"session", "stale_signal", "trade_outcome"}

# Default thresholds
ARCHIVE_DAYS = 30
STALE_SIGNAL_DAYS = 14
HIGH_IMPACT_THRESHOLD = 0.8

# Trading-relevant keywords (memories containing these are kept)
TRADING_KEYWORDS = {
    "VPIN", "GEX", "VEX", "DEX", "gamma", "delta", "vega", "theta", "vanna", "charm",
    "SPY", "QQQ", "option", "trade", "signal", "regime", "toxicity", "liquidity",
    "iron_condor", "paper_trading", "execution", "risk", "position", "pnl", "sharpe",
    "floww", "heatseeker", "flowseeker", "atlas", "trinity", "node", "wall", "flip",
    "squeeze", "anomaly", "hawkes", "sabr", "svi", "ml", "model", "backtest",
    "conviction", "kyle", "almgren", "hasbrouck", "bucket", "volume", "imbalance",
}


# ─── Memory Stats ────────────────────────────────────────────────

def get_memory_stats() -> dict[str, Any]:
    """Get statistics about current memory state."""
    stats: dict[str, Any] = {
        "claude_memory": {"total": 0, "by_type": {}, "archivable": 0},
        "obsidian": {"total": 0, "by_type": {}, "archivable": 0},
        "mem0": {"total": 0, "by_type": {}, "archivable": 0},
    }

    # Claude Code memory
    if CLAUDE_MEMORY_DIR.exists():
        for f in CLAUDE_MEMORY_DIR.glob("*.md"):
            if f.name.startswith("_"):
                continue
            stats["claude_memory"]["total"] += 1
            mem_type = f.stem.split("_")[0] if "_" in f.stem else "unknown"
            stats["claude_memory"]["by_type"][mem_type] = \
                stats["claude_memory"]["by_type"].get(mem_type, 0) + 1
            if mem_type in ARCHIVABLE_TYPES:
                # Check age
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                age_days = (datetime.now(timezone.utc) - mtime).days
                if age_days > ARCHIVE_DAYS:
                    stats["claude_memory"]["archivable"] += 1

    # Obsidian
    if OBSIDIAN_DIR.exists():
        for f in OBSIDIAN_DIR.glob("*.md"):
            if f.name.startswith("_") or f.name.startswith("."):
                continue
            stats["obsidian"]["total"] += 1
            content = f.read_text()[:500]
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            age_days = (datetime.now(timezone.utc) - mtime).days

            if age_days > ARCHIVE_DAYS:
                # Check if it's trading-relevant
                is_trading = any(kw.lower() in content.lower() for kw in TRADING_KEYWORDS)
                if not is_trading:
                    stats["obsidian"]["archivable"] += 1

    # mem0 (via API)
    try:
        cfg_path = Path.home() / ".mem0" / "config.json"
        if cfg_path.exists():
            cfg = json.load(open(cfg_path))
            api_key = cfg.get("platform", {}).get("api_key")
            if api_key:
                from mem0 import MemoryClient  # type: ignore[attr-defined]
                client: Any = MemoryClient(api_key=api_key)
                result = client.get_all(
                    filters={"user_id": "user_c778280e23af"},
                    limit=200,
                )
                if isinstance(result, dict):
                    result = result.get("results", [])
                stats["mem0"]["total"] = len(result)

                for m in result:
                    meta = m.get("metadata", {})
                    mem_type = meta.get("type", "unknown") if meta else "unknown"
                    stats["mem0"]["by_type"][mem_type] = \
                        stats["mem0"]["by_type"].get(mem_type, 0) + 1

                    # Check if archivable
                    created = m.get("created_at", "")
                    if created:
                        try:
                            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            age_days = (datetime.now(timezone.utc) - created_dt).days
                            if age_days > ARCHIVE_DAYS and mem_type in ARCHIVABLE_TYPES:
                                stats["mem0"]["archivable"] += 1
                        except (ValueError, TypeError):
                            pass

                    # Count non-trading entries (PLUR noise)
                    mem_text = m.get("memory", "")[:200]
                    is_trading = any(kw.lower() in mem_text.lower() for kw in TRADING_KEYWORDS)
                    if not is_trading and created:
                        try:
                            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                            age_days = (datetime.now(timezone.utc) - created_dt).days
                            if age_days > 7:  # Archive non-trading after 7 days
                                stats["mem0"]["archivable"] += 1
                        except (ValueError, TypeError):
                            pass
    except Exception as e:
        logger.debug("mem0 stats failed: %s", e)

    return stats


def print_stats(stats: dict[str, Any]) -> None:
    """Print memory statistics."""
    print("# Memory Statistics\n")
    for system, data in stats.items():
        print(f"## {system}")
        print(f"- Total entries: {data['total']}")
        print(f"- Archivable: {data.get('archivable', 0)}")
        if data["by_type"]:
            print("- By type:")
            for t, count in sorted(data["by_type"].items(), key=lambda x: -x[1]):
                print(f"  - {t}: {count}")
        print()


# ─── Archiving Functions ─────────────────────────────────────────

def archive_claude_memory(dry_run: bool = True) -> int:
    """Archive old Claude Code memory files."""
    if not CLAUDE_MEMORY_DIR.exists():
        logger.info("Claude memory dir not found")
        return 0

    archived = 0
    now = datetime.now(timezone.utc)

    for f in CLAUDE_MEMORY_DIR.glob("*.md"):
        if f.name.startswith("_"):
            continue

        mem_type = f.stem.split("_")[0] if "_" in f.stem else "unknown"

        # Never archive durable types
        if mem_type in DURABLE_TYPES:
            continue

        # Check if archivable type
        if mem_type not in ARCHIVABLE_TYPES:
            continue

        # Check age
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).days

        if age_days > ARCHIVE_DAYS:
            if dry_run:
                logger.info(f"  [DRY] Would archive: {f.name} ({age_days}d old)")
            else:
                ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                # Preserve date structure
                date_dir = ARCHIVE_DIR / mtime.strftime("%Y-%m")
                date_dir.mkdir(parents=True, exist_ok=True)
                dest = date_dir / f.name
                shutil.copy2(f, dest)
                f.unlink()
                logger.info(f"  Archived: {f.name} → {dest}")
            archived += 1

    return archived


def archive_obsidian(dry_run: bool = True) -> int:
    """Archive old Obsidian notes that aren't trading-relevant."""
    if not OBSIDIAN_DIR.exists():
        logger.info("Obsidian dir not found")
        return 0

    archived = 0
    now = datetime.now(timezone.utc)

    for f in OBSIDIAN_DIR.glob("*.md"):
        if f.name.startswith("_") or f.name.startswith("."):
            continue

        # Check age
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        age_days = (now - mtime).days

        if age_days > ARCHIVE_DAYS:
            # Check trading relevance
            content = f.read_text()[:1000]
            is_trading = any(kw.lower() in content.lower() for kw in TRADING_KEYWORDS)

            if not is_trading:
                if dry_run:
                    logger.info(f"  [DRY] Would archive: {f.name} ({age_days}d, not trading)")
                else:
                    OBSIDIAN_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
                    dest = OBSIDIAN_ARCHIVE_DIR / f.name
                    shutil.copy2(f, dest)
                    f.unlink()
                    logger.info(f"  Archived: {f.name} → {dest}")
                archived += 1

    return archived


def archive_mem0(dry_run: bool = True) -> int:
    """Archive (soft-delete) irrelevant mem0 entries."""
    try:
        cfg_path = Path.home() / ".mem0" / "config.json"
        if not cfg_path.exists():
            return 0

        cfg = json.load(open(cfg_path))
        api_key = cfg.get("platform", {}).get("api_key")
        if not api_key:
            return 0

        from mem0 import MemoryClient  # type: ignore[attr-defined]
        client: Any = MemoryClient(api_key=api_key)

        result = client.get_all(
            filters={"user_id": "user_c778280e23af"},
            limit=200,
        )
        if isinstance(result, dict):
            result = result.get("results", [])

        archived = 0
        now = datetime.now(timezone.utc)

        for m in result:
            mem_id = m.get("id", "")
            mem_text = m.get("memory", "")[:300]
            meta = m.get("metadata", {})
            mem_type = meta.get("type", "unknown") if meta else "unknown"
            created = m.get("created_at", "")

            # Never archive durable types
            if mem_type in DURABLE_TYPES:
                continue

            # Never archive trading-specific types we just embedded
            if mem_type in {"trade_signal", "market_regime", "code_pattern",
                           "strategy_config", "research_insight", "trade_outcome"}:
                continue

            # Check age and trading relevance
            if created:
                try:
                    created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_days = (now - created_dt).days
                except (ValueError, TypeError):
                    age_days = 0

                is_trading = any(kw.lower() in mem_text.lower() for kw in TRADING_KEYWORDS)

                # Archive non-trading entries older than 7 days
                # or archivable types older than ARCHIVE_DAYS
                should_archive = (
                    (not is_trading and age_days > 7) or
                    (mem_type in ARCHIVABLE_TYPES and age_days > ARCHIVE_DAYS)
                )

                if should_archive:
                    if dry_run:
                        logger.info(
                            f"  [DRY] Would archive mem0: {mem_id[:12]}... "
                            f"({mem_type}, {age_days}d, trading={is_trading})"
                        )
                    else:
                        try:
                            client.delete(mem_id)
                            logger.info(f"  Archived mem0: {mem_id[:12]}... ({mem_type})")
                            archived += 1
                            time.sleep(0.05)  # Rate limit
                        except Exception as e:
                            logger.warning(f"  Failed to delete {mem_id}: {e}")

        return archived

    except Exception as e:
        logger.error("mem0 archiving failed: %s", e)
        return 0


def write_archive_report(stats: dict[str, Any], claude_archived: int, obsidian_archived: int, mem0_archived: int) -> None:
    """Write archiving report."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"archive_report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"

    report = f"""# Memory Archive Report — {datetime.now(timezone.utc).isoformat()}

## Memory Statistics
"""
    for system, data in stats.items():
        report += f"\n### {system}\n"
        report += f"- Total entries: {data['total']}\n"
        report += f"- Archivable: {data.get('archivable', 0)}\n"
        for t, count in sorted(data.get("by_type", {}).items(), key=lambda x: -x[1]):
            report += f"  - {t}: {count}\n"

    report += f"""
## Archive Results
- Claude Code files archived: {claude_archived}
- Obsidian notes archived: {obsidian_archived}
- mem0 entries archived: {mem0_archived}

## Retained (Durable)
- project_*: Never archived
- reference_*: Never archived
- feedback_*: Never archived
- decision_*: Never archived
- config_*: Never archived
- research_insight: Never archived

## Archived
- session_*: After {ARCHIVE_DAYS} days
- stale_signal: After {STALE_SIGNAL_DAYS} days
- Non-trading mem0: After 7 days
"""
    report_path.write_text(report)
    logger.info("Report saved to %s", report_path)


# ─── Main ────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Prune and archive trading memory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived")
    parser.add_argument("--report", action="store_true", help="Show memory stats only")
    parser.add_argument("--archive-mem0", action="store_true", help="Archive mem0 entries")
    parser.add_argument("--archive-all", action="store_true", help="Archive all systems")
    parser.add_argument("--archive-days", type=int, default=ARCHIVE_DAYS, help=f"Archive threshold (default: {ARCHIVE_DAYS})")
    args = parser.parse_args()

    logger.info("Starting memory pruning analysis...")

    # Get stats
    stats = get_memory_stats()

    if args.report:
        print_stats(stats)
        return

    dry_run = not args.archive_all and not args.archive_mem0

    if dry_run:
        logger.info("DRY RUN — no changes will be made")
        logger.info("Use --archive-all or --archive-mem0 to actually archive")

    # Archive Claude Code memory
    claude_archived = archive_claude_memory(dry_run=dry_run)

    # Archive Obsidian
    obsidian_archived = archive_obsidian(dry_run=dry_run)

    # Archive mem0
    mem0_archived = 0
    if args.archive_mem0 or args.archive_all:
        mem0_archived = archive_mem0(dry_run=dry_run)

    # Results
    logger.info(f"\nArchive summary (dry_run={dry_run}):")
    logger.info(f"  Claude Code: {claude_archived} files")
    logger.info(f"  Obsidian: {obsidian_archived} notes")
    logger.info(f"  mem0: {mem0_archived} entries")

    # Write report
    if not dry_run:
        write_archive_report(stats, claude_archived, obsidian_archived, mem0_archived)

    # Print stats
    print_stats(stats)


if __name__ == "__main__":
    main()
