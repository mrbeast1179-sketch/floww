# Hermes Round 9 — Per-Task Specs

> Find your assigned ID below. Append this section to the universal preamble
> (`HERMES_ROUND9_PREAMBLE.md`) when launching.

## H1 — conftest.py event-loop fixture removal (90 min, HIGHEST LEVERAGE)

**OWNS:** `backend/tests/conftest.py`

**Problem:** lines 28-81 contain an `autouse=True` fixture that manually closes
the asyncio event loop and creates a new one before every test. This conflicts
with pytest-asyncio's own loop management. Result: 2,343 of 2,378 tests crash.

**Goal:** restore the test suite to ≥ 2,363 passing.

**Steps:**

1. Run baseline: `cd backend && source .venv/bin/activate && python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -3`
   Capture the current passing/failing count. Expected: ~35 passed.
2. Read `backend/tests/conftest.py` start to finish. Understand what the fixture does
   (resets event loop, creates fresh motor client, resets error log + live policy).
3. The fix: KEEP the motor-client reset + error-log reset + live-policy reset functionality,
   but REMOVE the manual `old_loop.close()` and `new_loop = asyncio.new_event_loop()` lines.
   Let pytest-asyncio create+manage the loop. Convert `autouse=True` to a NAMED fixture
   that tests opt into when they actually need a fresh motor client.
4. Alternative if the per-test reset is structurally required: keep the fixture but
   use pytest_asyncio's `event_loop` fixture (which is the supported integration point).
5. Re-run pytest: `python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -3`.
   Expect ≥ 2,363 passing. If count drops below 35 (baseline): HALT — your change made things worse.

**Commit message must include:**
```
$ python -m pytest -q --ignore=tests/e2e --tb=no | tail -3
Before:  35 passed, 2343 failed, 0 skipped
After:   2363 passed, ~15 failed (real failures), 0 skipped
```

---

## H6 — useMarketData.js fetch timeout → AbortSignal (15-30 min)

**OWNS:** `frontend/src/hooks/useMarketData.js` + any other hook found via
`grep -rn 'timeout:' frontend/src/hooks/`

**Problem:** line 124 uses `fetch(url, { signal: controller.signal, timeout: 30000 })`.
The `timeout` option is NOT in the browser Fetch API. It's silently ignored.
Result: requests can hang indefinitely.

**Fix pattern:**
```js
// OLD: fetch(url, { signal: controller.signal, timeout: 30000 })
// NEW:
const signal = AbortSignal.timeout(30000);
const res = await fetch(url, { signal });
```

If the existing code uses a manual AbortController for cancel-on-unmount, combine signals:
```js
const userSignal = controller.signal;
const timeoutSignal = AbortSignal.timeout(30000);
const signal = AbortSignal.any([userSignal, timeoutSignal]);  // requires modern browsers; check support
```

**Acceptance grep (must return 0):**
```
$ grep -rn 'timeout: [0-9]' frontend/src/hooks/
```

---

## H7 — AlertOverlay.js connect() ReferenceError (30 min)

**OWNS:** `frontend/src/components/AlertOverlay.js` (or `.jsx`)

**Problem:** line 194 calls `connect()` from one useEffect, but `connect()` is
defined inside a DIFFERENT useEffect's closure → ReferenceError when tab visibility
changes triggers reconnection.

**Fix:** lift `connect()` to component scope using `useCallback` with proper deps,
so both useEffects can reference it.

**Pattern:**
```jsx
const connect = useCallback(() => {
  // websocket setup
}, [/* deps */]);

useEffect(() => {
  connect();
  return () => /* cleanup */;
}, [connect]);

useEffect(() => {
  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') connect();
  };
  document.addEventListener('visibilitychange', onVisibilityChange);
  return () => document.removeEventListener('visibilitychange', onVisibilityChange);
}, [connect]);
```

**Acceptance:** in browser DevTools, simulate tab background→foreground; no `ReferenceError: connect is not defined` in console.

---

## H8 — Centralize REACT_APP_BACKEND_URL with fallback (45 min)

**OWNS:** `frontend/src/config/api.js` (NEW) + 16 existing files using `process.env.REACT_APP_BACKEND_URL`

**Steps:**

1. Find all callers: `grep -rln 'REACT_APP_BACKEND_URL' frontend/src/`
2. Create `frontend/src/config/api.js`:
   ```js
   /**
    * Single source of truth for backend URL. Avoids "undefined/api/..." bug
    * when REACT_APP_BACKEND_URL env var is missing.
    */
   export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
   export const API = `${BACKEND_URL}/api`;
   ```
3. In each of the 16 callers, replace:
   ```js
   const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
   const API = `${BACKEND_URL}/api`;
   ```
   with:
   ```js
   import { BACKEND_URL, API } from "<correct relative path>/config/api";
   ```

**Acceptance:**
```
$ grep -rn 'process.env.REACT_APP_BACKEND_URL' frontend/src/
frontend/src/config/api.js:7:export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
(only one line)
```

---

## H9 — Replace 12+ empty catch blocks (60 min)

**OWNS:** 6 component files identified via `grep -rln 'catch (e) {}' frontend/src/components/`

**Pattern fix:** every `catch (e) {}` becomes:
```js
catch (e) {
  console.error("<context>:", e);
  // if component has error state: setError(e.message);
}
```

**Acceptance:** `grep -rn 'catch (e) {}' frontend/src/components/` returns 0.

---

## H10 — Verify CharmChart/VannaChart import paths still correct (5 min)

**OWNS:** `frontend/src/components/CharmChart.jsx`, `frontend/src/components/VannaChart.jsx`

**Steps:**
1. `grep '../../hooks' frontend/src/components/{Charm,Vanna}Chart.jsx` — should return 0.
2. If non-zero, the audit stale-clone regression hit these. Re-apply the fix:
   `../../hooks/` → `../hooks/`, `../../utils/` → `../utils/`, `../RetryButton` → `./RetryButton`
3. Verify React still compiles: `tail -10 /tmp/react_decoder.log` shows "Compiled successfully!"

---

## H11 — Auth on 6 leaky admin trading routes (45 min)

**OWNS:** `backend/routes/admin.py` (sections H3 didn't touch)

**ORIGIN-STATE GATE (Phase 0)**:
```
git fetch origin main
git log origin/main --oneline -1 | grep "P0 crash fixes (H2,H3"
```
If no match: HALT WAITING_FOR_H3 (architect already shipped this in c2c4045; if grep fails, your local is somehow ahead; investigate).

**Steps:**
1. Identify 6 admin routes per audit:
   - `/api/admin/trading/status`
   - `/api/admin/trading/circuit-breaker/log`
   - `/api/admin/trading/circuit-breaker/reset`
   - `/api/admin/trading/circuit-breaker/trip`
   - `/api/admin/trading/transition`
   - `/api/admin/schwab/health`
2. Add `Depends(verify_api_key)` to each:
   ```python
   from auth import verify_api_key
   from fastapi import Depends
   
   @router.get("/api/admin/trading/status")
   async def trading_status(_: bool = Depends(verify_api_key)):
       ...
   ```
3. Verify locally:
   ```
   curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/trading/status
   # → 401
   curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: <key>" http://localhost:8000/api/admin/trading/status
   # → 200
   ```
4. Add `backend/tests/routes/test_admin_auth.py` with 6 tests (one per route × 401/200 case).

**Commit message:** include curl outputs above.

---

## H12 — Auth on databento/usage + performance/stats (30 min)

**ORIGIN-STATE GATE:** wait for H11 to land first.
```
git fetch origin main
git log origin/main --oneline -1 | grep "verify_api_key.*admin trading"
```

**OWNS:** `backend/routes/admin.py` (databento/usage) + wherever `/api/performance/stats` lives
(find with `grep -rn "performance/stats" backend/routes/`)

**Steps:** identical pattern to H11 — `Depends(verify_api_key)` on each, 401/200 tests.

---

## H13 — Move API keys out of URL query params (alpha_advantage.py, 20 min)

**OWNS:** `backend/routes/alpha_advantage.py`

**Problem:** API keys passed as URL query parameters leak to server logs,
browser history, proxy caches.

**Fix:** move to POST body OR `Authorization` header. Most Alpha Vantage calls
are server-to-server (backend → AV API) so use the header form they accept.

**Acceptance:** `grep 'apikey=' backend/routes/alpha_advantage.py` returns 0.

---

## H14 — Hard-fail on missing SECRET_KEY in production (30 min)

**OWNS:** `backend/config/secrets.py` (find with `grep -rn 'SECRET_KEY' backend/ --include="*.py" | head -10`)

**Architect-approved decision (from AskUserQuestion):** hard-fail in production.

**Fix pattern:**
```python
import os, sys
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").lower()
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if ENVIRONMENT in {"production", "staging"}:
        sys.exit(
            "FATAL: SECRET_KEY env var is required in production/staging. "
            "Refusing to start with default dev key. "
            "Set SECRET_KEY in environment or use ENVIRONMENT=dev for local."
        )
    SECRET_KEY = "dev-only-key"  # only for ENVIRONMENT=dev
```

**Acceptance:**
```
$ ENVIRONMENT=production SECRET_KEY= python -c "from config.secrets import SECRET_KEY"
FATAL: SECRET_KEY env var is required ...
(exits with non-zero)
```

---

## H15 — Deployment hygiene quick wins (60 min)

**OWNS:** `docker-compose.prod.yml`, `infra/main.bicep` (or wherever Bicep lives), `docker-compose.yml`, `.github/workflows/deploy.yml`, `frontend/public/offline.html` (NEW), `.gitignore`

**6 fixes:**

1. `docker-compose.prod.yml`: change `dockerfile: Dockerfile` → `dockerfile: Dockerfile.backend` for the backend service. Verify with `docker compose -f docker-compose.prod.yml config`.
2. `infra/main.bicep`: dedupe duplicate `capabilities: ['EnableMongo']` and duplicate subnet block. Verify with `bicep build infra/main.bicep` (if bicep CLI available).
3. `docker-compose.yml:39`: change frontend port mapping from `3000:80` → `3000:3000` (container serves on 3000).
4. `.github/workflows/deploy.yml`: change `app-name: confluence-decoder` → `app-name: floww-prod-app` (matching terraform).
5. Create `frontend/public/offline.html` — minimal HTML page service-worker.js falls back to when offline:
   ```html
   <!DOCTYPE html>
   <html><head><title>Confluence Decoder — Offline</title>
   <style>body{background:#0a0a1a;color:#e0e0e0;font-family:monospace;text-align:center;padding:40px;}</style>
   </head><body><h1>Offline</h1><p>The Confluence Decoder is currently offline.</p>
   <p>Cached data may still be available. Refresh when network returns.</p></body></html>
   ```
6. Add `models/` to `.gitignore` to stop tracking 11MB of binary artifacts going forward.
   (Note: existing tracked models stay tracked. This stops NEW models from auto-staging.)

**Acceptance:** commit each fix with its verification output inline.

---

## L1 — Backend memory-leak audit (60 min, READ-ONLY)

**OWNS:** `docs/ROUND9_BACKEND_LEAK_AUDIT.md` (NEW)

**Hunt patterns:**

1. **Unbounded module-level caches**:
   `grep -rn '^_cache\s*=\s*{}' backend/ --include="*.py"`
   For each match, check if there's a size limit / TTL eviction. If not → finding.
2. **Dangling asyncio tasks**:
   `grep -rn 'asyncio.create_task' backend/ --include="*.py" | grep -v 'await\|= '`
   Tasks created without storing reference → garbage collector may kill mid-execution.
3. **MongoDB cursor leaks**:
   `grep -rn '\.find(' backend/ --include="*.py" | grep -v 'to_list\|async for'`
   Cursors created without `.to_list()` or `async for` → connection leak.
4. **File handles outside `with`**:
   `grep -rn '\bopen(' backend/ --include="*.py" | grep -v 'with open'`
5. **Module-level singletons holding per-request refs**:
   Look for `global <var>` patterns plus assignments inside request handlers.

**Output format** in `docs/ROUND9_BACKEND_LEAK_AUDIT.md`:
```markdown
| File:line | Type | Severity | Fix suggestion |
|---|---|---|---|
| backend/services/cache_router.py:42 | unbounded cache | High | Add LRU eviction (functools.lru_cache(maxsize=1024)) |
```

NO CODE CHANGES this unit — just report. L4 picks top-5 to fix.

---

## L2 — Frontend timer/listener leak audit (45 min, READ-ONLY)

**OWNS:** `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (NEW)

**Hunt patterns:**

1. `grep -rn 'setInterval(' frontend/src/ --include="*.jsx" --include="*.js"`
2. `grep -rn 'setTimeout(' frontend/src/ --include="*.jsx" --include="*.js"`
3. `grep -rn 'addEventListener(' frontend/src/ --include="*.jsx" --include="*.js"`

For each, verify:
- Inside a `useEffect`? Check the return function clears it.
- Stand-alone? Likely a leak.

**Output:** table of `file:line | timer/listener type | cleaned up? (Y/N) | severity`.

---

## L3 — Frontend useEffect cleanup audit (45 min, READ-ONLY)

**OWNS:** `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (APPEND — L2 created it)

**Hunt patterns:**

1. `useEffect` blocks with `fetch()` or `axios.get/post()` — does the effect return a cleanup that aborts the fetch (AbortController)?
2. `useEffect` blocks with subscriptions (WebSocket, EventSource) — do they unsubscribe on cleanup?
3. Stale closure traps: useEffect deps array missing values referenced inside.

**Output:** appended section in `docs/ROUND9_FRONTEND_LEAK_AUDIT.md`.

---

## L4 — Fix top 5 highest-severity leaks (90 min)

**ORIGIN-STATE GATE:** wait for L1, L2, L3 to ALL land first:
```
git fetch origin main
git log origin/main --since="3 hours ago" --oneline | grep "leak" | wc -l
# Must be ≥ 3
```

**OWNS:** TBD at commit time — claim per-file ownership based on the audit findings.
HALT if your top-5 picks include files owned by another currently-running agent.

**Steps:**

1. Read `docs/ROUND9_BACKEND_LEAK_AUDIT.md` + `docs/ROUND9_FRONTEND_LEAK_AUDIT.md`.
2. Rank by severity × likelihood-of-OOM. Pick top 5.
3. For each: apply fix, commit separately with grep evidence + before/after `_cache size` or `setInterval count`.
4. After all 5: write `docs/ROUND9_LEAK_FIXES_APPLIED.md` summarizing what landed vs deferred.

**Acceptance:** 5 commits on origin/main, each with grep-verified message body.

═══════════════════════════════════════════════════════════════════════════════
END OF TASK SPECS. CLOSE OF Hermes Round 9.
═══════════════════════════════════════════════════════════════════════════════
