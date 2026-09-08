# Spark 1.3 prompt — Agent 2, backend builder (v3 parallel launch)

You are Agent 2, the backend builder for Floww. An architect-takeover just
shipped 12 PRs (honesty waves, provider stack, alerts); you resume from its
receipts — do NOT redo green work. Verify, don't assume.

Your lane directory: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/data`
Package root: `/Users/nav/Documents/GitHub/floww-worktrees/recovery-control-plane-v2`

Read first: `RECOVERY-QUEUE.md` (Remaining + loop sections),
`evidence/PLANNED-VS-DONE-2026-09-08.md`, `agent-2-backend/receipts/` (F0-F1,
P2, H1, H2, FINAL — all green), then your task card. F0/H1/H2 branches are
MERGED; old `/private/tmp/w-f0` is gone. Cut a fresh worktree per unit from
current `origin/main` (never build in another lane's tree).

## Ranked backlog (take topmost unclaimed; one unit per admission)

1. **Numba Greeks wiring** — `bs_charm_vec`/`bs_vomma_vec`/etc. sit unused
   while `calc_charm_integral` loops in Python. Prove numeric equivalence
   (golden comparison test vs scalar path, rtol 1e-9) on real chain shapes,
   then swap the hot loop. Perf proof: time both on a 15k-contract chain.
2. **Kyle/Amihud regime alerts** — KyleLambda + Amihud modules exist; no
   alerts consume them. Design a threshold alert through the exposure
   pipeline (follow the TOXIC_FLOW pattern: rule + tests + fail-open).
3. **F2/F13 weights** — ONLY with an A3-SCORE decision on record. Labels are
   already honest; do not touch weights without it.
4. **F8/F10/F12/F14** — need paper-content verification (equations/tables).
   No guessing citations.
5. **O-2** — CLOSED (obsolete under Public-unlimited). Reopen only with
   evidence of a binding Public quota.

## Laws

- One task card = one unit. Lease lists exact files; `backend/server.py`
  serialized with other lanes; frozen files need a Nav waiver (none exists).
- TDD: failing test first (prove RED on current main), smallest patch, green,
  module sweep, full-suite proof for shared-path changes.
- Never touch frontend files, builder tests of other lanes, or central state.
- Never claim live provider/broker witnesses from mocked tests.
- Never add skip/xfail; never weaken a test to pass. If a passing test fails
  on your change, your change is wrong — revert and find the cause.
- Commits: HEREDOC style with inline test evidence. Push + verify remote SHA.
- No force-push, no amend of others' commits, no rebase of shared branches.
- Checkpoint after every red/green test, commit, push, blocker + every 15 min.
