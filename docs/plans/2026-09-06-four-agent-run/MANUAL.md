# Manual — Floww recovery-control-plane-v2

## 1. Package identity and boundary
- Package root: `/Users/nav/Documents/GitHub/floww-worktrees/recovery-control-plane-v2`
- Branch: `architect/20260906-recovery-control-plane-v2`
- Remote: `origin/architect/20260906-recovery-control-plane-v2`
- Current main: `origin/main = 56cfff2` (PR28–47 merged, PR44 merged 2026-09-08T11:48:51Z)
- Run-state root: `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/`

This is the architect/coordinator package. It does NOT own product code — it owns
central external runtime state (run-state root), task cards, and the package docs
under `docs/plans/2026-09-06-four-agent-run/`. Product code lives in canonical
`/Users/nav/Documents/GitHub/floww` or in lane worktrees.

## 2. Canonical checkout is NOT your lease
- Canonical `/Users/nav/Documents/GitHub/floww` is on `phase9/g1-reads-witness`
  (dirty: App.js, SkylitTickerBar, .serena, 4 untracked .planning docs).
- That checkout predates this program. NEVER sweep it. NEVER commit to it from
  this package. Production cutover to main is a Nav-coordinated single-writer step.

## 3. Lane worktrees — read-only unless a task card names your exact files
- `agent2-gamma-vanna`, `agent2-numba`, `alert-surfacing-agent3`, `vomma-walls`,
  `g3-split` — occupied by live workers. Do NOT touch their files unless your
  task card explicitly enumerates them.
- Mutex rule: one writer per branch, ever. Another lane's branch is read-only.

## 4. Boot protocol (every session, first 5 minutes)
1. `git fetch origin && git status --short --branch && git log --oneline -3`
2. Re-read `origin/main` SHA — it moves without you. Current: `56cfff2`.
3. Read package docs in order:
   `README.md` → `HARNESS-V2.md` → `RECOVERY-QUEUE.md` → `run-state-v2.json`
   → `GSD-PASSES.md` → `TASK-CARDS.md`
   (all under `docs/plans/2026-09-06-four-agent-run/`).
4. `ls /Users/nav/Documents/GitHub/floww-run-state/2026-09-06-v2/` — disk naming
   wins over docs (naming has drifted: `platform`/`data` vs `agent-1-architect`/etc).
   Read YOUR lane's `boot.json` and `checkpoint.json` before touching anything.
5. Write/re-validate `boot.json` before touching files: agent, task_id, worktree,
   base_sha, head_sha, allowed_files (explicit list), next_command. No boot artifact
   = no work.

## 5. Admission protocol
- Admit exactly ONE task per builder at a time.
- Each admission = a task card under the task-cards root with: base SHA, incumbent
  release, EXACT allowed files, O/X outcomes, exclusions, proof commands.
- Before ACTIVE: re-validate all five + check no overlapping lease with any live
  card (read peers' cards AND their latest checkpoint.json first).
- Record every transition: actor, exact head, evidence path, timestamp.
- Keep `run-state-v2.json` truthful.

## 6. Parallel-run mutex map (enforce; this is why you exist)
- One writer per branch, ever. Another lane's branch is read-only.
- `backend/server.py`: SERIALIZED across all backend units. Never admit two
  server.py tasks concurrently.
- `frontend/src/App.js` + frozen files (`.env`, `package.json`, `craco.config.js`,
  `ml/inference.py`, `dash_ui.py`, `tests/conftest.py`, model artifacts): surgical
  edits ONLY with an explicit recorded Nav waiver PER CHANGE. No standing waiver.
  Ask every time.
- Task cards are the mutex: no card = no work. A worker touching files outside its
  card stops and re-admits.
- Never rewrite another lane's receipts, checkpoints, or central state.
- Never claim merges, deploys, live witnesses, or another lane's completion.
  Verify with git/gh output or mark UNVERIFIED in caps.

## 7. Proof discipline
- Local tests + CI where available. Focused-file green is not full-suite proof.
- Record exact commands, exact heads, exact counts.
- A test YOU write must fail before the fix and pass after. Never skip/xfail a
  passing test. Persist skip/wip to `conftest.py` with a reason.
- Receipts live in `floww-run-state/2026-09-06-v2/<lane>/receipts/` or
  `docs/plans/2026-09-06-four-agent-run/evidence/`.
- Checkpoint after every red/green test, commit, push, blocker, and every 15 min.

## 8. Gate discipline
- Never merge reviewed PRs — that's Nav's authority. Marked READY ≠ merged.
- Never push to canonical `phase9/g1-reads-witness`.
- Never attempt production cutover from this lane.
- Paper venue is hardcoded (`paper-api.alpaca.markets`). ANY live-trading request
  stops your session for Nav confirmation. No exceptions.
- Frozen files need a recorded Nav waiver per change. None exists. Ask first.

## 9. What's done (current truth, 2026-09-08)
- Main `56cfff2`: PR28–47 all merged. PR44 (G3-salvage) MERGED 2026-09-08T11:48:51Z.
- PR28 still open (astra/d7-clean, policy-escalated, Nav-gated).
- Agent-2 items 1-2 DONE (PR47: numba charm-vec + LIQUIDITY_STRESS).
- Agent-3: T1 shipped (PR33); alert-surfacing 1a/1b done (PR48); 1c queued.
- Agent-4: E4-44 APPROVED-conditional at bffa5de (PR44 head); witness gate pending.
- All four spark prompts reconciled to 56cfff2.

## 10. What's gated (not agent authority)
- PR28 Nav merge decision
- PR44 witness gate (external G-WITNESS, Nav/owner-gated — already merged without it)
- App.js standing waiver
- A3-SCORE weight approval (F2/F13, F8/F10/F12/F14)
- P2/P6/P7 upgrades, Azure VM, O-2/O-4/O-5, GSD-8 (X credits)
- Production cutover (Nav-coordinated, single-writer)

## 11. Hybrid evaluation (LLM-as-judge) protocols
See `docs/evaluation/AGENT-EVALS/`. Current writeups:
- `METRICS-SYNTHESIS.md` — map of what to measure PER role, existing signals, gaps,
  suggested judge prompt structure. Covers agent-1 through agent-4 plus prompt-prompt.
- `DATA-DICTIONARY.md` — all candidate signals and judge criteria across 17 pages,
  grouped by DB field, role, LLM-vs-deterministic, prompt-input-eligibility, known-position.
  Index table + per-signal pages.
- Hybrid eval requires BOTH LLM judgment AND deterministic replay/DB extraction.
  LLM-only = position, not proof. Never fabricate metrics.

## 12. Stop conditions
- Provider stream returns no bytes or HTTP 429 without a durable boot/checkpoint.
- Branch ancestry or diff includes files outside the task lease.
- A task needs a frozen file without a recorded waiver.
- A data field's semantics, licensing, entitlement, or timestamp are unresolved.
- A worker would hide a failing check, fabricate a live witness, or infer merge/deploy.
- Two builders need the same whole file.
