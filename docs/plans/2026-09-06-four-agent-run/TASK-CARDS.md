# Initial task cards — SUPERSEDED 2026-09-08

> All three cards below are CLOSED. F0-F1 merged as PR35; RH-1 superseded by
> shipped PR33/PR34/PR36; E4 superseded by per-PR receipts (E4-29/30/31/32/44).
> Live cards live in `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/task-cards/`
> (`PR44-g3-witness.md`, `Nav-gated-decisions.md`). Do not admit from this file.

Snapshot note: these initial task cards record the Sep-6 launch boundary at `5b9d9a9`. Main has since advanced to `56cfff2` (PR28–47 merged, PR44 merged 2026-09-08T11:48:51Z). Do not admit from this file — re-fetch at every launch.

These cards are launch inputs. Agent 1 revalidates the base, incumbent release and exact files before granting ACTIVE. A READY card or existing WIP is not a running worker. Task evidence goes to the lane's external receipt.

## F0-F1 — complete preserved citation/proxy correction

### Why

The preserved F1 patch removes a fabricated citation from the docstring but the runtime interpretation still claims the attribution. User-facing scientific claims must agree with the actual theta-derived calculation.

### Outcomes

- O-1: charm_hedging_pressure documentation removes the fabricated SSRN/author claim and only documents real arguments.
- O-2: returned interpretation labels the calculation as a heuristic/proxy and removes the unsupported attribution.
- O-3: existing numeric behavior, signal identifiers and function signature remain unchanged; focused behavioral regression and relevant module tests pass.

### Exclusions

- X-1: no F2/F3/F4/F7/F13 changes in this unit.
- X-2: no scoring weights, new theory, provider, frontend, frozen file or schema change.
- X-3: do not discard existing WIP or stage another author's files.

### Code pointers

Base 5b9d9a96a29951e548e883d108a806b93c2d11a9; worktree /private/tmp/w-f0; branch astra/f0-honesty-backend.
Exact lease: backend/services/gex_paper_accurate.py and backend/tests/services/test_honesty_f0.py.
Read .planning/eval/phase-9/fix-queue.md F1 and the preserved diff. Nav's pasted Agent2 F0 assignment and subsequent explicit continuation authorize this existing-service F1 scope, superseding the older Agent2 “new services only” restriction for these two files. Agent1 records this authority in the external task card and verifies no incumbent writer before ACTIVE; no broader waiver is granted.

### Testing notes

From the backend directory, run the actual installed interpreter's pytest on tests/services/test_honesty_f0.py; record version and import root. Run Ruff on the two changed paths from the correct directory. Preserve a valid behavioral red for the remaining runtime claim. Compare representative numeric outputs and run related gex module regressions; no paid provider calls.

### Manual walkthrough

Call the pure helper with the regression fixture; inspect signal, numeric fields and interpretation. Compare before/after output, with only the intended explanatory text changed.

## RH-1 — recent Heat/ticker audit

### Why

G1 history contains Discord plus ten Heat/ticker commits through b5f9ae5, including a universe experiment, reversal and later5000-symbol reintroduction. Latest scroller caps are still dirty. The saved audit covers this boundary; a clean integration decision requires its net behavior and any later delta.

### Outcomes

- O-1: record current head/dirty paths and account for all ten product commits through b5f9ae5 plus the latest scroller diff, reusing the saved audit where still current.
- O-2: reproduce or qualify all six questions in RECOVERY-QUEUE and the SCROLL-1 outcomes.
- O-3: produce a minimal split into backend Heat, frontend Heat and ticker/scroller contracts with exact file lists and dependencies.

### Exclusions

- X-1: no product-file writes, checkout switches, commits or pushes on canonical G1.
- X-2: no service restarts, external market calls or new scoring/data semantics.
- X-3: no claim that historical live process/bundle prose proves current deployment.

### Code pointers

Read canonical /Users/nav/Documents/GitHub/floww at actual current head; recorded current head b5f9ae5d99a4d502efdaf1d0c4d8386c2fa9b0d0. RH-1 source audit is complete at this boundary; reuse evidence/recent-heat-audit.md and focus the next discovery unit on the SCROLL-1 decision/acceptance gaps rather than repeating the sweep.
Read new evidence/recent-heat-audit.md if present, SOLSTICE-SCROLLER.md, data_providers.py, server.py, SkylitTickerBar/ControlBar/Dashboard/HeatmapGrid, App.js/App.css and actual Solstice components.
Allowed product files: none. Receipt path: external agent-3-frontend/receipts/RH-1.md.

### Testing notes

Use immutable source snapshots and fixtures; distinguish source findings, deterministic reproductions, tests and browser evidence. Ask for the heavy-test lease before a full suite. Existing audit findings are starting evidence, not grounds to rerun everything.

### Manual walkthrough

Trace a ticker from API response through search, keyboard selection, visible button and Heatmap request; compare mounted Solstice surface to the reported Skylit fix.

## E4 — review existing candidates

### Why

D7 and X1 have clean replacement PRs but remain unmerged. Saved code needs outcome-based review before integration.

### Outcomes

- O-1: resolve current PR/issue linkage, exact full head, current CI and existing trusted verdict.
- O-2: audit every O/X item in the linked contract with evidence at that head.
- O-3: save an independent verdict and limitation list; reuse completed current-head GSD review work.

### Exclusions

- X-1: no feature repair, builder-test changes, commits, pushes or merge.
- X-2: no live provider/broker/message witness from mocked tests.
- X-3: no approval from presence-only checks or advisory CI summaries.

### Code pointers

PR28 issue18 initial head18b10b5601ef0bc0dd27a083d66f2d8ad164665a; then PR29 issue17 head568de16a3d2da32c218660e1007ad89b2d97228f. GSD-PASSES.md gives this session's actual review status. Allowed product files: none.

PR28's current-head pass is now complete and policy-escalated to Nav; next review is E4-29 unless its head/verdict changes before boot.

### Testing notes

Inspect full diff and touched files; verify required checks on the same head. Reproduce targeted contract tests when environment allows and disclose unrun browser/live/manual work. Native GSD review follows its installed playbook and bundled sync scripts; managed proof only writes a local receipt.

### Manual walkthrough

Read the linked issue's exact walkthrough and classify its result as performed, fixture-equivalent or not run. Never infer genuine user actions.
