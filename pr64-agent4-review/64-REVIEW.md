---
status: review-complete
files_reviewed: 4
depth: standard
phase_dir: pr64-agent4-review
review_path: pr64-agent4-review/64-REVIEW.md
diff_base: 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b
critical: 0
warning: 1
info: 3
total: 4
timestamp: 2026-09-11T00:50:00Z
---

# Agent-4 Review: PR64 — fix(frontend): honest proxy copy + X4 dynamic-behavior tests

## Scope

- **Head:** 095a273d36a53252db926aed115f3b1d6f5063f0
- **Base:** 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b (current main, PR58 merged)
- **Files:** 4 changed files, 239 insertions, 2 deletions
  - `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (+4/-2)
  - `frontend/src/components/flowseeker/FlowseekerProBlademap.test.jsx` (+18)
  - `frontend/src/components/flowseeker/scanLogic.X4.test.js` (+155, new)
  - `frontend/src/components/flowseeker/FlowseekerProBlademap.X4.test.js` (+64, new)
- **PR state:** OPEN, mergeState UNSTABLE (CI re-running after main merge)
- **CI:** ruff/SUCCESS, frontend-build/SUCCESS (rerun), backend-tests/IN_PROGRESS

## Summary

PR64 started as a copy fix (remove "volume" from Pulse BLOCK titles) and has expanded to include X4 dynamic-behavior tests (21 new tests across 2 files). The copy fix is correct. The X4 tests pin pure-function contracts for `elapsedClock` and `pulseState` classification, plus `pollMs` localStorage persistence. No mounted behavior, no App.js changes, no backend changes.

## Findings

### INFO-1: Copy fix is correct and complete (Info)

**Files:** `FlowseekerProBlademap.jsx:172,177`

The fix removes "volume" from BLOCK titles in both `flowClassTitle()` and `FILTER_CHIP_TITLES`. Pulse BLOCK = premium >= $50M, not Scanner volume. Verified: both code paths (public API line 87, cvserver line 666) classify by premium. The cvserver path never had the wrong wording. No action needed.

### INFO-2: X4 tests are pure-function contracts, not mounted behavior (Info)

**Files:** `scanLogic.X4.test.js`, `FlowseekerProBlademap.X4.test.js`

The X4 tests pin:
1. `elapsedClock()` boundary behavior (null/undefined/NaN/negative → "—", seconds/minutes/hours formatting, rounding)
2. `pulseState()` classification contract (error wins, stale+retry→ERR, stale without retry→WARN, no data→LOADING)
3. `pollMs` localStorage persistence (default 60000, custom value persisted, survives re-render)

These are pure-function tests that pin the contract without rendering the full component. No App.js, no backend, no live feed. This is appropriate scope for discovery findings — the tests document the contracts that would need to be preserved if X4 behavior work is ever admitted.

### INFO-3: X4 tests do NOT claim mounted behavior (Info)

**Files:** `FlowseekerProBlademap.X4.test.js:1-15`

The test file explicitly states: "No backend, no App.js, no live feed, no dead-component revival." It tests `pollMs` persistence only. The `scanLogic.X4.test.js` tests pure functions. Neither test renders the full FlowseekerProBlademap component with real data flow. This is honest — X4 discovery findings are documented as contracts, not implemented behavior.

No action needed. This is correct scoping.

### WR-1: X4 tests add 21 tests but the receipt claims "discovery findings remain scoped — not implemented" (Warning)

**File:** `scanLogic.X4.test.js:1-15` (header comment), commit message 095a273

The commit message says: "Discovery findings (race-safety gap, partial-data visibility gap, inline-surface poll gap) remain scoped in receipts — not implemented". However, the tests pin contracts for `pulseState` classification and `pollMs` persistence — these ARE implementations of the discovery contracts, not just scoped findings. The wording is slightly inconsistent: the tests implement the pinned contracts, which is the right thing to do, but the commit message frames them as "not implemented".

This is a Warning because it could confuse future readers about what X4 actually delivered. The tests are good — they pin real contracts. The framing should match: "X4 pins dynamic-behavior contracts for pulseState and pollMs; full mounted behavior requires separate admission."

**Deeper finding — X4 scope boundary is honest but the commit message over-claims discovery gaps:**

The commit message lists three "discovery findings": race-safety gap, partial-data visibility gap, inline-surface poll gap. But the X4 tests only pin contracts for `pulseState` classification and `pollMs` persistence — they do NOT test for race-safety (no concurrent-poll test), partial-data visibility (no test that verifies what happens when data is partial), or inline-surface poll gap (the `pollMs` persistence test is a contract pin, not a gap test). 

The commit message frames these as "discovery findings" that are "scoped in receipts" — but the actual tests don't cover them. This is the correct behavior (don't implement unadmitted work), but the wording is misleading: it implies the tests address these gaps when they don't. A reader might assume the race-safety gap is tested when it isn't.

**Recommendation:** No code change needed. The tests are correctly scoped. If this PR is merged, consider clarifying the commit message to say: "X4 pins dynamic-behavior contracts for pulseState and pollMs. Discovery gaps (race-safety, partial-data visibility, inline-surface poll) remain documented in receipts X2-phase9-consumer.md + X4-dynamic-behavior.md, not implemented."

## Verdict

The PR64 copy fix is correct. The X4 tests are well-scoped pure-function contracts that pin behavior without claiming mounted UI. No blockers.

**Blocker:** None.
**Advisory:** Clarify commit message framing around X4 — tests implement contracts, not just scoped findings.
**Merge readiness:** CLEAR for merge after backend-tests CI passes. 558 frontend tests pass locally.

## Limitations

- This is a code review, not a broker witness, visual owner signoff, or profitability proof.
- Green tests do not establish alpha or production readiness.
- No downstream impact analysis beyond the 4 changed files.
- PR64 does not modify any backend code, frozen files (App.js, .env, package.json, craco.config.js), or dependency configuration.

## Next action

Wait for backend-tests CI to pass, then merge PR64. If backend-tests fails, diagnose and fix before merge.
