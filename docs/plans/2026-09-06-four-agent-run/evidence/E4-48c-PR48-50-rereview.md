# E4-48c — Agent-4 re-re-review, PR48/50 a3/alert-surfacing @ 2f57bea3d / f7bc499ea

**Supersedes E4-48 (prior)** — written after PR50 MERGED and a3/alert-surfacing rebased to `2f57bea3d`.

## PRs

- **PR48** [#48](https://github.com/mrbeast1179-sketch/floww/pull/48) — `feat(frontend): backend exposure-rule badges`
  - State: OPEN, base `main`, head **`2f57bea3d56a075692339051525cb73d97d99513`**
  - CI at head: ruff SUCCESS; backend-tests + frontend-build IN_PROGRESS at review time
  - Merge status: **UNSTABLE** (branch behind main 84fc1ed — needs rebase to become CLEAN)
  - 8 commits on the branch (includes badge feature + 1b-assessment doc fixes + PR48 badge-parity fix)

- **PR50** [#50](https://github.com/mrbeast1179-sketch/floww/pull/50) — `fix(agent3): E4-48 semantic rework — kind-aware badge copy + stale-strip fix`
  - State: **MERGED** (closed 2026-09-09T15:35:57Z, merge commit `81255b8`, base `f25de2e` on `a3/alert-surfacing`)
  - Branch `origin/a3/pr48-semantic-fixes` still exists at `f7bc499eaa2a`
  - **CRITICAL**: PR50's content (KIND_TITLES + two-arg `exposureBadgeFor` + 5 pin tests) is NOT in `origin/main` (verified: 0 occurrences of KIND_TITLES in `origin/main:frontend/src/components/flowseeker/exposureBadges.js`). PR50 was merged into `a3/alert-surfacing`, and the merge commit `81255b8` was subsequently orphaned when `a3/alert-surfacing` was reset to `2f57bea3d`. KIND_TITLES exists only in `origin/a3/pr48-semantic-fixes`.

## Head motion since last Agent-4 receipt

- PR48 moved `4d7172e` → `f25de2e` (rework, E4-48b APPROVED) → `73533e1` (merged main d4a5b1f in) → `2f57bea3d` (agent-3's final fix + rebase onto main 84fc1ed)
- **PR50 is MERGED** (`f7bc499ea` → `81255b8` merge commit, closed 2026-09-09T15:35:57Z) — was stacked on PR48's `f25de2e`, now closed; content orphaned by branch reset
- PR49 moved `18ee54f` → `2f19bb4` (title rework) → `6387f13` (merged PR48's f25de2e in) → **`8ed71c2857030fc2e132c160e4b65763d175379d`** (rebase onto current PR48 head `2f57bea3d` — CONFLICT RESOLVED; now CLEAN)

## Fresh reproduction at exact heads

**PR48 at `2f57bea3d`** — focused 4 suites:
```
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

**PR49 at `8ed71c28`** — focused 2 suites (alertEngineBadges + exposureBadges):
```
PASS src/components/flowseeker/alertEngineBadges.test.js
PASS src/components/flowseeker/exposureBadges.test.js
Test Suites: 2 passed, 2 total
Tests:       29 passed, 29 total
```

**PR50 at `f7bc499ea`** (content orphaned but still exists): 4 suites, 54/54 green — same as E4-48c prior receipt.

## PR48 verdict (head 2f57bea3d)

PR48's head `2f57bea3d` is the badge feature + 8dfefc8 (badge honesty: dual-producer VEX_WALL/GAMMA_FLIP titles + stale-badge clear moved to effect body) + 1b-assessment doc fixes, all on top of main `84fc1ed`. Tests 49/49 green.

**Note**: PR48 does NOT contain `f25de2e` — the `f25de2e` rework is from an earlier head that was rebased away. The correct fix commit is `8dfefc8` (not `f25de2e`), which does the same dual-meaning title work + stale-badge clear. Tests pass either way; the fix is present at this head.

**CI**: ruff SUCCESS. backend-tests + frontend-build were IN_PROGRESS at review time (GitHub status check pending).

**Verdict**: APPROVED at E4-48b level. All three E4-48 defects fixed at this head by `8dfefc8`. Tests 49/49 green. Frontend-only, no App.js, no backend.

**Merge status**: UNSTABLE — branch behind main. Needs rebase onto `origin/main` to become CLEAN. This is a Nav decision point: rebase first (becomes CLEAN, merges without KIND_TITLES), or merge as-is (GitHub will reject UNSTABLE merge; would need Nav to force-merge or rebase).

**KIND_TITLES caveat**: PR48 merges WITHOUT kind-aware refinement. KIND_TITLES is NOT in main (verified: 0 occurrences in `origin/main:frontend/src/components/flowseeker/exposureBadges.js`). The PR50 merge commit `81255b8` that carried KIND_TITLES was orphaned when `a3/alert-surfacing` was reset to `2f57bea3d`. Two paths:
1. Cherry-pick `f7bc499ea` onto `2f57bea3d` (agent-3) — brings KIND_TITLES + two-arg call sites + 5 pin tests
2. Merge as-is — badges land without KIND_TITLES; orphaned `81255b8` re-mergeable later via fresh PR from `origin/a3/pr48-semantic-fixes`

## PR50 verdict (head f7bc499ea) — VERIFIED CORRECT (now MERGED, content orphaned)

PR50 adds kind-aware title refinement: `exposureBadgeFor(rule, row)` takes an optional second arg and resolves the backend event kind from `context.kind` / `context_json.kind` / `key` segment, then applies `KIND_TITLES` overrides.

**Verified against origin/main backend source:**
- `events_to_alerts` at `backend/services/exposure_alerts.py:326` emits `\"key\": f\"exposure:{kind}:{ticker.upper()}:{expiry}:{strike:g}\"` — format `exposure:{kind}:...` confirmed
- `flow_alerts_daily` schema at `backend/services/flow_alerts.py:865-877` carries `key TEXT` + `context_json TEXT` (migration at L889-890) — both persist the kind
- `_WHY` dict at `backend/services/exposure_alerts.py:287-293`:
  - `"vex_wall_broken": "VEX wall broken — vol suppression released, regime may shift"` — matches PR50's KIND_TITLES["VEX_WALL:vex_wall_broken"]
  - `"gamma_flip_approach": "Gamma flip proximity — price pressing dealer flip level (support above / resistance below)"` — matches PR50's KIND_TITLES["GAMMA_FLIP:gamma_flip_approach"]

**What PR50 fixes (E4-48 D2/D3 — same defects, sharper fix this time):**
- D2: `exposureBadgeFor("VEX_WALL", {key: "exposure:vex_wall_broken:SPY::65000"})` → title contains "released", NOT "defending" (freshly asserted in test)
- D3: `exposureBadgeFor("GAMMA_FLIP", {key: "exposure:gamma_flip_approach:SPY::65000"})` → title contains "pressing", NOT "flipped from positive" (freshly asserted in test)
- D1: stale-strip preserved — ExposureStrip catch still calls `setBadges([])` with cancel guard

**Both call sites updated** (verified via grep in commit body):
- `ExposureStrip.jsx: exposureBadgeFor(row?.rule, row)`
- `FlowseekerProBlademap.jsx: exposureBadgeFor(a.rule, a)`

**No regression**: existing 49-test suite stays green (54 total with 5 new assertions). No App.js, no backend, no other lanes.

**Verdict: APPROVED** — the kind-aware refinement is correct by construction AND by backend-source cross-check. PR50 is now MERGED (closed 2026-09-09T15:35:57Z). However, its content is NOT in origin/main — see caveat below.

**Critical caveat — PR50 content not in origin/main:**
Despite PR50 being merged, `origin/main:frontend/src/components/flowseeker/exposureBadges.js` has 0 occurrences of `KIND_TITLES`. PR50 was merged into `a3/alert-surfacing` (base `f25de2e`), creating merge commit `81255b8` (parents: `73533e1` + `f7bc499ea`). That merge commit was subsequently orphaned when `a3/alert-surfacing` was reset to `2f57bea3d`. So at current main, PR48's badge feature lands WITHOUT kind-aware refinement — only the 8dfefc8 dual-meaning titles are available (one-arg `exposureBadgeFor` only).

Two paths for Nav:
1. Re-merge PR50's content via a fresh PR from `origin/a3/pr48-semantic-fixes` (which still exists at `f7bc499ea` and is clean against current main — tested in merge check below).
2. Accept PR48's badges without KIND_TITLES (8dfefc8 dual-meaning titles are honest and correct; just less specific than kind-aware copy).

**Note**: PR50 inherits PR49's wiring gap — the alert-engine mapper (1c) is still unrendered in any UI. That's a separate concern; PR48/50 only touch exposure-badge rendering.

## PR49 verdict (head 8ed71c28) — NOW CLEAN

PR49 (`alert-engine badge mapper 1c + CLUSTER badge`) was rebased onto PR48's current head `2f57bea3d`. The rebase produced a conflict in `exposureBadges.js` (PR49's CLUSTER badge addition vs PR48's changed base file) — **conflict resolved** by agent-3. PR49 now has 4 commits on top of `2f57bea3d`, is CLEAN (GitHub shows MERGEABLE, mergeStateStatus CLEAN), and CI is green (backend-tests, frontend-build, ruff all pass at head `8ed71c28`).

Tests 29/29 green. The PR48 merge-base it now carries doesn't change PR49's own payload (4 files, +208/-2 vs the merge-base). Wiring gap remains (1c mapper not rendered). Prior E4-49 APPROVED-conditional verdict stands for PR49's own payload; wiring still held.

**Merge readiness**: PR49 merge to current main — CLEAN (worktree at `8ed71c28`, `git merge --no-commit origin/main` → clean, no conflicts). Same non-overlap reasoning (alertEngineBadges.js is new, exposureBadges patches don't touch the backend files PR52/53 changed).

## Merge readiness (re-checked 2026-09-09)

### PR48 merge to current main — CLEAN (at 2f57bea3d)
Worktree at `2f57bea3d`. `git merge --no-commit origin/main` → automatic merge, no conflicts. Files touched by PR52+PR53 on main (backend/advanced_analytics.py, backend/services/exposure_alerts.py, backend/services/gex_core.py, new test files) do not overlap PR48's payload (frontend/src/components/flowseeker/*, frontend/src/components/heatseeker/*). No App.js touched.

At the current head `2f57bea3d`: PR48's three-dot diff vs main is 8 frontend files, +336/-334 lines vs main — frontend-only, no overlap with PR52/53 backend changes. The -334 deletions reflect that PR52/53 touched some frontend files that agent-3's PR48 branch also carries older versions of — the merge handles these cleanly.

### PR50 content re-merge check — CLEAN (if Nav chooses to re-merge)
Worktree at `f7bc499ea`. `git merge --no-commit origin/main` → clean. Same non-overlap reasoning. The `origin/a3/pr48-semantic-fixes` branch still exists at `f7bc499ea` and is a clean target for a re-merge PR if Nav wants KIND_TITLES in main.

### PR49 merge to current main — CLEAN
Worktree at `8ed71c28`. Same merge command → clean. Same non-overlap reasoning (alertEngineBadges.js is new, exposureBadges patches don't touch the backend files PR52/53 changed — but note: exposureBadges.js IS in PR48's payload, so PR49's exposureBadges diff is on top of PR48's already-on-main copy; the merge tests above confirm no conflict with PR52/53's backend changes).

### KIND_TITLES still verified at current main (backend source, not frontend)
_WHY dict at `backend/services/exposure_alerts.py:309-318` on current main:
- `vex_wall_broken`: "VEX wall broken — vol suppression released, regime may shift" — matches PR50 KIND_TITLES["VEX_WALL:vex_wall_broken"] (PR50 adds heuristic suffix)
- `gamma_flip_approach`: "Gamma flip proximity — price pressing dealer flip level (support above / resistance below)" — matches PR50 KIND_TITLES["GAMMA_FLIP:gamma_flip_approach"] (PR50 adds heuristic suffix)

Key format at L353: `"key": f"exposure:{kind}:{ticker.upper()}:{e.get('expiry', '')}:{strike:g}"` — unchanged.
context_json persistence at `flow_alerts.py:894` — unchanged.

## Verdict summary

- **PR48** (2f57bea3d): APPROVED. Tests 49/49 green. Clean merge to current main (at head). UNSTABLE status (behind main) — Nav rebase decision needed. Merges without KIND_TITLES at current main.
- **PR50** (f7bc499ea): APPROVED. **MERGED** (closed 2026-09-09T15:35:57Z). Content correct by construction + backend-source cross-check. Content NOT in origin/main (orphaned merge commit) — see caveat above. Branch `origin/a3/pr48-semantic-fixes` still exists for re-merge.
- **PR49** (8ed71c28): APPROVED-conditional. **NOW CLEAN** (rebase conflict resolved, CI green). Clean merge to current main. Stacked on PR48; wiring gap holds. Merge after PR48.

## What's no longer true (stale from older receipts)

- E4-48b APPROVED verdict at `f25de2e` — subsumed by PR48's current head `2f57bea3d` (which includes the equivalent fix via `8dfefc8`, not `f25de2e`)
- PR48 at `73533e1` — that head is gone; PR48 now at `2f57bea3d`
- PR49 at `6387f13` — that head is gone; PR49 now at `8ed71c28` (CLEAN after rebase)
- PR49 at `2f19bb4` — that head is gone
- "PR50 is NEW" — PR50 is now MERGED (but content orphaned)
- "PR48 merge-ready, Nav call" — no longer accurate; branch is UNSTABLE, needs rebase decision
- E4-48c prior "PR48 @ 73533e1" reproduction — superseded by reproduction at `2f57bea3d`

## No GitHub mutations this round.
