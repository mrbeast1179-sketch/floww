# Agent-2 vomma-walls receipt

Date: 2026-09-09 ET
Worker: agent-2-backend
Branch: astra/vomma-walls @ 47401d6 (from origin/main 04605df via PR47)
Remote verified: origin/astra/vomma-walls == 47401d6

## What it is

Vomma (dVega/dVol) wall alerts — vol-convexity concentration, one Greek
deeper than VEX. Same wall semantics (formed/broken), same structural
score scale, heuristic copy with no direction calls.

## Provenance

Found as orphaned in-progress work in the vomma-walls worktree (emission
half + RED test file, untouched 17h, no commits, no remote branch).
Adopted into agent-2 (numba Greeks / exposure-alerts lane) and finished.

## Work done

1. Emission (pre-existing, kept): compute_gex_grid emits vomma_grid in
   the Python fallback path.
2. Emission gap fixed (new): the Rust fast path (_RUST_GEX) returns early
   without vomma_grid (decoder_core predates vomma — verified its output
   keys). The Python layer now merges a vomma section with identical
   fallback semantics (same filters incl. gamma>0, same sign convention,
   same strike-key encoding, same units).
3. Rules (new): RULE_VOMMA_WALL + vomma_wall_formed/_broken events.
   VEX block extracted verbatim into shared _wall_events helper used by
   both sections (VEX behavior unchanged). _WHY copy, alert mapping
   (vomma_ prefix), ticker cache carries vomma_grid.

## Proof

- Adopted test file backend/tests/services/test_vomma_walls.py (6 tests):
  collection ERROR pre-fix (RULE_VOMMA_WALL missing) + emission assert
  failing (Rust path); all 6 GREEN post-fix. No skip/xfail scaffold
  (grep count 0).
- Focused + adjacent: vomma + exposure_alerts + charm_vec + liquidity +
  conviction + gamma_flip + kyle_streaming + exposure_gate + blademap +
  squeeze = 108 passed.
- Ruff clean on all 3 touched files.

## Not touched

- codex/signal-truth-repair, dependency-p2-v1 replay: other lanes.
- Dirty docs in recovery-control-plane-v2 (agent-4 PR48/49 review files):
  not committed, not reverted.
- P2/P6/P7/F-weights/papers, PR48/49 merges, witness gate: Nav-gated.
