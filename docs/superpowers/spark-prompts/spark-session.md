# Spark 1.3 prompt — generic session startup

Use this when you need a reusable session bootstrap that is not agent-specific.

1. Read the recovery package root:
   `/Users/nav/Documents/GitHub/floww-worktrees/recovery-control-plane-v2`
2. Read the run-state manifest:
   `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2`
3. Identify the active lane, task card, and checkpoint you are responsible for.
4. cd into the matching worktree.
5. Re-validate `git status`, `git log`, remote state, and the task card before
   any new investigation.
6. Write or re-validate `boot.json` in the external lane directory before you
   begin work.
7. Do the smallest coherent unit that admits one clear next command.
8. Checkpoint after every red test, green test, commit, push, blocker, and at
   least every 15 minutes of meaningful work.
9. When the unit is green, commit and push; leave unfinished work on its branch
   with a precise next command.
10. Never claim a merge, deploy, or external witness you did not observe.

Lane directories:
- architect: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/platform`
- backend: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/data`
- frontend: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/frontend`
- proof: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/proof`
