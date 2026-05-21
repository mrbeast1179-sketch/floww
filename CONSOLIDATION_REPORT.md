# Consolidation Report — 2026-05-20

## Summary

Consolidated 6 floating directories into a clean structure with a single canonical floww.

## Canonical Floww

- **Path:** `/Users/nav/Documents/GitHub/floww`
- **Remote:** `git@github.com:JattMoosewala5911/floww.git` (switched from HTTPS)
- **Commits:** 265
- **Status:** Clean, truth audit GREEN (12/12)

## Duplicate Archived

- **Original:** `/Users/nav/GitHub/floww`
- **Archive:** `~/.archive/floww_dup_20260709/floww/`
- **Reason:** Identical commit history (263 commits, same HEAD)
- **Reversible:** `mv ~/.archive/floww_dup_20260709/floww ~/GitHub/floww`
- **Preserved from loser:**
  - `backend/tests/services/test_microstructure_property.py` (340 lines, property-based tests)
  - `backend/services/execution_doctrine.py` (140 lines)
  - `backend/services/order_router.py` (225 lines)
  - `backend/services/signal_translator.py` (150 lines)

## Repos Moved from `/Applications/Claude everything/gex-repos/`

| Repo | Owner | License | Action |
|------|-------|---------|--------|
| option-strategy-pricer | harryho71 | MIT | ✅ Moved |
| Options_Portfolio | George-Dros | MIT | ✅ Moved |

## Repos Skipped (No Permissive License)

| Repo | Owner | Reason |
|------|-------|--------|
| Dynamic-Derivatives-Portfolio-Hedging | bottama | No LICENSE file |
| gex-backtesting | emlama | No LICENSE file |
| GEX-Dashboard | American-Dynasty | No LICENSE file |
| SPX_Gamma_Exposure | Nicholas-Battista | No LICENSE file |
| Unusual-Options | SweepCast | No LICENSE file |

## Repos Already in Manifest (Skipped as Duplicates)

| Repo | Owner |
|------|-------|
| EzOptions | EazyDuz1t |
| floe | FullStackCraft |
| Gamma-Vanna-Options-Exposure | Proshotv2 |
| gex-tracker | Matteo-Ferrara |

## Non-Floww Directories (Documented, NOT Moved)

| Path | Purpose |
|------|---------|
| `/Users/nav/GitHub/swarmSPX` | SwarmSPX project (dhawalc) |
| `/Users/nav/GitHub/Hermes` | Obsidian vault (personal knowledge base) |
| `/Users/nav/Documents/GitHub/swarmSPX` | Duplicate swarmSPX clone |
| `/Users/nav/hermes-env` | Python venv (218MB) |
| `/Users/nav/OpenBBUserData` | OpenBB Terminal data (88KB) |
| `/Applications/Claude everything/` | Nav's personal workspace |

## Folder Count

- **BEFORE:** 6 floating directories (2 floww + swarmSPX + Hermes + hermes-env + OpenBBUserData)
- **AFTER:** 5 (1 canonical floww + swarmSPX + Hermes + hermes-env + OpenBBUserData + archive)
- **Net change:** -1 (duplicate floww archived)

## Commits

1. `c17ef32` — chore(repos): canonical floww decision + preserve microstructure property tests
2. `733dd92` — chore(repos): consolidate option-strategy-pricer + Options_Portfolio
3. `a54ead6` — chore(repos): preserve 3 new service files from duplicate floww
4. (this report) — chore(repos): final consolidation report + directory inventory
