# Round 10 Agent A9 Close-Out

**Agent:** A9
**Date:** 2026-05-27
**Role:** Backend Dead-Code Audit (READ-ONLY)

## What Was Done

1. **AST scan** of all 2,206 top-level definitions in backend/ (excl. tests, .venv)
2. **Caller counting** via file-level grep across backend/ + frontend/src/ + scripts/
3. **Decorator triage** to filter false positives (FastAPI routes, cron jobs, etc.)
4. **Manual eyeball** of top A_DEAD candidates
5. **Frontend URL cross-reference** — 154 of 199 routes have no frontend string match
6. **Scripts/cron cross-reference** — 18 unique service names imported by scripts

## Key Findings

- **433 high-confidence dead code entries** (342 public functions, 91 classes)
- **304 private functions** that may be dead (need owner sign-off)
- **235 false positives** (FastAPI routes, cron jobs, decorators)
- **154 unused frontend route URLs** (but may be used via path construction)
- Most dead code concentrated in: services/ (189), scripts/ (38), data/ (16), config/ (16)

## Deliverables

- `docs/ROUND10_DEAD_CODE_AUDIT.md` — full audit report with tables
- `scripts/audit_dead_code.py` — reusable AST scanner
- `/tmp/a9_triaged.tsv` — full triage data (not committed, reproducible)

## What Was NOT Done (By Design)

- No source files were modified (READ-ONLY scope)
- No deletions (Round 10's job)
- No test modifications
- Frontend route analysis is incomplete (template literal paths not fully traced)

## Recommended Next Steps for Round 10

1. Delete 91 dead classes in ~10 PRs (grouped by module)
2. Delete 189 dead public functions from services/
3. Investigate 304 private functions (factory pattern check)
4. Add vulture to CI to prevent regression
5. Deprecate unused routes with 410 Gone for 30 days

## Files Touched

- `docs/ROUND10_DEAD_CODE_AUDIT.md` (NEW)
- `scripts/audit_dead_code.py` (NEW, committed)
- `kanban/cards/agent_A9_status.md` (NEW)
- No source files modified
