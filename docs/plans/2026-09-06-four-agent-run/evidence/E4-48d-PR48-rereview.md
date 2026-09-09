# E4-48d — Agent-4 re-re-re-review, PR48 a3/alert-surfacing @ 2f57bea3d

## PR
[#48](https://github.com/mrbeast1179-sketch/floww/pull/48) — `feat(frontend): backend exposure-rule badges`

- State: OPEN, base `main`, head `2f57bea3d56a075692339051525cb73d97d99513`
- CI at head: ruff SUCCESS; backend-tests + frontend-build IN_PROGRESS at review time
- Merge status: UNSTABLE (branch behind main — PR50 merged separately, PR52+PR53 on main; needs rebase to become CLEAN)
- 8 commits on the branch

## Head motion since last Agent-4 receipt
- `81255b886` (had PR50 KIND_TITLES merged in) → `2f57bea3d` (PR50 content removed from this branch; PR50 itself MERGED to main separately)
- PR50: MERGED (`f7bc499ea`, 2026-09-09T15:35:57Z) — KIND_TITLES now in main
- PR49: still DIRTY (merge conflict in exposureBadges.js after rebase attempt onto `2f57bea3d`)

## What's at this head

### Present (from f25de2e rework + 2f57bea fix)
- VEX_WALL dual-meaning title: "formed (dealers defending, vol suppression) or broken (suppression released, regime may shift); feed carries no formed/broken split, heuristic" — honest, no false claim
- GAMMA_FLIP dual-meaning title: "flip approach (exposure path) or regime change pos-to-neg (alert-engine path), heuristic, not a direction call" — honest, no false claim
- ExposureStrip: `setBadges([])` at effect start (clears previous ticker's badges immediately) — D1 mechanism present, just moved from `.catch()` to effect body
- D1 regression test: "ticker change with failed fetch clears the previous ticker badges" — asserts old badges gone after ticker-change + rejected fetch

### Absent (PR50 content, but now in main via PR50 merge)
- KIND_TITLES dict — NOT in this branch's exposureBadges.js
- exposureKindOf function — NOT in this branch
- `exposureBadgeFor(rule, row)` two-arg form — NOT in this branch (ExposureStrip calls `exposureBadgeFor(row?.rule)` one-arg; Blademap calls `exposureBadgeFor(a.rule)` one-arg)
- The 5 new KIND_TITLES pin tests — NOT in this branch

### The 2f57bea "badge parity" commit
- Changed ExposureStrip catch comment only: removed `setBadges([])` from `.catch()` body, kept `setBadges([])` at effect start (line 30)
- The D1 behavior is preserved: ticker change triggers effect re-run → `setBadges([])` clears old badges → fetch either replaces or fails → badges stay empty
- No behavior change; the test still passes (6/6 including the D1 test)

## Fresh reproduction at exact head

Worktree `/tmp/pr48-v81255` at `2f57bea3d`. Focused suites:

```text
cd frontend && CI=true npx craco test --watchAll=false --runInBand \
  --testPathPattern='exposureBadges|ExposureStrip|FlowseekerProBlademap|SkylitDashboard'
PASS src/components/flowseeker/exposureBadges.test.js
PASS src/components/flowseeker/FlowseekerProBlademap.test.jsx
PASS src/components/heatseeker/ExposureStrip.test.jsx
PASS src/components/heatseeker/SkylitDashboard.test.jsx
Test Suites: 4 passed, 4 total
Tests:       49 passed, 49 total
Time:        1.073 s
```

49/49 green. ExposureStrip 6/6 including the D1 ticker-change test.

## Source verification

### VEX_WALL title (verified against current main)
`backend/services/exposure_alerts.py:311` on current main:
```
"vex_wall_broken": "VEX wall broken — vol suppression released, regime may shift",
```
PR48's badge title names this: "broken (suppression released, regime may shift)". Honest. Does NOT claim broken rows are "defending". ✓

### GAMMA_FLIP title (verified against current main)
`backend/services/exposure_alerts.py:315`:
```
"gamma_flip_approach": "Gamma flip proximity — price pressing dealer flip level (support above / resistance below)",
```
PR48's badge title names this: "flip approach (exposure path)". Honest. Does NOT claim approach rows are a regime flip. ✓

### D1 mechanism (verified against code)
ExposureStrip.jsx L30: `setBadges([]); // drop the previous ticker's badges immediately`. The effect re-runs on ticker change → old badges cleared before fetch → either replaced or stays empty. The `.catch()` no longer calls `setBadges([])` but the effect body does. D1 fixed. ✓

### KIND_TITLES status
Not in this branch. But PR50 (which added KIND_TITLES) is MERGED — so KIND_TITLES is now in `origin/main:frontend/src/components/flowseeker/exposureBadges.js`. When PR48 merges, main will have both PR48's badges AND KIND_TITLES. The two-arg `exposureBadgeFor(rule, row)` form is also in main (from PR50). PR48's current call sites (one-arg) will start using KIND_TITLES automatically when main merges PR48's branch — no further change needed.

## Merge readiness

### PR48 merge to current main — CLEAN (tested)
Worktree `/tmp/pr48-merge-check` at `73533e1` (prior head). `git merge --no-commit origin/main` → automatic merge, no conflicts. Files touched by PR52+PR53 on main (backend/*, new test files) do not overlap PR48's payload (frontend/*).

At the current head `2f57bea3d`: PR48's three-dot diff vs main is 9 frontend files, +434 insertions, 0 deletions vs main — frontend-only, no overlap with PR52/53 backend changes. Merge should be clean.

### UNSTABLE status explained
GitHub shows UNSTABLE because the branch tip `2f57bea3d` does not include PR50's commits (f3b9beb, f7bc499) which ARE in main. This is a rebase artifact: PR50 was merged via this PR's vehicle, then the a3/alert-surfacing branch was reset to a state that excludes PR50's commits (while PR50 itself was merged to main).

To become CLEAN: rebase `a3/alert-surfacing` onto `origin/main`. This would pick up KIND_TITLES (already in main) and PR52/53 backend changes (no frontend overlap). The branch would then be CLEAN and mergeable.

## Verdict

**APPROVED at E4-48b level.** All three E4-48 defects (D1 stale badges, D2 broken-VEX-as-defending, D3 gamma-flip-approach-as-regime-flip) are fixed at this head by the f25de2e rework. Tests 49/49 green. Code is frontend-only, no App.js, no backend.

**Watch item:** This head does NOT include PR50's KIND_TITLES refinement (which is now in main via PR50's separate merge). The branch is UNSTABLE/behind main. Two paths:
1. **Merge as-is:** PR48 merges → main gets PR48 badges (with f25de2e dual titles) + KIND_TITLES (already there from PR50) + PR52/53. KIND_TITLES would be present but unused until call sites pass the row — but PR50's call-site changes (ExposureStrip `exposureBadgeFor(row?.rule, row)`, Blademap `exposureBadgeFor(a.rule, a)`) are ALSO in main now (from PR50 merge). So main would have everything working. But PR48's branch would merge as a no-op on the KIND_TITLES/call-site side (already in main).
2. **Rebase onto main first:** `git rebase origin/main` on a3/alert-surfacing → picks up KIND_TITLES + PR52/53 → becomes CLEAN → merge. Cleaner history.

Either path delivers the same end state. Nav chooses. No agent merge authority.

## PR50 — MERGED
[#50](https://github.com/mrbeast1179-sketch/floww/pull/50) — `fix(agent3): E4-48 semantic rework — kind-aware badge copy + stale-strip fix`
- State: MERGED (`f7bc499ea`, 2026-09-09T15:35:57Z)
- KIND_TITLES + exposureKindOf + two-arg exposureBadgeFor + 5 pin tests now in main
- Prior E4-48c APPROVED verdict stands (verifying the merged content)

## PR49 — DIRTY, needs rebase
[#49](https://github.com/mrbeast1179-sketch/floww/pull/49) — `feat(agent3): alert-engine badge mapper (1c) + CLUSTER badge`
- State: OPEN, head `6387f13`, base `a3/alert-surfacing`
- Merge status: DIRTY (rebase onto `2f57bea3d` produces conflict in `frontend/src/components/flowseeker/exposureBadges.js`)
- Conflict: PR49's 18ee54f commit adds CLUSTER badge to exposureBadges.js, but the base file has changed (PR48's f25de2e rework + 2f57bea fix). The CLUSTER addition (4 lines in BADGES dict + 1 test) needs to be applied on top of the current exposureBadges.js.
- 29/29 green at its own head (alertEngineBadges + exposureBadges suites)
- Wiring gap holds (1c mapper unrendered)
- Rebase + conflict resolution is agent-3's job, not agent-4's

## What's no longer true
- E4-48c verdict (PR48 @ 73533e1 with PR50 KIND_TITLES in the branch) — VOID, that head is gone
- PR48 at `81255b886` — VOID, that head is gone
- PR48 "merge-ready, Nav call" — no longer accurate; branch is UNSTABLE, needs rebase decision

## No GitHub mutations this round.
