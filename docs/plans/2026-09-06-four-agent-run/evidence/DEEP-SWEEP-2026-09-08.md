# Deep sweep — whole-repo audit 2026-09-08 (main `dea655a`)

Method: ancestor analysis on all 61 remote refs, patch-id content proof,
import-graph sweeps (2 subagents), live test baselines, clock-patch repros.
Azure excluded per owner order.

## Branch verdicts

- MERGED (in main, verified): PR28/29/30/31/33/34/35/36 + flowseeker lanes.
- DELETED 2026-09-08 (proven superseded, content in main or archive):
  `astra/a3-conviction-wiring`, `astra/d7-contract-parity`,
  `astra/p1-silent-except`, `astra/x1-tradeentry-journal` (product commits
  patch-identical to merged heads; doc tails in `archive/20260907-g1-recovery`),
  `agent3/t1-scroller-fix-v2` (PR32 closed; T1 content in main via PR33),
  `astra/c4-doc-hygiene` (Sep-6 planning status scratch; essence: ROADMAP 6.4
  box honestly OPEN, budget landed+wired — both true on main today).
- KEPT deliberately: `archive/*`, mypy/feature/audit/backup lanes (historical),
  `phase9/g1-reads-witness` (active canonical branch), `phase9/g3-paper-loop`
  (G3 salvage source), `heatmap-agent5`/`other-lanes-artifacts` (knowledge
  source for backlogs below), `agent1-architect`/`agent4-eval` (history).

## Rescue backlogs (assessed, NOT auto-merged — each needs product sign-off)

- G3-SALVAGE (`phase9/g3-paper-loop`, 8 commits): Discord paper-loop fixes
  (approve-unavailable, U3 contract, reconcile fill, venue errors, approve
  loop) + counters. Needs: split from ledger docs, offline GATE-2 proof,
  external witness (guild/channel, non-admin help, paper approve/fill/close).
- SWARM-SIZING (`phase9/other-lanes-artifacts`): `swarm_risk.py` (432) +
  `sta_pairs.py` (505) + `wb_wti_vol.py` (245) + 35 tests. Status: UNWIRED
  (zero references anywhere) and BROKEN (`from backend.bs_greeks import
  norm_cdf` — symbol does not exist on main; main uses scipy norm).
  Repair spec: scipy norm.cdf, drop `backend.` prefix, product decision on
  wiring (routes/server), run 35 tests, ruff, PR.
- Panels (`Wtipanel`/`RussellPanel` in same branch): DELIBERATELY deleted by
  lane per ROADMAP ("already deleted by lane") — not missed work. Closed.
- O-2/O-4/O-5, P2 upgrades, P6/P7: see RECOVERY-QUEUE remaining table.

## Dead code policy (this sweep)

- DELETED (PR38): `Movers.jsx` (dup of App.js local, zero refs/tests),
  `finnhub_api.py` (176-line unwired shim; live impl `finnhub_client.py`).
- FIXED (PR37): GEX date-string crash (`_parse_expiry`, unskipped linearity
  pin, golden oracle green). FIXED (PR38): kanban datetime bug (un-xfailed).
- KEPT: entry-point scripts (collector_service, ml_pipeline, 21 train/backtest
  one-offs — run directly, never imported), tested-but-unwired modules
  (causal/*, memory/*, rl/*, flowseeker helpers — tested code is not dead
  code; prior ROUND10_DEAD_CODE_AUDIT concurs), fixture JSONs (tiny).
- Remaining skips (all legitimate): live-service/network skips (heatseeker,
  test_api, clone-extract, yoptions conditional), 1 stateful skip
  (ingestion timing). Zero skipped frontend tests, zero TODOs in frontend.

## Baselines (main `dea655a`, this session)

- Backend: **5048 passed**, 64 skipped, 1 xfailed (3 pre-existing env/flaky
  deselects: 2 LLM-key tests, 1 ML-threshold flake). Ruff clean.
- Frontend: **62 suites / 479 tests**, all green.
- Canonical G1 worktree dirt + untracked .planning docs: pre-existing, untouched.
- Worktrees pruned: /tmp/e432, /tmp/w-f0*, /tmp/w-d7 (all pushed before removal).
