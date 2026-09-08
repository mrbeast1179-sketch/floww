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
- `origin/main` was `dea655a` (all five take-over PRs merged, zero open PRs)
- No ungated builder work remains — see RECOVERY-QUEUE.md remaining table;
  do not invent work to look busy
- `phase9/g1-reads-witness` dirt predates this program — NOT your lease
