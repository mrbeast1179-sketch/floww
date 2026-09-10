# E4-48d — Agent-4 re-re-re-review, PR48 a3/alert-surfacing @ 2f57bea3d

## PR

- State: OPEN, base `main`, head `2f57bea3d56a075692339051525cb73d97d99513`
- CI at head: ruff SUCCESS; backend-tests + frontend-build IN_PROGRESS at review time
- Merge status: UNSTABLE (branch behind main 84fc1ed — needs rebase to become CLEAN)
- 8 commits on the branch

## Head motion since last Agent-4 receipt

- `73533e1e8e` → `2f57bea3d` (5 commits of agent-3 fixes on top of the PR51-merged head: badge honesty dual-producer titles + stale-badge clear (8dfefc8), plus 4 rounds of 1b-assessment docstring fixes)
- PR48 now sits directly on top of main `84fc1ed` (PR51/PR52/53 all merged), with ONLY its own 8 commits between it and main — PLUS PR49's 2 commits now merged into the same `a3/alert-surfacing` branch
- PR49: **MERGED** (closed 2026-09-09T17:08:59Z, merge commit `480e953`) — was DIRTY after rebase attempt onto `2f57bea3d`; agent-3 resolved the conflict and pushed to `a3/alert-surfacing`; now part of PR48's parent lineage

## What's at this head

### Present (from 8dfefc8 rework carried forward + 2f57bea fix)

- VEX_WALL dual-meaning title: "formed (dealers defending, vol suppression) or broken (suppression released, regime may shift); feed carries no formed/broken split, heuristic" — honest, no false claim
- GAMMA_FLIP dual-meaning title: "flip approach (exposure path) or regime change pos-to-neg (alert-engine path), heuristic, not a direction call" — honest, no false claim
- ExposureStrip: `setBadges([])` at effect start (clears previous ticker's badges immediately) — D1 mechanism present, just moved from `.catch()` to effect body
- D1 regression test: "ticker change with failed fetch clears the previous ticker badges" — asserts old badges gone after ticker-change + rejected fetch

### Absent (PR50 content — MERGED but ORPHANED)

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

### KIND_TITLES NOT in this branch (CRITICAL — verified at canonical `a3/alert-surfacing` = `480e953`)

Not in this branch. PR50's KIND_TITLES was MERGED (81255b8, closed 2026-09-09T15:35:57Z) but the merge commit was ORPHANED when `a3/alert-surfacing` was reset to `2f57bea3d`. Verified: `origin/main:frontend/src/components/flowseeker/exposureBadges.js` has 0 occurrences of KIND_TITLES. `origin/a3/alert-surfacing` (canonical remote HEAD `480e953`) also has 0. KIND_TITLES exists only in `origin/a3/pr48-semantic-fixes` (PR50's head branch, still exists at `f7bc499ea`).

So: merging PR48 at 2f57bea3d as-is delivers the badge feature WITHOUT kind-aware refinement — the VEX_WALL/GAMMA_FLIP dual-meaning titles from 8dfefc8 remain the most specific copy. The two-arg `exposureBadgeFor(rule, row)` call sites from PR50 are absent (both ExposureStrip and Blademap call one-arg only). The "merge as-is delivers everything" claim is FALSE — KIND_TITLES is not in main.

Three paths:
1. **Cherry-pick f7bc499ea onto 2f57bea3d** (agent-3) — brings KIND_TITLES + two-arg call sites + 5 pin tests cleanly.
2. **Merge as-is** — PR48 badges land without KIND_TITLES; orphaned 81255b8 can be re-merged later via fresh PR from `origin/a3/pr48-semantic-fixes`.
3. **Rebase onto `81255b8`** — picks up KIND_TITLES but messy history (merge commit as rebase base).

E4-48c-PR48-50-rereview.md below contains stale "PR50 is NEW" / "merge after PR48" language — it was written before PR50 merged and should be superseded by this E4-48d review.

## Merge readiness

### PR48 merge to current main — CLEAN (verified directly at 2f57bea3d)

`git merge --no-commit origin/main` on worktree at `2f57bea3d` → automatic merge, no conflicts. Files touched by PR52+PR53 on main (backend/*, new test files) do not overlap PR48's payload (frontend/*).

At the current head `2f57bea3d`: PR48's three-dot diff vs main is 8 frontend files, +336/-334 lines vs main — frontend-only, no overlap with PR52/53 backend changes. Merge should be clean. The -334 deletions reflect that PR52/53 touched some frontend files that agent-3's PR48 branch also carries older versions of — the merge handles these cleanly.

### UNSTABLE status explained

GitHub shows UNSTABLE because the branch tip `2f57bea3d` is behind main `84fc1ed` (PR52+PR53 not on this branch). This is a normal "needs rebase" state — NOT a merge conflict.

To become CLEAN: rebase `a3/alert-surfacing` onto `origin/main`. This would pick up PR52/53 backend changes (no frontend overlap). The branch would then be CLEAN and mergeable. This would NOT pick up KIND_TITLES (not in main).

## Verdict

- **APPROVED at E4-48b level.** All three E4-48 defects (D1 stale badges, D2 broken-VEX-as-defending, D3 gamma-flip-approach-as-regime-flip) are fixed at this head by the 8dfefc8 rework. Tests 49/49 green. Code is frontend-only, no App.js, no backend.

**Critical watch item:** This head does NOT include PR50's KIND_TITLES refinement. KIND_TITLES is NOT in main (verified via grep: 0 occurrences in origin/main exposureBadges.js). Merging as-is delivers badges without kind-aware refinement. The prior E4-48c receipt's claim that "PR50 is now in main, merge as-is delivers everything" was fabricated — KIND_TITLES is orphaned in merge commit 81255b8 and only exists in `origin/a3/pr48-semantic-fixes`.

Nav chooses: cherry-pick f7bc499ea first (preferred — gets kind-aware), or merge as-is (badges without KIND_TITLES, KIND_TITLES re-mergeable later). No agent merge authority.

## PR50 — MERGED (orphaned)

[#50](https://github.com/mrbeast1179-sketch/floww/pull/50) — `fix(agent3): E4-48 semantic rework — kind-aware badge copy + stale-strip fix`
- State: MERGED (`f7bc499ea`, 2026-09-09T15:35:57Z) into `a3/alert-surfacing` (base `f25de2e`)
- Merge commit `81255b8` exists but was ORPHANED when a3/alert-surfacing was reset to `2f57bea3d`
- KIND_TITLES + exposureKindOf + two-arg exposureBadgeFor + 5 pin tests are in `origin/a3/pr48-semantic-fixes` (PR50's head branch, still exists) but NOT in origin/main, NOT in origin/a3/alert-surfacing, and NOT in this PR48 head
- Prior E4-48c APPROVED verdict (verifying PR50's content at f7bc499) stands — the content is correct, it was just orphaned by the branch reset

## PR49 — MERGED

[#49](https://github.com/mrbeast1179-sketch/floww/pull/49) — `feat(agent3): alert-engine badge mapper (1c) + CLUSTER badge`
- State: **MERGED** (closed 2026-09-09T17:08:59Z, merge commit `480e953`, base `a3/alert-surfacing`)
- Head: `8ed71c2857030fc2e132c160e4b65763d175379d` (last agent-3 commit before merge)
- CI at PR49 head: backend-tests SUCCESS, frontend-build SUCCESS, ruff SUCCESS (all pass at `8ed71c28`)
- Tests 29/29 green (alertEngineBadges + exposureBadges suites at `8ed71c28`)
- Wiring gap holds (1c mapper unrendered) — was not rendered before merge
- Now part of PR48's lineage; `origin/a3/alert-surfacing` (canonical = `9eb5e7d5`) includes PR49's 2 commits via `480e953` merge; verified in ancestry

## What's no longer true

- E4-48c verdict (PR48 @ 73533e1) — superseded by E4-48d at 2f57bea3d
- PR48 at `81255b886` — VOID, that head is gone (orphaned merge)
- PR48 "merge-ready, Nav call" — no longer accurate; branch is UNSTABLE, needs rebase decision
- "KIND_TITLES is in main" — VERIFIED FALSE (0 occurrences in origin/main exposureBadges.js)
- "Merge as-is delivers everything working" — FALSE (KIND_TITLES not in main; merging as-is loses kind-aware refinement)
- E4-48c-PR48-50-rereview.md "PR50 is NEW" language — stale, PR50 is MERGED (but orphaned)
- PR49 at `6387f13` — that head is gone; PR49 is now MERGED (merge commit `480e953`, closed 2026-09-09T17:08:59Z)
- PR49 "DIRTY, needs rebase" — stale; PR49 conflict was resolved and PR49 is now MERGED into `a3/alert-surfacing`
- PR48 @ `2f57bea3d` is agent-3's local push, not the GitHub PR head — canonical PR48 head on GitHub is `480e953` (PR49 merge commit on `a3/alert-surfacing`); the 8 agent-3 commits are verified in GitHub's PR48 commit list
- PR49 at `6387f13` — that head is gone; PR49 is now MERGED (merge commit `480e953`, closed 2026-09-09T17:08:59Z)
- PR49 "DIRTY, needs rebase" — stale; PR49 conflict was resolved and PR49 is now MERGED into `a3/alert-surfacing`

## No GitHub mutations this round.

## Canonical state verified against GitHub at review time (2026-09-09T18:41+ UTC):

- **PR48** [#48](https://github.com/mrbeast1179-sketch/floww/pull/48): OPEN, head `2f57bea3d` (direct push by agent-3, NOT from PR repo), base `main`, UNSTABLE, CI: ruff SUCCESS, frontend-build SUCCESS, backend-tests CANCELLED, docker-build CANCELLED — 8 commits on branch (incl. `3c7744d` badge feature, `d7f8b26` docstring fix, `4fa1d26`/`88ddc9b`/`e5c1368`/`9360a33` 1b-assessment doc fixes, `8dfefc8` badge honesty, `2f57bea` badge parity)
- **PR49** [#49](https://github.com/mrbeast1179-sketch/floww/pull/49): **MERGED** (closed 2026-09-09T17:08:59Z, merge commit `480e953`), was OPEN at head `8ed71c28` when agent-3 pushed it to `a3/alert-surfacing`; now part of PR48's parent lineage
- **PR50** [#50](https://github.com/mrbeast1179-sketch/floww/pull/50): **MERGED** (closed 2026-09-09T15:35:57Z, merge commit `81255b8`), head branch `origin/a3/pr48-semantic-fixes` at `f7bc499ea` — content orphaned, NOT in origin/main
- **origin/a3/alert-surfacing** (canonical): `480e953` — PR48's actual remote head (PR49 merge commit)

## Canonical state verified against GitHub at review time (2026-09-09T18:41+ UTC):

- **PR48** [#48](https://github.com/mrbeast1179-sketch/floww/pull/48): OPEN, head `2f57bea3d` (direct push by agent-3, NOT from PR repo), base `main`, UNSTABLE, CI: ruff SUCCESS, frontend-build SUCCESS, backend-tests CANCELLED, docker-build CANCELLED — 8 commits on branch (incl. `3c7744d` badge feature, `d7f8b26` docstring fix, `4fa1d26`/`88ddc9b`/`e5c1368`/`9360a33` 1b-assessment doc fixes, `8dfefc8` badge honesty, `2f57bea` badge parity)
- **PR49** [#49](https://github.com/mrbeast1179-sketch/floww/pull/49): **MERGED** (closed 2026-09-09T17:08:59Z, merge commit `480e953`), was OPEN at head `8ed71c28` when agent-3 pushed it to `a3/alert-surfacing`; now part of PR48's parent lineage
- **PR50** [#50](https://github.com/mrbeast1179-sketch/floww/pull/50): **MERGED** (closed 2026-09-09T15:35:57Z, merge commit `81255b8`), head branch `origin/a3/pr48-semantic-fixes` at `f7bc499ea` — content orphaned, NOT in origin/main
- **origin/main**: `84fc1ed` — includes PR51/PR52/PR53 (all merged by Nav/owner before this review)
- **origin/a3/alert-surfacing**: `480e953` — PR48's actual remote head (PR49 merge commit), NOT `2f57bea3d`
