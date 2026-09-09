# Agent-2 signal-truth repair receipt

Date: 2026-09-09 ET
Worker: agent-2-backend
Branch: astra/agent2-signal-truth @ b1fad09 (from origin/main 56cfff2)
Remote verified: origin/astra/agent2-signal-truth == b1fad09

## Bugs fixed (PR47 runtime contracts, math tests were green)

1. Charm vec silent-zero on non-lowercase types
   (backend/advanced_analytics.py, calc_charm_integral vec path).
   Root cause: exact == "call"/== "put" matching; "CALL"/None matched
   neither numba pass, contributed 0.0, yet marked vec-done so scalar
   fallback never ran. Fix: normalize strip().lower() once; unknown
   types route to scalar fallback (legacy semantics preserved).

2. Liquidity estimators fed cumulative chain volume as interval flow
   (backend/services/liquidity_state.py feed()). Kyle x was the
   cumulative share (near-constant); Amihud DV was cumulative
   dollar-volume (grows all day). Fix: per-ticker baseline differencing;
   first snapshot seeds baseline (no push), later snapshots push
   max(0, cur - last). Estimator zero-volume guards absorb resets.

## Proof

- New tests backend/tests/services/test_signal_truth.py (4 tests):
  failed 4/4 pre-fix (RED), pass post-fix (GREEN). No skip/xfail
  scaffold in the file (grep count 0).
- Focused: test_signal_truth + charm_vec_wiring + liquidity_stress +
  exposure_alerts + conviction_exposure_wiring = 41 passed.
- Adjacent regression: kyle_lambda_streaming + gamma_flip_alerts +
  exposure_adjustment_gate + blademap_conviction +
  squeeze_exposure_profile = 65 passed.
- Ruff clean on all 3 touched files.

## Not touched

- codex/signal-truth-repair worktree/branch (control-plane lane): clean,
  no commits ahead of main — left alone.
- recovery-control-plane-v2 dirty docs (GSD-PASSES.md 220-line rewrite +
  RECOVERY-QUEUE.md P2 softening): another lane's in-flight work —
  not committed, not reverted.
- dependency-p2-v1 replay branch: control-plane lane, left alone.
- P2 upgrades, P6 rotation, P7 Oracle, F-weights/papers: Nav-gated,
  unchanged standing.
