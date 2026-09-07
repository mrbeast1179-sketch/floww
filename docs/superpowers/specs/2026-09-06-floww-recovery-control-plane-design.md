# Floww Recovery Control Plane Design

**Date:** 2026-09-06
**Status:** Recovery and planning authorized by Nav; this design records the resulting proposal. Unresolved product/vendor decisions remain open.
**Repository:** `mrbeast1179-sketch/floww`

## Purpose

Floww has substantial work on feature branches, local worktrees, saved plan objects,
and external notes, but no trustworthy program-level view of what is merged, merely
committed, reviewable, deployed, or human-witnessed. The previous four-worker launch
also failed at the model-provider layer before it produced any promised `astra_G_*`
receipts. This control plane turns that state into small, resumable delivery units and
prevents a worker report from becoming a completion claim by itself.

## Settled boundaries

- `origin/main` is the acceptance baseline. A local commit, pushed branch, open PR,
  green check, merge, deployed process, and human witness are separate states.
- Main remains protected. Nav owns merges and the human `gsd:ready` label.
- Paper and simulation only. No autonomous live-order execution.
- Existing frozen files and dual GEX scale conventions remain frozen.
- Unknown market data stays unknown. A quote-derived side, interpolated visual row,
  model estimate, and exchange-reported trade are distinct data classes.
- The existing Public API remains the comparator and rollback path during any
  proprietary-feed transition.
- `swarmSPX` is a separate repository and program. Its work is not silently folded
  into Floww tasks.
- The missing Tidehunter artifact is the newer redesign brief/mockups. The accessible
  `floww-2` fork itself is present and inspectable.

## Why the previous launch failed

The package had useful task contracts, but runtime truth never reached its state file.
Hermes delegation `deleg_72bd2bfa` started four tasks; three ended after streams
returned no bytes and one ended on HTTP 429. No `astra_G_*.md` output was created.
The central and per-lane state files still read `prepared_not_started`, so later prose
could describe lanes as running without a boot receipt or checkpoint.

The new design treats launch as a handshake:

1. `DISPATCHED`: a prompt was submitted.
2. `BOOT_ACK`: the worker writes its identity, worktree, base SHA, task, and first
   executable step to its own checkpoint.
3. `ACTIVE`: the coordinator verifies the checkpoint and grants a whole-file lease.
4. `REVIEW`: the worker provides a candidate head and evidence receipt.
5. `ACCEPTED`: an independent reviewer approves the exact head.
6. `MERGED`: GitHub reports the PR merged and `origin/main` contains the result.
7. `DEPLOYED`: runtime provenance points at the merged revision.
8. `WITNESSED`: a required human/external observation is recorded.

No state may be inferred from elapsed time, a chat spinner, or a worker's final prose.

## Four-agent topology

### Agent 1 — Architect and coordinator

Agent 1 is the only writer of central run state and the only allocator of tasks and
whole-file leases. It inventories branch/worktree/PR state, writes immutable task
cards, serializes heavy suites, creates candidate integration branches, and reports
what Nav must merge or witness. It does not build product features while coordinating.

### Agent 2 — Backend and market-data builder

Agent 2 handles one admitted backend/data contract at a time: honesty findings,
provider boundaries, budgets/caches, QC gates, dependencies, and later the
provider-neutral proprietary data plane. It may not edit frontend product files or
pick a second task from GitHub on its own.

### Agent 3 — Frontend and Tidehunter builder

Agent 3 handles one admitted frontend/consumer contract at a time: journal persistence,
Heatseeker/ticker salvage, Phase 9 UI honesty, compose/render acceptance, and the
redesign only after its source artifacts arrive. `App.js` requires an explicit
task-level waiver and surgical diff.

### Agent 4 — Independent proof and review

Agent 4 audits exact commits and PR heads against outcome and exclusion IDs, then
checks correctness, security, failure behavior, and performance. It owns proof
artifacts and can add independent tests only under an admitted path. It never repairs
the candidate it reviews, pushes, merges, sends messages, or makes orders.

## Two supported execution modes

### Managed four-session mode

Agent 1 directly admits local GSD-style task cards. Agents 2 and 3 may build in
parallel only when their exact file sets are disjoint; Agent 4 reviews. None of these
workers invokes the repository-wide GSD issue picker. This is the mode for four
separate Hermes sessions.

### Native GSD queue mode

Exactly one scheduled builder invokes `$gsd-loop-build`, and a separate chat runs
`$gsd-loop-review`. This repository never has two queue-claiming GSD builders. The
current host exposes no native recurring-task tool, so this mode is designed but not
scheduled by this session. A shell loop is not an acceptable substitute.

## Durable artifacts

- `RECOVERY-AUDIT.md`: fact table for current heads, PRs, dirty work, and failed run.
- `RECOVERY-QUEUE.md`: ordered work contracts and disposition of every active program.
- `HARNESS-V2.md`: launch, checkpoint, failure, review, integration, and continuation
  protocol.
- `PROPRIETARY-DATA-DISCOVERY-MAP.md`: valid GSD discovery-map draft for unresolved
  data-source decisions.
- `AGENT-1..4-*.md`: complete copy/paste role prompts.
- `run-state-v2.json`: static initial state; the coordinator copies it to the external
  runtime checkpoint directory before launch.
- GitHub issues/PRs: immutable delivery contracts and candidate changes after the
  relevant human gates.

Mutable runtime evidence lives outside Git at
`/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/`. Each worker writes only
its own lane directory. Agent 1 is the sole central-state writer.

## Task contract

Every admitted task carries:

- `Why`, permanent `O-N` outcomes, permanent `X-N` exclusions;
- exact base SHA and exact allowed files;
- consumers/producers and contract signatures;
- a red/green or verification-only proof plan;
- targeted and broader checks, manual walkthrough, and live-proof classification;
- branch name, retry count, failure class, blocker owner, and next executable command.

A hypothesis cannot become a build until it has a failing behavioral reproduction or
an explicit product decision. A passing verification closes it as
`VERIFIED_EXISTING` without a cosmetic commit.

## Branch and integration design

Each task begins from fresh `origin/main`. A worker never cuts a branch from the
canonical G1 checkout or another feature branch unless the task card explicitly names
and justifies a stack. Before PR creation, the coordinator checks:

```text
git merge-base --is-ancestor BASE HEAD
git diff --name-only BASE...HEAD
git log --oneline BASE..HEAD
```

The changed file set must be a subset of the task lease. When several accepted tasks
need combined tests, Agent 1 builds a temporary candidate integration branch. Passing
there does not mark any task merged.

## Failure and continuation design

- No response bytes or provider 5xx: mark `HARNESS_FAILED`, retain checkpoint, rotate
  the session once, then pause the lane if the same failure repeats.
- HTTP 429: stagger launches, reduce active model calls, preserve the task lease for a
  bounded grace period, and resume from checkpoint. Do not launch all workers again.
- Command approval denial: record the exact command segment and continue read-only or
  offline work that does not need it.
- Test failure: classify baseline, task regression, environment, or flaky evidence.
  Never hide it with `|| true`, skip, or xfail.
- Three failed repair attempts at the same root cause: checkpoint the attempts and
  rotate to review or another eligible task.
- Context/session exhaustion: checkpoint before exit; a replacement starts from the
  artifact and Git state, not from the original prompt.

## Proprietary data transition

The transition is a contract migration, not a provider-name edit. The normalized
boundary must carry source, venue, exchange timestamp, receive timestamp, sequence or
watermark, symbol identity, entitlement class, staleness, correction/cancel state,
and field-level availability. Quotes, trades, daily OI, computed Greeks, and vendor
analytics remain separate payloads.

The rollout is shadow-first:

```text
proprietary capture -> validate/quarantine -> normalize -> replay store
                                           -> shadow comparator vs Public API
                                           -> consumer router -> Floww analytics/UI
```

Cutover requires an entitlement/licensing decision, recorded representative payloads,
deterministic replay, gap/duplicate/correction handling, clock and symbology tests,
field-level provenance, and a rollback threshold. No existing signal receives a new
scientific meaning merely because a richer feed exists.

## Acceptance

The control plane is accepted when its documents validate, every known branch/PR and
external gate has one disposition, the four prompts reference the stable package path,
and a clean commit exists on a branch based on `origin/main`. Product work remains
open until its own contracts pass review and merge.
