# Spark 1.3 prompt — recovery package bootstrap

This is the entry point for the Floww recovery package.

Read this file first, then read the four agent prompts:
- `agent-1.md`
- `agent-2.md`
- `agent-3.md`
- `agent-4.md`

Package root:
`/Users/nav/Documents/GitHub/floww-worktrees/recovery-control-plane-v2`

Run-state root:
`/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2`

Core docs:
- `docs/plans/2026-09-06-four-agent-run/README.md`
- `docs/plans/2026-09-06-four-agent-run/HARNESS-V2.md`
- `docs/plans/2026-09-06-four-agent-run/RECOVERY-QUEUE.md`
- `docs/plans/2026-09-06-four-agent-run/run-state-v2.json`
- `docs/plans/2026-09-06-four-agent-run/GSD-PASSES.md`
- `docs/plans/2026-09-06-four-agent-run/TASK-CARDS.md`
- `docs/plans/2026-09-06-four-agent-run/EVIDENCE-INDEX.md`
- `docs/plans/2026-09-06-four-agent-run/evidence/`

Rules:
- One task per builder at a time.
- Boot artifact first, then work, then checkpoint.
- Never widen a lease silently.
- Never claim a merge, deploy, or external witness you did not observe.
- Save evidence to the lane receipt directory.
- When credits are low, stop after a clean checkpoint and commit/push.

Verification before use:
- `git fetch origin`
- re-read `origin/main` merge state: PR29/30/31 merged, PR28 still open/escalated at 18b10b5, PR32 open at 9289775 (scope call pending — evidence/T1-SPLIT-ANALYSIS.md)
- re-read `astra/f0-honesty-backend` head: f880971, NOT merged to main, 14 commits on feature branch
- re-read `agent3/t1-scroller-fix-v2` head: 9289775, clean, PR32 open
- H1 ACTIVE: `astra/h1-strike-truth` 573fe8c (= remote), red fixture landed
- re-read `architect/20260906-recovery-control-plane-v2` actual head (`git log --oneline -1`): recovery package committed, remote-backed
- confirm `phase9/g1-reads-witness` dirty files are NOT your lease and predate this session
