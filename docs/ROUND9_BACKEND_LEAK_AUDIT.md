# Round 9 Backend Memory-Leak Audit

Generated 2026-05-26T02:05:00Z, READ-ONLY audit by L1.
No code changes -- fixes are L4's job after this audit landed.

## Summary

Total findings: 14
High severity: 4
Med severity: 6
Low severity: 4

---

## Findings

| # | File:Line | Type | Severity | Fix Suggestion |
|---|-----------|------|----------|----------------|
| 1 | `backend/server.py:1573` | dangling asyncio task | DONE 2026-05-27 5c60a2a | Wrapped in `_logged_task()` + tracked in `_background_tasks` |
| 2 | `backend/server.py:2623` | dangling asyncio task | DONE 2026-05-27 5c60a2a | Cancelled + awaited in enlarged `on_stop()` body |
| 3 | `backend/server.py:2817` | dangling asyncio task | DONE 2026-05-26 e3844b7 | Already fixed by H25 (commit e3844b7) — `_mock_feed_task` stored + cancelled in `shutdown_ingestion()` |
| 4 | `backend/services/duckdb_engine.py:180` | dangling asyncio task | DONE 2026-05-27 d322d79 | `_flush_task` stored + cancelled/awaited in `stop()` + double-start guard |
| 5 | `backend/server.py:2182` | dangling asyncio task | Med | `_prefetch_paid_oi()` is fire-and-forget inside the scheduler loop. If the scheduler runs faster than prefetch completes, tasks accumulate. Store reference or use a semaphore to limit concurrency. |
| 6 | `backend/routes/ml_predict_api.py:246` | dangling asyncio task | Med | `_run_training_job()` is fire-and-forget. If training fails, the error is silently lost. Store the task and add error logging, or use a job-tracking dict. |
| 7 | `backend/routes/replay.py:64` | dangling asyncio task | Med | `engine.start()` is fire-and-forget. The engine task is never stored or cancelled. Store the task and cancel in the `/stop` endpoint. |
| 8 | `backend/services/paper_trader.py:411` | dangling asyncio task | Med | `self.mongo.insert_one(order)` is fire-and-forget. If the insert fails, the order is silently lost. Store the task or use `await` with try/except. |
| 9 | `backend/services/paper_trader.py:427` | dangling asyncio task | Med | Same pattern as line 411 -- `self.mongo.insert_one(doc)` is fire-and-forget. Trade records may be lost on failure. |
| 10 | `backend/services/gex_history.py:186,197` | sync iteration on async cursor | DONE 2026-05-27 27d3598 | Changed to `async for` + made `build_gex_history` async |
| 11 | `backend/services/code_suggester.py:249` | file handle leak (low) | Low | `open(cfg_path)` is used without `with` statement. If `json.load()` raises, the file handle leaks. Use `with open(cfg_path) as f: cfg = json.load(f)`. |
| 12 | `backend/error_tracking.py:107` | unbounded dict growth (low) | Low | `_error_counts` dict keys grow with every unique error type string. If error types contain dynamic content (e.g., with IDs), this grows without bound. Use a fixed set of error type buckets. |
| 13 | `backend/error_tracking.py:117` | unbounded list growth (low) | Low | `_error_log` is capped at 1000 entries (good), but `_error_counts` dict is never pruned. Over long runtimes with many error types, this grows. Add periodic pruning or use `MAX_ERROR_TYPES`. |
| 14 | `backend/server.py:89` | unbounded dict growth (low) | Low | `_rate_limits` dict grows with every new IP. The cleanup at line 141 only triggers when `len > 10000` and only removes IPs with empty deques. Under sustained traffic from many IPs, this grows. Add TTL-based eviction. |

---

## Detailed Analysis

### Pattern 1: Unbounded Module-Level Caches

**Result: No findings in production code.**

- `^_cache = {}` -- zero matches in `backend/` (excluding `.venv/`).
- `lru_cache` decorators in `config/secrets.py` all use `maxsize=1` (safe).
- `dash_ui.py:232` uses `lru_cache(maxsize=32)` (safe).
- `_rate_limits` (server.py:89) -- see Finding #14 above.
- `_error_counts` / `_error_log` (error_tracking.py) -- see Findings #12-13 above.

### Pattern 2: Dangling Asyncio Tasks

**Result: 9 production findings (4 High, 5 Med).**

The most critical pattern in this codebase. `asyncio.create_task()` is used 12 times
in production code. Of those, 4 store the result in a variable (websocket_streamer,
ingestion_pipeline, scheduler options), while 8 are fire-and-forget.

Fire-and-forget tasks are problematic because:
1. Exceptions are silently swallowed (no `await` means no error propagation).
2. Tasks may outlive the event loop on shutdown (no cancel/await).
3. Under load, unbounded task creation can exhaust memory.

### Pattern 3: MongoDB Cursor Leaks

**Result: 1 finding (Med).**

Most `.find()` calls in the codebase properly consume the cursor via:
- `await cursor.to_list(length=N)` -- used in server.py, ml/features.py, ml/registry.py, ml/retrain.py, routes/analytics.py, routes/admin.py, routes/heatseeker.py, routes/ml_api.py, data/repositories.py
- `async for doc in cursor` -- used in routes/heatseeker.py, data/repositories.py, order_router.py

**Finding #10**: `gex_history.py` uses synchronous `for` loops on what appear to be
async Motor cursors. This is a bug (will raise TypeError at runtime) and also a
potential connection leak since the cursor is never properly consumed.

### Pattern 4: File Handles Outside `with` Blocks

**Result: 1 finding (Low).**

`backend/services/code_suggester.py:249` -- `open(cfg_path)` without `with`.
All other `open()` calls in production code use `with` blocks correctly.

### Pattern 5: Module-Level Singletons Holding Per-Request Refs

**Result: No critical findings.**

- `_redis_client` (cache.py) -- singleton pattern, safe.
- `_memory_client` (memory_integration.py) -- singleton pattern, safe.
- `_hist_client` / `_cache` (databento_provider.py) -- singleton pattern, safe.
- `_registry_instance` (ml/registry.py) -- singleton pattern, safe.
- `_alert_rules` (server.py:2220) -- list of alert rules, only grows when rules are added via API. Not a leak, but has no size limit.
- `_ingestion_pipeline` / `_mock_feed` / `_paper_engine` (server.py) -- singletons, properly cleaned up on shutdown.

---

## Top 5 for L4 to Fix

1. ~~**`backend/server.py:2623`**~~ [DONE in commit 5c60a2a] -- `_scheduler_loop()` fire-and-forget with no shutdown cancel. This is the highest-impact leak: the scheduler task runs forever and is never cleaned up. On server restart or reload, a new task is spawned while the old one may still run.

2. ~~**`backend/server.py:1573`**~~ [DONE in commit 5c60a2a] -- `save_snapshot()` fire-and-forget. Called on every snapshot save. Under high-frequency tick data, this creates unbounded tasks. Failed saves are silently lost.

3. ~~**`backend/services/duckdb_engine.py:180`**~~ [DONE in commit d322d79] -- `_flush_loop()` fire-and-forget with no task reference stored. On `stop()`, the loop exits via `_running = False` but the task is never awaited, so buffered data may be lost.

4. ~~**`backend/services/gex_history.py:186,197`**~~ [DONE in commit 27d3598] -- Synchronous `for` on async Motor cursors. This is a runtime bug (TypeError) and also leaks MongoDB connections. Must be `async for`.

5. ~~**`backend/server.py:2817`**~~ [DONE in commit e3844b7 (H25)] -- `_mock_feed.start()` fire-and-forget. The mock feed task runs forever with no stored reference. On shutdown, `_mock_feed.stop()` is called but the underlying task is never cancelled.

---

## Verification Commands

```bash
# Pattern 1: Unbounded caches
$ grep -rn '^_cache\s*=\s*{}' backend/ --include="*.py"
(no results in production code)

# Pattern 2: Dangling asyncio tasks
$ grep -rn 'asyncio.create_task' backend/ --include="*.py" | grep -v '\.venv/' | grep -v 'backend/tests/' | grep -v 'await\|= '
backend/server.py:1573:    asyncio.create_task(save_snapshot(ticker, payload))
backend/server.py:2182:                asyncio.create_task(_prefetch_paid_oi())
backend/server.py:2623:        asyncio.create_task(_scheduler_loop())
backend/server.py:2817:        asyncio.create_task(_mock_feed.start())
backend/routes/replay.py:64:    asyncio.create_task(engine.start())
backend/routes/ml_predict_api.py:246:    asyncio.create_task(_run_training_job(job_id, ticker, days, n_splits))
backend/services/paper_trader.py:411:                asyncio.create_task(self.mongo.insert_one(order))
backend/services/paper_trader.py:427:                asyncio.create_task(self.mongo.insert_one(doc))
backend/services/duckdb_engine.py:180:        asyncio.create_task(self._flush_loop())
backend/services/websocket_streamer.py:96:            asyncio.create_task(self._tick_broadcast_loop()),
backend/services/websocket_streamer.py:97:            asyncio.create_task(self._analytics_broadcast_loop()),
backend/services/websocket_streamer.py:98:            asyncio.create_task(self._toxicity_broadcast_loop()),

# Pattern 3: MongoDB cursors (gex_history sync-for bug)
$ grep -n 'for.*bars_cur\|for.*chains_cur' backend/services/gex_history.py
190:    for b in bars_cur:
201:    for chain in chains_cur:

# Pattern 4: File handles without with
$ grep -rn '\bopen(' backend/ --include="*.py" | grep -v '\.venv/' | grep -v 'backend/tests/' | grep -v 'with open\|\.open('
backend/services/code_suggester.py:249:                    cfg = json.load(open(cfg_path))

# Pattern 5: Global statements
$ grep -rn 'global ' backend/ --include="*.py" | grep -v '\.venv/' | grep -v 'backend/tests/' | head -10
backend/databento_provider.py:23:    global _hist_client, DBN_KEY
backend/databento_provider.py:177:    global _cache
backend/server.py:2027:    global PAID_TICKERS
backend/server.py:2059:    global PAID_TICKERS
backend/server.py:2250:    global _alert_rules
backend/server.py:2620:    global _scheduler_started
backend/server.py:2800:    global _ingestion_pipeline, _mock_feed
backend/server.py:2825:    global _ingestion_pipeline, _mock_feed
backend/server.py:2844:    global _paper_engine
```
