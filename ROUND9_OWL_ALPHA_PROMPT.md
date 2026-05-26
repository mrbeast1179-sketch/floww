# Owl Alpha Round 9 — Single-Session Comprehensive Fix Mission

> **WHERE TO PASTE**: Hermes terminal → new agent session → **select Owl Alpha model** → paste everything below the first `═══` line. One session, runs 6-8 hours sequentially. Will write 15-min status pulses; if it halts, paste the halt report to the architect and they will unblock within 5 minutes.

═══════════════════════════════════════════════════════════════════════════════

You are an Owl Alpha agent running on Hermes. Architect: Nav (PhD math/physics, Stanford, ex-Jane Street HFT). Repo: `/Users/nav/Documents/GitHub/floww`. You have ONE long session (6-8 hours). Your mission is **9 sequential fix phases**, each gated on the prior phase landing on `origin/main`. You will commit + push between every phase so progress survives any interruption.

═══════════════════════════════════════════════════════════════════════════════
HARD RULES (violating any = P0 incident — STOP and HALT instead)
═══════════════════════════════════════════════════════════════════════════════

R1. **Canonical clone only.** `pwd` MUST equal `/Users/nav/Documents/GitHub/floww`. NOT `/Users/nav/GitHub/floww` (the stale clone that caused 3+ production incidents). Verify with `pwd && git remote -v`. If wrong: HALT WRONG_CLONE.

R2. **Forbidden git commands.** NEVER run any of these:
    `git rebase --abort`, `git reset --hard`, `git push --force`, `--no-verify`,
    `--amend` (someone else's commit), `git checkout .`, `git restore .`,
    `git clean -fd`, `rm -rf .git`. The repo has recently-resolved rebase state
    — any of these commands could destroy committed work.

R3. **File ownership is STRICT.** Each phase below names the files you may modify. Touching anything not listed = HALT. ALWAYS FORBIDDEN regardless of phase:
    - `backend/services/ml/inference.py` (architect-resolved last rebase, frozen)
    - `backend/services/dash_ui.py` (Round 7 frozen)
    - `backend/server.py` EXCEPT for any single-line edit explicitly named in your phase
    - `frontend/src/App.js`, `App.css`, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
    - Any `.joblib`, `.pt`, `.json` model artifact
    - `backend/tests/conftest.py` (audit was stale on this; tests are already 2,329 passing — DO NOT TOUCH)

R4. **Grep/curl evidence in every commit message.** Every commit message body MUST include the literal output of a grep/curl/test command that proves the claim. Example:
    ```
    fix(thing): description
    
    $ grep -c 'pattern' file.py
    Before: 5
    After:  0
    ```
    No fabricated success claims. If you can't grep-verify it, don't claim it.

R5. **NEVER mark a test xfail or skip without architect approval.** If a test breaks, HALT with the failing test name and ask. Hiding red with xfail is the Round 7 pattern that destroyed audit trust.

R6. **15-minute status pulse — HARD RULE.** Every 15 minutes you MUST append ONE line to BOTH:
    ```
    kanban/cards/agent_OWL_status.md
    /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    ```
    Line format (exact):
    ```
    [<ISO8601-UTC>] OWL :: <status> :: <one-line summary> :: HEAD=<sha7>
    ```
    Valid statuses: `launched`, `in-progress`, `committing`, `verifying`, `DONE-PHASE-N`, `STALLED`, `HALTED`, `RETRYING`.
    If 15 minutes pass without a status line: self-HALT with `STALLED`.

R7. **Halt format** (use this exact structure when stopping):
    ```
    ──── HALT REPORT ────
    Agent:    Owl Alpha Round 9
    Phase:    <phase number>  Step: <n>
    Reason:   <one sentence>
    Output:   <verbatim diagnostic from your last command>
    Question: <one specific yes/no or A/B question for architect>
    ─────────────────────
    ```
    Then STOP and wait. The architect monitors every 15 min and resolves halts in 5 min average.

R8. **Origin-state gates** (anti-skip protocol). Before starting each phase, verify the PRIOR phase's commit is on `origin/main`:
    ```bash
    git fetch origin main
    git log origin/main --oneline -1 | grep "<previous phase commit subject>"
    ```
    If the prior phase's commit isn't there: HALT. You cannot fake completion; if the next phase's gate fails, the architect will know.

R9. **Per-phase commit + push + verify-on-origin.** After each phase:
    ```bash
    git add <your owned files>
    git commit -m "<message with grep evidence inline>"
    git pull --rebase origin main
    git push origin main
    SHA=$(git rev-parse HEAD)
    git fetch origin
    [ "$SHA" = "$(git rev-parse origin/main)" ] && echo "ON ORIGIN: $SHA" || { echo "GATE FAIL"; exit 1; }
    ```

R10. **The Confluence Decoder PWA launch convention.** If you need to visually verify anything, NEVER run `open http://localhost:3000` (that spawns a Chrome tab). Use:
    ```bash
    open -a "$HOME/Applications/Chrome Apps.localized/Confluence Decoder.app"
    ```

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — COMMON SETUP (run this once at the very start, ~5 min)
═══════════════════════════════════════════════════════════════════════════════

```bash
cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v                              # R1 check — MUST show canonical path
ls .git/rebase-merge/ .git/rebase-apply/ 2>&1     # MUST show "No such file or directory"
git pull --rebase origin main                     # sync
git rev-parse HEAD > /tmp/r9_OWL_start.txt
git branch backup/r9_OWL_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OWL :: launched :: Phase 0 complete :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_OWL_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"
```

Confirm the test baseline (must show ~2,329 passing — this is the current state):
```bash
cd backend && source .venv/bin/activate
python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -3 > /tmp/r9_OWL_baseline.txt
cat /tmp/r9_OWL_baseline.txt
cd ..
```

If the baseline shows < 2,000 passing: HALT. Something broke between architect's commit `b9d182f` and your launch. Architect needs to investigate before you start changing files.

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — useMarketData.js: fetch timeout → AbortSignal.timeout (~20 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `frontend/src/hooks/useMarketData.js`

**Problem:** Line 124 currently uses `fetch(url, { signal: controller.signal, timeout: 30000 })`. The `timeout` option is NOT in the browser Fetch API specification — browsers silently ignore it. Result: every request from CharmChart, VannaChart, and any other component using this hook can hang indefinitely.

**Fix pattern:**
```js
// OLD: fetch(url, { signal: controller.signal, timeout: 30000 })
// NEW (combine user-cancel signal with timeout signal):
const timeoutSignal = AbortSignal.timeout(30000);
const combinedSignal = AbortSignal.any([controller.signal, timeoutSignal]);
const res = await fetch(url, { signal: combinedSignal });
```

`AbortSignal.timeout(ms)` returns a signal that aborts after `ms` milliseconds. `AbortSignal.any([sig1, sig2])` returns a signal that aborts when ANY input aborts. Both are standard, supported in all modern browsers (Chrome 103+, Safari 17.4+, Firefox 124+).

**Steps:**
1. Read `frontend/src/hooks/useMarketData.js` start to finish. Understand the existing AbortController pattern.
2. Apply the Edit. Verify the resulting code:
   ```bash
   grep -n "AbortSignal\|timeout:" frontend/src/hooks/useMarketData.js
   ```
   Should show `AbortSignal.timeout(30000)` and NO line with `timeout: <number>`.
3. Also check `frontend/src/hooks/` for any OTHER hook with the same `timeout:` pattern:
   ```bash
   grep -rn "timeout: [0-9]" frontend/src/hooks/
   ```
   If found, apply the same fix to those too.
4. Verify React still compiles (CRA hot-reload picks up within ~10s):
   ```bash
   sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null || tail -10 /tmp/react_pwa.log 2>/dev/null
   ```
   If you see "Failed to compile" or "Module not found": HALT and revert.

**Commit message template:**
```
fix(round-9-phase1-OWL): useMarketData fetch timeout → AbortSignal.timeout

The fetch() option `timeout: 30000` is not in browser Fetch API spec and was
being silently ignored. Replaced with AbortSignal.timeout() combined with the
existing user-cancel signal via AbortSignal.any(). Now requests actually time
out after 30s instead of hanging indefinitely.

Affects: CharmChart.jsx, VannaChart.jsx, and any other component using useMarketData.

Verification:
  $ grep -rn 'timeout: [0-9]' frontend/src/hooks/
  (empty — all instances replaced with AbortSignal.timeout)

  $ grep -c 'AbortSignal.timeout' frontend/src/hooks/useMarketData.js
  1

  $ tail -3 /tmp/react_decoder.log
  webpack compiled successfully

Co-Authored-By: Owl Alpha <owl@floww.dev>
```

Push + origin-state verify per R9. Status pulse: `DONE-PHASE-1`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — AlertOverlay: fix connect() ReferenceError (~30 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `frontend/src/components/AlertOverlay.js` (or `.jsx` — check which extension)

**Problem:** Line ~194 calls `connect()` from a `useEffect`, but `connect()` is defined inside a DIFFERENT useEffect's closure. When the browser tab changes visibility (background→foreground), the visibility handler tries to call `connect()` and throws `ReferenceError: connect is not defined`, crashing the WebSocket reconnection logic.

**Root cause pattern:**
```jsx
// CURRENT BROKEN STRUCTURE
useEffect(() => {
  const connect = () => { /* websocket setup */ };
  connect();
  return () => /* cleanup */;
}, []);

useEffect(() => {
  const onVisibilityChange = () => {
    if (document.visibilityState === 'visible') connect();  // ← ReferenceError
  };
  document.addEventListener('visibilitychange', onVisibilityChange);
  return () => document.removeEventListener('visibilitychange', onVisibilityChange);
}, []);
```

**Fix pattern (lift connect to component scope via useCallback):**
```jsx
const connect = useCallback(() => {
  /* websocket setup */
}, [/* state deps */]);

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

**Steps:**
1. Read the file. Identify `connect()` and both useEffects.
2. Lift `connect` to a `useCallback` at component scope. Identify what state values it captures and put those in the dep array.
3. Both useEffects now have `connect` in their deps array.
4. Verify compilation + grep that the function is at component scope, not inside an effect:
   ```bash
   grep -nB 1 'const connect =' frontend/src/components/AlertOverlay.*
   ```
   Should show `const connect = useCallback(` at the top level of the component function body, NOT inside another `useEffect(() => {`.

**Commit message** must include the before/after grep. Push + origin gate. Status: `DONE-PHASE-2`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — Centralize REACT_APP_BACKEND_URL with fallback (~45 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `frontend/src/config/api.js` (NEW FILE) + every existing file using `process.env.REACT_APP_BACKEND_URL`.

**Problem:** 16+ files reference `process.env.REACT_APP_BACKEND_URL` directly. When the env var is missing (e.g., production deploys without .env), the value is `undefined`, so `${BACKEND_URL}/api` becomes `"undefined/api/..."` — making real HTTP calls to a literal URL containing the string "undefined". Browser shows network errors; user sees blank panels.

**Steps:**

1. Find all callers:
   ```bash
   grep -rln 'REACT_APP_BACKEND_URL' frontend/src/
   ```
   Note the count.

2. Create `frontend/src/config/api.js`:
   ```js
   /**
    * Single source of truth for backend URL configuration.
    *
    * Falls back to localhost:8000 when REACT_APP_BACKEND_URL is missing,
    * preventing the "undefined/api/..." bug that crashed every panel when
    * the env var wasn't set in production builds.
    *
    * Added Round 9 Phase 3.
    */
   export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
   export const API = `${BACKEND_URL}/api`;
   ```

3. For each caller file, replace the local declaration. Two common patterns to look for:

   Pattern A (most common):
   ```js
   // OLD:
   const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
   const API = `${BACKEND_URL}/api`;
   // NEW:
   import { BACKEND_URL, API } from "<correct relative path>/config/api";
   ```

   Pattern B (less common):
   ```js
   // OLD:
   const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
   // NEW:
   import { API } from "<correct relative path>/config/api";
   ```

   The relative path depends on the file's location:
   - From `frontend/src/App.js`: `./config/api`
   - From `frontend/src/components/Foo.jsx`: `../config/api`
   - From `frontend/src/components/heatseeker/Foo.jsx`: `../../config/api`
   - From `frontend/src/hooks/Foo.js`: `../config/api`

   **EXCEPTION**: do NOT modify `frontend/src/App.js` — it's in the FORBIDDEN list. If `App.js` is one of the 16, leave it alone and document that exception in your commit message ("App.js excluded — owner: future Hermes A track for Round 10").

4. Verify only the new file references the env var:
   ```bash
   grep -rn 'process.env.REACT_APP_BACKEND_URL' frontend/src/ | grep -v 'config/api.js'
   ```
   Should be empty (or only `App.js` if you excluded it).

5. Verify React compiles cleanly:
   ```bash
   sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null || tail -10 /tmp/react_pwa.log 2>/dev/null
   ```

**Commit message** must show the before count (`grep -rl ... | wc -l`) → after count (1, only the new file). Push + origin gate. Status: `DONE-PHASE-3`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — Replace empty catch blocks with explicit logging (~60 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** Files matched by `grep -rln 'catch (e) {}' frontend/src/components/` — should be ~6 files per the audit.

**Problem:** Empty catch blocks silently swallow every error. A user staring at a blank AlertsPanel doesn't know if the API is down, their network is down, there are no alerts, or the code has a bug. For a trading application, this is the most dangerous antipattern in the codebase.

**Fix pattern:**
```js
// OLD:
try {
  await axios.get(...);
} catch (e) {}

// NEW:
try {
  await axios.get(...);
} catch (e) {
  console.error("AlertsPanel fetch failed:", e);
  // if component has error state already wired:
  setError(e?.message || String(e));
  // OR if no error state, at minimum log it (user can check console)
}
```

**Steps:**
1. List the offenders:
   ```bash
   grep -rln 'catch (e) {}' frontend/src/components/
   ```
2. For each file, read it, find the empty catch, look for existing error-state patterns nearby:
   - If component already has `setError(...)` calls somewhere: use that
   - If it has `setErr(...)`: use that
   - Otherwise: at minimum add `console.error("<ComponentName> <operation> failed:", e);`
3. After all files done:
   ```bash
   grep -rn 'catch (e) {}' frontend/src/components/
   ```
   MUST return 0.

**Commit message** must show before/after counts. Push + origin gate. Status: `DONE-PHASE-4`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — Verify CharmChart/VannaChart import paths (~10 min, often a no-op)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `frontend/src/components/CharmChart.jsx`, `frontend/src/components/VannaChart.jsx`

**Problem:** Earlier rounds had a bug where these files used `../../hooks/useMarketData` and `../RetryButton` paths that resolved outside `src/` (which CRA forbids). DeepSeek fixed it in commit `edcf7a6`. The audit stale-clone may have regressed them.

**Steps:**
1. Verify:
   ```bash
   grep -n 'import' frontend/src/components/CharmChart.jsx frontend/src/components/VannaChart.jsx | grep -E 'useMarketData|dataDecimator|RetryButton'
   ```
2. Expected output:
   ```
   import { useMarketData } from "../hooks/useMarketData";
   import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
   import { ErrorState } from "./RetryButton";
   ```
3. If you see `../../hooks` or `../RetryButton` (regression): apply the same sed fix:
   ```bash
   sed -i '' \
     -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
     -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
     -e 's|"../RetryButton"|"./RetryButton"|' \
     frontend/src/components/CharmChart.jsx frontend/src/components/VannaChart.jsx
   ```
4. If no regression: still commit a one-line marker (or skip to Phase 6). Either way log status pulse `DONE-PHASE-5`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — Auth on 6 leaky admin trading routes (~45 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `backend/routes/admin.py`

**Problem:** Six routes leak trading state with zero authentication. Anyone who finds these URLs sees your trading switch state, circuit breaker logs, Schwab connection health, etc. The architect already fixed admin.py's missing-await bug; this phase adds auth.

**Routes to protect:**
- `/api/admin/trading/status`
- `/api/admin/trading/circuit-breaker/log`
- `/api/admin/trading/circuit-breaker/reset`
- `/api/admin/trading/circuit-breaker/trip`
- `/api/admin/trading/transition`
- `/api/admin/schwab/health`

**Steps:**
1. Find the existing auth dependency:
   ```bash
   grep -rn 'verify_api_key\|Depends(verify' backend/ --include="*.py" | head -5
   ```
   You should find a `verify_api_key` function in `backend/auth.py` or similar.
2. For each of the 6 routes, add `_: bool = Depends(verify_api_key)` to the function signature:
   ```python
   from auth import verify_api_key  # add this import at top if not present
   from fastapi import Depends
   
   @router.get("/api/admin/trading/status")
   async def trading_status(_: bool = Depends(verify_api_key)):
       ...
   ```
3. Verify locally:
   ```bash
   # First restart backend if it's running:
   kill $(lsof -i :8000 -t) 2>/dev/null && sleep 2
   cd backend && source .venv/bin/activate && nohup uvicorn server:app --port 8000 > /tmp/uvicorn_owl.log 2>&1 &
   sleep 6
   
   # Now probe:
   for ep in trading/status trading/circuit-breaker/log schwab/health; do
     code=$(curl --max-time 5 -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/admin/$ep")
     echo "/api/admin/$ep without key → $code (expected 401)"
   done
   ```
4. Create `backend/tests/routes/test_admin_auth.py` with 6 tests (one per route), each asserting 401 without key and 200 with valid key. Test scaffold:
   ```python
   from fastapi.testclient import TestClient
   from server import app
   
   client = TestClient(app)
   
   def test_trading_status_requires_auth():
       r = client.get("/api/admin/trading/status")
       assert r.status_code == 401
   
   def test_trading_status_works_with_key():
       r = client.get("/api/admin/trading/status", headers={"X-API-Key": "test-secret-key"})
       assert r.status_code == 200
   ```
5. Run the tests:
   ```bash
   cd backend && python -m pytest tests/routes/test_admin_auth.py -v
   ```
   All must pass.

**Commit message** must include the curl outputs (401 without key, 200 with key) + pytest output. Push + origin gate. Status: `DONE-PHASE-6`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 7 — Move API keys out of URL query params (~30 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `backend/routes/alpha_advantage.py`

**Problem:** API keys passed as URL query parameters leak to server logs, browser history (if the URL ever reaches a client), proxy caches, and observability platforms. Alpha Vantage's API accepts the key in the URL but ALSO via Authorization header or POST body.

**Steps:**
1. Locate the query-param usage:
   ```bash
   grep -n 'apikey\|API_KEY' backend/routes/alpha_advantage.py
   ```
2. Refactor each call. Alpha Vantage's free tier still requires the key in the query string for most endpoints — if that's the only option, at minimum:
   a. Use a request module that omits the apikey from logged URLs (or strip it in your logging wrapper)
   b. Add a comment documenting that the upstream API requires query-param auth
   c. Ensure the key is read from env vars, not hardcoded
3. If Alpha Vantage actually supports header auth for some endpoints (check their docs), prefer header for those.
4. Verify:
   ```bash
   grep -n 'apikey=' backend/routes/alpha_advantage.py
   ```
   Either: (a) zero matches, OR (b) only matches wrapped in a comment explaining the upstream constraint.

**Commit message** documents the decision (header vs comment-and-strip). Push + origin gate. Status: `DONE-PHASE-7`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 8 — SECRET_KEY hard-fail in production (~20 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `backend/config/secrets.py` (find with `grep -rln 'SECRET_KEY' backend/config/ backend/ --include="*.py" 2>/dev/null | head -3`)

**Problem:** Currently defaults to `"dev-only-key"` if `SECRET_KEY` env var is missing, even in production. Architect-approved decision: hard-fail in production.

**Fix:**
```python
import os, sys

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").lower()
SECRET_KEY = os.environ.get("SECRET_KEY")

if not SECRET_KEY:
    if ENVIRONMENT in {"production", "staging"}:
        sys.exit(
            "FATAL: SECRET_KEY env var is required when ENVIRONMENT is "
            f"'{ENVIRONMENT}'. Refusing to start with default dev key. "
            "Set SECRET_KEY in your environment, or set ENVIRONMENT=dev for local."
        )
    SECRET_KEY = "dev-only-key"  # only allowed when ENVIRONMENT=dev
```

**Verify:**
```bash
# Should exit non-zero with the FATAL message:
cd backend && source .venv/bin/activate
ENVIRONMENT=production SECRET_KEY= python -c "from config.secrets import SECRET_KEY" 2>&1 | head -3
echo "Exit code: $?"

# Should work fine:
ENVIRONMENT=dev SECRET_KEY= python -c "from config.secrets import SECRET_KEY; print('OK:', SECRET_KEY[:10])"
```

Push + origin gate. Status: `DONE-PHASE-8`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 9 — Deployment hygiene quick wins (6 fixes, ~60 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `docker-compose.prod.yml`, `infra/main.bicep` (or wherever the Bicep file lives — find with `find . -name "*.bicep" -not -path "*/.venv/*"`), `docker-compose.yml`, `.github/workflows/deploy.yml`, `frontend/public/offline.html` (NEW), `.gitignore`

**6 fixes:**

1. **`docker-compose.prod.yml`** — change `dockerfile: Dockerfile` → `dockerfile: Dockerfile.backend` for the backend service. Verify:
   ```bash
   docker compose -f docker-compose.prod.yml config 2>&1 | head -3
   ```
2. **`infra/main.bicep`** — dedupe duplicate `capabilities: ['EnableMongo']` block AND duplicate subnet declaration. Use:
   ```bash
   grep -n 'EnableMongo\|subnet' infra/main.bicep | head -10
   ```
   to find both pairs. Remove ONE of each. Verify:
   ```bash
   bicep build infra/main.bicep 2>&1 | head -3   # only if bicep CLI is installed; skip with comment if not
   ```
3. **`docker-compose.yml:39`** — port mapping `3000:80` → `3000:3000` (the container actually serves on port 3000, not 80).
4. **`.github/workflows/deploy.yml`** — change `app-name: confluence-decoder` → `app-name: floww-prod-app` (must match what's in `infra/main.bicep` / terraform).
5. **`frontend/public/offline.html`** — create this file (the service worker references it but it doesn't exist, so offline fallback gives a 404):
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
     <meta charset="utf-8">
     <title>Confluence Decoder — Offline</title>
     <meta name="viewport" content="width=device-width, initial-scale=1">
     <style>
       body { background: #0a0a1a; color: #e0e0e0; font-family: monospace;
              text-align: center; padding: 60px 20px; margin: 0; }
       h1 { color: #34d399; font-size: 24px; }
       p { color: #94a3b8; font-size: 14px; }
       a { color: #34d399; }
     </style>
   </head>
   <body>
     <h1>Offline</h1>
     <p>The Confluence Decoder is currently offline.</p>
     <p>Cached data may still be available. Refresh when network returns.</p>
     <p><a href="/">Retry connection</a></p>
   </body>
   </html>
   ```
6. **`.gitignore`** — add `models/` to stop tracking 11MB of binary model artifacts going forward (existing tracked models stay tracked unless `git rm --cached` is run, which is OUT OF SCOPE).

Commit ALL six fixes as one commit. Each fix should appear in the message body with a one-line verification command + expected output. Push + origin gate. Status: `DONE-PHASE-9`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 10 — bare `except:` → `except Exception:` (~30 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** All `backend/**/*.py` matching `ruff check --select E722 backend/`. Special: `backend/services/social_flow_pipeline.py:335`.

**Problem:** Bare `except:` catches `KeyboardInterrupt` and `SystemExit`, preventing Ctrl-C and clean shutdown. `except Exception:` is the correct form.

**Steps:**
1. Baseline:
   ```bash
   cd backend && source .venv/bin/activate
   ruff check --select E722 . 2>&1 | tee /tmp/r9_E722_before.txt | tail -3
   ```
2. Auto-fix what's mechanically safe:
   ```bash
   ruff check --select E722 --fix .
   ```
3. For any remaining matches that ruff can't auto-fix (rare — multi-line or unusual formatting), edit manually. Special handling:
   - `backend/services/social_flow_pipeline.py:335` — MUST become `except Exception:` (currently catches KeyboardInterrupt, prevents Ctrl-C).
4. Confirm zero E722 remain:
   ```bash
   ruff check --select E722 .
   ```
   Should output `All checks passed!`
5. Run the test suite to confirm no regression:
   ```bash
   python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -3
   ```
   Passing count must be ≥ 2,329 (the pre-Phase-10 baseline).

**Commit message** includes before/after E722 count + test count. Push + origin gate. Status: `DONE-PHASE-10`.

═══════════════════════════════════════════════════════════════════════════════
PHASE 11 — Lint CI gate (~25 min, last phase)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `.github/workflows/lint.yml` (NEW), `backend/pyproject.toml`

**Goal:** prevent future drift on what was just cleaned up (unused imports, prints, bare excepts).

**Steps:**

1. Add ruff config to `backend/pyproject.toml`. If the file exists, add (or update) the `[tool.ruff]` section:
   ```toml
   [tool.ruff]
   line-length = 120
   target-version = "py312"
   
   [tool.ruff.lint]
   select = ["E", "F", "W", "I"]   # pycodestyle, pyflakes, warnings, isort
   ignore = ["E501"]                # line-too-long is already controlled by line-length
   
   [tool.ruff.lint.per-file-ignores]
   "tests/*" = ["F401", "F811"]    # tests may have intentional unused imports
   ```
   If `pyproject.toml` doesn't exist, create it with these contents.

2. Create `.github/workflows/lint.yml`:
   ```yaml
   name: lint
   on:
     pull_request:
       paths: ['backend/**', '.github/workflows/lint.yml']
     push:
       branches: [main]
       paths: ['backend/**']
   jobs:
     ruff:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.12'
         - run: pip install ruff
         - run: cd backend && ruff check .
   ```

3. Validate the workflow YAML:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml')); print('YAML valid')"
   ```

4. Run ruff with the new config locally to confirm it passes:
   ```bash
   cd backend && ruff check .
   ```
   Should output `All checks passed!`

**Commit message** includes the workflow validity check + local ruff pass. Push + origin gate. Status: `DONE-PHASE-11`.

═══════════════════════════════════════════════════════════════════════════════
CLOSURE — write summary doc + status pulse + STOP
═══════════════════════════════════════════════════════════════════════════════

After Phase 11 lands on origin:

```bash
cat > docs/ROUND9_OWL_CLOSURE.md <<EOF
# Round 9 Owl Alpha Closure

Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by Owl Alpha agent.

## Phases completed (11/11)

$(git log origin/main --since="10 hours ago" --grep="round-9-phase.*OWL" --pretty=format:"- %h %s")

## Test suite delta
$(cd backend && source .venv/bin/activate && python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -3)

## Files touched
$(git diff --name-only $(cat /tmp/r9_OWL_start.txt) HEAD | head -40)

## Out of scope (deferred to Round 10)
- App.js toggle composition (CHARM/Chain/Expiries/DTE wiring)
- Skylit hang investigation (/api/heatseeker/flip-zones 500)
- Backend ML feature unification (3 cloned compute paths)
- ML training data leakage (labels before temporal split)
- Type-hint adoption (88.8% functions still untyped)
EOF

git add docs/ROUND9_OWL_CLOSURE.md
git commit -m "docs(round-9-OWL): closure with origin-verified phase SHAs

Co-Authored-By: Owl Alpha <owl@floww.dev>"
git pull --rebase origin main && git push origin main

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] OWL :: DONE-ALL :: 11 phases on origin :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_OWL_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

echo ""
echo "──── ROUND 9 OWL ALPHA COMPLETE ────"
echo "Start HEAD:    $(cat /tmp/r9_OWL_start.txt)"
echo "Final HEAD:    $(git rev-parse HEAD)"
echo "Test count:    $(cd backend && python -m pytest -q --ignore=tests/e2e --tb=no 2>&1 | tail -1)"
echo "Closure doc:   docs/ROUND9_OWL_CLOSURE.md"
echo "─────────────────────────────────────"
echo "DONE"
```

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS — read after every phase
═══════════════════════════════════════════════════════════════════════════════

- Phases are STRICTLY sequential. Each phase's first step is the origin-state gate for the prior phase. You cannot skip phases.
- You do NOT touch `App.js`, `App.css`, `dash_ui.py`, `inference.py`, `conftest.py`, `server.py`, or any model artifact. EVER.
- If you finish all 11 phases before 8 hours: print closure and STOP. Do NOT invent additional work — there are no Phase 12 or Phase 13. The 132 unverified audit findings are Round 10 backlog.
- Every commit message claim must be backed by a grep/curl/test output INLINE in the message body. No fabricated success claims.
- If you HALT: the architect monitors every 15 min and resolves halts within ~5 min average. Wait for the architect's authorization before proceeding.

END OF PROMPT. BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
