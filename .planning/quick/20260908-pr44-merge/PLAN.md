# PLAN: PR44 G3-salvage merge (owner-ordered)

## Description
Update `astra/g3-paper-loop` onto current main, exact-head test proof, CI green, merge PR44. Owner waived the G-WITNESS gate on record; the waiver is recorded here, not hidden.

## Context
- PR44 head `d6fad39`, base `a6e6f79`; main `04605df`; mergeState BEHIND, mergeable MERGEABLE.
- Prior verdict E4-44 APPROVED-conditional (131 offline tests, ruff clean). Condition (1) CI green re-verified on update commit; condition (2) witness WAIVED by owner order 2026-09-08.
- Worktree: /Users/nav/Documents/GitHub/floww-worktrees/g3-split (clean, branch astra/g3-paper-loop).

## Steps
1. `git fetch origin`; merge `origin/main` into branch (merge commit, no rebase of shared branch).
2. Focused pytest: paper-loop + ops + gateway + order_router suites at new head; record counts.
3. Ruff on the 6 touched paths + silent-except gate check.
4. Push branch; verify remote SHA; wait for CI (ruff, backend-tests, frontend-build) green on new head.
5. Merge PR44 (squash or merge per repo habit — prior merges used merge commits; use `gh pr merge --merge`).
6. Verify `git log origin/main --oneline -1` shows the merge; record merge SHA.

## Acceptance
- Merge commit on origin/main; CI green on the update head; E4-44 receipt + this SUMMARY updated with merge SHA.
- Do NOT touch: other lanes' worktrees/branches, canonical G1 checkout, frozen files.

## Deviation note
PLAN/SUMMARY live uncommitted in canonical .planning/quick (precedent: existing uncommitted .planning files; G1 branch is Nav's active checkout — no doc commits there).
