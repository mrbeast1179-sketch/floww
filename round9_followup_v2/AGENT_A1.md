# Agent A1 — Backend Leak Sweep + Lint CI Gate (target: 3 hours)

**You are Agent A1.** First read `round9_followup_v2/_PREAMBLE.md` in full. Your scope: 5 remaining L4 medium-severity dangling-asyncio-task leaks + DS3 bare-except sweep + DS4 permanent ruff CI gate + Round-10 leak-prevention doc.

Your file ownership (per matrix): `backend/server.py`, `backend/routes/replay.py`, `backend/services/paper_trader.py`, `backend/routes/ml_predict_api.py`, `backend/pyproject.toml`, `.github/workflows/lint.yml`, new files under `backend/tests/services/`, `backend/tests/routes/`.

---

## Mission overview

| # | Task | Files | Min |
|---|------|-------|-----|
| 1 | Pre-flight + read Pro's pattern | (read only) | 10 |
| 2 | L4 leak #5 — `_prefetch_paid_oi` track | `server.py`, new test | 20 |
| 3 | L4 leak #7 — `replay.py` engine task | `routes/replay.py`, new test | 25 |
| 4 | L4 leak #8 — paper_trader `insert_one` x2 | `services/paper_trader.py`, new test | 25 |
| 5 | L4 leak #6 — `_run_training_job` track | `routes/ml_predict_api.py`, new test | 20 |
| 6 | Smoke test full audit grep — confirm 0 leaks | (verify only) | 5 |
| 7 | DS3 bare-except sweep (per-file manual) | `backend/**/*.py` (your scope only) | 30 |
| 8 | DS4 ruff config + CI gate | `pyproject.toml`, `.github/workflows/lint.yml` | 20 |
| 9 | Round-10 leak-prevention doc | `docs/ROUND10_LEAK_PREVENTION.md` | 15 |
| 10 | Close-out + final pulse | `docs/ROUND9_A1_CLOSEOUT.md` | 10 |

Total: 180 min (3 hours).

---

## Task 1 — Pre-flight + study Pro's pattern (10 min)

- [ ] **1.1** `pwd` → must end in `/Users/nav/Documents/GitHub/floww`.
- [ ] **1.2** Confirm Pro's 5 commits on origin:
  ```bash
  git fetch origin && git log origin/main --oneline -10 | grep -E 'L4-leak-#1-#2|L4-leak-#3|L4-leak-#4|H12'
  ```
  Expected ≥4 matches. Else HALT.
- [ ] **1.3** Confirm working tree clean (only `test_ml_integration.py` untracked is allowed):
  ```bash
  git status --short
  ```
- [ ] **1.4** Read the pattern source — Pro's `_logged_task` helper:
  ```bash
  sed -n '83,98p' backend/server.py
  ```
  Expected: `_background_tasks: Set[asyncio.Task] = set()` at ~line 83 and `async def _logged_task(coro, name: str)` at ~line 86. Memorize the 3-line registration pattern:
  ```python
  _t = asyncio.create_task(_logged_task(<coro>, "<name>"))
  _background_tasks.add(_t)
  _t.add_done_callback(_background_tasks.discard)
  ```
- [ ] **1.5** First pulse:
  ```bash
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] A1 :: started :: pre-flight OK :: HEAD=$(git rev-parse --short HEAD)" \
    | tee -a kanban/cards/agent_A1_status.md ~/Documents/GitHub/Hermes/Daily\ Log.md
  ```

---

## Task 2 — `_prefetch_paid_oi` tracked (20 min)

- [ ] **2.1** Locate:
  ```bash
  grep -n 'asyncio.create_task(_prefetch_paid_oi' backend/server.py
  ```
- [ ] **2.2** Read 10 lines of context to get indentation. Use the `Read` tool.
- [ ] **2.3** Write failing test `backend/tests/services/test_prefetch_paid_oi_tracked.py`:
  ```python
  """Regression: _prefetch_paid_oi is wrapped in _logged_task, not fire-and-forget."""
  import inspect
  
  def test_prefetch_call_uses_logged_task():
      import server
      src = inspect.getsource(server)
      assert 'asyncio.create_task(_prefetch_paid_oi())' not in src, \
          "_prefetch_paid_oi() still fire-and-forget"
      assert '_logged_task(_prefetch_paid_oi()' in src, \
          "_prefetch_paid_oi() not wrapped in _logged_task"
  ```
- [ ] **2.4** Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_prefetch_paid_oi_tracked.py -v 2>&1 | tail -5`. Expect 1 FAILED.
- [ ] **2.5** Apply fix. Find:
  ```python
          asyncio.create_task(_prefetch_paid_oi())
  ```
  Replace (same indentation, 8 spaces):
  ```python
          _t = asyncio.create_task(_logged_task(_prefetch_paid_oi(), "_prefetch_paid_oi"))
          _background_tasks.add(_t)
          _t.add_done_callback(_background_tasks.discard)
  ```
- [ ] **2.6** Re-run test → 1 PASSED.
- [ ] **2.7** Smoke: `cd backend && .venv/bin/python3 -c "from server import app, _logged_task, _background_tasks; print('OK')"` → `OK`.
- [ ] **2.8** Commit:
  ```bash
  git add backend/server.py backend/tests/services/test_prefetch_paid_oi_tracked.py
  git commit -m "$(cat <<'EOF'
  fix(L4-leak-#5): track _prefetch_paid_oi task in scheduler loop
  
  Closes Round-9 leak audit finding #5. Previously fire-and-forget inside
  the scheduler loop — if scheduler ran faster than prefetch, tasks
  accumulated unbounded.
  
  Now wrapped in _logged_task (Pro's helper from 5c60a2a) and registered
  in _background_tasks so on_stop() cancels pending prefetches.
  
  Verification:
  \$ grep -c '_logged_task(_prefetch_paid_oi' backend/server.py
  1
  \$ cd backend && .venv/bin/python3 -m pytest tests/services/test_prefetch_paid_oi_tracked.py -v
  1 passed
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#5'
  ```
- [ ] **2.9** Pulse.

---

## Task 3 — `replay.py` engine task tracked (25 min)

- [ ] **3.1** `grep -n 'asyncio.create_task(engine.start' backend/routes/replay.py` → 1 line.
- [ ] **3.2** Read 30 lines of context. Identify whether `/stop` handler exists alongside `/start`. If yes, your fix also wires task cancellation into `/stop`.
- [ ] **3.3** Failing test `backend/tests/routes/test_replay_task_tracked.py`:
  ```python
  """Regression: replay engine.start() task is stored for cancellation."""
  import inspect
  
  def test_engine_start_task_is_stored():
      import routes.replay as r
      src = inspect.getsource(r)
      assert 'asyncio.create_task(engine.start())' not in src, \
          "engine.start() still fire-and-forget"
      assert ('_engine_task' in src) or ('engine._task' in src), \
          "engine task not stored — cannot be cancelled"
  ```
- [ ] **3.4** Run → FAIL.
- [ ] **3.5** Apply fix. At top of `backend/routes/replay.py` (after existing imports):
  ```python
  from typing import Optional
  import asyncio
  
  _engine_task: Optional[asyncio.Task] = None
  ```
  At the `create_task` site (line ~64):
  ```python
      global _engine_task
      _engine_task = asyncio.create_task(engine.start())
  ```
  If `/stop` exists, add at the START of its handler body:
  ```python
      global _engine_task
      if _engine_task is not None and not _engine_task.done():
          _engine_task.cancel()
          try:
              await _engine_task
          except asyncio.CancelledError:
              pass
      _engine_task = None
  ```
- [ ] **3.6** Re-run test → PASS.
- [ ] **3.7** Smoke import: `cd backend && .venv/bin/python3 -c "from routes.replay import router, _engine_task; print(router, _engine_task)"` → router obj + None.
- [ ] **3.8** Run all replay tests: `cd backend && .venv/bin/python3 -m pytest tests/routes/ -k replay -v 2>&1 | tail -8`. Must not regress.
- [ ] **3.9** Commit + push + gate (subject contains `L4-leak-#7`):
  ```bash
  git add backend/routes/replay.py backend/tests/routes/test_replay_task_tracked.py
  git commit -m "$(cat <<'EOF'
  fix(L4-leak-#7): store replay engine task ref + cancel on /stop
  
  Verification:
  \$ grep -c '_engine_task =' backend/routes/replay.py
  1
  \$ cd backend && .venv/bin/python3 -m pytest tests/routes/ -k replay 2>&1 | tail -1
  <paste actual pass count>
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#7'
  ```
- [ ] **3.10** Pulse.

---

## Task 4 — paper_trader 2 fire-and-forget Mongo inserts (25 min)

These are different from prior leaks: they're per-event, not long-running. Right fix is an error-logging wrapper, NOT registration in `_background_tasks` (would explode under tick load).

- [ ] **4.1** `grep -n 'asyncio.create_task(self.mongo.insert_one' backend/services/paper_trader.py` → 2 lines.
- [ ] **4.2** Read context to confirm `order` and `doc` are dicts.
- [ ] **4.3** Failing test `backend/tests/services/test_paper_trader_insert_logged.py`:
  ```python
  """Regression: paper_trader.py wraps Mongo inserts in error logging."""
  import inspect
  
  def test_paper_trader_inserts_are_logged():
      import services.paper_trader as pt
      src = inspect.getsource(pt)
      assert 'asyncio.create_task(self.mongo.insert_one(order))' not in src
      assert 'asyncio.create_task(self.mongo.insert_one(doc))' not in src
      assert '_log_failed_insert' in src, "helper _log_failed_insert missing"
  ```
- [ ] **4.4** Run → FAIL.
- [ ] **4.5** Apply fix. Near top of `paper_trader.py` after existing imports:
  ```python
  import logging
  _pt_log = logging.getLogger("paper_trader")
  
  async def _log_failed_insert(coro, kind: str):
      """Wrap a fire-and-forget DB insert so failures are logged, not silent."""
      try:
          await coro
      except Exception as e:
          _pt_log.error(
              "paper_trader insert (%s) failed: %s: %s",
              kind, type(e).__name__, e, exc_info=True,
          )
  ```
  Line ~411:
  ```python
      asyncio.create_task(_log_failed_insert(self.mongo.insert_one(order), "order"))
  ```
  Line ~427:
  ```python
      asyncio.create_task(_log_failed_insert(self.mongo.insert_one(doc), "trade"))
  ```
- [ ] **4.6** Re-run test → PASS. Run wider sweep: `cd backend && .venv/bin/python3 -m pytest tests/services/ -k paper -v 2>&1 | tail -8`. Must not regress.
- [ ] **4.7** Commit + push + gate (subject `L4-leak-#8-#9`).
- [ ] **4.8** Pulse.

---

## Task 5 — `_run_training_job` tracked (20 min)

- [ ] **5.1** `grep -n 'asyncio.create_task(_run_training_job' backend/routes/ml_predict_api.py`.
- [ ] **5.2** Read context. The endpoint returns a `job_id` and lets training run in background. Leak: errors silently lost.
- [ ] **5.3** Failing test `backend/tests/routes/test_training_job_tracked.py`:
  ```python
  """Regression: _run_training_job uses _logged_task for visibility."""
  import inspect
  
  def test_training_job_uses_logged_task():
      import routes.ml_predict_api as m
      src = inspect.getsource(m)
      assert 'asyncio.create_task(_run_training_job(' not in src
      assert '_logged_task' in src, "_logged_task wrap missing"
  ```
- [ ] **5.4** Run → FAIL.
- [ ] **5.5** Apply fix. At the create_task site (use deferred import to avoid circular cycle since `server` imports `ml_predict_api`):
  ```python
      from server import _logged_task, _background_tasks
      _t = asyncio.create_task(
          _logged_task(
              _run_training_job(job_id, ticker, days, n_splits),
              f"train:{ticker}:{job_id}",
          )
      )
      _background_tasks.add(_t)
      _t.add_done_callback(_background_tasks.discard)
  ```
- [ ] **5.6** Re-run test → PASS. Smoke import: `cd backend && .venv/bin/python3 -c "from routes.ml_predict_api import router; print('OK')"`.
- [ ] **5.7** Commit + push + gate (subject `L4-leak-#6`).
- [ ] **5.8** Pulse.

---

## Task 6 — Audit-grep verify (5 min)

- [ ] **6.1** Re-run audit's grep from `docs/ROUND9_BACKEND_LEAK_AUDIT.md` line 115:
  ```bash
  grep -rn 'asyncio.create_task' backend/ --include="*.py" \
    | grep -v '\.venv/' | grep -v 'backend/tests/' \
    | grep -v 'await\|= ' \
    | grep -v '_logged_task\|_background_tasks\|_log_failed_insert'
  ```
  Expected: ≤2 hits — `websocket_streamer.py:96-98` (stored in list inside `start()` — already managed). If more, you missed a site.
- [ ] **6.2** Pulse: `T6 done :: backend leak audit closed`.

---

## Task 7 — DS3 bare-except sweep (manual per-file) (30 min)

- [ ] **7.1** Ensure ruff installed: `backend/.venv/bin/ruff --version` or `backend/.venv/bin/pip install ruff` if missing.
- [ ] **7.2** Capture BEFORE count:
  ```bash
  backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3
  ```
  Note the N. Save the file list.
- [ ] **7.3** **FOR EACH FILE** with E722 hits, do this loop:
  - Open the file with `Read`. Read 3 lines above each bare `except:` and 3 below.
  - Decide per occurrence:
    - **(a) Safe**: convert `except:` → `except Exception:`
    - **(b) Intentional BaseException catch** (rare — usually long-running daemon loops): keep `except:` and add comment `# noqa: E722 — intentional BaseException catch for daemon loop`
    - **(c) Probable bug** (clearly hiding errors): convert to specific exception type. If unsure, fall back to (a).
  - Apply the edit with `Edit`.
  - After each file, run the matching test module to verify no regression:
    ```bash
    cd backend && .venv/bin/python3 -m pytest tests/ -k <module-name> --tb=line 2>&1 | tail -5
    ```
- [ ] **7.4** Special: `backend/services/social_flow_pipeline.py:335` — the original Round 9 plan flagged this as catching `KeyboardInterrupt`. Inspect; convert to `except Exception:` (KeyboardInterrupt should propagate).
- [ ] **7.5** After all files: `backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3` → 0 (or only intentional noqa-marked).
- [ ] **7.6** Single commit covering all files (use git status to verify only your scope):
  ```bash
  git status --short
  git diff --stat | tail -5  # eyeball: small targeted changes only
  git add backend/  # but verify above first
  git commit -m "$(cat <<'EOF'
  fix(DS3): replace bare except with except Exception across backend
  
  Ruff E722 sweep, file-by-file manual review (not bulk --fix). Each
  occurrence inspected for intent.
  
  BEFORE:
  \$ backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -1
  Found <N> errors.
  
  AFTER:
  \$ backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -1
  All checks passed!
  
  Files touched: <list>
  Special: social_flow_pipeline.py:335 → except Exception (was masking KeyboardInterrupt).
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'DS3'
  ```
- [ ] **7.7** Pulse.

---

## Task 8 — DS4 permanent ruff CI gate (20 min)

- [ ] **8.1** `ls backend/pyproject.toml` — if exists, READ it first.
- [ ] **8.2** If MISSING, create `backend/pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py313"
  extend-exclude = [
      ".venv",
      "services/ml/inference.py",
      "services/dash_ui.py",
      "tests/conftest.py",
  ]
  
  [tool.ruff.lint]
  select = ["F", "E722"]
  ignore = ["E501"]
  
  [tool.ruff.lint.per-file-ignores]
  "tests/**/*.py" = ["F401", "F403"]
  ```
  If EXISTS, ADD or MERGE the `[tool.ruff]` section without overwriting unrelated sections.
- [ ] **8.3** Verify: `cd backend && .venv/bin/ruff check . 2>&1 | tail -5` → should pass cleanly.
- [ ] **8.4** `ls .github/workflows/lint.yml` — if MISSING, create:
  ```yaml
  name: lint
  
  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]
  
  jobs:
    ruff:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: '3.13'
        - name: Install ruff
          run: pip install ruff
        - name: Run ruff
          working-directory: backend
          run: ruff check .
  ```
- [ ] **8.5** Validate YAML: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"`.
- [ ] **8.6** Commit + push + gate (subject `DS4`).
- [ ] **8.7** Pulse.

---

## Task 9 — Round 10 leak-prevention doc (15 min)

- [ ] **9.1** Write `docs/ROUND10_LEAK_PREVENTION.md` capturing the pattern so future agents can apply it without re-reading commit history:
  ```markdown
  # Round-10 Backend Leak Prevention Patterns
  
  Synthesizes the H25/Pro/A1 work into reusable patterns. Future agents
  adding new async background work MUST follow these.
  
  ## Pattern 1 — Long-running background task (scheduler loop, mock feed)
  
  ```python
  from server import _background_tasks, _logged_task
  
  _t = asyncio.create_task(_logged_task(my_long_loop(), "my_long_loop"))
  _background_tasks.add(_t)
  _t.add_done_callback(_background_tasks.discard)
  ```
  
  Why: `on_stop()` iterates `_background_tasks` and cancel+awaits each
  with a 5s bound. Without registration, tasks outlive the event loop.
  
  ## Pattern 2 — Per-event fire-and-forget DB write
  
  Do NOT register in `_background_tasks` (would explode under load).
  Wrap in a local error-logging helper:
  
  ```python
  async def _log_failed_insert(coro, kind):
      try:
          await coro
      except Exception as e:
          log.error("insert (%s) failed", kind, exc_info=True)
  
  asyncio.create_task(_log_failed_insert(mongo.insert_one(doc), "trade"))
  ```
  
  ## Pattern 3 — One-off task with cancellation endpoint (replay, training)
  
  Store task ref on module or app state. Cancel + await in matching
  `/stop` route (or `on_stop` for long-lived):
  
  ```python
  _job_task: Optional[asyncio.Task] = None
  
  @router.post("/start")
  async def start():
      global _job_task
      _job_task = asyncio.create_task(engine.start())
  
  @router.post("/stop")
  async def stop():
      global _job_task
      if _job_task and not _job_task.done():
          _job_task.cancel()
          try: await _job_task
          except asyncio.CancelledError: pass
  ```
  
  ## Anti-patterns (will NOT pass code review)
  
  - Bare `asyncio.create_task(coro)` with no storage — silently leaks errors AND task ref
  - `for x in async_cursor:` (Motor) — use `async for x in async_cursor`
  - `except:` bare — use `except Exception:` (lint gate DS4 catches this)
  - Mutable module-level dict cache with no eviction policy — use TTL or LRU
  
  ## Audit history
  
  | Round | Findings | Closed |
  |-------|----------|--------|
  | R9 L1 audit | 14 | 14 (4 Pro + 5 A1 + 5 H25/pre-fix) |
  ```
- [ ] **9.2** Commit:
  ```bash
  git add docs/ROUND10_LEAK_PREVENTION.md
  git commit -m "docs(round-10): leak-prevention pattern reference for future agents"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **9.3** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** Update `docs/ROUND9_BACKEND_LEAK_AUDIT.md` — mark findings #5, 6, 7, 8, 9 as DONE with your SHAs.
- [ ] **10.2** Write `docs/ROUND9_A1_CLOSEOUT.md`:
  ```markdown
  # Agent A1 Close-out
  
  **Session date:** <today>
  **Duration:** ~3 hr
  
  ## Commits landed
  
  | Task | SHA | Subject |
  |------|-----|---------|
  | 2 | <sha> | L4-leak-#5 _prefetch_paid_oi tracked |
  | 3 | <sha> | L4-leak-#7 replay engine task tracked |
  | 4 | <sha> | L4-leak-#8-#9 paper_trader inserts logged |
  | 5 | <sha> | L4-leak-#6 _run_training_job tracked |
  | 7 | <sha> | DS3 bare-except sweep |
  | 8 | <sha> | DS4 ruff CI gate |
  | 9 | <sha> | docs ROUND10_LEAK_PREVENTION |
  
  ## L4 audit final status: 14/14 fixed
  ## Lint gate: live on main branch
  ```
  Fill SHAs from `git log origin/main --oneline --since="3 hours ago"`.
- [ ] **10.3** Final commit + push + gate.
- [ ] **10.4** Final pulse: `A1 :: DONE :: 7 commits :: L4 audit closed :: lint gate live`.

---

## Halt conditions

1. Pre-flight finds wrong dir or missing Pro commits.
2. Any failing-test step doesn't actually fail.
3. Any PASS step doesn't pass.
4. Wider test sweep regresses.
5. Any origin gate returns empty.
6. Ruff sweep breaks a previously-passing test → revert that edit.
7. 15-min pulse gap → self-HALT.
