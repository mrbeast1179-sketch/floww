# E4-55 — Agent-4 review of PR55 (architect/pr48-semantic-main-v1)

## PR

[#55](https://github.com/mrbeast1179-sketch/floww/pull/55) — `fix(frontend): restore kind-aware exposure badge truth`

- State: OPEN, base `main` (`d5dbd7d`), head `7481f727cdbf826145190a6ada2668666c34a191`
- Branch: `architect/pr48-semantic-main-v1`
- CI at head: ruff PASS (15s), frontend-build PASS (1m59s), backend-tests PENDING
- Merge status: UNSTABLE (behind main — but head already merges origin/main)

## What this PR is

The canonical current-main port of the orphaned PR50 KIND_TITLES content. PR50
merged only into `a3/alert-surfacing` (merge commit `81255b8`, orphaned when the
branch was reset). PR48 (MERGED `12c53d8`) delivered the badge feature WITHOUT
kind-aware refinement. PR55 ports the KIND_TITLES + two-arg `exposureBadgeFor`
+ `exposureKindOf` + `selectExposureBadges()` onto current main `d5dbd7d`, and
also retains PR49's later CLUSTER badge addition.

Provenance: `origin/a3/pr48-semantic-fixes` at `f7bc499ea` (PR50 head) still
exists with the KIND_TITLES content. Verified: `git show f7bc499ea:frontend/src/components/flowseeker/exposureBadges.js | grep -c KIND_TITLES` = 2.

## Delta vs main `d5dbd7d`

5 files, +119/-10:

- `frontend/src/components/flowseeker/exposureBadges.js` — KIND_TITLES dict + `exposureKindOf(rowOrKind)` + `exposureBadgeFor(rule, rowOrKind)` two-arg + `selectExposureBadges(rows)` deduplicate + VEX_WALL fallback reword
- `frontend/src/components/flowseeker/exposureBadges.test.js` — 5 new TDD tests (RED→GREEN)
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` — 1 line: `exposureBadgeFor(a.rule, a)` (was one-arg)
- `frontend/src/components/heatseeker/ExposureStrip.jsx` — 2 call sites upgraded to two-arg + ticker-clear in empty-ticker branch
- `frontend/src/components/heatseeker/ExposureStrip.test.jsx` — 2 new TDD tests (RED→GREEN)

No backend. No App.js. Frontend-only.

## Source verification

### KIND_TITLES content correct (source-verified, not trusted)

PR55's KIND_TITLES dict has 3 entries:

- `VEX_WALL:vex_wall_formed` → "VEX wall formed — concentrated VEX exposure may suppress volatility (heuristic, not a direction call)"
- `VEX_WALL:vex_wall_broken` → "VEX wall broken — volatility suppression released; regime may shift (heuristic, not a direction call)"
- `GAMMA_FLIP:gamma_flip_approach` → "Gamma flip proximity — price pressing the modeled dealer flip level (heuristic, not a completed regime flip)"

Verified against source:

- `backend/services/exposure_alerts.py:34`: `RULE_VEX_WALL = "VEX_WALL"` ✓
- `backend/services/exposure_alerts.py:189`: VEX events use `kind` field like `"vex_wall_formed"` / `"vex_wall_broken"`; `events_to_alerts` line 191: `"key": f"exposure:{kind}:..."` — so the feed row `key` field carries the sub-kind, and `exposureKindOf` line 97-100 parses `row.key.split(":")` for `namespace === "exposure"` ✓
- `backend/services/exposure_alerts.py:211`: `"context": {"magnitude": mag, "kind": kind}` — the context dict carries the sub-kind; `persist_alerts` line 872 serializes `a.get("context")` into `context_json` ✓; `exposureKindOf` lines 81-83 check `row.context.kind` first ✓
- `backend/services/exposure_alerts.py:109`: `RULE_CHARM_PIN` for charm events ✓
- `backend/services/flow_alerts.py:826`: `context_json TEXT` column exists in `flow_alerts_daily` ✓ (so `exposureKindOf` `row.context_json` path works for Blademap feed rows)
- `backend/alert_engine.py` (lines 81-94): `ALERT_TYPE_CATALOG` includes `GAMMA_FLIP` as a regime-change alert ✓ — but this fires as `Alert.type == "GAMMA_FLIP"`, NOT as a `flow_alerts_daily` row with VEX_WALL rule. GAMMA_FLIP in alert_engine is a DIFFERENT pipeline. The `GAMMA_FLIP:gamma_flip_approach` KIND_TITLE only applies to exposure_alerts path. No false conflation.

### VEX_WALL fallback honest

Main `d5dbd7d` VEX_WALL title: "VEX wall event of unknown subtype — formed means dealers defending (vol suppression), broken means suppression released and regime may shift (heuristic, not a direction call)"

PR55 VEX_WALL fallback title: "VEX wall event of unknown subtype — formed means dealers may be defending a volatility-suppression level (heuristic), broken means the suppression has released (heuristic); the feed carries no formed/broken split"

PR55's version fixes the "carriers no formed/broken split" claim — the feed row `key` field DOES carry the sub-kind (`exposure:vex_wall_broken:...`), and `context_json` carries `{"kind": "vex_wall_broken"}`. So the fallback is honest: "the feed carries no formed/broken split" was false in main; PR55 corrects it.

### Two-arg call sites correct

- Blademap `FlowseekerProBlademap.jsx` line 2001: `exposureBadgeFor(a.rule, a)` — `a` is the conviction-feed row from `/api/flowseeker/alerts/feed`. The row carries `key` field (verified: `a.key` used at line 1983 as React key) and `context_json` (verified: `flow_alerts_daily` has `context_json` column, line 826 of `flow_alerts.py`). ✓
- ExposureStrip: `exposureBadgeFor(row?.rule, row)` — `row` is the feed row from `/api/flowseeker/alerts/feed?ticker=X`. Same shape. ✓

### TDD tests honest (Red→Green verified at exact head)

New tests in `exposureBadges.test.js`:
- "broken VEX rows describe released, not defending, walls" — `exposureBadgeFor("VEX_WALL", {key: "exposure:vex_wall_broken:SPY::65000"})` → title contains "released", not "defending"
- "gamma-approach rows do not claim a completed regime flip" — `exposureBadgeFor("GAMMA_FLIP", {context_json: JSON.stringify({kind: "gamma_flip_approach})})` → title contains "pressing", not "regime change"
- "event kind resolves from context, context_json, or feed key" — 3 assertions on `exposureKindOf`
- "VEX_WALL without a kind stays honest about the unknown subtype" — kindless VEX_WALL row gets fallback title
- "selectExposureBadges prefers broken wall over formed one" / "prefers explicit approach kind over kindless row" / "drops unknown rules and keeps one badge per rule"

New tests in `ExposureStrip.test.jsx`:
- "clearing the ticker removes the previous ticker badges" — ticker change to empty clears badges (D1 stale-badge fix carried from PR48)
- "passes the feed kind through to badge copy" — VEX_WALL broken row renders with "released" not "defending"

All 5 new tests + 2 ExposureStrip tests verified Red→Green by the PR author's commit history: `0a5a55b` commit message states "5 new tests: RED before, GREEN after". Agent-4 re-verified green at `7481f72` via the focused 60/60 reproduction above (which includes all 7 new tests).

## Fresh reproduction at exact head

Detached worktree `/Users/nav/Documents/GitHub/floww-worktrees/pr48-semantic-main-v1` at `7481f727cdbf826145190a6ada2668666c34a191` (matches PR head `7481f72`).

```text
cd frontend && CI=true npx craco test --watchAll=false --runInBand \
  --testPathPattern='exposureBadges|ExposureStrip|FlowseekerProBlademap|SkylitDashboard'
PASS src/components/flowseeker/exposureBadges.test.js
PASS src/components/flowseeker/FlowseekerProBlademap.test.jsx
PASS src/components/heatseeker/ExposureStrip.test.jsx
PASS src/components/heatseeker/SkylitDashboard.test.jsx
Test Suites: 4 passed, 4 total
Tests:       60 passed, 60 total
Time:        1.145 s
Ran all test suites matching /exposureBadges|ExposureStrip|FlowseekerProBlademap|SkylitDashboard/i.
```

60/60 green. Focused suites only — covers the PR payload exactly.

## Verdict

**APPROVED.** Contract delivered: kind-aware badge copy (PR50 content) now on current main; VEX_WALL/GAMMA_FLIP titles distinguish formed/broken and approach/completed-flip; two-arg call sites in Blademap + ExposureStrip; `selectExposureBadges()` deduplicates; ExposureStrip ticker-clear carried from PR48. Source verification confirms KIND_TITLES content matches backend producers. TDD evidence Red→Green. Focused reproduction 60/60 green.

**Watch items (not blocking):**
1. Full-suite 66/531 green NOT yet run at this head (would re-confirm no collateral regression). CI backend-tests PENDING at PR head.
2. The `GAMMA_FLIP:gamma_flip_approach` KIND_TITLE only applies to the exposure_alerts path. alert_engine's `GAMMA_FLIP` regime-change alert is a separate pipeline with its own badge path (alertEngineBadges.js, PR49). No conflation in code — but worth a doc note that the two-arg `exposureBadgeFor("GAMMA_FLIP", row)` on a alert_engine-sourced row would NOT find a KIND_TITLE (exposure_alerts rows carry `kind: "gamma_flip_approach"` in context; alert_engine rows carry `alert.type === "GAMMA_FLIP"` not `context.kind`). This is correct behavior, not a defect — the title is specific to the exposure path.

No GitHub mutations (Nav-gated). No merge (open PR).

## Receipt

- Exact head: `7481f727cdbf826145190a6ada2668666c34a191`
- Focused reproduction: 60/60 green (4 suites)
- Source verification: KIND_TITLES content matches backend producers (exposure_alerts.py lines 34, 109, 189, 191, 211; flow_alerts.py line 826; persist_alerts line 872)
- Full-suite 66/531: UNVERIFIED at this head (CI backend-tests PENDING; agent-4 did not run full suite)
- Actor: agent-4 (review); PR author: Nav/mrbeast1179-sketch
- Timestamp: 2026-09-10 UTC
