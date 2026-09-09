# E4-51 — Agent-4 post-merge review, PR51 agent2-signal-truth @ b1fad09

## PR
[#51](https://github.com/mrbeast1179-sketch/floww/pull/51) — `fix(agent2): signal-truth repair — charm type normalization + liquidity interval flow`

- State: MERGED to main as `d4a5b1f` (2026-09-09T05:03:29Z), 0 reviews on record. This is a POST-MERGE audit — no merge call involved.
- Head: `b1fad090a86355e391378ae7fc807c7ca160ef59` (1 commit on `56cfff2`)
- Payload: 3 files, +115/-8 — `backend/advanced_analytics.py` (+15/-7),
  `backend/services/liquidity_state.py` (+29/-1), `backend/tests/services/test_signal_truth.py` (new, 79 lines)

## RED/GREEN (both reproduced locally, exact commits)

Detached worktree `/tmp/agent4-pr51`:

- RED at `56cfff2` (new test file copied in): **4/4 FAIL** —
  `test_charm_uppercase_type_matches_lowercase`,
  `test_charm_unknown_type_falls_back_to_scalar`,
  `test_liquidity_feed_uses_interval_flow`,
  `test_liquidity_feed_interval_dollar_volume`.
- GREEN at `b1fad09` (test file as committed): **12/12 PASS** (4 signal-truth
  + 8 neighbors in test_charm_vec_wiring / test_liquidity_stress).

(One procedural note: an intermediate run appeared to fail at `b1fad09`
because `git checkout` had aborted on my untracked test copy — HEAD was still
`56cfff2`. Caught by re-reading `git rev-parse HEAD`, removed the copy,
checked out clean, re-ran. The numbers above are from verified HEADs.)

## Fix review

FIX 1 — charm type normalization: correct. Old code appended every
validity-passing row to the vec arrays with `_Sgn` from exact `== "call"`,
then kind passes filtered by exact match — so `"CALL"`/`"PUT"`/None matched
neither pass, contributed 0.0, yet sat in `_Idx` → vec-done → scalar skipped:
silent zero, confirmed by reading. New code normalizes once
(`strip().lower()`), `continue`s unknown types out of ALL vec arrays (never
vec-done), and the scalar fallback handles them with legacy semantics
(`bs_charm(kind=raw)`, `else -1.0` sign — same as all-scalar mode, pinned by
`test_charm_unknown_type_falls_back_to_scalar` asserting vec+fallback EQUALS
scalar-only). "Legacy semantics preserved" is true by construction + test.

FIX 2 — liquidity interval flow: correct. `feed()` now differences per-ticker
cumulative snapshots (`max(0, cur - last)`), first snapshot seeds baseline
with no push, non-finite/negative inputs return WITHOUT poisoning the
baseline (`last` untouched — checked). Reset days clamp to 0 and the
estimators' zero-guards skip them. Documented in the docstring. Tests pin
interval semantics (Kyle x = +1.0 not +1/3; Amihud DV = 50*102 not 300*102).

## Verdict

**APPROVED (post-merge).** Both fixes correct, RED/GREEN proven at exact
commits, tests pin the contracts. No defects found. Merge already landed;
nothing to hold. Watch item (non-blocking): `max(0,·)` clamping also masks
legit exchange restatements — accepted tradeoff, estimators skip zeros.

Receipt: `evidence/E4-51-PR51-signal-truth.md`. No GitHub mutations.
