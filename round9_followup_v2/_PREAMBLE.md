# Shared Safety Preamble — All 10 Hermes Owl Alpha Agents (READ BEFORE STARTING)

You are one of 10 parallel Hermes Owl Alpha agents working concurrently on the floww/Confluence Decoder codebase. Each agent has a disjoint file scope. The architect (Nav) is monitoring origin/main and the kanban directory.

## Canonical paths (ABSOLUTE)

- Working clone: `/Users/nav/Documents/GitHub/floww` (production-tracked, the only place commits should land)
- **STALE clone (DO NOT TOUCH)**: `/Users/nav/GitHub/floww` (caused 3+ incidents)
- If your `pwd` doesn't end in `Documents/GitHub/floww` → **STOP immediately, ping architect via halt pulse**

## Universal forbidden files

- `backend/services/ml/inference.py` (architect-frozen, READ-ONLY)
- `backend/services/dash_ui.py` (Round 7 frozen, READ-ONLY)
- `backend/tests/conftest.py` (Round 9 verified-not-broken, READ-ONLY)
- Any model artifact: `.joblib`, `.pt`, `*_manifest.json`, `*_meta.json`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` (heavy concurrent WIP — only A3 may surgically edit if absolutely required, and must origin-gate first)

## Universal forbidden git operations

- `git push --force`, `--force-with-lease`
- `git commit --no-verify`
- `git commit --amend` on a commit not authored by yourself (your own current-session HEAD is fine to amend)
- `git rebase --abort` (use `git rebase --continue` after fixing conflicts; if rebase is stuck, HALT)
- `git reset --hard`
- `git checkout .`, `git restore .`, `git clean -fd`
- `git rebase -i` (interactive — not supported in this environment)

## Universal test discipline

- **NEVER** add `@pytest.mark.skip`, `@pytest.mark.xfail`, `it.skip()`, `xit()`, or any other "this test doesn't run" marker to a test that was previously passing.
- If your change causes a previously-passing test to fail, your change is WRONG. Revert it. Find the root cause.
- A test you write yourself MUST fail before your fix and pass after. The failing-then-passing pair IS the evidence.
- Commit messages must include grep/test output INLINE proving the claim. No fabricated success.

## File-ownership matrix (your agent ID determines what you may modify)

| Agent | Backend writable | Frontend writable | Tests writable | Docs writable |
|-------|------------------|-------------------|----------------|---------------|
| A1 | `server.py`, `routes/replay.py`, `services/paper_trader.py`, `routes/ml_predict_api.py`, `pyproject.toml` | — | `tests/services/` (new files only) | `docs/ROUND9_*` (your own close-out) |
| A2 | `services/__init__.py`, `services/ml/__init__.py` | — | `tests/services/ml/test_ml_integration.py` (rewrite), `tests/test_services_is_package.py` (new), `pytest.ini` (new) | `docs/ROUND9_A2_*` (your own) |
| A3 | — | `hooks/*` EXCEPT those owned by A5/A6/A7; `components/*` EXCEPT `heatseeker/`, `CharmChart.jsx`, `VannaChart.jsx`, `OptionsChainTable.jsx`, `ToxicityGauge.jsx`, `App.js` | matching `__tests__/` for above | `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (new) |
| A4 | `services/heatseeker.py`, `services/heatseeker_snapshots.py` | `components/heatseeker/*` | matching test files | `docs/ROUND9_A4_*` (your own) |
| A5 | — | `components/CharmChart.jsx`, `components/VannaChart.jsx`, `hooks/useGreeks.js`, `hooks/useWebSocketGex.jsx` | matching test files | `docs/ROUND9_A5_*` (your own) |
| A6 | `routes/market_data.py` (chain endpoint additions only) | `components/OptionsChainTable.jsx`, `components/ExpiryFilter*` (if exists), `components/DTEFilter*` (if exists) | matching test files | `docs/ROUND9_A6_*` |
| A7 | `services/ml_ensemble.py` (toxicity-related sections only), `routes/toxicity*.py` (if exists) | `components/ToxicityGauge.jsx`, toxicity hooks | matching test files | `docs/ROUND9_A7_*` |
| A8 | `schwab/*`, `services/websocket_streamer.py`, `services/ingestion_pipeline.py` | `hooks/useWebSocket*` (if not owned by A5) | new chaos tests | `docs/ROUND9_A8_*` |
| A9 | **READ ONLY across all of backend/** — your job is audit | — | — | `docs/ROUND10_DEAD_CODE_AUDIT.md` (the ONLY file you write) |
| A10 | `services/option_chain.py`, `services/bs_greeks.py`, `services/spy_helpers.py`, `error_tracking.py`, `mypy.ini` | — | new type-check tests | `docs/ROUND9_A10_*` |

If you need to modify a file outside your scope, **STOP and ping architect** via halt pulse — do not "just this once" override the matrix.

## 15-min pulse cadence (HARD RULE)

Every 15 minutes you must append ONE line to TWO files:
1. `kanban/cards/agent_<YOUR_ID>_status.md` (per-agent log, repo-tracked)
2. `~/Documents/GitHub/Hermes/Daily Log.md` (Obsidian-synced daily aggregate)

Line format:
```
[2026-05-27T01:15:00Z] A1 :: in-progress :: T3 paper_trader insert wrapped, tests green :: HEAD=abc1234
```

Status keywords: `started`, `in-progress`, `blocked-on-<agent>`, `HALT-<reason>`, `DONE`.

If 15 min elapse without a pulse line, **you have self-HALTed**. Stop work, write a HALT line, wait for architect.

## Anti-skip gate (per-task)

Every task in your mission ends with:
1. `git commit` with grep/test/curl evidence INLINE in message body (HEREDOC format)
2. `git pull --rebase origin main && git push origin main` (rebase handles concurrent pushes from other agents)
3. `git fetch origin && git log origin/main --oneline -1 | grep <commit subject substring>` — MUST find your subject. If grep returns empty, your push failed silently — STOP and investigate.

Dependent tasks in your mission (where Task N+1 builds on Task N's commit) must verify Task N's SHA is on origin in their pre-flight step. The plan-author already encoded this where needed.

## What "DONE" means for a mission

- All numbered tasks in your mission file's task list show ✅ in your kanban status
- Each task has a corresponding commit on origin/main
- A final close-out commit updates `docs/ROUND9_A<X>_CLOSEOUT.md` with: commit SHA table, pytest/lint deltas, follow-ups for Round 10
- Your last pulse line says `DONE`

## How to use these prompts

You are receiving ONE agent's mission file in your context. Read the file top-to-bottom before doing anything. Then execute task-by-task. Use `Read` (not `cat`) when opening codebase files. Use `Edit` (not `Write`) for modifying existing files. Use `Write` only for new files. Use `Bash` for git, pytest, grep, and verification commands.

If anything in this preamble conflicts with your specific mission file, the **mission file wins** (it has the architect's intent for your specific scope).

Architect contact channel: write to `kanban/cards/architect_inbox.md` (append-only). The architect checks this file every 15 minutes.
