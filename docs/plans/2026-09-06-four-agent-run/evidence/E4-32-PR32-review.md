# E4-32 — PR32 review at current head `c17fc61` → REWORK (2 blocking)

Reviewer: architect lane (Agent-4 mission `harness/agent4-e432-review.md`).
Date: 2026-09-07. Head re-fetched live before and during audit: still `c17fc61`.
No GitHub mutations made (no comment, no labels, no merge) — Nav-gated PR; receipt only.

## Head pinning

- PR: mrbeast1179-sketch/floww#32, `agent3/t1-scroller-fix-v2` → `main`
- head `c17fc61f9c822a1fdc4e46d58229e3f22db37647`, base `e68bdb5` (= origin/main tip)
- Merge-base: `5ab259f`. Mergeable: MERGEABLE. Merge state: BEHIND.
- Linked issue: NONE (`closingIssuesReferences: []`, no `Closes #` in body).

## CI at head (merge commit `55cae55`)

- `ruff` (required): FAIL — 5 errors, all in 2 branch-payload files:
  `routes/market_data.py:18` F401 (`Request` imported but unused — added by this
  PR's own diff, usage never added), `:113`/`:156` I001, `server.py:9`/`:20` I001.
- `backend-tests` (required): FAIL — pytest shard itself passed 11/11; the job fails
  on its lint gate with 6 errors (the 5 above + SIM105 market_data.py:156, UP017
  server.py:20 under the wider ruleset).
- `frontend-build`: PASS. `docker-build`: skipped.
- Local confirmation: `ruff check backend/routes/market_data.py backend/server.py`
  → 5 errors at `c17fc61`; **All checks passed** at `e68bdb5`. (Local ruff 0.15.14;
  counts match CI exactly for the ruff job.)

## Diff composition (three-dot `5ab259f..c17fc61` — 23 files, NOT 35)

Two-dot-vs-main overcounts: `TradeEntry.jsx` M, `tradeMath.js` M, silence-gate Ds etc.
are main-side-only (PR29/30/31) and survive the merge untouched. Zero files were
touched on BOTH sides (verified per-file) → merge is textually clean.

Branch payload layers:
- G1-base divergence (pre-existing, NOT agent-3): Discord backend
  (`discord_harness.py` A, `discord_ops.py`, `discord_bot.py`, 6 discord test files),
  `/tickers/all` endpoint + finnhub/cvserver/market_data/server changes, LEDGER, kanban.
- Agent-3 T1 5 commits (9 files): `tickerUniverse.js` A (57-line pure contract module —
  clean), `tickerUniverse.test.js` A, `SkylitTickerBar.contract.test.jsx` A,
  `SkylitTickerBar.jsx` / `SkylitControlBar.jsx` / `App.css` M, `App.js` M (28 lines,
  surgical: 3 inline universe-spreads replaced by one helper, order-preserving popular
  dedup, normalized wrap arrows; free-text submit + 12-cap preserved), `.gitignore`,
  `yarn.lock` (4270-line churn inside `8e30a60`, unjustified — advisory).

## Exact-head reproduction (detached worktree `/tmp/e432-c17fc61`, removed after)

- `yarn install --frozen-lockfile` → exit 0.
- Focused: `craco test tickerUniverse|SkylitTickerBar.contract` → 2 suites / 16 tests pass.
- Touched areas: `SkylitControlBar|SkylitTickerBar|tradeMath|TradeEntry` → 4 suites /
  49 tests pass (no TradeEntry suite exists at this head — predates PR29).
- Full: `craco test --watchAll=false` → **61 suites / 469 tests pass** (PR body claims
  468 with boxes unchecked; reviewer-observed count is 469).

## Findings

- [CI] Required `ruff` fails at head (5 errors, branch-attributable, main is clean).
  Same root fails `backend-tests` job gate. Trivial fix: drop unused `Request`,
  `ruff check --fix`, resolve SIM105/UP017.
- [SCOPE] No linked issue, so no O/X contract exists to approve against. Title/body
  sell T1-only; payload ships a Discord/backend delta with it. G1-SALVAGE already
  requires exactly this split. Either rebase a T1-only branch (9 files) or link an
  issue authorizing full scope — reviewer cannot approve scope the contract doesn't cover.
- Advisory: BEHIND main; `App.js` touch is surgical but the CLAUDE.md frozen-file
  waiver is still unrecorded; `yarn.lock` churn should be dropped; PR test-plan boxes
  unchecked (reviewer reproduced 469 green independently).

## Verdict

**REWORK, not merge-ready.** T1 core itself is sound (contract green, App.js surgical,
frontend-build green, full suite 469 green) — after the lint fix + a scope decision
(split vs authorized full scope), this is approval-ready without re-audit of T1 behavior.
Prescribed loop action when a loop runner takes it: sync issue outcomes pending (no
linked issue — none to sync), apply `gsd:rework`, no verdict comment repost needed
beyond this receipt until head or scope changes.

## Supplement — CI on lint-fix head `9289775` (same session)

- `ruff`: PASS. `frontend-build`: PASS.
- `backend-tests`: 4931 passed / **1 failed** —
  `test_anomaly_training.py::TestTraining::test_overfit_small_dataset`
  (loss=0.0131 vs 0.01 threshold). Main-side test file, untouched by this PR;
  rerun locally on branch HEAD: **1 passed**. Verdict: flaky ML-convergence
  threshold (env/seed-sensitive), not payload-attributable. Prescription: CI
  re-run; do NOT retune the test to chase green.
- [CI] finding from the original verdict is therefore resolved subject to a green
  re-run; [SCOPE] (split vs authorize) remains the live blocker.

## Limitations

No browser/live witness (mocked/fixture only). Backend full suite not run locally
(CI shard 11/11 cited). No second full-suite run post-any-fix (no fix applied by
reviewer — review never repairs).
