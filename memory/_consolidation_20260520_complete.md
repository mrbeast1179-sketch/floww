# Folder Consolidation — Complete (2026-05-20)

## What was done

1. **Identified canonical floww**: `/Users/nav/Documents/GitHub/floww` wins by precedent (all memory + dispatch plans reference it). Remote switched from HTTPS to SSH.

2. **Archived duplicate**: `/Users/nav/GitHub/floww` → `~/.archive/floww_dup_20260709/floww/`. Preserved 4 untracked files (855 lines of new code) before archiving.

3. **Consolidated gex-repos**: Moved 2 MIT-licensed repos from `/Applications/Claude everything/gex-repos/` to `data/github-repos/cloned/`. 5 repos skipped (no permissive license). 5 already in manifest.

4. **Documented non-floww directories**: 7 directories inventoried and documented. None moved.

5. **Final report**: `CONSOLIDATION_REPORT.md` committed. `MEMORY.md` updated with canonical path.

## Final folder structure

```
/Users/nav/Documents/GitHub/floww/          ← CANONICAL (265 commits, SSH)
/Users/nav/GitHub/swarmSPX/                 ← Separate project (untouched)
/Users/nav/GitHub/Hermes/                   ← Obsidian vault (untouched)
/Users/nav/Documents/GitHub/swarmSPX/       ← Duplicate clone (untouched)
/Users/nav/hermes-env/                      ← Python venv (untouched)
/Users/nav/OpenBBUserData/                  ← App data (untouched)
/Applications/Claude everything/            ← Personal workspace (gex-repos consolidated)
~/.archive/floww_dup_20260709/floww/        ← Reversible archive
```

## Reversibility

- Duplicate floww: `mv ~/.archive/floww_dup_20260709/floww ~/GitHub/floww`
- gex-repos: Already in `data/github-repos/cloned/` (gitignored, tracked via manifest)
