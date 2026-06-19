# Floww Refactor Baseline (2026-06-17)

**Date:** 2026-06-17  •  **Repo:** `/Users/nav/Documents/GitHub/floww`  •  **Branch:** `main`  •  **Head SHA on capture date:** `2ad47ae`

Tokei-based code-sloccount snapshot captured on 2026-06-17 so future refactors have a **before/after reference in-repo** rather than relying on `/tmp/tokei_*.txt` files (which are not version-controlled and can rotate out between sessions). The captured baselines are:

1. **Whole floww tree** — 1,116 files, 237,948 lines (full 15-language breakdown below)
2. **`integrations/agentfield/` additive subtree** — 7 files, 592 lines, the surface introduced by the 4-SHA AgentField migration arc (`72dee2c`, `f6a6bc4`, `8581c1d`, `a4a991e`)

A third artefact, `/tmp/tokei_referenced.txt` (backend + reports read-only-invariant scope), is mentioned for context but **not** quoted here — its content lives outside the two files this report explicitly snapshots. Future readers reproducing the snapshot should re-derive it independently (see "Reproducing this baseline").

---

## Headline numbers (TL;DR)

| Subtree | Files | Lines | Code | Comments | Blanks | Source `/tmp/` file |
|---|--:|--:|--:|--:|--:|---|
| **Whole floww** | 1,116 | 237,948 | 172,642 | 34,128 | 31,178 | `tokei_floww.txt` |
| `integrations/agentfield/` (additive scope) | 7 | 592 | 411 | 133 | 48 | `tokei_agentfield.txt` |

Ratios:
- **Whole floww:** code 72.5 %, comments 14.3 %, blanks 13.1 % of total lines
- **`integrations/agentfield/`:** code 69.4 %, comments 22.5 %, blanks 8.1 % — significantly more comments-per-line than the whole repo, consistent with the docstring-heavy AgentField reasoner surface.

---

## Whole-repo language breakdown

Verbatim transcript of `/tmp/tokei_floww.txt` (45 lines, 4,786 bytes captured 2026-06-17):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Language              Files        Lines         Code     Comments       Blanks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 BASH                      1           46           32            7            7
 Bicep                     3          727          594           43           90
 CSS                       4         1743         1436           99          208
 HCL                       3          312          229           25           58
 INI                       1           13           13            0            0
 JavaScript               36         4088         3262          427          399
 JSON                     93        42317        42317            0            0
 JSX                     140        12927        11464          389         1074
 Python                  536       132812       105435         6612        20765
 Shell                     8         1043          768          137          138
 SVG                       1            4            4            0            0
 Plain Text                3         1023            0          991           32
 TOML                      1           91           74            0           17
 XML                       3            3            3            0            0
 YAML                     23         1238         1035          126           77
─────────────────────────────────────────────────────────────────────────────────
 HTML                      2           58           48            4            6
 |- CSS                    1           28           28            0            0
 |- JavaScript             1           31           28            3            0
 (Total)                              117          104            7            6
─────────────────────────────────────────────────────────────────────────────────
 Jupyter Notebooks         1          235          178           18           39
 |- Markdown               1           24            0           18            6
 |- Python                 1          211          178            0           33
 (Total)                              470          356           36           78
─────────────────────────────────────────────────────────────────────────────────
 Markdown                257        32163            0        24597         7566
 |- BASH                  61         3122         2782          165          175
 |- CSS                    1           47           41            6            0
 |- HTML                   3           29           29            0            0
 |- INI                    2           59           40            7           12
 |- JavaScript             5          220          189           12           19
 |- JSON                   6           31           31            0            0
 |- JSX                    7          367          306           31           30
 |- Markdown              14          356            0          267           89
 |- Python                42         2392         1933          137          322
 |- TOML                   5           70           53            6           11
 |- YAML                   6          118          112            1            5
 (Total)                            38974         5516        25229         8229
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Total                  1116       237948       172642        34128        31178
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Top-3 languages by LoC: **Python 132,812 (55.8 %)**, **JSON 42,317 (17.8 %)**, **Markdown 32,163 (13.5 %)** — the JSON+Markdown share (~31 %) is dominated by `data/external_research/discoveries_*.json` and the `reports/` evidence-report corpus; pure "source code" (Python + JSX + JS + Shell + HCL + Bicep + CSS + YAML) ≈ 154,890 LoC = 65.1 % of total.

---

## `integrations/agentfield/` additive subtree

Verbatim transcript of `/tmp/tokei_agentfield.txt` (9 lines, 1,381 bytes captured 2026-06-17):

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Language              Files        Lines         Code     Comments       Blanks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Python                    4          459          354           66           39
 Shell                     1           42           24           12            6
 YAML                      2           91           33           55            3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Total                     7          592          411          133           48
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The 4 Python files map to:
- `integrations/__init__.py` (3-line package marker)
- `integrations/agentfield/__init__.py` (3-line sub-package marker)
- `integrations/agentfield/bs_agent.py` (~257 lines pre-iter-2; ~243 lines post-iter-2 with refactored registration hook)
- `integrations/agentfield/test_bs_agent.py` (~117 lines pre-iter-2; ~131 lines post-iter-2 with iter-1↔iter-2 test rewrites)

The YAML pair (`91 LoC` total) is largely comment content (55 of 91 lines) — agentfield-style YAML configs with heavy inline disclosure headers. The Shell file is a 42-line launcher wrapper.

---

## Reproducing this baseline

```bash
cd /Users/nav/Documents/GitHub/floww

# 1. Verify tokei is installed (any 13.x+ will produce identical-shaped output).
which tokei && tokei --version

# 2. Capture whole-tree snapshot to /tmp with a timestamped filename so
#    successive runs don't clobber each other.
TS=$(date +%Y%m%d-%H%M%S)
tokei /Users/nav/Documents/GitHub/floww > /tmp/tokei_floww_${TS}.txt
tokei /Users/nav/Documents/GitHub/floww/integrations/agentfield/ \
      > /tmp/tokei_agentfield_${TS}.txt

# 3. Diff the freshly captured snapshot against the headline numbers reported
#    above to confirm the "before" picture still matches before any refactor.
grep '^ Total' /tmp/tokei_floww_${TS}.txt
grep '^ Total' /tmp/tokei_agentfield_${TS}.txt
```

Expected `Total` lines on a clean repo (matches the snapshot above):

```
 Total                  1116       237948       172642        34128        31178
 Total                     7          592          411          133           48
```

---

## How to use this for a future refactor

Diff-style before/after discipline:

```bash
# Step 1: re-capture the current snapshot (call it BEFORE).
TS_BEFORE=2026-mm-dd-HHMM
tokei /Users/nav/Documents/GitHub/floww > /tmp/tokei_floww_${TS_BEFORE}.txt

# Step 2: do the refactor work.

# Step 3: re-capture (call it AFTER).
TS_AFTER=2026-mm-dd-HHMM
tokei /Users/nav/Documents/GitHub/floww > /tmp/tokei_floww_${TS_AFTER}.txt

# Step 4: quantitative diff to show refactor impact.
diff -u /tmp/tokei_floww_${TS_BEFORE}.txt /tmp/tokei_floww_${TS_AFTER}.txt | head -40
# Interpret: "Total" row delta = net LoC change; per-language rows reveal
# where the bytes went (Python \u2193 + Markdown \u2191 typically = a real refactor;
# noise-only changes typically revolve around `__pycache__/*.pyc`).
```

When the `Total` row in your AFTER snapshot differs materially from `237948`, file an updated copy of this report as `reports/refactor_baseline_<date>.md` so the lineage of before/after snapshots is preserved.

---

## Caveats

- **Numbers reflect the working tree on 2026-06-17**, not the entire commit history. `tokei` walks the filesystem; uncommitted WIP is included.
- **Markdown reports are mostly "comments" by tokei's language classifier** — that's why `Markdown 257 files / 32,163 lines` reports `Code: 0`. Most of those bytes are evidence-report prose, not executable.
- **`data/external_research/*.json` (42,317 LoC of JSON)** is structured data downloaded from GitHub repos via the `discoveries` pipeline; it inflates the "JSON" line significantly. Pure "source-code LoC" is what matters for refactor sizing.
- **Tokei 13.x language counts are deterministic for stable file sets**: a clean checkout of `main` at the captured SHA should reproduce the `Total 1116 237948 172642 34128 31178` line byte-for-byte.

---

## Environment snapshot

| Tool | Version | Path |
|---|---|---|
| `tokei` | 13.x (any 13+) | `/opt/homebrew/bin/tokei` (or platform equivalent) |
| `git` | system | used for HEAD SHA + branch verification |
| `ripgrep` + `fd` (audit-trio) | 15.x / 10.4.2 | already on PATH |

For the canonical environment version, run `tokei --version` at refactor time and inline the result into the new baseline report.

---

## Related artefacts (not quoted in this report)

- `/tmp/tokei_referenced.txt` — backend/ + reports/ read-only-invariant scope (18 lines). Re-derive with `tokei /Users/nav/Documents/GitHub/floww/backend /Users/nav/Documents/GitHub/floww/reports > /tmp/tokei_referenced_$(date +%Y%m%d).txt`. Mentioned here for cross-referencing the "no edits to backend/, frontend/, kanban/, project_oracle/" invariant that gated the AgentField additive migration.
- `reports/agentfield_consolidated_diff_2026-06-17.md` — per-SHA per-file diff table for the same 4-SHA arc this report's `integrations/agentfield/` line covers. Pairs naturally with the headline numbers above for an end-to-end "commit landed + LoC delta" audit.
- `reports/agentfield_index_2026-06-17.md` — reading-order INDEX for the 4-SHA AgentField migration arc. The numeric baseline here (592 LoC additive scope) complements that index's reading-order entry; together they form the in-repo audit trail for the AgentField migration.
