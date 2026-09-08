# Planned vs done — Sep 6 four-agent package vs Sep 8 reality

Source of "planned": the Sep 6–7 recovery package transcript (GSD passes,
Agent 1/2/3/4 Hermes reports, RECOVERY-QUEUE, TASK-CARDS, run-state-v2).
Source of "done": git history + CI + receipts (this file's claims are all
re-verifiable with `git log origin/main` / `gh pr list`).

## Agent 1 (architect/central) — planned vs done

- Planned: preserve audits, deliver execution package, own task cards. DONE
  (package committed, prompt set current, run-state kept truthful).
- Planned: GSD-8 blocked on X credits. STILL BLOCKED (unchanged, honest).

## Agent 2 (backend) — planned vs done

- Planned: F0 wave (F1/F3/F4/F7, P1/P3/P4, D1–D7) on a feature branch, "force-
  with-lease pushed", merge posture "mechanically mergeable, not verified".
  DONE + EXCEEDED: independently re-verified (151 gate tests green), merged
  as PR35 after fixing a REAL fake-clock bug CI caught. No force-push ever
  happened (reflog: normal post-rebase push; the "force" claim was false).
- Planned: P2 baseline UNKNOWN (pip-audit timed out). DONE: completed via
  uvx (11 advisories, pins untouched, upgrades Nav-gated).
- Planned: H1/H2 as next admissions. DONE: H1 fixture merged (PR34), H2
  O-1/O-3 shipped (PR36), O-2/O-4/O-5 closed/superseded/satisfied with
  recorded rationale (not silently dropped).
- Planned: P6 inventory-only, P7 Oracle offline. UNCHANGED (Nav-gated).

## Agent 3 (frontend) — planned vs done

- Planned: T1 candidate at f89d6ea, PR32 open, "61 suites / 469 tests".
  CORRECTED then DONE: prior review covered stale head 2b594ed; branch
  carried G1 backend scope + failing ruff. Split hunk-level to PR33 (8 files,
  zero riders), fixed lint, merged. Count verified: 62/479.
- Planned: App.js waiver decision (Nav). Done under blanket take-over order
  with surgical scope recorded; STANDING waiver still explicitly ungranted.

## Agent 4 (reviewer) — planned vs done

- Planned: E4-28 escalated, E4-29 approved-pending-merge, E4-30 merged, E4-31
  approved-conditional, PR32 "APPROVED at 2b594ed". CORRECTED: the PR32
  verdict was stale-by-3-commits with no receipt on disk. Re-reviewed at
  current heads throughout (E4-32 REWORK→fixed, E4-44 G3 conditional).
- PR28/29/30/31 all MERGED (escalation was branch-convention policy, no
  defect — human decision supplied under owner order).

## Take-over loop additions (unplanned, owner-ordered)

PR36–46: provider stack (Public-first, 20/hr cvserver cap, deepen, enrich,
strike floor — KYTX live-validated 8 strikes), T2 full universe (IHRT fix),
order-key 401 fix (paper order proven + cancelled), GEX crash fix, kanban
datetime fix, dead-code removal, honesty waves (F5/F6/F9/F11/F15/F17/F19,
F2/F13 labels), VPIN + flip alerts, G3 split (PR44 open), deep sweep,
61-ref archaeology (6 branches pruned with patch-id proof).

## Genuinely not done (gated, with owners)

PR44 review-refresh + external witness (Nav) · O-2/O-4/O-5 specs stay filed
(Nav) · P2 upgrades, P6/P7, Azure secrets (Nav) · App.js standing waiver
(Nav) · GSD-8 credits · G3/swarm admission (Nav) · production cutover
(Nav-coordinated, single-writer) · F2/F13 weights (A3-SCORE) · F8/F10/F12/F14
(paper verification) · E2 chaos matrix (unclaimed).
