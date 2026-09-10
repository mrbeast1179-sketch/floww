# Agent-1 review receipts — Wave 1, 2026-09-10 UTC

Exact-head verdicts. A head move voids the verdict for that PR.

## PR57 (agent2/wave1 @ 0b05229) — REWORK

Production delta in-lease and sound: momentum/volume inputs forwarded to
detectors (alert_engine.py +4/-4 param, routes/alerts.py strike-map and
momentum coercion). No threshold or scoring change.

Blocker is test isolation, not product behavior:

- CI full-suite: TestAlertsSummaryEmptyState::test_empty_state_returns_zeros
  fails, assert 17 == 0 (run 34429114597; 1 failed / 5064 passed).
- Local repro at detached 0b05229: the plumbing file plus the summary file
  together -> 1 failed, 10 passed; each file alone passes.
- Root cause: test_alert_plumbing.py is new in this PR and uses a
  module-scoped TestClient against the process-global engine; posted
  snapshots persist into the pre-existing empty-state test.

Repair condition: isolate the plumbing tests (function-scoped client with
engine reset, or unique tickers plus cleanup) so the pair passes; then
green CI at the new head. Verdict posted on the PR. Never weaken the
empty-state test.

## PR58 — verdict withheld (head moved 1c5f886 -> a3fe6db, CI churning)

- At 1c5f886: backend red on
  test_anomaly_training.py::TestTraining::test_overfit_small_dataset
  (loss=0.0105). Local: passes 3/3 in isolation and 24/24 with the PR's own
  reconcile tests. Payload (routes/alpaca.py + reconcile test) cannot
  plausibly move ML overfit loss. Classified environmental flake.
- Owning lane pushed a3fe6db (drift-check endpoint + test, +177 lines) while
  Agent-1 was reproducing. Stale-run rerun by Agent-1 targets the old head
  and is meaningless for the gate; the lane's own run plus an Agent-1
  rerun of 34430761740 (accepted, pending at a3fe6db) will decide the new
  head. No merge until green CI exists at the current head.

## PR59 (agent2/data-contract @ 1c8a827) — APPROVED, integrating

Additive-only: event_envelope.py (123) + test (100), zero deletions. No
secrets, live orders, vendor SDK, or licensed rows (synthetic fixtures).
Exact-head CI green (backend 11m48s, frontend, Ruff). Branch updated to
main via a364128 (5 PR55 frontend files only, zero payload drift); CI
re-running. Merge iff green at a364128.

## PR60 (agent2/eval-harness @ c8ca7c4) — APPROVED, queued

Additive-only: eval_harness.py (88) + test (95). Exact-head CI green
(backend 13m16s, frontend, Ruff). Needs main-update + CI, then merge.
Next after PR59 lands.

## PR61 (agent2/vex-parity @ dc01004) — APPROVED (payload), queued

Docstring-only production delta (bs_greeks.py +6, gex_vex_calculator.py +5)
documenting the GEX-parity display scale vs per-unit-sigma scale, plus a
64-line parity test. No behavior change; dual-scale convention preserved.
Exact-head CI green (backend 11m34s, frontend, Ruff). Needs main-update +
CI, then merge. Queued behind PR60.

## PR62 (agent2/composite-truth @ db77e38) — APPROVED, queued

4-line docstring correction (formula already 5-component in code at base
in both mirrored modules — verified) + 40-line parity guard. No behavior
change. Exact-head CI green (backend 12m37s, frontend, Ruff). Needs
main-update + CI, then merge. Queued behind PR61.

## PR63 (agent2/calib-registry @ 2c63666) — verdict withheld (flake rerun)

Additive-only (2 new files, +187/-0). CI backend red on
test_greeks_api.py::TestPerformance::test_latency_under_50ms_all[SPY]
(2974.9ms vs 2500ms wall-clock budget under load) — cannot be caused by an
additive-only payload. Classified environmental; Agent-1 reran the failed
workflow (in_progress at same head). Merge iff the rerun goes green; any
second failure needs base-rate evidence before another rerun.

## Integration order (disjoint payloads, branch protection needs fresh base)

PR59 -> PR60 -> PR61 -> PR62, each: merge main (fast-forward push, no
force, never touching lane worktrees) -> green CI at merged head -> merge.
PR57 needs a repair push first. PR58/PR63 need green reruns first.
