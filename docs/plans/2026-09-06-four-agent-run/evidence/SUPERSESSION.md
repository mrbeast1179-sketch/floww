# Supersession log — agent-4 receipts

Agent-4 evidence discipline: a receipt supersedes older ones when the exact head it covered has moved AND the verdict or the canonical branch/state has changed. Remove superseded observations; never claim a stale receipt is current.

## Entries (newest first — top supersedes lower for the same PR/head)

- E4-55 (2026-09-10): PR55 `architect/pr48-semantic-main-v1` @ `7481f727cdbf826145190a6ada2668666c34a191`. APPROVED at exact head. 60/60 focused (4 suites: exposureBadges, ExposureStrip, FlowseekerProBlademap, SkylitDashboard) + full-suite 66/66 (531/531) green. Source-verified KIND_TITLES content (exposure_alerts.py lines 34/109/189/191/211; flow_alerts.py line 826/872; events_to_alerts line 211 sets `context: {kind: ...}`). PR55 MERGED (`mergedAt` 2026-09-10T02:44:15Z, merge commit `7a0a16aed` verified in git). Receipt: `evidence/E4-55-PR55-kind-aware-rereview.md`. Status: CURRENT CANONICAL for PR55.
- E4-49 (re-verified 2026-09-09): PR49 `a3/alert-engine-badges` @ `8ed71c2857030fc2e132c160e4b65763d175379d`. APPROVED-conditional (29/29 green, MERGED `480e953`). Wiring gap holds (1c mapper unrendered — no UI call site for alertEngineBadges.js in main `2c33de0`). Receipt: `evidence/E4-49-PR49-review.md`.
- E4-48d (2026-09-09): PR48 `a3/alert-surfacing` @ `2f57bea3d56a075692339051525cb73d97d99513`. APPROVED at E4-48b level (49/49 green; clean merge to main at review time; UNSTABLE/behind main — needed rebase). Superseded by PR48 MERGED (`12c53d8` 2026-09-09T23:19:09Z, merge commit `12c53d88d431880d87a688ffc072bbb586af770b`). The head-motion analysis (73533e1 → 2f57bea3d, 5 agent-3 commits) remains historically accurate and is preserved in E4-48d. Verdict stands: APPROVED. Receipt: `evidence/E4-48d-PR48-rereview.md`.
- E4-48c (superseded 2026-09-09): historical snapshot at `73533e1` (PRE-PR51 main `d4a5b1f`). Captured the now-superseded head before PR48 moved to 2f57bea3d. Reception note (E4-48c-observation.md): supersession annotation added; the overlap-check conclusion (no file overlap between PR48 agent work and PR51 main) remains valid and is carried forward. The 73533e1 head is VOID. The file `evidence/E4-48c-observation.md` was REMOVED (commit 2039a12, superseded). The receipt `evidence/E4-48c-PR48-50-rereview.md` remains in archive as historical evidence but is superseded by E4-48d.

## What this replaces

- Prior claim (now VOID): "KIND_TITLES is in main; merge as-is delivers everything." Verified FALSE: `origin/main` exposureBadges.js (verified at `2c33de0`) has 0 occurrences of KIND_TITLES; KIND_TITLES exists only in `origin/a3/pr48-semantic-fixes` (`f7bc499ea`). PR55 (`7481f72`, `mergedAt` 2026-09-10T02:44:15Z) is the canonical current-main port of that content.
- Prior claim (now VOID): PR48 at `81255b886` — that head is gone (orphaned merge commit `81255b8`). PR48's canonical remote HEAD at review time (`2f57bea3d`) is superseded by the merged `12c53d8`; PR55 delivers the kind-aware content onto current main.
- Prior claim (now VOID): PR49 at `6387f13` — that head superseded by `8ed71c2`; PR49 is MERGED (`480e953`). The "DIRTY, needs rebase" verdict is superseded; the APPROVED-conditional verdict (wiring gap holds) stands.

## Verification artifacts (not replaced)

- E4-48d receipt (`evidence/E4-48d-PR48-rereview.md`): head-motion section, source verification for VEX_WALL/GAMMA_FLIP titles + D1 mechanism, merge-readiness confirmation against `2c57bea3d..origin/main`. Not overwritten.
- E4-55 receipt (`evidence/E4-55-PR55-kind-aware-rereview.md`, new at this session): exact-head reproduction (worktree `pr48-semantic-main-v1` at `7481f72`), 60/60 + 531/531 green, source verification, verdict APPROVED, watch items (wiring gap; full CI pending at review time — now green per `mergedAt`), provenance note.
- E4-48c-observation.md and E4-49c-observation.md: REMOVED (commit 2039a12, superseded); historical notes preserved in this file.
- RECOVERY-QUEUE.md + agent-4.md + GSD-PASSES.md + run-state-v2.json: updated by agent-4 to reflect PR48/49/54/55/56/60 states (commits 2af785a, 2039a12, e4e15e9, c4356d0).
