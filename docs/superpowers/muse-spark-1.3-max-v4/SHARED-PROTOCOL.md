# Shared protocol — all four agents

## 1. Boot before work

Run `git fetch --all --prune`, resolve repository root, list worktrees, read open
PRs and required checks, then write your own lane's `boot.json`. Record exact
base/head SHAs, branch, worktree, task ID, allowed files, first command, and any
dirty paths. A prompt SHA is a hint; fetched Git is truth.

Live runtime root:
`/Users/nav/Documents/GitHub/floww-run-state/2026-09-09-v4/`

Lane roots are exactly `agent-1-architect`, `agent-2-backend`,
`agent-3-frontend`, and `agent-4-reviewer`. Each lane owns only its own
`boot.json`, `checkpoint.json`, `events.jsonl`, and receipts. Agent 1 alone owns
`admissions/` and `run-state.json`.

## 2. One immutable task contract

No card means no mutation. A task card must contain these GSD-grade sections:

```markdown
## Why
## Outcomes
- [ ] O-1 — observable result
## Exclusions
- X-1 — behavior that must remain unchanged
## Code pointers
## Exact lease
## Testing notes
## Manual walkthrough
```

It must also pin base SHA, branch, worktree, incumbent owner, proof commands,
first command, dependencies, and a maximum one-agent-day scope. Outcomes keep
stable O-N IDs; exclusions keep stable X-N IDs. Workers do not silently expand
scope. Agent 1 issues a new card when scope genuinely changes.

## 3. Concurrency and leases

- One writer per branch and one task per builder.
- Agent 2 never edits frontend; Agent 3 never edits backend; Agent 4 never edits a
  candidate. Agent 1 edits coordination documents/runtime only.
- `backend/server.py`, workflow files, dependency manifests, global frontend
  shell files, schemas/migrations, and execution paths are serialized leases.
- Never work in the canonical checkout or another agent's dirty worktree.
- Start every implementation from fetched `origin/main` in a dedicated worktree.
- Read-only inspection across worktrees is allowed. Treat all unexplained dirt as
  user/agent property and preserve it.

## 4. Test-driven implementation

For a defect or feature: prove RED at the accepted base, implement the smallest
contract-complete patch, prove focused GREEN, then run the proportional module,
full-suite, lint, build, and invariant checks named by the card. Do not add
skip/xfail, weaken thresholds, delete coverage, or silently refresh snapshots.

An environmental failure is classified by reproducing it on the immutable base
under the same environment. This qualifies the failure; it does not turn the
candidate green. Clean CI remains required.

## 5. Financial and data truth

Every output must identify its epistemic class:

1. exchange/vendor-observed event;
2. quote-derived inference;
3. aggregate/OI/volume proxy;
4. model estimate;
5. hypothesis awaiting out-of-sample evidence.

Never promote a proxy into institutional identity, signed trade flow, causality,
or tradable alpha. Preserve event time, receive time, source, entitlement mode,
correction state, freshness, coverage, fallback, and formula/version provenance.
Use point-in-time joins; prohibit look-ahead, revised-data leakage, and survivor
bias. Backtests include fees, spread, slippage, latency, capacity, rejects, and
paper/live separation.

## 6. Execution safety

- Paper endpoint only; live endpoints and live credentials are out of scope.
- One logical approval maps to one stable venue client-order ID.
- Accepted/submitted is not filled. P&L uses confirmed fills only.
- No agent may place a paper order unless its card explicitly authorizes the
  exact mocked/replay/paper walkthrough and Agent 1 records the single owner.
- Never print secrets, raw private fills, private messages, or proprietary rows.
- No paid request, credential rotation, service restart, deployment, or recurring
  scheduler is implied by this harness.

## 7. Git and review gates

- No force push, amend of another author's commit, wholesale divergent-branch
  merge, destructive reset, or unreviewed conflict resolution.
- Commit only enumerated leased files. Use a detailed commit message containing
  actual test evidence and limitations.
- Push, then verify local SHA equals remote SHA.
- Agent 4 reviews the exact remote head in a clean detached worktree. A head move
  voids the verdict.
- Agent 1 may merge only when required CI is green, Agent 4 says APPROVED for the
  exact head, the PR remains mergeable, and the payload has no live execution,
  secrets, paid-provider, deployment, destructive migration, or external-witness
  requirement. Otherwise record `STOP_OWNER`.
- After merge, fetch main, verify ancestry and merged-head checks, then update
  runtime state. GitHub “merged” into a feature branch is not delivery to main.

## 8. Checkpoints and low-credit behavior

Checkpoint after boot, RED, GREEN, commit, push, review verdict, merge, blocker,
and at least every 60 minutes. Include exact SHAs, dirty owned paths, last command
and exit, proof paths, unresolved limits, and one executable next command.

When credits are low: stop exploration, land only a coherent tested unit, push it,
write the checkpoint, and release the lease. Never loop, repeat status checks, or
fill output with narration. A dirty tree without an exact recovery command is a
failed handoff.

## 9. Definition of done

Done means the contracted outcomes are proven at one immutable head, exclusions
are intact, receipts state what was not tested, branch and remote agree, and the
next lane can resume without inference. “Tests exist,” “CI once passed,” “PR
merged,” and “agent said done” are not sufficient alone.

