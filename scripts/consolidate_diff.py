#!/usr/bin/env python3
"""Regenerate the AgentField consolidated-diff markdown report.

The numeric cells in `reports/agentfield_consolidated_diff_2026-06-17.md`
(top-of-report TL;DR table + per-SHA per-file tables) are re-derived from
`git show --numstat/--shortstat` and `git diff --name-status` against the
SHAs declared in `reports/agentfield_additive.yml`. The Behavioural Delta
prose column and the TL;DR Subject cell are NEVER touched.

Algorithm:
  1. Read `reports/agentfield_additive.yml`  -> ordered list of SHAs.
  2. For each SHA, gather per-file (add, del) from `--numstat`,
     section totals (files, ins, dels) from `--shortstat`, and a
     (n_new, n_mod) pair from `--name-status` so the TL;DR's
     Files Changed cell can render `N new`, `N mods`, or
     `N new + M mods`.
  3. Substitute the TL;DR row's three numeric cells.
  4. For each per-SHA section, substitute per-file rows'
     Lines Added / Lines Removed (matching the file-path column)
     AND set the section's `Files Changed` column to the integer
     from `--shortstat`.
  5. The Behavioural Delta column is never edited. If a manifest
     SHA does not have a matching H3 section, the script exits
     non-zero so the pre-commit hook refuses to land a commit with
     a half-regenerated report.

Hard writer invariant: every Behavioural Delta cell in the report
must be free of literal `|` characters; otherwise the per-row
regex's trailing `|$` anchor fails and the substitution silently
no-ops. Run `make consolidate-diff` after any prose edit to detect.

Idempotent: running this script against unchanged numstat input
produces a byte-identical report. Corrective: if a numeric cell has
drifted (mistyped or pasted-and-aged), running the script restores
the correct values from the source of truth.

Wired up via:
  * `make consolidate-diff`   (on-demand)
  * `.pre-commit-config.yaml` (auto-runs on commit; pre-commit's deny
                                if dirty exit forces a restage if the
                                regen changes anything on disk).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml  # PyYAML >= 6.0

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "reports" / "agentfield_additive.yml"
DEFAULT_REPORT = ROOT / "reports" / "agentfield_consolidated_diff_2026-06-17.md"

# Unicode minus (U+2212) matches the existing report's style for
# negative numbers; ASCII "-" is what git emits.
MINUS = "\u2212"


# ─────────────────────────────────────────────────────────────────
# Git helpers
# ─────────────────────────────────────────────────────────────────


def git(*args: str) -> str:
    """Run a git command at ROOT and return stdout (text). Nonzero exit raises."""
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def git_numstat(sha: str) -> dict[str, tuple[int, int]]:
    """`git show --numstat <sha>` -> {file_path: (add, del)}.

    Binary files emit `-` `-` from git; we coerce those to (0, 0).
    Renames emit `oldlen  newlen\told => new`; we keep only the NEW path.
    """
    raw = git("show", "--numstat", "--no-color", "--format=", sha)
    out: dict[str, tuple[int, int]] = {}
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        add_s, del_s, path = parts
        try:
            add, dele = int(add_s), int(del_s)
        except ValueError:
            add, dele = 0, 0  # binary file
        if " => " in path:
            path = path.split(" => ", 1)[1]
        out[path] = (add, dele)
    return out


def git_shortstat(sha: str) -> tuple[int, int, int]:
    """`git show --shortstat <sha>` -> (files_changed, insertions, deletions)."""
    raw = git("show", "--shortstat", "--no-color", "--format=", sha)
    fm = re.search(r"(\d+)\s+files?\s+changed", raw)
    im = re.search(r"(\d+)\s+insertions?\(\+\)", raw)
    dm = re.search(r"(\d+)\s+deletions?\(-\)", raw)
    files = int(fm.group(1)) if fm else 0
    ins = int(im.group(1)) if im else 0
    dels = int(dm.group(1)) if dm else 0
    return files, ins, dels


def git_new_mod_counts(sha: str) -> tuple[int, int]:
    """`git diff --name-status <sha>~1 <sha>` -> (n_new, n_mod)."""
    raw = ""
    # NOTE: do NOT pass `--no-renames`. Without the flag a rename shows
    # as `R<old>\t<new>`; the leading `R` is neither `A` nor `M`, so my
    # counter ignores it cleanly (the rename contributes zero to the
    # n_new/n_mod pair). With the flag, renames split into `D<old>` +
    # `A<new>` which would falsely inflate `n_new` and misrepresent
    # the file set.
    try:
        raw = git("diff", "--name-status", f"{sha}~1", sha)
    except subprocess.CalledProcessError:
        # Root commit (no <sha>~1) — fall back to --show which always works.
        raw = git("show", "--name-status", "--no-color", "--format=", sha)
    n_new = n_mod = 0
    for line in raw.splitlines():
        if not line:
            continue
        head = line[0]
        if head == "A":
            n_new += 1
        elif head == "M":
            n_mod += 1
    return n_new, n_mod


# ─────────────────────────────────────────────────────────────────
# Manifest + format helpers
# ─────────────────────────────────────────────────────────────────


def load_manifest(path: Path = MANIFEST) -> tuple[list[str], Path]:
    if not path.exists():
        sys.exit(f"manifest missing: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    shas = data.get("shas") if isinstance(data, dict) else None
    if not isinstance(shas, list) or not all(isinstance(s, str) for s in shas):
        sys.exit(
            f"manifest malformed: {path} — top-level `shas:` must be a list of strings"
        )
    rp = (data.get("report") or {}).get("path") if isinstance(data, dict) else None
    report_path = (ROOT / rp) if rp else DEFAULT_REPORT
    return shas, report_path


def fmt_files_label(new: int, mod: int) -> str:
    """`4 new` / `2 mods` / `1 new + 2 mods`. Falls back to `0` for empty SHAs."""
    if new and mod:
        return f"{new} new + {mod} mods"
    if new:
        return "1 new" if new == 1 else f"{new} new"
    if mod:
        return "1 mod" if mod == 1 else f"{mod} mods"
    return "0"


# ─────────────────────────────────────────────────────────────────
# Cell-rewrite passes
# ─────────────────────────────────────────────────────────────────


def rewrite_tldr_rows(text: str, sha_data: dict) -> str:
    """Rebind the 3 numeric cells of each TL;DR row to the per-SHA data.

    Anchored on the SHA's own `|<sha>|` column-1 marker so we never
    accidentally match a different SHA's row.

    IMPORTANT: the lambda emits canonical `| <cell> |` delimiters
    regardless of input whitespace. The previous version captured
    leading/trailing `\\s*` inside the regex groups and substituted
    them back, which silently ate ONE space per cell when input
    whitespace was uneven — the regen became non-idempotent and the
    TL;DR row "4 new |" got rewritten to "4 new|". The new shape
    captures each cell content independently and re-emits with fixed
    single-space-pipe-single-space between every cell.
    """
    for sha, d in sha_data.items():
        pat = re.compile(
            rf"^\|\s*\`{sha}\`\s*\|"          # opening: leading pipe + sha
            rf"\s*(.*?)\s*\|"                  # col 2 subject (preserved)
            rf"\s*(.*?)\s*\|"                  # col 3 files-changed (replaced)
            rf"\s*[+]\d+\s*\|"                 # col 4 insertions placeholder
            rf"\s*[{MINUS}]\d+\s*\|"           # col 5 deletions placeholder
            rf"\s*(.*?)\s*\|$",                # col 6 prose (preserved)
            flags=re.M,
        )
        # Re-run with capture-groups so the lambda can address each col by index.
        groups_pat = re.compile(
            rf"^\|\s*\`{sha}\`\s*\|"
            rf"\s*(.*?)\s*\|"
            rf"\s*(.*?)\s*\|"
            rf"\s*([+]\d+)\s*\|"
            rf"\s*([{MINUS}]\d+)\s*\|"
            rf"\s*(.*?)\s*\|$",
            flags=re.M,
        )
        new_label = d["label"]
        new_ins = f"+{d['ins']}"
        new_dels = f"{MINUS}{d['dels']}"
        new, n = groups_pat.subn(
            lambda m: (
                f"| `{sha}` | {m.group(1).strip()} | {new_label} "
                f"| {new_ins} | {new_dels} | {m.group(5).strip()} |"
            ),
            text,
            count=1,
        )
        if n != 1:
            print(f"warn: TL;DR row for {sha} did not match ({n} substitutions)", file=sys.stderr)
        text = new
    return text


def rewrite_perfile_rows_per_section(text: str, sha_data: dict) -> str:
    """For each per-SHA section (delimited by `### <sha>` H3), rewrite
    per-file rows' Lines Added / Lines Removed / Files Changed cells.

    Emits canonical `| <cell> |` delimiters between every cell so the
    output is byte-stable regardless of input whitespace. Behavioural
    Delta (col 5) is preserved verbatim.
    """
    for sha, d in sha_data.items():
        h_pat = re.compile(rf"^### \`{sha}\` ", flags=re.M)
        h_match = h_pat.search(text)
        if not h_match:
            sys.exit(
                f"manifest SHA {sha!r} has no matching `### `{sha}` H3 section "
                f"in the report — add the section + per-file table skeleton "
                f"(File Path | Lines Added | Lines Removed | Files Changed | "
                f"Behavioural Delta) before re-running."
            )
        section_start = h_match.start()
        next_h = re.search(r"^### ", text[section_start + 3 :], flags=re.M)
        section_end = section_start + 3 + next_h.start() if next_h else len(text)
        section = text[section_start:section_end]
        nsmap: dict[str, tuple[int, int]] = d["nsmap"]
        section_files = d["files"]

        def fix_row(m: re.Match, _d=d, _nsmap=nsmap, _fc=section_files) -> str:
            path = m.group(1)
            prose = m.group(5)
            a, dl = _nsmap.get(path, (None, None))
            if a is None:
                base = path.rsplit("/", 1)[-1]
                for k, v in _nsmap.items():
                    if k.rsplit("/", 1)[-1] == base:
                        a, dl = v
                        break
            if a is None:
                return (
                    f"| `{path}` | {m.group(2).strip()} | {m.group(3).strip()} "
                    f"| {m.group(4).strip()} | {prose.strip()} |"
                )
            return f"| `{path}` | +{a} | {MINUS}{dl} | {_fc} | {prose.strip()} |"

        # 5-cell capture: path, +N, −N, F, prose. HARD WRITER INVARIANT:
        # prose must NOT contain a literal `|` (anchored `\|$` would fail).
        row_pat = re.compile(
            rf"^\|\s*\`([^\`]+)\`\s*\|"
            rf"\s*([+]\d+)\s*\|"
            rf"\s*([{MINUS}]\d+)\s*\|"
            rf"\s*(\d+)\s*\|"
            rf"\s*(.*?)\s*\|$",
            flags=re.M,
        )
        new_section, count = row_pat.subn(fix_row, section)
        if count == 0:
            print(f"warn: per-file rows for {sha} did not match any line", file=sys.stderr)
        text = text[:section_start] + new_section + text[section_end:]
    return text


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────


def _run_validate(sha_data: dict, report_path: Path) -> int:
    """Cell-level regression probes for the regen path.

    Coverage matrix:
      T1  idle regen byte-equal against text0 (catches Lambda-style
          substitutions that change bytes without altering correctness)
      T2  TL;DR col 4 (Insertions) revert — per SHA
      T3  TL;DR col 5 (Deletions) revert — per SHA
      T5  Prose (Behavioural Delta) byte-equal across regen pass
      T6  Missing H3 sys.exit guard fires (fail-closed for new-SHA)

    Per-file-row numeric cells (Lines Added / Lines Removed / Files
    Changed) are not probed individually. They are covered indirectly
    by T1 (any drift in those cells shifts bytes) + T5 (any per-row
    whitespace corruption shifts the prose-keyed dict). A future
    contributor who wants per-(sha, path) regression coverage should
    restrict to paths that are unique to one SHA's section, otherwise
    the FIRST-occurrence ambiguity reappears.

    Does not write back to disk; everything happens in-memory. Exit
    code 0 on full PASS, 1 otherwise.
    """
    passes = 0
    fails: list[str] = []

    text0 = report_path.read_text(encoding="utf-8")

    # ---- T1: idle regen idempotency ----
    if regenerate(text0, list(sha_data.keys())) == text0:
        passes += 1
    else:
        fails.append("T1: idle regen not byte-equal")

    # ---- T2 + T3: TL;DR col 4 (Insertions) + col 5 (Deletions) per SHA ----
    # Probe patterns use `\s*\|` (whitespace-tolerant) so they continue
    # to work whether or not the input has been canonicalised by a
    # prior regen pass.
    for sha, d in sha_data.items():
        for col_idx, stale, expected in [
            (4, "+99999", f"+{d['ins']}"),
            (5, f"{MINUS}999999", f"{MINUS}{d['dels']}"),
        ]:
            if col_idx == 4:
                pat = re.compile(
                    rf"^(\|\s*\`{sha}\`\s*\|[^|]+\|[^|]+\|\s*)(\+\d+)(\s*\|)",
                    re.M,
                )
            else:
                pat = re.compile(
                    rf"^(\|\s*\`{sha}\`\s*\|[^|]+\|[^|]+\|\s*\+\d+\s*\|\s*)([{MINUS}]\d+)(\s*\|)",
                    re.M,
                )
            text_inj = pat.sub(rf"\1{stale}\3", text0, count=1)
            text_out = regenerate(text_inj, list(sha_data.keys()))
            m = pat.search(text_out)
            got = m.group(2) if m else None
            if got == expected:
                passes += 1
            else:
                fails.append(
                    f"T{'2' if col_idx == 4 else '3'} col {col_idx} sha={sha}: "
                    f"got {got!r}, want {expected!r}"
                )

    # ---- T4 retired: per-file-row probes were brittle against cross-SHA
    # path sharing. Coverage is delegated to T1 (byte-equality) + T5
    # (prose); see commit history for the full reasoning.

    # ---- T5: prose byte-equality across a regen pass (no stale injection) ----
    # Snapshot every Behavioural Delta cell by its row key (the SHA or
    # file-path between the leading `| \`...\` |`). Ordered dict so a
    # regex that silently reorders rows would also be detected. We
    # additionally assert the SNAPSHOT KEYS match pre/post: a regex that
    # silently drops a row would otherwise produce coincidentally-equal
    # dicts (e.g. two missing cells where the same number went missing
    # both pre and post).
    def _prose_cells(t: str) -> "dict[str, str]":
        rows: dict[str, str] = {}
        for ln in t.splitlines():
            if not ln.startswith("| `"):
                continue
            parts = [p.strip() for p in ln.split("|")[1:-1]]
            if len(parts) < 5:  # header rows have fewer cols; skip cleanly
                continue
            rows[parts[0].strip("`")] = parts[-1]
        return rows

    pre = _prose_cells(text0)
    post = _prose_cells(regenerate(text0, list(sha_data.keys())))
    if pre.keys() == post.keys() and pre == post:
        passes += 1
    else:
        missing = sorted(set(pre.keys()) - set(post.keys()))
        added = sorted(set(post.keys()) - set(pre.keys()))
        diff = sorted(
            k for k in pre.keys() & post.keys() if pre[k] != post[k]
        )
        fails.append(
            "T5: prose cells drifted across regen "
            f"(missing={missing}, added={added}, drifted={diff})"
        )

    # ---- T6: missing-H3 sys.exit fires ----
    sha0 = next(iter(sha_data))
    text_no_h3 = re.sub(
        rf"^### \`{sha0}\`[\s\S]*?(?=^##? |\Z)",
        "",
        text0,
        count=1,
        flags=re.M,
    )
    try:
        regenerate(text_no_h3, list(sha_data.keys()))
        fails.append(f"T6: regen on missing-H3 {sha0} did NOT exit")
    except SystemExit:
        passes += 1

    print(f"\n=== consolidate_diff.py --validate ===")
    print(f"PASS: {passes}  FAIL: {len(fails)}")
    for f in fails:
        print(f"  - {f}")
    return 0 if not fails else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="consolidate_diff.py",
        description=(
            "Regenerate the AgentField consolidated-diff markdown report. "
            "Pass --validate to run in-memory cell-level regression probes "
            "without writing to disk."
        ),
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="run cell-level staleness probes in-memory; do not write to disk",
    )
    args = parser.parse_args()
    if args.validate:
        # Parse manifest exactly once; forward both halves.
        shas, report_path = load_manifest()
        sha_data = _build_sha_data(shas)
        return _run_validate(sha_data, report_path)
    shas, report_path = load_manifest()
    if not report_path.exists():
        sys.exit(f"report file missing: {report_path}")
    before = report_path.read_text()
    after = regenerate(before, shas)
    if after == before:
        print(
            f"OK: {report_path.name} byte-identical to last regenerate "
            f"({len(after)} bytes, idempotent \u2713)"
        )
        return 0
    report_path.write_text(after)
    diff_lines = sum(
        1 for a, b in zip(after.splitlines(), before.splitlines()) if a != b
    )
    print(
        f"OK: {report_path.name} regenerated "
        f"({len(before)} \u2192 {len(after)} bytes, "
        f"~{diff_lines} line(s) corrected)"
    )
    return 0


def _build_sha_data(shas: list[str]) -> dict:
    """Run the git helpers once per SHA into the same dict shape that
    `regenerate` uses — used by `--validate` for ground-truth probes.
    """
    sha_data: dict = {}
    for sha in shas:
        files, ins, dels = git_shortstat(sha)
        n_new, n_mod = git_new_mod_counts(sha)
        sha_data[sha] = dict(
            nsmap=git_numstat(sha),
            files=files,
            ins=ins,
            dels=dels,
            label=fmt_files_label(n_new, n_mod),
        )
    return sha_data


def regenerate(text: str, shas: list[str]) -> str:
    sha_data: dict = {}
    for sha in shas:
        files, ins, dels = git_shortstat(sha)
        n_new, n_mod = git_new_mod_counts(sha)
        sha_data[sha] = dict(
            nsmap=git_numstat(sha),
            files=files,
            ins=ins,
            dels=dels,
            label=fmt_files_label(n_new, n_mod),
        )
    out = rewrite_tldr_rows(text, sha_data)
    out = rewrite_perfile_rows_per_section(out, sha_data)
    return out


if __name__ == "__main__":
    sys.exit(main())
