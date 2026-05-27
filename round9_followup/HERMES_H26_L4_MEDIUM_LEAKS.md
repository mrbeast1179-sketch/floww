# Hermes Owl Alpha — Agent H26 · L4 Medium-Severity Leaks (4 fixes, ~75 min)

You are Agent H26. You complete the L4 backend memory-leak remediation by fixing the 4 Medium-severity dangling-asyncio-task findings that DeepSeek Pro left for follow-up. Pattern you will follow is already proven by 4 commits on origin (`5c60a2a`, `d322d79`, `27d3598`, `8189251` — read those diffs to internalize the pattern before starting).

---

## Mission scope

Four leaks, each one fire-and-forget asyncio task with no error handling and no shutdown cancellation. For each, you wrap the task in `_logged_task()` (already exists at `backend/server.py:86`) and register it in `_background_tasks` (already exists at `backend/server.py:83`).

| # | File:Line | What leaks |
|---|-----------|------------|
| 1 | `backend/server.py:2188` | `_prefetch_paid_oi()` in scheduler loop — if scheduler runs faster than prefetch, tasks accumulate |
| 2 | `backend/routes/replay.py:64` | `engine.start()` task — never stored, never cancelled in `/stop` |
| 3 | `backend/services/paper_trader.py:411` | `self.mongo.insert_one(order)` — silent loss on failure |
| 4 | `backend/services/paper_trader.py:427` | `self.mongo.insert_one(doc)` — silent loss on failure |
| 5 | `backend/routes/ml_predict_api.py:267` | `_run_training_job()` — training errors silently lost |

(Yes, 5 sites — finding #1 is one site, paper_trader is two sites in one file.)

---

## Hard constraints (READ EVERY ONE)

- **Canonical clone**: `/Users/nav/Documents/GitHub/floww`. If you find yourself in `/Users/nav/GitHub/floww`, STOP — that is the stale clone that has caused 3+ production incidents.
- **Forbidden files**: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, model artifacts (`.joblib`, `.pt`, model `.json`), `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`. Do not even open them.
- **Forbidden git operations**: no `--force`, no `--no-verify`, no `--amend` on commits not your own, no `git rebase --abort`, no `git reset --hard`, no `git checkout .`, no `git clean -fd`. If you need to undo work, ask the architect by writing a HALT line.
- **Test discipline**: NEVER mark a test `@pytest.mark.xfail` or `@pytest.mark.skip`. If a test fails, find the root cause. If you cannot, HALT.
- **Origin-state gate after every commit**: `git fetch origin && git log origin/main --oneline -1 | grep '<your commit subject substring>'` — if the grep fails, the push didn't land, STOP and investigate.
- **15-minute pulse**: every 15 minutes, append one line to `kanban/cards/agent_H26_status.md` AND `~/Documents/GitHub/Hermes/Daily Log.md` in the format below. If 15 min pass without a pulse, self-HALT.
  ```
  [2026-05-27T01:15:00Z] H26 :: in-progress :: T3 paper_trader.py:411 wrap done, running tests :: HEAD=abc1234
  ```

---

## Pre-flight (do this exactly, in order)

- [ ] **PF1.** `pwd` → must end in `/Users/nav/Documents/GitHub/floww`. **Else STOP.**
- [ ] **PF2.** `git fetch origin && git log origin/main --oneline -8 | grep -E 'L4-leak-#1-#2|L4-leak-#3|L4-leak-#4|H12'` — must show all 4 Pro commits (`5c60a2a`, `d322d79`, `27d3598`, `8189251`). **Else STOP** — your base assumption is broken.
- [ ] **PF3.** `git status --short` — should show only `?? backend/tests/services/ml/test_ml_integration.py` and nothing else. If your working tree has other uncommitted work, STOP and ask the architect.
- [ ] **PF4.** Read the helper you'll use repeatedly:
  ```
  sed -n '83,98p' backend/server.py
  ```
  Confirm `_background_tasks: Set[asyncio.Task] = set()` at line 83 and `async def _logged_task(coro, name: str)` at line 86. **Else STOP** — your pattern source isn't there.
- [ ] **PF5.** Read one of Pro's diffs to internalize the pattern:
  ```
  git show 5c60a2a -- backend/server.py | grep -A6 '_logged_task'
  ```
  Note the 3-line pattern: `_t = asyncio.create_task(_logged_task(...))`, `_background_tasks.add(_t)`, `_t.add_done_callback(_background_tasks.discard)`.
- [ ] **PF6.** Confirm baseline pytest:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/test_graceful_shutdown.py tests/services/test_duckdb_engine_shutdown.py -v 2>&1 | tail -5
  ```
  Expected: 4 passed (these are Pro's tests — they must still pass after your changes).
- [ ] **PF7.** Write your first pulse line:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H26 :: started :: pre-flight clean :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H26_status.md
  ```

---

## Task 1: `_prefetch_paid_oi` task in scheduler loop (15 min)

**File**: `backend/server.py:2188` (or thereabouts — grep first)

- [ ] **T1.1** Locate the exact site:
  ```
  grep -n 'asyncio.create_task(_prefetch_paid_oi' backend/server.py
  ```
  Expected: exactly 1 line. Note the indentation (it's inside the scheduler loop, so indented at least 8 spaces).

- [ ] **T1.2** Read 10 lines of context:
  ```
  grep -n 'asyncio.create_task(_prefetch_paid_oi' backend/server.py
  # then read 5 lines above and 5 below at that line
  ```

- [ ] **T1.3** Write the failing test. Create `backend/tests/services/test_prefetch_paid_oi_tracked.py`:
  ```python
  """Regression test: _prefetch_paid_oi task is tracked in _background_tasks."""
  import inspect
  
  
  def test_prefetch_call_uses_logged_task():
      """The prefetch call site must use _logged_task and register the task."""
      import server
      src = inspect.getsource(server)
      # Old fire-and-forget pattern must not exist
      assert 'asyncio.create_task(_prefetch_paid_oi())' not in src, \
          "_prefetch_paid_oi() is still fire-and-forget — must be wrapped"
      # New pattern present
      assert '_logged_task(_prefetch_paid_oi()' in src, \
          "_prefetch_paid_oi() not wrapped in _logged_task"
  ```

- [ ] **T1.4** Run the test to confirm it fails:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/test_prefetch_paid_oi_tracked.py -v 2>&1 | tail -8
  ```
  Expected: 1 FAILED.

- [ ] **T1.5** Replace the fire-and-forget at the line you found in T1.1.

  Find (with original indentation, likely 8 spaces):
  ```python
          asyncio.create_task(_prefetch_paid_oi())
  ```
  Replace with (same indentation):
  ```python
          _t = asyncio.create_task(_logged_task(_prefetch_paid_oi(), "_prefetch_paid_oi"))
          _background_tasks.add(_t)
          _t.add_done_callback(_background_tasks.discard)
  ```

- [ ] **T1.6** Re-run the test:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/test_prefetch_paid_oi_tracked.py -v 2>&1 | tail -5
  ```
  Expected: 1 PASSED.

- [ ] **T1.7** Smoke-import the module:
  ```
  cd backend && .venv/bin/python3 -c "from server import app, _logged_task, _background_tasks; print('imports OK')"
  ```
  Expected: `imports OK`.

- [ ] **T1.8** Commit + push + gate:
  ```
  git add backend/server.py backend/tests/services/test_prefetch_paid_oi_tracked.py
  git commit -m "$(cat <<'EOF'
  fix(L4-leak-#5): track _prefetch_paid_oi task in scheduler loop
  
  Closes Round-9 leak audit finding #5 (server.py:2185 _prefetch_paid_oi
  fire-and-forget inside scheduler loop). If scheduler ran faster than
  prefetch completed, tasks accumulated without bound.
  
  Now wrapped in _logged_task (added by Pro session, commit 5c60a2a) and
  registered in _background_tasks so on_stop() cancels pending prefetches.
  
  Verification:
  \$ grep -c '_logged_task(_prefetch_paid_oi' backend/server.py
  1
  \$ cd backend && .venv/bin/python3 -m pytest tests/services/test_prefetch_paid_oi_tracked.py -v
  1 passed
  EOF
  )"
  git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#5'
  ```
  **Else STOP.**

- [ ] **T1.9** Pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H26 :: T1 done :: $(git rev-parse --short HEAD) :: _prefetch_paid_oi tracked" \
    >> kanban/cards/agent_H26_status.md
  ```

---

## Task 2: `engine.start()` in replay.py (15 min)

**File**: `backend/routes/replay.py:64`

- [ ] **T2.1** Grep + read:
  ```
  grep -n 'asyncio.create_task(engine.start' backend/routes/replay.py
  sed -n '55,80p' backend/routes/replay.py
  ```
  Note the surrounding function — likely a `/start` POST handler. There may be a corresponding `/stop` that this fix should make work properly.

- [ ] **T2.2** Look for the `/stop` handler:
  ```
  grep -n '@router\|def stop\|engine.stop' backend/routes/replay.py | head -10
  ```
  If `/stop` exists and calls `engine.stop()` but never touches the task, your fix should ALSO cancel-and-await the task there.

- [ ] **T2.3** Write the failing test. Create `backend/tests/routes/test_replay_task_tracked.py`:
  ```python
  """Regression test: replay engine.start() task is stored and cancellable."""
  import inspect
  
  
  def test_engine_start_task_is_stored():
      """The engine.start() task must be stored on a module-level or app-state ref."""
      import routes.replay as r
      src = inspect.getsource(r)
      assert 'asyncio.create_task(engine.start())' not in src, \
          "engine.start() is still fire-and-forget"
      # Either pattern: module-level _engine_task or attach to engine itself
      stored = ('_engine_task' in src) or ('engine._task' in src) or ('_replay_task' in src)
      assert stored, "engine.start() task is not stored anywhere — cannot be cancelled"
  ```

- [ ] **T2.4** Run + confirm FAIL.

- [ ] **T2.5** Pick storage strategy and apply. Recommended (module-level for simplicity):

  Near top of `backend/routes/replay.py`, add:
  ```python
  from typing import Optional
  import asyncio
  
  _engine_task: Optional[asyncio.Task] = None
  ```

  At line 64 (the create_task site), replace:
  ```python
      asyncio.create_task(engine.start())
  ```
  with:
  ```python
      global _engine_task
      _engine_task = asyncio.create_task(engine.start())
  ```

  If a `/stop` route exists, ADD task cancellation BEFORE the existing `engine.stop()` call:
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

- [ ] **T2.6** Re-run test + confirm PASS.

- [ ] **T2.7** Smoke-import:
  ```
  cd backend && .venv/bin/python3 -c "from routes.replay import router, _engine_task; print('OK', _engine_task)"
  ```
  Expected: `OK None`.

- [ ] **T2.8** Commit + push + gate (subject must contain `L4-leak-#6` — even though audit numbered it #7, this is your 2nd Medium fix):
  ```
  git add backend/routes/replay.py backend/tests/routes/test_replay_task_tracked.py
  git commit -m "fix(L4-leak-#7): store replay engine task ref + cancel on /stop"
  git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#7'
  ```

- [ ] **T2.9** Pulse.

---

## Task 3: Paper-trader 2 fire-and-forget Mongo inserts (15 min)

**File**: `backend/services/paper_trader.py:411 and :427`

These are different: the previous tasks were "scheduler/long-running". These are "fire one DB write per call". The correct fix is NOT to register in `_background_tasks` (would explode under load) — it's to add an error wrapper.

- [ ] **T3.1** Grep + read both sites:
  ```
  grep -n 'asyncio.create_task(self.mongo.insert_one' backend/services/paper_trader.py
  ```
  Expected: 2 lines (411, 427).

- [ ] **T3.2** Read the surrounding 5 lines of each to understand what `order` and `doc` carry.

- [ ] **T3.3** Decide: are these `async def` methods on a class? If yes, the simplest correct fix is to make them `await self.mongo.insert_one(...)` instead — synchronous-from-the-caller's-perspective, and any failure surfaces as an exception the caller can handle. **BUT** only do this if it doesn't add observable latency (Mongo inserts are sub-millisecond; usually safe). If you're unsure, fall back to the wrapper approach.

  **Default decision (use this unless you have reason otherwise):** keep fire-and-forget for non-blocking, but wrap each in a small helper that logs failures:

  Add this helper near the top of `paper_trader.py` (after imports):
  ```python
  import logging
  _pt_log = logging.getLogger("paper_trader")
  
  async def _log_failed_insert(coro, kind: str):
      try:
          await coro
      except Exception as e:
          _pt_log.error(f"paper_trader insert ({kind}) failed: {type(e).__name__}: {e}")
  ```

- [ ] **T3.4** Write the failing test. Create `backend/tests/services/test_paper_trader_insert_logged.py`:
  ```python
  """Regression: paper_trader.py wraps Mongo inserts in error logging."""
  import inspect
  
  
  def test_paper_trader_inserts_are_logged():
      import services.paper_trader as pt
      src = inspect.getsource(pt)
      # Old patterns must be gone
      assert 'asyncio.create_task(self.mongo.insert_one(order))' not in src, \
          "order insert is still bare fire-and-forget"
      assert 'asyncio.create_task(self.mongo.insert_one(doc))' not in src, \
          "doc insert is still bare fire-and-forget"
      # New helper present
      assert '_log_failed_insert' in src, "helper _log_failed_insert not present"
      assert 'await _log_failed_insert' in src or 'create_task(_log_failed_insert' in src, \
          "helper not used"
  ```

- [ ] **T3.5** Run + confirm FAIL.

- [ ] **T3.6** Replace both call sites:

  Line ~411:
  ```python
      asyncio.create_task(self.mongo.insert_one(order))
  ```
  →
  ```python
      asyncio.create_task(_log_failed_insert(self.mongo.insert_one(order), "order"))
  ```

  Line ~427:
  ```python
      asyncio.create_task(self.mongo.insert_one(doc))
  ```
  →
  ```python
      asyncio.create_task(_log_failed_insert(self.mongo.insert_one(doc), "trade"))
  ```

- [ ] **T3.7** Re-run test + confirm PASS.

- [ ] **T3.8** Run the wider paper_trader tests to confirm no regression:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/ -k paper -v 2>&1 | tail -10
  ```
  Expected: prior count of passes maintained, plus your 1 new test.

- [ ] **T3.9** Commit + push + gate:
  ```
  git add backend/services/paper_trader.py backend/tests/services/test_paper_trader_insert_logged.py
  git commit -m "fix(L4-leak-#8-#9): wrap paper_trader Mongo inserts in error logger"
  git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#8-#9'
  ```

- [ ] **T3.10** Pulse.

---

## Task 4: `_run_training_job` in ml_predict_api.py (15 min)

**File**: `backend/routes/ml_predict_api.py:267` (audit said 246 — grep-verify)

- [ ] **T4.1** Grep:
  ```
  grep -n 'asyncio.create_task(_run_training_job' backend/routes/ml_predict_api.py
  ```
  Expected: 1 line.

- [ ] **T4.2** Read surrounding context. The endpoint likely starts a long-running training job and returns a job ID immediately. The leak: if `_run_training_job` raises, the job ID points at a phantom and the error is invisible.

- [ ] **T4.3** Failing test in `backend/tests/routes/test_training_job_tracked.py`:
  ```python
  """Regression: _run_training_job task failures are logged + trackable."""
  import inspect
  
  def test_training_job_uses_logged_task():
      import routes.ml_predict_api as m
      src = inspect.getsource(m)
      assert 'asyncio.create_task(_run_training_job(' not in src, \
          "_run_training_job still bare fire-and-forget"
      assert '_logged_task' in src or '_training_jobs' in src, \
          "neither _logged_task wrap nor job-tracking dict present"
  ```

- [ ] **T4.4** Run + confirm FAIL.

- [ ] **T4.5** Patch. The training task is best wrapped in `_logged_task` from `server.py`:

  At top of `ml_predict_api.py`, ensure import:
  ```python
  from server import _logged_task, _background_tasks
  ```
  (If circular-import risk — `ml_predict_api` is included by `server`, so this import must be deferred. In that case, do it inside the function body, not at module top.)

  At the create_task site, replace:
  ```python
      asyncio.create_task(_run_training_job(job_id, ticker, days, n_splits))
  ```
  with (deferred import to avoid cycle):
  ```python
      from server import _logged_task, _background_tasks
      _t = asyncio.create_task(
          _logged_task(_run_training_job(job_id, ticker, days, n_splits), f"train:{ticker}:{job_id}")
      )
      _background_tasks.add(_t)
      _t.add_done_callback(_background_tasks.discard)
  ```

- [ ] **T4.6** Re-run test + PASS.

- [ ] **T4.7** Smoke import:
  ```
  cd backend && .venv/bin/python3 -c "from routes.ml_predict_api import router; print('OK')"
  ```

- [ ] **T4.8** Commit + push + gate:
  ```
  git add backend/routes/ml_predict_api.py backend/tests/routes/test_training_job_tracked.py
  git commit -m "fix(L4-leak-#6): wrap _run_training_job in _logged_task + track"
  git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#6'
  ```

- [ ] **T4.9** Pulse.

---

## Task 5: Final close-out (10 min)

- [ ] **T5.1** Update `docs/ROUND9_BACKEND_LEAK_AUDIT.md` — mark findings 5, 6, 7, 8, 9 as DONE with your commit SHAs (use the same pattern Pro used for findings 1-4).

- [ ] **T5.2** Append to `docs/ROUND9_PRO_SESSION_CLOSE.md` (or write a new sibling `docs/ROUND9_H26_FOLLOWUP_CLOSE.md`) a short table:
  ```
  | # | Audit ID | SHA | Subject |
  |---|----------|-----|---------|
  | 1 | #5 | <sha> | _prefetch_paid_oi tracked |
  | 2 | #7 | <sha> | replay engine task tracked |
  | 3 | #8-#9 | <sha> | paper_trader inserts logged |
  | 4 | #6 | <sha> | _run_training_job tracked |
  ```

- [ ] **T5.3** Run the audit's verification command once more — the remaining dangling-task count should drop to 0 in production code:
  ```
  grep -rn 'asyncio.create_task' backend/ --include="*.py" \
    | grep -v '\.venv/' | grep -v 'backend/tests/' \
    | grep -v 'await\|= ' | grep -v '_logged_task\|_background_tasks\|_log_failed_insert' \
    | wc -l
  ```
  Expected: ≤2 (websocket_streamer.py:96-98 are stored in a list inside `start()` — already managed, not a leak). If higher, you missed a site.

- [ ] **T5.4** Final commit:
  ```
  git add docs/
  git commit -m "docs(round-9-h26): close-out — 4 commits, audit findings #5-#9 fixed"
  git push origin main
  ```

- [ ] **T5.5** Final pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H26 :: DONE :: 5 commits landed :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H26_status.md
  ```

---

## Halt conditions (any one = STOP immediately)

1. Pre-flight finds wrong directory or missing Pro commits → STOP, ping architect.
2. Any task's failing-test step doesn't actually fail (means your test is wrong, not the code).
3. Any task's PASS step doesn't pass after your patch.
4. The wider pytest suite for a touched module (paper_trader, replay, ml_predict_api) shows REGRESSED test count.
5. An origin-state gate grep returns empty (push silently failed).
6. You realize a fix you planned would break `backend/services/ml/inference.py` or any other forbidden file — STOP and re-scope.
7. 15 min elapses without a pulse line — self-HALT.

Format for halt line:
```
[<UTC-timestamp>] H26 :: HALT :: <task#> :: <reason> :: HEAD=<sha>
```

---

## What success looks like

- 5 new commits on `origin/main` (one per task + close-out), each with grep/test evidence in the message
- Total backend `asyncio.create_task` fire-and-forget count in production code drops to ≤2 (only the websocket_streamer list, which is already managed)
- 4 new test files exist, each with at least 1 passing regression test
- `docs/ROUND9_BACKEND_LEAK_AUDIT.md` marks findings #5, #6, #7, #8, #9 as DONE
- `kanban/cards/agent_H26_status.md` has at least 8 pulse lines (1 per major step) ending in DONE
