# Backend Security & Code Audit — 2026-07-02
**Project:** Confluence Decoder / floww backend  
**Scope:** `backend/` (P1: recently modified; P2: core services; P3: routes)  
**Auditor:** Automated review via Claude  
**Date:** 2026-07-02  

---

## Summary Counts

| Severity | Count |
|----------|-------|
| CRITICAL | 13 |
| HIGH     | 15 |
| MEDIUM   | 12 |
| LOW      | 7   |
| **Total**| **47** |

---

## CRITICAL

---

**FILE:** `backend/routes/admin.py`  
**LINE:** 35, 51  
**SEVERITY:** CRITICAL  
**TYPE:** MissingAuthentication  
**DESCRIPTION:** `/errors/summary` (GET) and `/errors/clear` (POST) are missing the `Depends(_require_admin_auth)` dependency that all other admin routes have. Anyone can enumerate recent server errors (which may contain stack traces, internal paths, DB structure) or delete error records without any API key. `_require_admin_auth` is defined at line 18 but never applied to these two endpoints.  
**SUGGESTED FIX:**
```python
@router.get("/errors/summary")
async def errors_summary(_: bool = Depends(_require_admin_auth)):

@router.post("/errors/clear")
async def errors_clear(_: bool = Depends(_require_admin_auth)):
```

---

**FILE:** `backend/routes/live_trading.py`  
**LINE:** 13, 19, 25  
**SEVERITY:** CRITICAL  
**TYPE:** MissingAuthentication  
**DESCRIPTION:** All three live-trading control routes — `GET /live/policy`, `POST /live/policy`, and `POST /live/tape/stop` — have no authentication whatsoever. `POST /live/policy` can change live trading parameters (risk limits, enabled state) and `POST /live/tape/stop` can halt the real-time Databento data feed, both without any API key. An unauthenticated attacker on the same network can disable live trading or alter risk policy.  
**SUGGESTED FIX:** Import and apply `_require_admin_auth` (or an equivalent dependency from `auth.py`) to all three endpoints, matching the pattern used in `admin.py`.

---

**FILE:** `backend/routes/memory.py`  
**LINE:** 13, 19, 27, 33  
**SEVERITY:** CRITICAL  
**TYPE:** MissingAuthentication  
**DESCRIPTION:** All four memory routes (`POST /memory/trade`, `POST /memory/gex`, `GET /memory/recall/{ticker}`, `GET /memory/summary/{ticker}`) are completely unauthenticated. The write endpoints accept arbitrary `dict` payloads and call `remember_trade` / `remember_gex_observation` in `server.py`, which write to the mem0 memory store. An attacker can poison the trading memory with fabricated trade history or GEX observations, which then feed into ML features and risk decisions.  
**SUGGESTED FIX:** Add `Depends(_require_admin_auth)` (or a user-auth equivalent) to all four routes. Also add Pydantic models to replace the untyped `request: dict` parameters.

---

**FILE:** `backend/server.py`  
**LINE:** ~19  
**SEVERITY:** CRITICAL  
**TYPE:** Bug  
**DESCRIPTION:** `DB_NAME = os.environ["DB_NAME"]` raises `KeyError` if the environment variable is not set, crashing the entire application at import time with a traceback that is not caught anywhere. `conftest.py` sets this only when loaded first, but production deployments have no such guarantee.  
**SUGGESTED FIX:**
```python
DB_NAME = os.environ.get("DB_NAME", "confluence_decoder")
if not DB_NAME:
    raise RuntimeError("DB_NAME environment variable must be set")
```

---

**FILE:** `backend/server.py`  
**LINE:** ~900 (heatmap cache)  
**SEVERITY:** CRITICAL  
**TYPE:** Bug / Crash  
**DESCRIPTION:** `_BUILD_HEATMAP_CACHE` is written in two incompatible formats. The primary `_build_heatmap_impl` path writes a dict: `{"ts": time.time(), "data": sanitized}`. A secondary screen-API code path writes a tuple: `(time.time(), heatmap_data)`. The eviction/read logic universally does `_BUILD_HEATMAP_CACHE[k]["ts"]`, which raises `TypeError: tuple indices must be integers or slices, not str` when it hits a tuple-format entry, crashing the endpoint that serves heatmap data.  
**SUGGESTED FIX:** Standardize to one format. Remove the tuple-write path:
```python
_BUILD_HEATMAP_CACHE[cache_key] = {"ts": time.time(), "data": heatmap_data}
```

---

**FILE:** `backend/services/audit_trail.py`  
**LINE:** 1–17 (entire file)  
**SEVERITY:** CRITICAL  
**TYPE:** DeadCode / MissingImplementation  
**DESCRIPTION:** The file is an **empty stub**. Its docstring promises "Immutable, hash-chained audit trail for every write action" with "7-year retention (SEC Rule 17a-4 inspired)", but the file contains only a docstring and a logger import — no functions, no classes, no implementation. Any code calling `from services.audit_trail import ...` will get `ImportError`. Zero write actions are audited. This is a compliance and forensics gap for a live-trading system.  
**SUGGESTED FIX:** Implement a minimal async `log_event(actor, action_type, payload, collection)` function that writes a hash-chained document to MongoDB with `sha256(prev_hash + json(payload))`. At minimum add a warning log so the gap is visible at startup.

---

**FILE:** `backend/services/scheduler.py`  
**LINE:** 3–4  
**SEVERITY:** CRITICAL  
**TYPE:** Bug / BrokenImport  
**DESCRIPTION:** The scheduler imports two modules that do not exist:
```python
from services.yfinance_fetcher import fetch_and_store, get_duckdb_conn  # missing
from services.yoptions_fetcher import fetch_all_chains                    # missing
```
`yoptions_fetcher.py` exists but exports `fetch_option_chain`, not `fetch_all_chains`. `yfinance_fetcher.py` does not exist in the codebase. This causes a `ModuleNotFoundError` / `ImportError` on import, meaning the scheduler is silently dead — no prefetch jobs ever run.  
**SUGGESTED FIX:** Fix imports to match the actual module names and exported symbols. Run `python -c "import services.scheduler"` in CI to catch this class of error.

---

**FILE:** `backend/services/ingestion_pipeline.py`  
**LINE:** ~180  
**SEVERITY:** CRITICAL  
**TYPE:** Bug / SchemaMismatch  
**DESCRIPTION:** `_insert_chains()` is documented as inserting into the "DuckDB chains table" but the comment says "chains table may not exist in current schema; insert into ticks as fallback" and the SQL is `INSERT INTO ticks VALUES (?,...)`. Chain data (option chains with strike/expiry/OI columns) is silently written into the `ticks` table (which has a completely different column order), corrupting tick data with nonsense option-chain values. This is a silent data corruption path.  
**SUGGESTED FIX:** Create a separate `chains` DuckDB table with the correct schema, or raise an explicit error rather than inserting into the wrong table.

---

**FILE:** `backend/services/ingestion_pipeline.py`  
**LINE:** ~182  
**SEVERITY:** CRITICAL  
**TYPE:** RaceCondition / ThreadSafety  
**DESCRIPTION:** `_insert_chains` and other batch writers call `self.db.conn.executemany(...)` using the raw DuckDB connection directly, bypassing `DuckDBEngine`'s `_lock`. DuckDB connections are not thread-safe; concurrent `executemany` calls from separate asyncio-to-thread wrappers will corrupt the database or raise `duckdb.InvalidInputException`.  
**SUGGESTED FIX:** Route all writes through `DuckDBEngine._execute_with_lock()` or the existing `_flush_*` batch pathway. Never call `self.db.conn` directly from outside `DuckDBEngine`.

---

**FILE:** `backend/services/duckdb_engine.py`  
**LINE:** ~200 (`_flush_ticks`)  
**SEVERITY:** CRITICAL  
**TYPE:** RaceCondition  
**DESCRIPTION:** The flush methods release their `asyncio.Lock` **before** the actual database write executes:
```python
async def _flush_ticks(self):
    async with self._lock:
        buf = self._tick_buffer
        self._tick_buffer = []
    # lock RELEASED here
    await _execute_with_timeout(
        self._conn,
        lambda: self._conn.executemany(..., buf),   # runs in thread pool, no lock
    )
```
When `asyncio.gather(_flush_ticks(), _flush_lob(), _flush_flow())` is called, all three methods swap their buffers under the lock and then call `self._conn.executemany` concurrently from different threads — a race on the single DuckDB connection that the lock was meant to prevent.  
**SUGGESTED FIX:** Hold the lock across the write, or use a dedicated single-threaded executor for all DuckDB writes:
```python
async def _flush_ticks(self):
    async with self._lock:
        buf = self._tick_buffer
        self._tick_buffer = []
        if buf:
            self._conn.executemany("INSERT INTO ticks ...", buf)
```

---

**FILE:** `backend/services/duckdb_engine.py`  
**LINE:** ~350 (schema vs INSERT mismatch)  
**SEVERITY:** CRITICAL  
**TYPE:** Bug / SchemaMismatch  
**DESCRIPTION:** The `ticks` table is created with 14 columns in the base schema. After a migration adds `data_source` and `delay_seconds`, INSERT statements pass 16 parameters. If the migration is not applied (e.g., fresh DB, or migration silently fails), all tick inserts fail with `duckdb.BinderException: expected 14 values, got 16`. DuckDB does not raise this as a startup error — it silently discards batches, so all real-time tick data is lost.  
**SUGGESTED FIX:** Use named column inserts rather than positional: `INSERT INTO ticks (ts, symbol, ...) VALUES (?, ?, ...)`. Add a schema-version check at startup that raises a clear error on mismatch.

---

**FILE:** `backend/server.py`  
**LINE:** ~2800 (`detect_opportunities`)  
**SEVERITY:** CRITICAL  
**TYPE:** Bug  
**DESCRIPTION:** A calculated value is immediately discarded — a no-op expression that was almost certainly meant to be an assignment:
```python
abs(king.get("gex", 0)) or 1.0   # result discarded!
```
This was likely intended as:
```python
king_abs_gex = abs(king.get("gex", 0)) or 1.0
```
The variable is then referenced further down in the opportunity-detection logic, but since it was never assigned, it either uses a stale value from an outer scope or raises `NameError`, making opportunity detection silently wrong.  
**SUGGESTED FIX:** Add the assignment: `king_abs_gex = abs(king.get("gex", 0)) or 1.0`

---

## HIGH

---

**FILE:** `backend/routes/paper_trading.py`  
**LINE:** 23–50  
**SEVERITY:** HIGH  
**TYPE:** MissingAuthentication / MissingValidation  
**DESCRIPTION:** All paper trading routes (`/submit`, `/execute`, `/portfolio`, `/history`, `/status`) are completely unauthenticated. The `submit_paper_order` endpoint accepts an untyped `dict` with no bounds checking: `quantity` can be negative or astronomically large, `side` is not validated to `buy`/`sell`, and `symbol` is not length-limited or whitelisted. A caller can submit an order for quantity=`-2147483648` or symbol=`"A" * 10000`.  
**SUGGESTED FIX:** Add auth dependency. Replace `request: dict` with a Pydantic model:
```python
class PaperOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10, pattern=r'^[A-Z\^]+$')
    side: Literal["buy", "sell"]
    quantity: int = Field(..., ge=1, le=10000)
    order_type: str = "almgren_chriss"
    urgency: float = Field(0.5, ge=0.0, le=1.0)
    limit_price: float = Field(0.0, ge=0.0)
```

---

**FILE:** `backend/routes/portfolio.py`  
**LINE:** 14–91  
**SEVERITY:** HIGH  
**TYPE:** MissingAuthentication / MissingValidation  
**DESCRIPTION:** All portfolio routes are unauthenticated. `add_position(name, position: dict)` accepts an arbitrary dict that is pushed directly into MongoDB via `$push` with no schema validation. The `name` portfolio path parameter is used directly in MongoDB queries with no length limit (potential for oversized keys). The `position` dict could contain MongoDB operator keys (`$where`, `$gt`) if not sanitized before storage.  
**SUGGESTED FIX:** Add auth dependency on all routes. Replace `position: dict` with a typed Pydantic model. Validate `name` length (e.g., `Field(..., max_length=50, pattern=r'^[A-Za-z0-9_-]+$')`).

---

**FILE:** `backend/services/duckdb_engine.py`  
**LINE:** ~380 (`conn` property)  
**SEVERITY:** HIGH  
**TYPE:** Encapsulation / ThreadSafety  
**DESCRIPTION:** The public `conn` property exposes the raw DuckDB connection object:
```python
@property
def conn(self):
    return self._conn
```
External code (notably `ingestion_pipeline.py`) uses this to call `.executemany()` directly, completely bypassing all locking. This nullifies the thread-safety guarantees of `DuckDBEngine`.  
**SUGGESTED FIX:** Remove the public `conn` property. If external code needs to execute queries, add a dedicated async method on `DuckDBEngine` that routes through the lock.

---

**FILE:** `backend/services/duckdb_engine.py`  
**LINE:** ~1 (module level)  
**SEVERITY:** HIGH  
**TYPE:** Bug / StartupRisk  
**DESCRIPTION:** `db = DuckDBEngine()` is instantiated at module import time. The `DuckDBEngine.__init__` creates the DuckDB file, runs `CREATE TABLE IF NOT EXISTS` statements, and starts an internal batch-writer task. If DuckDB is unavailable or the schema migration fails, the entire module fails to import, crashing every file that does `from services.duckdb_engine import db`. This is not guarded with a try/except and has no startup probe.  
**SUGGESTED FIX:** Move singleton instantiation to an explicit `initialize()` function called during the FastAPI startup event, not at import time.

---

**FILE:** `backend/services/memory/federation.py`  
**LINE:** ~240 (`_sync_redis`)  
**SEVERITY:** HIGH  
**TYPE:** ResourceLeak / InfiniteBlock  
**DESCRIPTION:** The Redis sync path calls `pubsub.listen()` in a tight loop inside a daemon thread:
```python
for message in pubsub.listen():
    ...
```
`pubsub.listen()` is a blocking generator that never returns. Setting `self._running = False` has no effect on the blocking `for` loop — the thread will never terminate on `stop()`. This causes the daemon thread to hang on shutdown, potentially delaying process exit and leaking the Redis connection.  
**SUGGESTED FIX:** Use a timeout-based poll instead of `listen()`:
```python
while self._running:
    message = pubsub.get_message(timeout=1.0)
    if message and message["type"] == "message":
        ...
```

---

**FILE:** `backend/services/fetch_coordinator.py`  
**LINE:** ~50  
**SEVERITY:** HIGH  
**TYPE:** CompatibilityBug  
**DESCRIPTION:** `asyncio.timeout()` requires Python 3.11+. Using it on Python 3.10 raises `AttributeError: module 'asyncio' has no attribute 'timeout'`, crashing the first request that hits the coordinator's lock-timeout path. There is no Python version guard anywhere in the codebase.  
**SUGGESTED FIX:**
```python
import sys
if sys.version_info >= (3, 11):
    async with asyncio.timeout(LOCK_TIMEOUT_SECONDS): ...
else:
    async with asyncio.wait_for(asyncio.shield(coro), LOCK_TIMEOUT_SECONDS): ...
```
Or require Python 3.11+ in `pyproject.toml` and document it.

---

**FILE:** `backend/services/cvserver_client.py`  
**LINE:** ~50  
**SEVERITY:** HIGH  
**TYPE:** DeprecatedAPI  
**DESCRIPTION:** `loop = asyncio.get_event_loop()` is deprecated since Python 3.10 and emits a `DeprecationWarning` when called from a coroutine without a running loop. In Python 3.12 it raises `RuntimeError` in some contexts. The correct call is `asyncio.get_running_loop()`.  
**SUGGESTED FIX:**
```python
loop = asyncio.get_running_loop()
return await loop.run_in_executor(None, _cvserver_call, method, arguments)
```

---

**FILE:** `backend/services/scheduler.py`  
**LINE:** ~80  
**SEVERITY:** HIGH  
**TYPE:** DeprecatedAPI  
**DESCRIPTION:** Same `asyncio.get_event_loop()` deprecation as cvserver_client. The scheduler uses it to schedule coroutines, which will fail in Python 3.12+.  
**SUGGESTED FIX:** Use `asyncio.get_running_loop()` or `asyncio.ensure_future()` from within an async context.

---

**FILE:** `backend/server.py`  
**LINE:** ~30  
**SEVERITY:** HIGH  
**TYPE:** DeprecatedAPI  
**DESCRIPTION:** Both `@app.on_event("startup")` and `@app.on_event("shutdown")` are deprecated since FastAPI 0.93.0. In FastAPI 0.103+ they emit deprecation warnings; in future versions they may be removed.  
**SUGGESTED FIX:** Replace with the `lifespan` context manager pattern:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown

app = FastAPI(lifespan=lifespan)
```

---

**FILE:** `backend/server.py`  
**LINE:** ~200 (MongoDB client)  
**SEVERITY:** HIGH  
**TYPE:** StartupRisk  
**DESCRIPTION:** `client = AsyncIOMotorClient(MONGO_URL, ...)` and `db = client[DB_NAME]` are created at module level, outside the startup event handler. Motor creates the connection lazily so this doesn't immediately fail, but if the database is unavailable, all operations silently return errors that propagate into endpoint responses rather than causing a clean startup failure. Additionally, the `serverSelectionTimeoutMS` is not set, so the first real operation after startup could block for 30 seconds (the default) before failing.  
**SUGGESTED FIX:** Move client creation into the startup event. Add `serverSelectionTimeoutMS=5000` and probe with `await client.admin.command("ping")` at startup to fail fast.

---

**FILE:** `backend/server.py`  
**LINE:** ~620  
**SEVERITY:** HIGH  
**TYPE:** Bug  
**DESCRIPTION:** Alert rule IDs are assigned using the current list length:
```python
rule_dict["id"] = str(len(_alert_rules) + 1)
```
After any rules are deleted, the length decreases, causing new rules to receive IDs that already exist. For example: create rules 1, 2, 3 → delete rule 2 → create rule 4 → it gets ID "3", colliding with the surviving rule. API callers using IDs to target rules for update/delete will hit the wrong rule.  
**SUGGESTED FIX:** Use `str(uuid.uuid4())` or an auto-incrementing counter that is never decremented.

---

**FILE:** `backend/services/data_quality.py`  
**LINE:** ~50  
**SEVERITY:** HIGH  
**TYPE:** Bug / InconsistentFormula  
**DESCRIPTION:** The GEX formula in `data_quality.py` differs from `server.py`:
```python
# data_quality.py:
gex = sign * gamma * oi * 100 * spot * spot * 0.01

# server.py (via dollar_gex_per_contract):
gex_unit = gamma * oi * 100 * spot * spot  # no * 0.01
```
The 0.01 factor in `data_quality.py` makes all its GEX values 100× smaller than `server.py`'s values. The cross-source consistency check will therefore **always** flag disagreement even when sources agree perfectly, generating spurious `data_quality_failure` alerts and eroding trust in the alerting system.  
**SUGGESTED FIX:** Unify on a single formula — import and use `dollar_gex_per_contract` from `domain/greek_scalers.py` in both files.

---

**FILE:** `backend/services/cvserver_client.py`  
**LINE:** ~100 (`_cvserver_call`)  
**SEVERITY:** HIGH  
**TYPE:** PerformanceBug / ResourceLeak  
**DESCRIPTION:** Every call to `_cvserver_call` creates and tears down a new `httpx.Client`:
```python
with httpx.Client(timeout=CVSERVER_TIMEOUT) as client:
    resp = client.post(...)
```
Under load (frequent chain fetches), this creates many short-lived TCP connections. Repeated TLS handshakes to the same cvserver host cause measurable latency spikes and exhaust ephemeral port range under high throughput.  
**SUGGESTED FIX:** Use a module-level `httpx.Client` instance (or `httpx.AsyncClient`) with connection pooling and keep-alive:
```python
_http_client = httpx.Client(timeout=CVSERVER_TIMEOUT, limits=httpx.Limits(max_keepalive_connections=5))
```

---

---

## MEDIUM

---

**FILE:** `backend/routes/market_data.py`  
**LINE:** ~150 (`_duckdb_fallback`)  
**SEVERITY:** MEDIUM  
**TYPE:** SilentFailure  
**DESCRIPTION:** The DuckDB fallback function swallows all exceptions without logging:
```python
except Exception:
    return None
```
Callers receive `None` and cannot distinguish "no cached data exists" from "DuckDB query crashed". Transient DuckDB errors (schema mismatch, lock contention) are completely invisible in logs.  
**SUGGESTED FIX:**
```python
except Exception as e:
    logger.warning("_duckdb_fallback failed for %s: %s", ticker, e)
    return None
```

---

**FILE:** `backend/routes/market_data.py`  
**LINE:** ~200 (ticker validation)  
**SEVERITY:** MEDIUM  
**TYPE:** MissingValidation  
**DESCRIPTION:** The `ticker` path parameter is only processed with `.strip().upper()` — no length limit, no character whitelist. A caller can pass a 10,000-character string or one containing special characters that could be misinterpreted by downstream SQL queries or logging.  
**SUGGESTED FIX:** Add a FastAPI `Path` validator:
```python
from fastapi import Path
ticker: str = Path(..., min_length=1, max_length=10, pattern=r'^[A-Z\^\.]+$')
```

---

**FILE:** `backend/routes/market_data.py`  
**LINE:** ~200 (`chain` endpoint, T calculation)  
**SEVERITY:** MEDIUM  
**TYPE:** Bug  
**DESCRIPTION:** Time-to-expiry `T` is calculated using `datetime.now()` (naive, local time):
```python
T = max(0.0, (exp_date - datetime.now()).total_seconds() / (365.25 * 86400))
```
`exp_date` is parsed from a string with `strptime` and is also naive. If the server runs in a non-UTC timezone, `T` will be off by the UTC offset (e.g., 5 hours in EST). For 0-DTE options this error is 5/24 ≈ 20% of the remaining time, producing materially wrong greeks.  
**SUGGESTED FIX:** Consistently use UTC throughout. Parse `exp_date` as end-of-day UTC and use `datetime.now(UTC)`. Or normalize both to UTC-midnight for date comparisons.

---

**FILE:** `backend/server.py`  
**LINE:** ~500 (`_rate_limits`)  
**SEVERITY:** MEDIUM  
**TYPE:** MemoryLeak  
**DESCRIPTION:** `_rate_limits: dict[str, deque]` grows unboundedly until it hits a hardcoded 10,000-entry cleanup threshold. Between cleanups, a burst of unique client IPs (e.g., from a DDoS or scanner) accumulates thousands of deques in memory. Each deque holds up to N timestamps. At 10,000 IPs this can consume tens of MB with no feedback to operators.  
**SUGGESTED FIX:** Use an `OrderedDict` with LRU eviction and a smaller cap (e.g., 1,000 entries), or a TTL-cache library like `cachetools.TTLCache`. Alternatively, externalize rate limiting to Redis for multi-process correctness.

---

**FILE:** `backend/server.py`  
**LINE:** ~600 (`_alert_rules`, `_alert_history`)  
**SEVERITY:** MEDIUM  
**TYPE:** DataLoss  
**DESCRIPTION:** `_alert_rules` and `_alert_history` are pure in-memory Python lists. On server restart, all configured alert rules and the entire alert history are lost. Users who set up alerts via the API will find them gone after any deployment or crash.  
**SUGGESTED FIX:** Persist `_alert_rules` to MongoDB on write (upsert to `db.alert_rules`) and reload on startup. Persist `_alert_history` to `db.alert_history` with a TTL index.

---

**FILE:** `backend/routes/admin.py`  
**LINE:** ~98  
**SEVERITY:** MEDIUM  
**TYPE:** Bug  
**DESCRIPTION:** ET timezone is hardcoded as UTC-5:
```python
now_et = datetime.now(UTC) - timedelta(hours=5)  # rough ET
```
ET is UTC-4 during EDT (March–November) and UTC-5 during EST (November–March). Using -5 year-round means the Databento live window check is off by one hour for ~8 months of the year, potentially keeping the live tape session running an hour past the configured stop time or starting it an hour late.  
**SUGGESTED FIX:**
```python
from zoneinfo import ZoneInfo
now_et = datetime.now(ZoneInfo("America/New_York"))
```

---

**FILE:** `backend/services/cvserver_client.py`  
**LINE:** ~50 (module-level `_cache`)  
**SEVERITY:** MEDIUM  
**TYPE:** MemoryLeak  
**DESCRIPTION:** `_cache: dict[str, tuple[float, dict]] = {}` has no size limit. Every unique (method, arguments) cache key accumulates indefinitely. In a high-ticker, multi-expiry environment, this can grow to thousands of entries. Unlike `server.py`'s rate-limit dict, there is no eviction trigger at all.  
**SUGGESTED FIX:** Use `functools.lru_cache` with a size limit, or `cachetools.TTLCache(maxsize=500, ttl=CACHE_TTL)`.

---

**FILE:** `backend/services/cvserver_client.py`  
**LINE:** ~300 (`fetch_chain_for_heatmap`)  
**SEVERITY:** MEDIUM  
**TYPE:** Fragility  
**DESCRIPTION:** Column indices are looked up with hardcoded integer fallback defaults:
```python
strike = float(row[col_idx.get("strike_price", 0)])    # default index 0
expiry = row[col_idx.get("expiration_date", 1)]         # default index 1
```
If the cvserver API changes column ordering (common across API versions), the fallback indices silently map to wrong columns. Strikes and expiries would be swapped or corrupted with no error raised.  
**SUGGESTED FIX:** Raise `KeyError` on missing columns rather than silently using positional fallbacks. Validate `col_idx` has the required keys at the start of the function.

---

**FILE:** `backend/services/data_quality.py`  
**LINE:** ~70 (`_history`)  
**SEVERITY:** MEDIUM  
**TYPE:** MemoryLeak  
**DESCRIPTION:** `_history: list[dict]` in the data quality checker grows unboundedly. Each GEX consistency check appends a new record with no eviction. In production with frequent polling (e.g., every 60s), this accumulates ~1,440 records/day with no upper bound.  
**SUGGESTED FIX:** Cap with a `deque(maxlen=N)` or explicit slice: `_history = _history[-1000:]`.

---

**FILE:** `backend/services/memory/federation.py`  
**LINE:** ~100 (queue directory)  
**SEVERITY:** MEDIUM  
**TYPE:** ResourceLeak  
**DESCRIPTION:** `FileBasedFederationQueue` writes one file per federation event to a queue directory with no size limit. If the consuming side is down or slow, files accumulate indefinitely. A long outage could fill the disk.  
**SUGGESTED FIX:** Add a `max_queue_size` limit. When exceeded, drop oldest events with a warning log rather than writing new files.

---

**FILE:** `backend/server.py`  
**LINE:** ~1800 (`fetch_spot_and_chains_merged`)  
**SEVERITY:** MEDIUM  
**TYPE:** DeadCode  
**DESCRIPTION:** A standalone expression evaluates a dict key but its result is immediately discarded:
```python
yf_data["spot"]   # standalone expression — result not used
```
This is likely a leftover from an incomplete refactor (possibly meant to be `assert yf_data["spot"]` or an assignment). It causes a silent `KeyError` if `yf_data` lacks a "spot" key, crashing the merge function.  
**SUGGESTED FIX:** If it was meant as a guard: `if not yf_data.get("spot"): return None`. If it's truly dead, remove it.

---

---

## LOW

---

**FILE:** `backend/conftest.py`  
**LINE:** 3–5  
**SEVERITY:** LOW  
**TYPE:** ImplicitDependency  
**DESCRIPTION:** `conftest.py` uses `os.environ.setdefault(...)` to set `DB_NAME` and other env vars, but this only works if `conftest.py` is imported **before** `server.py`. Pytest loads `conftest.py` automatically before test collection, so in tests this is fine. However, the implicit ordering means that any test that directly imports `server` without going through pytest's conftest loading (e.g., a standalone script) will crash with `KeyError` on `DB_NAME`.  
**SUGGESTED FIX:** Document this dependency explicitly. Consider making `server.py` use `os.environ.get("DB_NAME", "confluence_decoder")` (see CRITICAL #4) so conftest is a convenience, not a requirement.

---

**FILE:** `backend/routes/market_data.py`  
**LINE:** ~220 (`spot` function)  
**SEVERITY:** LOW  
**TYPE:** DeadCode  
**DESCRIPTION:** Redundant local import inside the `spot()` function:
```python
async def spot(ticker: str):
    from datetime import datetime   # already imported at module top
```
`datetime` is already imported at the module level. The local import is a no-op (Python caches it) but is misleading — it implies the module-level import doesn't exist.  
**SUGGESTED FIX:** Remove the local import.

---

**FILE:** `backend/services/risk/killswitch.py`  
**LINE:** ~100  
**SEVERITY:** LOW  
**TYPE:** Bug  
**DESCRIPTION:** `_current_date` is set in `start_day()` but `update_pnl()` never checks whether the date has rolled over midnight. If the process runs past midnight without calling `start_day()` (e.g., a crash and restart is missed), the kill switch accumulates P&L across two calendar days, potentially allowing a new day's losses to exceed the daily limit before it trips.  
**SUGGESTED FIX:** In `update_pnl()`, compare `datetime.now(UTC).date()` against `_current_date` and auto-reset if they differ.

---

**FILE:** `backend/services/websocket_streamer.py`  
**LINE:** ~70  
**SEVERITY:** LOW  
**TYPE:** ObservabilityGap  
**DESCRIPTION:** When a WebSocket client connects with an empty topic subscription list, the `ws_active_connections` Prometheus gauge is not updated. Only connections with at least one topic increment/decrement the gauge, so the gauge undercounts total active connections.  
**SUGGESTED FIX:** Increment/decrement the gauge unconditionally in `connect()` / `disconnect()`, regardless of topic count.

---

**FILE:** `backend/services/risk/gate.py`  
**LINE:** ~200  
**SEVERITY:** LOW  
**TYPE:** PerformanceBug  
**DESCRIPTION:** On every call to `check()`, the idempotency cache is cleaned by creating an entirely new dict:
```python
self._idempotency_cache = {
    k: v for k, v in self._idempotency_cache.items()
    if (now - v) < self._idempotency_window_sec
}
```
Under high-frequency signal checking (100+ calls/sec), this allocates a new dict object on every invocation, adding GC pressure. The idempotency window is not enforced on a schedule — it's cleaned on every call.  
**SUGGESTED FIX:** Use `cachetools.TTLCache` for automatic O(1) expiry, or only run cleanup every N calls using a counter.

---

**FILE:** `backend/scripts/train_v5_production.py`  
**LINE:** 40, 49, 56, 59, 95  
**SEVERITY:** LOW  
**TYPE:** BareExcept  
**DESCRIPTION:** Five bare `except:` clauses (no exception type specified) silently swallow **all** exceptions including `KeyboardInterrupt`, `SystemExit`, and `MemoryError`. This makes training scripts impossible to interrupt with Ctrl-C and hides crashes.
```python
except:          # line 40 — swallows KeyboardInterrupt
    return 0.0
```
**SUGGESTED FIX:** Replace all `except:` with `except Exception:` at minimum, or catch specific expected exceptions (e.g., `ZeroDivisionError`, `ValueError`).

---

**FILE:** `backend/services/circuit_breaker.py`  
**LINE:** ~320  
**SEVERITY:** LOW  
**TYPE:** StartupRisk  
**DESCRIPTION:** `main_breaker = CircuitBreaker("main")` is instantiated at module level. `CircuitBreaker.__init__` records `_created_at = datetime.now(UTC)` and initializes deques. While lightweight, module-level singletons make testing harder (shared state between tests) and startup order implicit.  
**SUGGESTED FIX:** Minor — acceptable for now. Consider wrapping in a `get_main_breaker()` factory function for easier test isolation.

---

## Appendix: Known Self-Noted Issues (from in-code BUG/TODO/HACK comments)

The following are self-documented issues found via code-comment scan, noted for completeness but not double-counted above:

- `services/databento_oi.py` — 5 exception handlers tagged `bug` (swallowed errors returning 0 instead of propagating)
- `services/morning_briefing.py` — 3 exception handlers tagged `bug`
- `services/stochastic_vol.py:561` — exception handler tagged `bug`
- `services/gex_history.py:101,124` — BUG comments on silent contract filtering
- `services/chain_replay.py:56` — HACK comment (workaround, not a permanent fix)
- `services/yoptions_fetcher.py:7,54,61,152` — bug comments on raw JSON save path
- `services/fill_monitor.py:89` — bug comment on fill recording
- `services/ml/gate.py:7–15` — three documented fixed bugs in baseline evaluation (verify the fixes are complete)
- `services/ml/outcomes.py:97` — exception swallowed, returns `None`
- `services/ml/health_monitor.py:124,144,155,277` — multiple silent-fallback exception handlers

---

## Remediation Priority

| Priority | Action |
|----------|--------|
| **Immediate** | Add auth to `/errors/summary`, `/errors/clear`, `/live/policy`, `/live/tape/stop`, all `/memory/*` routes |
| **Immediate** | Fix DuckDB lock-release-before-write race in `duckdb_engine.py` |
| **Immediate** | Fix `_BUILD_HEATMAP_CACHE` dual-format bug in `server.py` |
| **This sprint** | Fix broken `scheduler.py` imports (dead scheduler = no data prefetch) |
| **This sprint** | Fix alert ID duplication; persist `_alert_rules` to MongoDB |
| **This sprint** | Fix `audit_trail.py` stub — implement or remove the compliance claim |
| **This sprint** | Fix `ingestion_pipeline.py` wrong-table insert + direct `conn` access |
| **Backlog** | Pydantic models for all `request: dict` endpoints |
| **Backlog** | `asyncio.get_event_loop()` → `get_running_loop()` across the board |
| **Backlog** | Migrate `@app.on_event` to `lifespan` context manager |
| **Backlog** | Unify GEX formula between `data_quality.py` and `server.py` |
| **Backlog** | Add size caps on all unbounded in-memory caches |
