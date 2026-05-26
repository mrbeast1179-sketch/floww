# DeepSeek Pro — Backend Hardening (2-hour Mission)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Round 9 backend hardening — comprehensive graceful `on_stop()` body + 3 dangling-asyncio-task leak fixes (from `docs/ROUND9_BACKEND_LEAK_AUDIT.md`) + auth gate on 2 leaky admin endpoints — in one ~2-hour DeepSeek Pro session.

**Architecture:** Replicate the already-committed H25 pattern (commit `e3844b7`) — `_background_tasks: Set[asyncio.Task]`, store task references with `add_done_callback(_background_tasks.discard)`, cancel-and-await on shutdown — for the 3 remaining unmanaged tasks. Add `Depends(verify_api_key)` to 2 admin endpoints following H11 pattern (commit `2d3a010`).

**Tech Stack:** Python 3.13 · FastAPI · asyncio · Motor (async MongoDB) · DuckDB · pytest with pytest-asyncio · uvicorn.

**Honest pre-condition snapshot by architect (2026-05-26 wrap-up):**
- `_background_tasks` set + `_shutdown_event` already exist at `server.py:82-83` (e3844b7)
- `_scheduler_task` already stored at `server.py:2620` but NOT cancelled in `on_stop()`
- `_mock_feed_task` already stored AND cancelled in `shutdown_ingestion()` at `server.py:2828-2845` — **no action needed for audit Leak #5**
- `on_stop()` at `server.py:2628` still has just `client.close()` — needs enlargement
- L4 audit's top-5 numbered list (audit doc lines 93-103) → **Leak #5 already done**, plus we add the `on_stop` body which covers Leak #2 cancellation
- Line numbers in audit doc drifted by ~10-50 lines since L1 wrote it — every task below grep-verifies before patching

**Time budget (~115 min + buffer):** Task 1 (15) · Task 2 (20) · Task 3 (20) · Task 4 (15) · Task 5 (15) · Task 6 (10) · Task 7 (10) · ~15 min slack for fetch/rebase/verify.

---

## File Structure

| Path | Change type | Why |
|------|-------------|-----|
| `backend/server.py:2628` | Modify (`on_stop()` body) | Enlarge to cancel `_scheduler_task` + remaining `_background_tasks`, then `client.close()` |
| `backend/server.py:1585` | Modify (`save_snapshot` task creation) | Wrap fire-and-forget in error handler + track in `_background_tasks` |
| `backend/services/duckdb_engine.py:232,237` | Modify (`start()` + `stop()`) | Store `_flush_loop` task ref, cancel + await in `stop()` |
| `backend/services/gex_history.py:191,203` | Modify (sync→async iteration) | Replace `for b in bars_cur:` with `async for b in bars_cur:` (2 sites) |
| `backend/routes/admin.py:41,61` | Modify (add auth dep) | `performance_stats` + `databento_usage` need `Depends(_require_admin_auth)` |
| `backend/tests/services/test_graceful_shutdown.py` | Create | Tests for `on_stop()` body cancelling background tasks |
| `backend/tests/services/test_duckdb_engine_shutdown.py` | Create | Test `_flush_loop` task is cancelled and awaited on `stop()` |
| `backend/tests/services/test_gex_history_async.py` | Create | Test `async for` works on Motor cursor (regression for bug #4) |
| `backend/tests/routes/test_admin_auth_extra.py` | Create | Test `/api/performance/stats` + `/databento/usage` return 401 without key |

---

## Pre-flight (DO NOT SKIP — anti-skip gate)

- [ ] **Pre-flight Step 1: Confirm canonical clone**

```bash
pwd
```
Expected: `/Users/nav/Documents/GitHub/floww`. **If anything else → STOP.** The stale clone is `/Users/nav/GitHub/floww` and has caused 3+ production incidents.

- [ ] **Pre-flight Step 2: Confirm H25 infrastructure already on origin**

```bash
git fetch origin && git log origin/main --oneline -10 | grep -E 'H25|graceful shutdown'
```
Expected: one line matching `e3844b7 feat(round-9-H25): graceful shutdown infrastructure ...`. **If missing → STOP** — base assumption of this plan is broken.

- [ ] **Pre-flight Step 3: Confirm working tree clean**

```bash
git status --short
```
Expected: `?? backend/tests/services/ml/test_ml_integration.py` (and nothing else). That's the intentionally-uncommitted broken test from the wrap-up session. **If other unstaged work → STOP and ask architect** — concurrent agent activity may be unfinished.

- [ ] **Pre-flight Step 4: Confirm pytest can collect baseline**

```bash
cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
```
Expected: a line ending in `tests collected` (target ~2,374). **If collection errors → STOP** — a prior agent broke something.

---

## Task 1: Enlarge `on_stop()` to cancel background tasks (15 min)

**Files:**
- Modify: `backend/server.py:2627-2629` (current minimal `on_stop`)
- Create: `backend/tests/services/test_graceful_shutdown.py`

- [ ] **Step 1: Locate current `on_stop` exactly**

```bash
grep -n '^async def on_stop\|^    client.close()' backend/server.py | head -5
```
Expected: shows `on_stop` and `client.close()` 1 line below. Confirm the function body is exactly:
```python
@app.on_event("shutdown")
async def on_stop():
    client.close()
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/services/test_graceful_shutdown.py`:

```python
"""Tests for the comprehensive on_stop() shutdown handler."""
import asyncio
import pytest


@pytest.mark.asyncio
async def test_on_stop_cancels_tracked_background_tasks():
    """on_stop() must cancel every task in _background_tasks."""
    # Import inside the test so the module-level infra is fresh
    from server import _background_tasks, on_stop

    # Spawn a never-ending task and register it
    async def _never_ends():
        await asyncio.sleep(3600)

    task = asyncio.create_task(_never_ends())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # Patch out client.close() so we don't kill the real Motor client
    import server as server_mod
    real_close = server_mod.client.close
    server_mod.client.close = lambda: None
    try:
        await on_stop()
    finally:
        server_mod.client.close = real_close

    assert task.cancelled() or task.done(), "background task was not cancelled"


@pytest.mark.asyncio
async def test_on_stop_sets_shutdown_event():
    """on_stop() must set the global _shutdown_event so loops can break out."""
    from server import _shutdown_event, on_stop

    _shutdown_event.clear()
    import server as server_mod
    real_close = server_mod.client.close
    server_mod.client.close = lambda: None
    try:
        await on_stop()
    finally:
        server_mod.client.close = real_close

    assert _shutdown_event.is_set(), "_shutdown_event was not set"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_graceful_shutdown.py -v 2>&1 | tail -10
```
Expected: 2 FAILED (test_on_stop_cancels — task not cancelled; test_on_stop_sets_shutdown_event — _shutdown_event not set).

- [ ] **Step 4: Replace `on_stop()` body**

Edit `backend/server.py` — replace the existing minimal `on_stop()`:

```python
@app.on_event("shutdown")
async def on_stop():
    """Graceful shutdown: signal loops, cancel tracked tasks, close MongoDB."""
    log.info("on_stop: shutdown signal received")
    _shutdown_event.set()

    # Cancel the scheduler task first so it stops queueing new work
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning(f"on_stop: scheduler task raised on cancel: {e}")

    # Cancel any remaining tracked background tasks
    pending = [t for t in _background_tasks if not t.done()]
    for t in pending:
        t.cancel()
    if pending:
        # Wait with a short bound so a stuck task can't block shutdown
        await asyncio.wait(pending, timeout=5.0)
        log.info(f"on_stop: cancelled {len(pending)} background task(s)")

    # Finally close MongoDB
    client.close()
    log.info("on_stop: shutdown complete")
```

- [ ] **Step 5: Re-run the test to verify it passes**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_graceful_shutdown.py -v 2>&1 | tail -10
```
Expected: 2 PASSED.

- [ ] **Step 6: Smoke-check server still imports**

```bash
cd backend && .venv/bin/python3 -c "from server import app, on_stop; print('imports OK')"
```
Expected: `imports OK`.

- [ ] **Step 7: Commit**

```bash
git add backend/server.py backend/tests/services/test_graceful_shutdown.py
git commit -m "$(cat <<'EOF'
feat(L4-leak-#2): comprehensive on_stop() body cancels tracked tasks

Closes Round-9 leak audit finding #2 (server.py:2623 _scheduler_task
fire-and-forget). H25 (commit e3844b7) added the infrastructure;
this commit uses it.

on_stop() now:
- sets _shutdown_event so polling loops can break
- cancels _scheduler_task and awaits its CancelledError
- cancels any remaining tasks in _background_tasks (5s bound)
- closes MongoDB last

Verification:
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_graceful_shutdown.py -v
2 passed
EOF
)"
git push origin main
```

- [ ] **Step 8: Origin gate**

```bash
git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#2'
```
Expected: one matching line. **If empty → STOP, the push failed.**

---

## Task 2: Track `save_snapshot()` task + add error handler (20 min)

**Files:**
- Modify: `backend/server.py:1585` (save_snapshot task creation)

L4 audit finding #1: `asyncio.create_task(save_snapshot(ticker, payload))` is fire-and-forget. If it raises, the exception silently dies and the snapshot is lost.

- [ ] **Step 1: Locate the exact line**

```bash
grep -n 'asyncio.create_task(save_snapshot' backend/server.py
```
Expected: one line (around 1585).

- [ ] **Step 2: Read the 5 lines of context**

```bash
sed -n '1580,1590p' backend/server.py
```
Note the indentation — it's inside a function. Replicate exactly when patching.

- [ ] **Step 3: Define a logging wrapper helper above the call site**

Add this helper function near the top of `server.py` (after the `_background_tasks` declaration around line 83):

```python
async def _logged_task(coro, name: str):
    """Run a coroutine and log any exception. Used to wrap fire-and-forget tasks."""
    try:
        return await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.warning(f"background task {name!r} raised: {type(e).__name__}: {e}")
```

- [ ] **Step 4: Replace the fire-and-forget at line ~1585**

Find:
```python
asyncio.create_task(save_snapshot(ticker, payload))
```

Replace with:
```python
_t = asyncio.create_task(_logged_task(save_snapshot(ticker, payload), f"save_snapshot:{ticker}"))
_background_tasks.add(_t)
_t.add_done_callback(_background_tasks.discard)
```

- [ ] **Step 5: Smoke import**

```bash
cd backend && .venv/bin/python3 -c "from server import _logged_task, _background_tasks; print('OK')"
```
Expected: `OK`.

- [ ] **Step 6: Verify the new pattern by grep**

```bash
grep -n '_logged_task(save_snapshot\|_background_tasks.add' backend/server.py
```
Expected: at least 2 hits (the new save_snapshot wrap + the existing scheduler/mock_feed registrations from H25).

- [ ] **Step 7: Commit**

```bash
git add backend/server.py
git commit -m "$(cat <<'EOF'
fix(L4-leak-#1): track save_snapshot task + log exceptions

Closes Round-9 leak audit finding #1 (server.py save_snapshot
fire-and-forget). Previously: if save_snapshot raised, the
exception silently disappeared and the snapshot was lost.

Now wrapped in _logged_task() helper that logs any non-cancel
exception, and the task is registered in _background_tasks so
on_stop() can cancel pending writes.

Verification:
$ grep -c '_logged_task(save_snapshot' backend/server.py
1
$ .venv/bin/python3 -c "from server import _logged_task; print('OK')"
OK
EOF
)"
git push origin main
```

- [ ] **Step 8: Origin gate**

```bash
git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#1'
```
Expected: one matching line.

---

## Task 3: Track `_flush_loop` task in duckdb_engine + cancel on stop (20 min)

**Files:**
- Modify: `backend/services/duckdb_engine.py:232,237`
- Create: `backend/tests/services/test_duckdb_engine_shutdown.py`

L4 audit finding #3: `_flush_loop()` is started fire-and-forget. `stop()` sets `_running = False` but never cancels or awaits the task — buffered data may be lost.

- [ ] **Step 1: Read the current `start()` and `stop()` methods**

```bash
sed -n '230,260p' backend/services/duckdb_engine.py
```
Confirm `start()` calls `asyncio.create_task(self._flush_loop())` and `stop()` sets `_running = False`. Note class name and any `self._...` task attribute pattern.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/services/test_duckdb_engine_shutdown.py`:

```python
"""Test that DuckDBEngine.stop() awaits the flush loop task."""
import asyncio
import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_stop_cancels_and_awaits_flush_loop():
    """After stop(), the flush_loop task must be done (not still running)."""
    from services.duckdb_engine import duckdb_engine

    # Start the engine (idempotent if already started)
    await duckdb_engine.start()
    task = duckdb_engine._flush_task  # attribute we are adding

    assert task is not None, "_flush_task should be stored on start"
    assert not task.done(), "_flush_task should be running after start"

    await duckdb_engine.stop()

    assert task.done(), "_flush_task should be done after stop"


@pytest.mark.asyncio
async def test_stop_is_idempotent():
    """Calling stop() twice should not raise."""
    from services.duckdb_engine import duckdb_engine
    await duckdb_engine.start()
    await duckdb_engine.stop()
    await duckdb_engine.stop()  # no exception
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_duckdb_engine_shutdown.py -v 2>&1 | tail -10
```
Expected: FAIL with `AttributeError: ... '_flush_task'` or similar.

- [ ] **Step 4: Patch `start()` to store the task**

In `backend/services/duckdb_engine.py`, find `async def start(self):` (around line 232) and the line:
```python
asyncio.create_task(self._flush_loop())
```
Replace with:
```python
self._flush_task = asyncio.create_task(self._flush_loop())
```

(If `start()` may run twice, guard with `if getattr(self, '_flush_task', None) is None or self._flush_task.done():` — read the file to decide.)

Also add to the class's `__init__` (or wherever attributes are initialized):
```python
self._flush_task: Optional[asyncio.Task] = None
```

- [ ] **Step 5: Patch `stop()` to cancel and await**

Find `async def stop(self):` (around line 237) and the line:
```python
self._running = False
```

Replace the body with:
```python
self._running = False
task = getattr(self, '_flush_task', None)
if task is not None and not task.done():
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
self._flush_task = None
```

- [ ] **Step 6: Re-run the test to verify it passes**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_duckdb_engine_shutdown.py -v 2>&1 | tail -10
```
Expected: 2 PASSED.

- [ ] **Step 7: Run the wider duckdb test file to verify no regression**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/ -k duckdb -v 2>&1 | tail -10
```
Expected: all duckdb-related tests still pass.

- [ ] **Step 8: Commit**

```bash
git add backend/services/duckdb_engine.py backend/tests/services/test_duckdb_engine_shutdown.py
git commit -m "$(cat <<'EOF'
fix(L4-leak-#3): track duckdb _flush_loop task, cancel+await on stop()

Closes Round-9 leak audit finding #3. Previously stop() set
_running=False but the task itself was never cancelled; buffered
writes could be silently dropped on event-loop shutdown.

Verification:
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_duckdb_engine_shutdown.py -v
2 passed
EOF
)"
git push origin main
```

- [ ] **Step 9: Origin gate**

```bash
git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#3'
```
Expected: one matching line.

---

## Task 4: Fix `async for` bug in gex_history.py (15 min)

**Files:**
- Modify: `backend/services/gex_history.py:191,203`
- Create: `backend/tests/services/test_gex_history_async.py`

L4 audit finding #4: `for b in bars_cur:` and `for chain in chains_cur:` use sync iteration on Motor async cursors. This raises `TypeError` at runtime AND leaks the connection.

- [ ] **Step 1: Read the two sites and the surrounding function signature**

```bash
sed -n '180,215p' backend/services/gex_history.py
```
Confirm both lines use `for ... in ..._cur:` and the cursor came from a Motor `.find()` (look 5-10 lines above each).

- [ ] **Step 2: Write the failing test**

Create `backend/tests/services/test_gex_history_async.py`:

```python
"""Regression test: gex_history iterates Motor cursors with async for."""
import inspect
import pytest


def test_gex_history_uses_async_for_on_cursors():
    """The bars_cur and chains_cur loops must be async for, not sync for."""
    import services.gex_history as gh
    src = inspect.getsource(gh)
    # No sync iteration on the *_cur variables
    assert 'for b in bars_cur' not in src, \
        "bars_cur must be iterated with `async for`"
    assert 'for chain in chains_cur' not in src, \
        "chains_cur must be iterated with `async for`"
    # And the async version IS present
    assert 'async for b in bars_cur' in src, \
        "async for b in bars_cur not found"
    assert 'async for chain in chains_cur' in src, \
        "async for chain in chains_cur not found"
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_gex_history_async.py -v 2>&1 | tail -10
```
Expected: FAIL with assertion `bars_cur must be iterated with async for`.

- [ ] **Step 4: Patch line 191**

Find:
```python
    for b in bars_cur:
```
Replace with:
```python
    async for b in bars_cur:
```

- [ ] **Step 5: Patch line 203**

Find:
```python
    for chain in chains_cur:
```
Replace with:
```python
    async for chain in chains_cur:
```

- [ ] **Step 6: Verify both sites changed**

```bash
grep -n 'async for b in bars_cur\|async for chain in chains_cur' backend/services/gex_history.py
```
Expected: 2 lines, one per pattern.

- [ ] **Step 7: Re-run the regression test**

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_gex_history_async.py -v 2>&1 | tail -10
```
Expected: 1 PASSED.

- [ ] **Step 8: Verify the enclosing functions are `async def`**

```bash
sed -n '180,210p' backend/services/gex_history.py | grep -E '^\s*(async )?def '
```
Expected: every function containing the `async for` is itself declared `async def`. **If any sync `def` wraps an `async for` → STOP and report**, that means the bug is deeper than the audit thought.

- [ ] **Step 9: Commit**

```bash
git add backend/services/gex_history.py backend/tests/services/test_gex_history_async.py
git commit -m "$(cat <<'EOF'
fix(L4-leak-#4): replace sync `for` with `async for` on Motor cursors

Closes Round-9 leak audit finding #4 (gex_history.py:191,203).
Sync iteration on a Motor async cursor raises TypeError and
leaks the underlying MongoDB connection.

Verification:
$ grep -c 'async for b in bars_cur\|async for chain in chains_cur' backend/services/gex_history.py
2
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_gex_history_async.py -v
1 passed
EOF
)"
git push origin main
```

- [ ] **Step 10: Origin gate**

```bash
git fetch origin && git log origin/main --oneline -1 | grep 'L4-leak-#4'
```
Expected: one matching line.

---

## Task 5: H12 auth on `/api/performance/stats` + `/databento/usage` (15 min)

**Files:**
- Modify: `backend/routes/admin.py:41,61`
- Create: `backend/tests/routes/test_admin_auth_extra.py`

H11 (commit `2d3a010`) already added `Depends(_require_admin_auth)` to 6 admin trading routes. These 2 endpoints were missed and leak performance data + Databento spend.

- [ ] **Step 1: Read the H11 auth pattern in the same file**

```bash
grep -n 'Depends(_require_admin_auth)' backend/routes/admin.py | head -10
```
Expected: ≥6 hits showing the established pattern.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/routes/test_admin_auth_extra.py`:

```python
"""H12: /api/performance/stats and /databento/usage must require X-API-Key."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "test-key-h12")
    from server import app
    return TestClient(app)


def test_performance_stats_requires_auth(client):
    r = client.get("/api/performance/stats")
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_performance_stats_succeeds_with_key(client):
    r = client.get("/api/performance/stats", headers={"X-API-Key": "test-key-h12"})
    assert r.status_code == 200, f"expected 200, got {r.status_code}"


def test_databento_usage_requires_auth(client):
    r = client.get("/databento/usage")
    assert r.status_code == 401, f"expected 401, got {r.status_code}"


def test_databento_usage_succeeds_with_key(client):
    r = client.get("/databento/usage", headers={"X-API-Key": "test-key-h12"})
    # 200 OK or 500 (DB may not be configured in test) — either proves the auth gate passed
    assert r.status_code in (200, 500), f"expected 200/500 (auth passed), got {r.status_code}"
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && .venv/bin/python3 -m pytest tests/routes/test_admin_auth_extra.py -v 2>&1 | tail -10
```
Expected: 2 of 4 FAIL (the no-auth cases — returning 200 instead of 401).

- [ ] **Step 4: Add auth dep to `performance_stats`**

In `backend/routes/admin.py`, find:
```python
@router.get("/api/performance/stats")
async def performance_stats():
```
Replace with:
```python
@router.get("/api/performance/stats")
async def performance_stats(_: bool = Depends(_require_admin_auth)):
```

- [ ] **Step 5: Add auth dep to `databento_usage`**

Find:
```python
@router.get("/databento/usage")
async def databento_usage():
```
Replace with:
```python
@router.get("/databento/usage")
async def databento_usage(_: bool = Depends(_require_admin_auth)):
```

- [ ] **Step 6: Re-run the tests to verify all 4 pass**

```bash
cd backend && .venv/bin/python3 -m pytest tests/routes/test_admin_auth_extra.py -v 2>&1 | tail -10
```
Expected: 4 PASSED.

- [ ] **Step 7: Verify H11's 6 routes still pass**

```bash
cd backend && .venv/bin/python3 -m pytest tests/routes/ -k admin -v 2>&1 | tail -15
```
Expected: H11 tests still pass, total ≥10 admin tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/routes/admin.py backend/tests/routes/test_admin_auth_extra.py
git commit -m "$(cat <<'EOF'
fix(H12): require X-API-Key on /api/performance/stats + /databento/usage

Completes the H11 admin-auth sweep. These 2 endpoints were missed
in commit 2d3a010; they leak rate-limit IP counts, uptime, and
full Databento spend history.

Verification:
$ cd backend && .venv/bin/python3 -m pytest tests/routes/test_admin_auth_extra.py -v
4 passed
EOF
)"
git push origin main
```

- [ ] **Step 9: Origin gate**

```bash
git fetch origin && git log origin/main --oneline -1 | grep 'H12'
```
Expected: one matching line.

---

## Task 6: Full pytest sweep + leak-audit re-grep (10 min)

**Files:** none modified — read-only verification.

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5
```
Expected: passing count ≥ baseline from the pre-flight collect step. **If lower → STOP and report which test regressed.**

- [ ] **Step 2: Re-grep dangling tasks per the audit's verification commands**

```bash
grep -rn 'asyncio.create_task' backend/ --include="*.py" \
  | grep -v '\.venv/' | grep -v 'backend/tests/' \
  | grep -v 'await\|= ' | grep -v '_logged_task\|_background_tasks'
```
Expected: ≤3 remaining lines (replay.py:64, paper_trader.py:411, paper_trader.py:427 — audit Medium-severity items NOT in tonight's top-5 scope).

- [ ] **Step 3: Re-grep the gex_history bug**

```bash
grep -n 'for b in bars_cur\|for chain in chains_cur' backend/services/gex_history.py
```
Expected: 0 hits (both are now `async for`).

- [ ] **Step 4: Confirm all 5 H12 + L4 commits visible on origin**

```bash
git log origin/main --oneline -10 | grep -E 'L4-leak|H12'
```
Expected: 4 commit lines (Task 1 = leak-#2, Task 2 = leak-#1, Task 3 = leak-#3, Task 4 = leak-#4, Task 5 = H12 — that's 5 lines).

---

## Task 7: Update the leak-audit doc to mark fixed items + close-out commit (10 min)

**Files:**
- Modify: `docs/ROUND9_BACKEND_LEAK_AUDIT.md` (mark leaks 1-4 as DONE)
- Create: `docs/ROUND9_PRO_SESSION_CLOSE.md` (one-page session log)

- [ ] **Step 1: Mark fixed leaks in the audit doc**

Edit `docs/ROUND9_BACKEND_LEAK_AUDIT.md` lines 19-22 (the `| 1 |`, `| 2 |`, `| 3 |`, `| 4 |` rows of the findings table). For each, change the `Severity` column from `High` (or `Med`) to `DONE <YYYY-MM-DD> <SHA>`. Example for finding #1:

```markdown
| 1 | `backend/server.py:1573` | dangling asyncio task | DONE 2026-05-27 <Task-2-SHA> | (see commit message) |
```

Also update the `## Top 5 for L4 to Fix` section (lines 93-103): prefix each fixed item with `~~` and `~~` to strike it through, and add a note after the colon like `[DONE in commit <SHA>]`.

- [ ] **Step 2: Generate the close-out doc from real git data (no manual fill)**

Run this exact script — it produces `docs/ROUND9_PRO_SESSION_CLOSE.md` with real SHAs:

```bash
cd /Users/nav/Documents/GitHub/floww
DATE=$(date -u +%Y-%m-%d)
PASS_COUNT=$(cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | grep -oE '[0-9]+ passed' | head -1 | awk '{print $1}')
SHA_T1=$(git log origin/main --oneline | grep 'L4-leak-#2' | head -1 | awk '{print $1}')
SHA_T2=$(git log origin/main --oneline | grep 'L4-leak-#1' | head -1 | awk '{print $1}')
SHA_T3=$(git log origin/main --oneline | grep 'L4-leak-#3' | head -1 | awk '{print $1}')
SHA_T4=$(git log origin/main --oneline | grep 'L4-leak-#4' | head -1 | awk '{print $1}')
SHA_T5=$(git log origin/main --oneline | grep 'fix(H12)' | head -1 | awk '{print $1}')

cat > docs/ROUND9_PRO_SESSION_CLOSE.md <<EOF
# Round 9 — DeepSeek Pro Backend Hardening · Session Close

**Session date:** ${DATE}
**Plan:** \`docs/superpowers/plans/2026-05-26-deepseek-pro-backend-hardening.md\`

## Commits landed on origin/main

| Task | SHA | Subject |
|------|-----|---------|
| 1 | \`${SHA_T1}\` | feat(L4-leak-#2): comprehensive on_stop() body |
| 2 | \`${SHA_T2}\` | fix(L4-leak-#1): track save_snapshot task |
| 3 | \`${SHA_T3}\` | fix(L4-leak-#3): track duckdb _flush_loop task |
| 4 | \`${SHA_T4}\` | fix(L4-leak-#4): async for on Motor cursors |
| 5 | \`${SHA_T5}\` | fix(H12): admin auth on /performance/stats + /databento/usage |

## Test impact

- Final pytest pass count: **${PASS_COUNT} passed**
- 0 regressions vs pre-flight baseline (verified by Task 6 Step 1)

## L4 audit status after this session

- **5 of 14** findings fixed (4 Highs + 1 Med [gex_history]) + #5 already done by H25
- **9 remaining**: 4 Med (replay/paper_trader x2/ml_predict_api) + 4 Low + 1 file-handle Low
- Recommendation: 4 remaining Mediums batch cleanly into a single ~45-min follow-up session

## Open follow-ups (deferred — not in this session's scope)

- \`backend/tests/services/ml/test_ml_integration.py\` (stale paths) — uncommitted in working tree, needs separate triage
- L4 Mediums (4 items above) — Round 10 candidate
- L2/L3 frontend setInterval/setTimeout audits — not yet started
EOF

echo "--- generated doc ---"
cat docs/ROUND9_PRO_SESSION_CLOSE.md
```

Expected output: the script prints the doc with all 5 SHAs filled in. **If any SHA is empty → STOP** — the corresponding commit didn't land, fix that before continuing.

- [ ] **Step 3: Commit both docs together**

```bash
git add docs/ROUND9_BACKEND_LEAK_AUDIT.md docs/ROUND9_PRO_SESSION_CLOSE.md
git commit -m "$(cat <<'EOF'
docs(round-9-pro): close-out — 5 commits, 4 of 14 leaks fixed

Plan: docs/superpowers/plans/2026-05-26-deepseek-pro-backend-hardening.md

Marked leaks 1-4 as DONE in ROUND9_BACKEND_LEAK_AUDIT.md (audit
table updated with SHA + date). Top-5 section strikes through
the completed items.

ROUND9_PRO_SESSION_CLOSE.md summarizes the session: 5 commits,
SHAs, test delta, remaining audit items.
EOF
)"
git push origin main
```

- [ ] **Step 4: Final origin gate**

```bash
git fetch origin && git log origin/main --oneline -8
```
Expected: the 6 commits from this session (5 fixes + 1 close-out doc), all visible on origin in order.

---

## Halt conditions (when to stop and ping architect)

Stop immediately and write a status line to `kanban/cards/agent_DSPRO_status.md` if **any** of these happen:

1. Pre-flight Step 1 shows wrong directory (stale clone)
2. Pre-flight Step 2 can't find commit `e3844b7`
3. Pre-flight Step 4 shows pytest collection errors above 0
4. Any task's Step 7/8 (origin gate) fails — the push didn't land
5. Full pytest sweep (Task 6 Step 1) shows REGRESSED tests vs baseline
6. Audit's "verification commands" in Task 6 Step 2 show MORE dangling tasks than expected (means a fix introduced new ones)
7. Any commit-message verification claim grep-fails

Format for the halt line:
```
[<UTC-timestamp>] DSPRO :: HALT :: <task#> :: <reason> :: HEAD=<sha>
```

---

## Forbidden during this session

- `backend/services/ml/inference.py` — architect-locked, do not touch
- `backend/services/dash_ui.py` — Round 7 frozen, do not touch
- `backend/tests/conftest.py` — Round 9 stale-audit verified not broken; do not touch
- Any `.joblib`, `.pt`, or model `.json` artifact in `backend/models/`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `--force`, `--no-verify`, `--amend` on any prior commit, `git rebase --abort`, `git reset --hard`, `git clean -fd`
- Marking any test `@pytest.mark.xfail` or `@pytest.mark.skip` — if a test fails, fix the cause; if it can't be fixed, HALT and ping architect
