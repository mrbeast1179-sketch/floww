#!/usr/bin/env python3
"""
memory_mesh.py — Triple memory mesh for Claude Code ↔ Hermes durable memory ↔ Obsidian vault.
- Pushes Claude MEMORY.md → claude_autonomous_log.md in vault
- Pushes Obsidian notes → hermes_persistent_facts.md in vault (deduped by YAML fence)
- Pushes Hermes annotations → hermes_persistent_facts.md in vault
- Pushes Obsidian note(s) → Claude Sync.md (concatenate under frontmatter block)
- Dedupe by updating content between matching YAML fences
- Normalises markdown anchors [[Name]]
- Incremental: uses stamp file to skip unmodified sources
"""

import argparse
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

# --- Configuration (absolute paths) ---
OBSIDIAN_VAULT = Path("/Users/nav/Documents/Obsidian Vault")
CLAUDE_PROJECT_MEM = Path("/Users/nav/.claude/projects/-Users-nav-Documents-GitHub-floww/memory")
CLAUDE_MEMORY_INDEX = CLAUDE_PROJECT_MEM / "MEMORY.md"
HERMES_ANNOTATION_DIR = Path("/Users/nav/.hermes/memory_annotations")
HERMES_STAMP = Path("/Users/nav/.hermes/memory_mesh.stamp")
STAMP_FILE = OBSIDIAN_VAULT / "00-system/Sources of Truth/mesh_sync.stamp"

TARGETS = {
    "claude_autonomous_log": OBSIDIAN_VAULT / "00-system/Sources of Truth/claude_autonomous_log.md",
    "hermes_persistent_facts": OBSIDIAN_VAULT / "00-system/Sources of Truth/hermes_persistent_facts.md",
    "claude_sync": OBSIDIAN_VAULT / "00-system/Sources of Truth/Claude Sync.md",
}

# Ensure parent dirs exist for targets
for t in TARGETS.values():
    t.parent.mkdir(parents=True, exist_ok=True)
HERMES_ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)


def parse_frontmatter(content):
    """Return (fm_dict, body) where fm_dict may be empty. Reconstructs full text."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", content, re.DOTALL)
    if m:
        m.group(0)
        try:
            import yaml
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
        return fm, content[m.end():]
    return {}, content


def extract_body(content):
    """Return body without frontmatter, stripped."""
    _, body = parse_frontmatter(content)
    return body.strip()


# We won't require pyyaml if not present: write simple manual block updates
def build_block(name, body, extra_keys=None):
    """Build a deduped YAML-block section for Obsidian."""
    now = datetime.now(UTC).isoformat()
    keys = {
        name + "_anchor": "active",
        "last_updated": now,
        "mesh_synced": now,
    }
    if extra_keys:
        keys.update(extra_keys)
    fm = "```yaml\n" + "\n".join(f"{k}: {v}" for k, v in keys.items()) + "\n```"
    return f"{fm}\n\n{body.strip()}\n"


def replace_block(content, anchor_key, new_block):
    """Replace the block that contains anchor_key line, or append."""
    pattern = re.compile(
        rf"({re.escape(anchor_key)}.*?\n)(.*?)(\n```|\Z)",
        re.DOTALL,
    )
    if pattern.search(content):
        return pattern.sub(r"\1" + new_block.split("\n", 2)[2] + r"\3", content)
    return content.rstrip() + "\n\n" + new_block + "\n"


def normalize_wikilinks(text):
    """[[Name]] -> [Name](Name.md) to make it portable."""
    return re.sub(r"\[\[([^\]]+)\]\]", lambda m: f"[{m.group(1)}]({m.group(1)}.md)", text)


def write_file_atomic(path, data):
    """Write file atomically to reduce partial-write risk."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    shutil.move(str(tmp), str(path))


MAX_READ_BYTES = 5 * 1024 * 1024  # 5 MB guard against runaway/corrupt target files

def read_file_safe(path):
    if path.exists():
        if path.stat().st_size > MAX_READ_BYTES:
            # Runaway target (an append-bug ballooned it): do NOT load it into
            # memory. Return empty so the next atomic write replaces it cleanly.
            return ""
        return path.read_text(encoding="utf-8")
    return ""


# --- Claude source ---
def read_claude_memory():
    """Return summary text from Claude MEMORY.md and latest sessions."""
    parts = []
    if CLAUDE_MEMORY_INDEX.exists():
        text = CLAUDE_MEMORY_INDEX.read_text(encoding="utf-8")
        parts.append("## MEMORY.md index\n\n" + text[:4000])
    sessions = sorted(
        CLAUDE_PROJECT_MEM.glob("session_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for s in sessions[:3]:
        txt = s.read_text(encoding="utf-8")
        parts.append(f"## {s.name}\n\n" + txt[:3000])
    return "\n\n".join(parts) if parts else ""


# --- Hermes source ---
def read_hermes_annotations():
    """Read Hermes durable annotations from JSONL files in annotations dir."""
    texts = []
    if not HERMES_ANNOTATION_DIR.exists():
        return ""
    for jf in sorted(HERMES_ANNOTATION_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        try:
            for line in jf.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("type") == "mesh_persistent_fact":
                    texts.append(f"- {rec.get('text', '')}")
        except Exception:
            pass
    return "\n".join(texts) if texts else ""


# --- Obsidian -> Obsidian push ---
def push_obsidian_to_obsidian(source_path: Path, target_path: Path, anchor_key: str):
    """Take body of source note, normalise wikilinks, embed under anchor in target."""
    src = read_file_safe(source_path)
    if not src:
        return 0
    _, body = parse_frontmatter(src)
    normed = normalize_wikilinks(body)
    target = read_file_safe(target_path)
    block = build_block(anchor_key.replace("_anchor", ""), normed, {anchor_key.split("_")[0] + "_source": str(source_path)})
    updated = replace_block(target, anchor_key + ": active", block)
    write_file_atomic(target_path, updated)
    return 1


# --- Push Claude -> claude_autonomous_log.md ---
def push_claude_to_obsidian():
    body = read_claude_memory()
    if not body:
        return 0
    target = TARGETS["claude_autonomous_log"]
    current = read_file_safe(target)
    block = build_block("claude_autonomous_log", body, {"claude_source": str(CLAUDE_MEMORY_INDEX)})
    updated = replace_block(current, "claude_autonomous_log_anchor: active", block)
    write_file_atomic(target, updated)
    return 1


# --- Push Hermes -> hermes_persistent_facts.md ---
def push_hermes_to_obsidian():
    body = read_hermes_annotations()
    if not body:
        return 0
    target = TARGETS["hermes_persistent_facts"]
    current = read_file_safe(target)
    block = build_block("hermes_persistent_facts", body, {"hermes_source": str(HERMES_ANNOTATION_DIR)})
    updated = replace_block(current, "hermes_persistent_facts_anchor: active", block)
    write_file_atomic(target, updated)
    return 1


# --- Push Obsidian -> Hermes (write annotation file) ---
def push_obsidian_to_hermes():
    """Emit Hermes-readable annotation from claude_sync.md body."""
    src = TARGETS["claude_sync"]
    if not src.exists():
        return 0
    text = src.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    now = datetime.now(UTC).isoformat()
    record = {
        "type": "mesh_persistent_fact",
        "source": "obsidian:claude_sync",
        "text": body[:4000],
        "ts": now,
    }
    out = HERMES_ANNOTATION_DIR / f"obsidian_sync_{int(datetime.now().timestamp())}.jsonl"
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return 1


# --- Push Obsidian -> Claude (append to MEMORY.md index) ---
def push_obsidian_to_claude():
    src = TARGETS["claude_sync"]
    if not src.exists():
        return 0
    _, body = parse_frontmatter(src.read_text(encoding="utf-8"))
    marker = "<!-- MESH_SYNC:OBSIDIAN -->"
    index = CLAUDE_MEMORY_INDEX if CLAUDE_MEMORY_INDEX.exists() else CLAUDE_PROJECT_MEM / "MEMORY.md"
    if index.exists():
        cur = index.read_text(encoding="utf-8")
    else:
        cur = "# Project MEMORY\n\n<!-- MESH_SYNC:OBSIDIAN -->\n"
    normed = normalize_wikilinks(body)
    snippet = f"{marker}\n{normed[:4000]}\n"
    # Replace any existing snippet between markers
    if marker in cur and "</p>" not in cur:
        cur = re.sub(
            re.escape(marker) + r".*?(?=\n<!--|\Z)",
            snippet,
            cur,
            flags=re.DOTALL,
        )
    else:
        cur = cur.rstrip() + "\n\n" + snippet + "\n"
    write_file_atomic(index, cur)
    return 1


def modified_since(path: Path, stamp: Path) -> bool:
    if not path.exists():
        return False
    if not stamp.exists():
        return True
    try:
        last = float(stamp.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        last = 0.0
    return path.stat().st_mtime > last


def touch_stamp():
    STAMP_FILE.write_text(str(datetime.now(UTC).timestamp()), encoding="utf-8")
    HERMES_STAMP.write_text(str(datetime.now(UTC).timestamp()), encoding="utf-8")


def run_sync(dry_run=False):
    """Perform sync. Returns summary dict."""
    summary = {"claude_to_obsidian": 0, "hermes_to_obsidian": 0, "obsidian_to_hermes": 0, "obsidian_to_claude": 0}
    if not OBSIDIAN_VAULT.exists():
        raise RuntimeError(f"Obsidian vault not found at {OBSIDIAN_VAULT}")

    # Build minimal targets if missing
    for k, p in TARGETS.items():
        if not p.exists():
            p.write_text(
                f"<!-- auto-created by memory_mesh.py: {k} -->\n",
                encoding="utf-8",
            )

    # Claude -> Obsidian
    if modified_since(CLAUDE_MEMORY_INDEX, STAMP_FILE) or not TARGETS["claude_autonomous_log"].exists():
        n = 0 if dry_run else push_claude_to_obsidian()
        summary["claude_to_obsidian"] = n

    # Hermes -> Obsidian
    if True:  # Hermes annotations can always resume push
        n = 0 if dry_run else push_hermes_to_obsidian()
        summary["hermes_to_obsidian"] = n

    # Obsidian -> Hermes
    if modified_since(TARGETS["claude_sync"], STAMP_FILE):
        n = 0 if dry_run else push_obsidian_to_hermes()
        summary["obsidian_to_hermes"] = n

    # Obsidian -> Claude (careful: only write to project memory dir)
    if modified_since(TARGETS["claude_sync"], STAMP_FILE):
        n = 0 if dry_run else push_obsidian_to_claude()
        summary["obsidian_to_claude"] = n

    if not dry_run:
        touch_stamp()

    return summary


def main():
    parser = argparse.ArgumentParser(description="Memory mesh sync: Claude ↔ Hermes ↔ Obsidian")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--full", action="store_true", help="Force full sync")
    args = parser.parse_args()

    if args.full:
        # Ignore stamp for full run
        if STAMP_FILE.exists():
            STAMP_FILE.unlink()
    try:
        result = run_sync(dry_run=args.dry_run)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(1)

    print("Memory mesh result:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    print("Done.")


if __name__ == "__main__":
    main()
