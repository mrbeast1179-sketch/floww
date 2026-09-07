# Spark 1.3 prompter — prompt anchoring for the recovery package

## What this is
This directory holds copy-paste launch prompts only. They are inputs to a
future worker boot, not a running agent. They are checked into Git so they
survive usage limits and context compaction.

## How to use
Copy one file into a fresh session and start with:

1. cd into the matching worktree
2. read the relevant run-package docs under
   `/Users/nav/Documents/GitHub/floww-worktrees/recovery-control-plane-v2/docs/plans/2026-09-06-four-agent-run/`
3. write or re-validate `boot.json` in the external lane directory under
   `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/<lane>/`
4. proceed only after the boot artifact is on disk and consistent with Git state

Do not infer momentum from a chat being open. A chat is spawned work, not
arrived work.

## Current prompt set
- agent-1.md
- agent-2.md
- agent-3.md
- agent-4.md
- recovery-package.md
- spark-session.md
- spark-architect.md
