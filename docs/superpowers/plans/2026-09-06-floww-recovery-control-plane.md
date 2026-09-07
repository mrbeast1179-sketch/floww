# Floww Recovery Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the recovered work and operate four restartable agents against a complete, evidence-backed queue.

**Architecture:** One architect admits exact contracts, backend and frontend builders work in disjoint worktrees, and a fourth agent reviews. Git preserves candidate code; per-lane external checkpoints preserve progress. Separate task specifications govern product changes and proprietary-data decisions.

**Tech Stack:** Git/GitHub, installed GSD scripts, Markdown/JSON receipts, existing FastAPI/pytest/Ruff and React/CRACO/Jest.

**Spec:** [Recovery design](../specs/2026-09-06-floww-recovery-control-plane-design.md)

## Global Constraints

- Main remains protected. Nav owns merges and the human `gsd:ready` label.
- Paper and simulation only. No autonomous live-order execution.
- Existing frozen files and dual GEX scale conventions remain frozen.
- Unknown market data stays unknown.
- The existing Public API remains the comparator and rollback path during any proprietary-feed transition.
- `swarmSPX` is a separate repository and program.
- No state may be inferred from elapsed time, a chat spinner, or a worker's final prose.

---

### Task 1: Preserve recovered plans and local work

Files: the fifteen original docs from84031ea; new package evidence directory; no product paths in the architect branch.

- [x] Create isolated architect worktree from origin/main5b9d9a9.
- [x] Recover fifteen plan artifacts, preserving main's institutional ledger (a2c6b08).
- [x] Capture branch/PR audit, four duplicate Heat notes, F1 WIP/test, scroller WIP and Serena migration as explicitly historical evidence.
- [x] Save latest G1 b5f9ae5 to origin/archive/20260907-g1-recovery; verify remote SHA.
- [ ] Verify final package commit and remote SHA; record receipt.

### Task 2: Establish restartable role prompts

Files: README.md, COMMON.md, COORDINATOR.md, AGENT-1-platform.md, AGENT-2-data.md, AGENT-3-experience.md, AGENT-4-proof.md, HARNESS-V2.md, run-state-v2.json under docs/plans/2026-09-06-four-agent-run/.

- [x] Replace stale coordinator-plus-four topology with four total roles.
- [x] Define boot acknowledgement, exact leases, one heavy-suite owner, checkpoint fields and failure classes.
- [x] Give each role a bounded initial contract and next-task protocol.
- [x] Record model/host capability checks for requested Spark/Muse1.3 without claiming unsupported persistence.
- [x] Validate JSON and all current local document links; check prompts reference the stable package path.
- [ ] After user launches sessions, Agent1 verifies actual boot receipts before ACTIVE. This step is future operation, not package acceptance.

### Task 3: Reconcile backlog and isolate verified defects

Files: RECOVERY-AUDIT.md, RECOVERY-QUEUE.md, BACKLOG-CROSSWALK.md, TASK-CARDS.md, SOLSTICE-SCROLLER.md, evidence/*.md.

- [x] Give all original P1–P7/D1–D7/X1–X5/E1–E5 and Phase9 F1–F19 a disposition.
- [x] Account for G1/G3, Obsidian/fork/Tidehunter, missing artifacts and swarmSPX64item groups.
- [x] Specify SCROLL-1 boundaries beyond rendered500 and source200, actual mount, focus/reveal and bounded DOM.
- [x] Attach final Heat audit and GSD review receipts, preserving proof limitations.
- [ ] Agent1 admits clean product repair branches using these receipts; no wholesale G1 merge.

### Task 4: Complete the explicitly requested GSD passes

Files: GSD-PASSES.md and independent review receipt.

- [x] Build preflight in a clean prepared worktree; verify origin/default branch, labels and empty rework/abandoned-claim queues.
- [x] Claim oldest eligible issue8; read full contract/discussion and revalidate claim.
- [x] Record unresolved credits dependency, apply gsd:blocked and release assignment; no paid request.
- [x] Finish or accurately checkpoint the single interrupted review pass; use trusted SHA/issue marker and bundled outcome synchronization.
- [x] Do not run a second pass as a substitute for finishing this receipt.

### Task 5: Prepare proprietary-data delivery

Files: PROPRIETARY-DATA-DISCOVERY-MAP.md and DATA-ENGINEERING-ROADMAP.md.

- [x] Define six prerequisite decisions and their dependency graph.
- [x] Keep schema/capture/replay/shadow/router/UI/operations/qualification/cutover as candidate slices until decisions settle.
- [x] Validate the draft with installed validate-discovery-map.mjs --allow-not-ready.
- [ ] Account owner supplies actual provider/entitlements; architect advances one discovery decision.
- [ ] File approved contracts using GSD spec; no automatic gsd:ready or vendor purchase.

### Task 6: Verification and handoff

- [x] Run git diff --check; inspect full changed-file set and secret-shaped text without printing values.
- [x] Validate preservation patches with git apply --check against immutable matching bases in disposable worktrees.
- [x] Confirm every current link resolves, every JSON parses and all four prompts exist.
- [ ] Commit explicit documentation paths with actual validation evidence.
- [ ] Push the architect feature branch and verify remote SHA equals local.
- [ ] Hand Nav the four prompt links and exact saved state; distinguish remaining product work and unsupported native scheduling.

Package acceptance does not require implementing the entire multi-day product backlog. Each later task has its own review, merge and runtime acceptance; no user witness is manufactured.
