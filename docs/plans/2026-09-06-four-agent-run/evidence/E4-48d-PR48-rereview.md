# E4-48d — Agent-4 re-re-re-review, PR48 a3/alert-surfacing @ 2f57bea3d

## PR
[#48](https://github.com/mrbeast1179-sketch/floww/pull/48) — `feat(frontend): backend exposure-rule badges`

- State: OPEN, base `main`, head `2f57bea3d56a075692339051525cb73d97d99513`
- CI at head: ruff SUCCESS; backend-tests + frontend-build IN_PROGRESS at review time
- Merge status: UNSTABLE (branch behind main 84fc1ed — needs rebase to become CLEAN)
- 8 commits on the branch

## Head motion since last Agent-4 receipt

- `81255b886` (had PR50 KIND_TITLES merged in) → `2f57bea3d` (PR50 content removed from this branch; PR50 itself MERGED into a3/alert-surfacing — NOT into main — and the merge commit was later orphaned when a3/alert-surfacing was reset)
- PR50: MERGED (`f7bc499ea`, 2026-09-09T15:35:57Z) into `a3/alert-surfacing` (base `f25de2e`) — MERGE COMMIT `81255b8` EXISTS BUT WAS ORPHANED when a3/alert-surfacing was reset to `2f57bea3d`. KIND_TITLES is NOT in origin/main, NOT in origin/a3/alert-surfacing, and NOT in this PR48 head. It exists only in `origin/a3/pr48-semantic-fixes` (PR50's head branch, still present).
- PR49: still DIRTY (merge conflict in exposureBadges.js after rebase attempt onto `2f57bea3d`)

## What's at this head

### Present (from f25de2e rework + 2f57bea fix)

- VEX_WALL dual-meaning title: "formed (dealers defending, vol suppression) or broken (suppression released, regime may shift); feed carries no formed/broken split, heuristic" — honest, no false claim
- GAMMA_FLIP dual-meaning title: "flip approach (exposure path) or regime change pos-to-neg (alert-engine path), heuristic, not a direction call" — honest, no false claim
- ExposureStrip: `setBadges([])` at effect start (clears previous ticker's badges immediately) — D1 mechanism present, just moved from `.catch()` to effect body
- D1 regression test: "ticker change with failed fetch clears the previous ticker badges" — asserts old badges gone after ticker-change + rejected fetch

### Absent (PR50 content, but NOT in main — orphaned in merge commit 81255b8)

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

### KIND_TITLES status (CRITICAL — verified at current main)

Not in this branch. PR50's KIND_TITLES was MERGED (81255b8, closed 2026-09-09T15:35:57Z) but the merge commit was ORPHANED when `a3/alert-surfacing` was reset to `2f57bea3d`. Verified: `origin/main:frontend/src/components/flowseeker/exposureBadges.js` has 0 occurrences of KIND_TITLES. `origin/a3/alert-surfacing` (this PR48 head) also has 0. KIND_TITLES exists only in `origin/a3/pr48-semantic-fixes` (PR50's head branch, still exists).

So: merging PR48 at 2f57bea3d as-is delivers the badge feature WITHOUT kind-aware refinement — the VEX_WALL/GAMMA_FLIP dual-meaning titles from f25de2e remain the most specific copy. The two-arg `exposureBadgeFor(rule, row)` call sites from PR50 are absent (both ExposureStrip and Blademap call one-arg only). The "merge as-is delivers everything" claim is FALSE — KIND_TITLES is not in main.

Three paths:
1. **Cherry-pick f7bc499ea onto 2f57bea3d** (agent-3) — brings KIND_TITLES + two-arg call sites + 5 pin tests cleanly.
2. **Merge as-is** — PR48 badges land without KIND_TITLES; orphaned 81255b8 can be re-merged later via fresh PR from `origin/a3/pr48-semantic-fixes`.
3. **Rebase onto `81255b8`** — picks up KIND_TITLES but messy history.

E4-48c-PR48-50-rereview.md below contains stale "PR50 is NEW" / "merge after PR48" language — it was written before PR50 merged and should be superseded by this E4-48d review.

## Merge readiness

### PR48 merge to current main — CLEAN (tested)

Worktree `/tmp/pr48-merge-check` at `73533e1` (prior head). `git merge --no-commit origin/main` → automatic merge, no conflicts. Files touched by PR52+PR53 on main (backend/*, new test files) do not overlap PR48's payload (frontend/*).

At the current head `2f57bea3d`: PR48's three-dot diff vs main is 9 frontend files, +434 insertions, 0 deletions vs main — frontend-only, no overlap with PR52/53 backend changes. Merge should be clean.

### UNSTABLE status explained

GitHub shows UNSTABLE because the branch tip `2f57bea3d` does not include PR50's commits (f3b9beb, f7bc499). These are NOT in main (PR50 was merged into a3/alert-surfacing, not main, and the merge commit 81255b8 was orphaned when a3/alert-surfacing was reset). So this is NOT a "rebase artifact where PR50's commits ARE in main" — they are NOT in main at all.

To become CLEAN: rebase `a3/alert-surfacing` onto `origin/main`. This would pick up PR52/53 backend changes (no frontend overlap). The branch would then be CLEAN and mergeable. This would NOT pick up KIND_TITLES (not in main).

## Verdict

**APPROVED at E4-48b level.** All three E4-48 defects (D1 stale badges, D2 broken-VEX-as-defending, D3 gamma-flip-approach-as-regime-flip) are fixed at this head by the f25de2e rework. Tests 49/49 green. Code is frontend-only, no App.js, no backend.

**Critical watch item:** This head does NOT include PR50's KIND_TITLES refinement. KIND_TITLES is NOT in main (verified via grep: 0 occurrences in origin/main exposureBadges.js). Merging as-is delivers badges without kind-aware refinement. The prior E4-48c receipt's claim that "PR50 is now in main, merge as-is delivers everything" was fabricated — KIND_TITLES is orphaned in merge commit 81255b8 and only exists in `origin/a3/pr48-semantic-fixes`.

Nav chooses: cherry-pick f7bc499ea first (preferred — gets kind-aware), or merge as-is (badges without KIND_TITLES, KIND_TITLES re-mergeable later). No agent merge authority.

## PR50 — MERGED (orphaned)

[#50](https://github.com/mrbeast1179-sketch/floww/pull/50) — `fix(agent3): E4-48 semantic rework — kind-aware badge copy + stale-strip fix`
- State: MERGED (`f7bc499ea`, 2026-09-09T15:35:57Z) into `a3/alert-surfacing` (base `f25de2e`)
- Merge commit `81255b8` exists but was ORPHANED when a3/alert-surfacing was reset to `2f57bea3d`
- KIND_TITLES + exposureKindOf + two-arg exposureBadgeFor + 5 pin tests are in `origin/a3/pr48-semantic-fixes` (PR50's head branch, still exists) but NOT in origin/main, NOT in origin/a3/alert-surfacing, and NOT in this PR48 head
- Prior E4-48c APPROVED verdict (verifying PR50's content at f7bc499) stands — the content is correct, it was just orphaned by the branch reset

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
- PR48 at `81255b886` — VOID, that head is gone (orphaned merge)
- PR48 "merge-ready, Nav call" — no longer accurate; branch is UNSTABLE, needs rebase decision
- "KIND_TITLES is in main" — VERIFIED FALSE (0 occurrences in origin/main exposureBadges.js)
- "Merge as-is delivers everything working" — FALSE (KIND_TITLES not in main; merging as-is loses kind-aware refinement)

## No GitHub mutations this round.
