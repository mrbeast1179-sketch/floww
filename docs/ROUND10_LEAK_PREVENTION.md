# Round-10 Backend Leak Prevention Patterns

Synthesizes the H25/Pro/A1 work into reusable patterns. Future agents
adding new async background work MUST follow these.

## Pattern 1 -- Long-running background task (scheduler loop, mock feed)

Use when: a coroutine runs indefinitely in the background (e.g. scheduler
loop, mock data feed).

```python
from server import _background_tasks, _logged_task

_t = asyncio.create_task(_logged_task(my_long_loop(), "my_long_loop"))
_background_tasks.add(_t)
_t.add_done_callback(_background_tasks.discard)
```

Why: `on_stop()` iterates `_background_tasks` and cancel+awaits each
with a 5s bound. Without registration, tasks outlive the event loop.

## Pattern 2 -- Per-event fire-and-forget DB write

Use when: a single insert/write is fired per event (e.g. trade logged,
position snapshot saved).

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

## Pattern 3 -- One-off task with cancellation endpoint (replay, training)

Use when: a background job is started via one API endpoint and stopped via
another.

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

- Bare `asyncio.create_task(coro)` with no storage -- silently leaks errors AND task ref
- `for x in async_cursor:` (Motor) -- use `async for x in async_cursor`
- `except:` bare -- use `except Exception:` (lint gate DS4 catches this)
- Mutable module-level dict cache with no eviction policy -- use TTL or LRU

## Audit history

| Round | Findings | Closed |
|-------|----------|--------|
| R9 L1 audit | 14 | 14 (4 Pro + 5 A1 + 5 H25/pre-fix) |
