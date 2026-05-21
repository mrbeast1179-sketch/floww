# Directory Inventory — 2026-05-20

## Non-Floww Directories (DO NOT MOVE)

### 1. `/Users/nav/GitHub/swarmSPX`
- **PURPOSE:** SwarmSPX — 24 AI agents debate SPX 0DTE trades in real-time
- **REMOTE:** `https://github.com/dhawalc/swarmSPX.git`
- **OWNERSHIP:** READ-ONLY (dhawalc's repo, cloned for reference)
- **ACTION:** Leave untouched

### 2. `/Users/nav/Documents/GitHub/Hermes`
- **STATUS:** Does not exist (was likely the Obsidian vault that moved to `/Users/nav/GitHub/Hermes/`)
- **ACTION:** N/A

### 3. `/Users/nav/GitHub/Hermes`
- **PURPOSE:** Obsidian vault — Nav's shared memory / knowledge base
- **REMOTE:** None (local-only vault)
- **OWNERSHIP:** READ-ONLY (personal knowledge base)
- **ACTION:** Leave untouched

### 4. `/Users/nav/Documents/GitHub/swarmSPX`
- **PURPOSE:** Duplicate of `/Users/nav/GitHub/swarmSPX` (same remote)
- **REMOTE:** `https://github.com/dhawalc/swarmSPX.git`
- **OWNERSHIP:** READ-ONLY
- **ACTION:** Leave untouched (may be a clone for IDE access)

### 5. `/Users/nav/hermes-env`
- **PURPOSE:** Python virtual environment for Hermes Agent
- **SIZE:** 218MB
- **OWNERSHIP:** OWNED (local venv)
- **ACTION:** Leave untouched — has hardcoded paths

### 6. `/Users/nav/OpenBBUserData`
- **PURPOSE:** OpenBB Terminal application data (logs, cache)
- **SIZE:** 88KB
- **OWNERSHIP:** OWNED (app data)
- **ACTION:** Leave untouched

### 7. `/Applications/Claude everything/`
- **PURPOSE:** Nav's personal cross-project workspace
- **CONTENTS:** DVT trading guide, Feigenbaum indicator code, MRI coursework, RSM syllabi, Pine scripts, personal docs
- **OWNERSHIP:** OWNED (personal workspace)
- **ACTION:** Leave untouched. gex-repos/ already consolidated (2 moved, 5 remain without permissive licenses)

## Canonical Floww

- **PATH:** `/Users/nav/Documents/GitHub/floww`
- **REMOTE:** `git@github.com:JattMoosewala5911/floww.git`
- **COMMITS:** 265 (after consolidation commits)
- **STATUS:** Clean, audit GREEN

## Archived

- **PATH:** `~/.archive/floww_dup_20260709/floww/`
- **ORIGINAL:** `/Users/nav/GitHub/floww` (deleted after archiving)
- **REASON:** Duplicate of canonical floww, same commit history
- **REVERSIBLE:** `mv ~/.archive/floww_dup_20260709/floww ~/GitHub/floww`
