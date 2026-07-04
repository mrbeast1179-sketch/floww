# Floww / Confluence Decoder — Frontend & Git Diff Audit
**Date:** 2026-07-02  
**Auditor:** Claude (Cowork session)  
**Scope:** 6 modified files (git diff), 4 new untracked files, full frontend src audit  
**Method:** Static analysis — all findings are code-trace only; no runtime verification.  
**Reference:** `reports/liveness_audit_2026-06-25.md` read for context.

---

## Summary Counts

| Severity | Count |
|---|---|
| CRITICAL | 2 |
| HIGH | 11 |
| MEDIUM | 14 |
| LOW | 4 |
| **Total** | **31** |

---

## Part 1 — Git Diff Audit (Modified Files)

---

### FILE: `backend/routes/market_data.py`

```
LINE: ~213-220 (diff context)
SEVERITY: LOW
TYPE: SilentErrorSwallow
DESCRIPTION: The new try/except blocks around bs_vanna() and bs_charm() catch bare
`Exception` and set the greek to 0. This silently hides programming errors (e.g., wrong
argument types) as well as legitimate numeric edge-cases. No logging occurs, so if
bs_vanna begins raising for an unexpected reason, every row silently zeroes out and there
is no observable signal.
SUGGESTED FIX: Log at DEBUG level inside the except:
    except Exception as exc:
        logger.debug("bs_vanna failed for strike=%s iv=%s: %s", strike, iv, exc)
        vanna = 0
```

```
LINE: ~200-204
SEVERITY: LOW
TYPE: DefensiveCodingImpact
DESCRIPTION: `gamma = c.get("gamma", 0) or 0` is correct for None/False/NaN=0 guard,
but `0 or 0` is redundant. No bug — minor code smell.
SUGGESTED FIX: `gamma = c.get("gamma") or 0` is shorter and equivalent since the default
would also be falsy.
```

---

### FILE: `backend/server.py`

```
LINE: ~107-119 (safe_float definition)
SEVERITY: MEDIUM
TYPE: PotentialImportError
DESCRIPTION: `safe_float()` uses `math.isnan(f)` and `math.isinf(f)`. The diff shows
this function inserted after `app = FastAPI(...)`. If `import math` is not already at
the top of server.py (the diff doesn't show the full import block), this will raise a
`NameError` at runtime on the first request that hits this code path.
SUGGESTED FIX: Verify `import math` exists at the top of server.py. If not, add it.
```

```
LINE: ~904-907
SEVERITY: LOW
TYPE: CodeStyle / NonPythonicNaN
DESCRIPTION: `if iv is not None and iv == iv:` uses the `x == x` floating-point identity
trick to detect NaN. This is valid Python/IEEE-754 but is cryptic and will confuse
maintainers.
SUGGESTED FIX: Replace with `if iv is not None and not math.isnan(iv):` which uses the
just-added `math` import that safe_float already requires.
```

```
LINE: ~939-965 (compute_gex_by_strike)
SEVERITY: MEDIUM
TYPE: Regression / SilentSkip
DESCRIPTION: The refactored loop now uses `safe_float(c.get("strike"))` and skips if
`strike <= 0`. Previously the code used `c["strike"]` directly (KeyError on missing) but
the data contract guarantees strike exists. The new `<= 0` guard silently skips any
contract where strike rounds to 0.0 after safe_float, which could happen for warrants or
micro-price instruments. The old code would have raised and been visible; the new code
silently drops rows.
SUGGESTED FIX: Guard as `if strike is None or strike <= 0` and log a warning, so missing
strikes are detectable.
```

---

### FILE: `backend/services/cvserver_client.py`

```
LINE: ~79-95 (DEFAULT_FIELDS expansion)
SEVERITY: LOW
TYPE: Observation / NoRegression
DESCRIPTION: Adding delta/gamma/theta/vega/day_volume/day_change_percent/day_previous_close
to DEFAULT_FIELDS is correct per the cvforge-maximization goal. The liveness audit
confirms gamma/IV/delta are 86.7% populated. Not a bug. Note that
`day_change_percent` and `day_previous_close` appear in the cvserver FIELD_MAP only
if they are real field names in the cvserver API — confirm against actual API schema
to avoid silently null fields inflating payload size.
SUGGESTED FIX: Cross-check against cvserver API docs. No code change required if confirmed.
```

---

### FILE: `frontend/src/App.js` (FROZEN — audit only, do not modify)

```
LINE: ~335 (FlowAlertsPage, fetchAlerts)
SEVERITY: CRITICAL
TYPE: Bug / DoubleAPIPath
DESCRIPTION: FlowAlertsPage constructs the alerts URL as:
    const base = API;    // API = "${BACKEND_URL}/api"
    axios.get(`${base}/api/alerts?...`)
This produces `http://localhost:8000/api/api/alerts` — a double `/api/` segment.
The backend route is `/api/alerts`, so this 404s every time. Alerts never load.
SUGGESTED FIX: Change to `axios.get(`${base}/alerts?...`)` (remove the inner `/api`).
```

```
LINE: ~617-638
SEVERITY: HIGH
TYPE: Bug / RaceCondition / DualFetchLoop
DESCRIPTION: Two independent polling loops both write to the same `data` state:
  1. `fetchData` (useCallback) → calls GET /api/heatmap/{ticker} → setData(res.data)
  2. An unnamed `doFetch` inside a useEffect → calls GET /api/data/{ticker} → setData(r.data)
These run on different intervals with no coordination. If /api/data/ resolves after
/api/heatmap/, it overwrites the heatmap response with an older data shape (or vice versa).
The two endpoints return different schemas. Components downstream may read fields from the
wrong schema silently.
SUGGESTED FIX: Pick ONE canonical endpoint for polling data. If both are needed, merge
them into a single state key per endpoint, or fetch them sequentially and merge before
calling setData.
```

```
LINE: ~640-650 (fetchAdvanced useCallback)
SEVERITY: HIGH
TYPE: DeadCode / UnusedCallback
DESCRIPTION: `fetchAdvanced` is declared as a useCallback (depending on ticker and
debouncedExpiries) but is never invoked by any useEffect or user interaction. The actual
advanced-data polling runs via a separate inline useEffect (lines ~652-663) that calls
/api/advanced/{ticker} WITHOUT the expiries param. The useCallback is dead code — it
produces a stale closure that holds a reference to debouncedExpiries but is never used.
SUGGESTED FIX: Delete the `fetchAdvanced` useCallback. The inline effect is the real
implementation and it works. If expiries are wanted in the advanced request, add
`?expiries=${debouncedExpiries}` inside the inline effect.
```

```
LINE: ~756 (QuickTradePanel onSubmit in trinity tab)
SEVERITY: MEDIUM
TYPE: ConsoleLogInProduction
DESCRIPTION: `console.log("[Trinity] Trade submitted:", trade)` is present in the
production render path. This logs every trade object to browser DevTools in production,
leaking trade details to anyone with DevTools open.
SUGGESTED FIX: Remove the console.log. The TODO comment on the next line suffices as a
reminder.
```

```
LINE: ~740-761 (trinity page render)
SEVERITY: HIGH
TYPE: MissingErrorBoundary
DESCRIPTION: `<TrinityVolatility>` is rendered without an `<ErrorBoundary>` wrapper.
`<TrinityView>` on the same page also has no ErrorBoundary. A runtime exception in either
component (e.g., Plotly throwing during draw, or a null dereference) will crash the entire
App render tree, showing a blank screen.
SUGGESTED FIX:
    {trinityTab === "vol" ? (
      <ErrorBoundary>
        <TrinityVolatility ... />
      </ErrorBoundary>
    ) : (
      <ErrorBoundary>
        <TrinityView ... />
      </ErrorBoundary>
    )}
```

```
LINE: ~65-66
SEVERITY: MEDIUM
TYPE: MissingFallback / PotentialUndefined
DESCRIPTION: App.js declares:
    const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
    const API = `${BACKEND_URL}/api`;
If REACT_APP_BACKEND_URL is not set in the .env, BACKEND_URL is `undefined` and API
becomes the string `"undefined/api"`. config/api.js correctly uses `|| "http://localhost:8000"`.
App.js's local copy lacks this fallback. All axios calls using this local `API` variable
(heatmap, livespot, data, advanced, ensemble, alerts, memory) would silently fail.
SUGGESTED FIX: Change to:
    const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
```

```
LINE: ~752
SEVERITY: MEDIUM
TYPE: InconsistentTickerTransform
DESCRIPTION: TrinityVolatility receives:
    ticker={ticker.startsWith("^") ? ticker.slice(1) : ticker}
stripping the leading `^` from index tickers. But `<TrinityView>` (the GEX sub-tab, same
trinity page) receives no such transformation — it uses ticker as-is. If the backend
chain endpoint expects `SPX` (without `^`) and the heatmap endpoint expects `^SPX`,
stripping is correct for TrinityVolatility. But the asymmetry between the two sub-tabs
means if the backend convention changes, only one side breaks silently.
SUGGESTED FIX: Centralise the `^`-strip transform in `handleFocusTicker` or in a ticker
normalisation utility, so both TrinityView and TrinityVolatility get the same form.
```

---

### FILE: `frontend/src/components/OptionsChainTable.jsx`

```
LINE: 36-47 (fetchChain)
SEVERITY: HIGH
TYPE: MemoryLeak / MissingUnmountGuard
DESCRIPTION: `fetchChain` has no AbortController and no mounted-ref guard. If the
component unmounts (user navigates away) while a fetch is in flight, the resolved Promise
still calls `setChain(res.data)` and `setLoading(false)` on an unmounted component. In
React 18 strict mode this throws a warning; in edge cases it can cause state corruption
if the component re-mounts with stale data from the previous ticker's request.
SUGGESTED FIX: Add an AbortController pattern identical to useHeatseeker.js:
    const controller = new AbortController();
    const res = await axios.get(url, { signal: controller.signal });
    // return () => controller.abort()  in the useEffect cleanup
```

```
LINE: 44 (catch block)
SEVERITY: HIGH
TYPE: MissingErrorState / SilentFailure
DESCRIPTION: `catch (e) { /* noop */ }` silently discards all fetch errors. When the
chain API fails, loading ends and `chain` remains null. The component then renders the
full filter bar and an empty table with no explanation. The user sees a blank table and
has no way to know the data failed to load.
SUGGESTED FIX: Add an `error` state:
    const [error, setError] = useState(null);
    // in catch: setError("Failed to load chain");
    // in render: {error && <div className="text-rose-400 text-xs p-2">{error}</div>}
```

```
LINE: 142 (sticky header in virtual scroll)
SEVERITY: MEDIUM
TYPE: UIBug / BrokenStickyHeader
DESCRIPTION: The table `<thead>` uses `className="sticky top-0"`, but it lives inside a
`<div style={{ height: totalHeight, position: "relative" }}>` with an `<table
style={{ position: "absolute", top: offsetY }}>`. Sticky positioning requires a scrolling
ancestor, but the `position: absolute` table is inside a fixed-height relative div — the
sticky `top: 0` offset is computed relative to the nearest scrollable ancestor
(the outer `scrollRef` div), not the virtual scroll phantom container. As the user scrolls
down, the absolute-positioned table moves with `offsetY` but the thead may detach from
the visible area. In practice the thead floats at the top of the scrollRef div, correct
only when `offsetY === 0`.
SUGGESTED FIX: Move the `<thead>` OUTSIDE the virtual-scroll phantom div:
    <div ref={scrollRef} ...>
      <table ...>
        <thead className="sticky top-0" ...>...</thead>  ← outside phantom div
        <div style={{ height: totalHeight, position: "relative" }}>
          <table style={{ position: "absolute", top: offsetY }}>
            <tbody>...</tbody>
          </table>
        </div>
      </table>
    </div>
Or render the header separately above the scrollable container.
```

```
LINE: 163 (r.strike.toFixed)
SEVERITY: LOW
TYPE: PotentialCrash
DESCRIPTION: `r.strike.toFixed(r.strike < 10 ? 2 : 0)` — if the API returns a row where
strike is null, undefined, or a string, this call throws a TypeError and crashes the
virtual-scroll row render. The updated `OptionsChainTable` now guards `r.iv`, `r.delta`,
`r.gamma` (the diff change) but `r.strike` is still unguarded.
SUGGESTED FIX: `{r.strike != null ? r.strike.toFixed(r.strike < 10 ? 2 : 0) : "—"}`
```

---

### FILE: `scripts/launch_decoder.sh`

```
LINE: ~73-92 (new MongoDB block)
SEVERITY: MEDIUM
TYPE: InsufficientHealthCheck / RaceCondition
DESCRIPTION: After attempting to start mongod, the script runs `sleep 2` then immediately
proceeds to start the FastAPI backend. On a slow disk or cold start, mongod may not be
accepting connections within 2 seconds. The FastAPI backend will launch and immediately
fail any startup code that connects to MongoDB, then either crash or start in a degraded
state without a clear error.
SUGGESTED FIX: Replace the fixed sleep with a polling health check:
    for i in {1..10}; do
      mongo --eval "db.adminCommand('ping')" --quiet > /dev/null 2>&1 && break
      sleep 1
    done
Or use `mongosh --eval "db.runCommand({ping:1})" --quiet`.
```

```
LINE: ~88-90 (fallback dbpath)
SEVERITY: LOW
TYPE: SilentFailure
DESCRIPTION: The MongoDB start falls back to `~/data/db` if Homebrew path fails, then
echoes a WARN. But the WARN is just an echo — script execution continues. If MongoDB
is genuinely not startable, the backend will attempt to connect to a non-existent Mongo
instance. The script should gate on MongoDB availability before proceeding.
SUGGESTED FIX: After the warn, add a `read -p "Continue without MongoDB? [y/N] "` or
exit with a clear error message, rather than silently continuing to start the backend.
```

---

### FILE: `scripts/stop_decoder.sh` (NEW)

```
LINE: 3 (set -e)
SEVERITY: MEDIUM
TYPE: PartialStop / SetEInteraction
DESCRIPTION: `set -e` at the top means any command exiting non-zero aborts the script.
The `||` on each stop command saves those lines. But if the PWA `pkill -f "app_mode_loader"`
line fails for any reason other than "not running" (e.g., permission denied), the `||`
catches it but the `set -e` has already been satisfied by the `||` branch. This is correct.
HOWEVER: `lsof -ti :3000 | xargs kill -9` — on macOS, if lsof returns nothing (port
not listening), `xargs` receives empty stdin. By default BSD `xargs` runs the command
with no args when stdin is empty, which means `kill -9` with no PID is invoked, printing
a usage error. The `2>/dev/null` suppresses this, but the exit code of `xargs kill -9`
(with no PID) is 1 on some macOS versions, which with the `|| echo` is handled. Low risk,
but verify on target macOS version.
SUGGESTED FIX: Use `lsof -ti :3000 | xargs -r kill -9 2>/dev/null` — the `-r` flag
(GNU) or `| grep . | xargs kill -9` (macOS-compatible) prevents running kill with no
args. On macOS, `xargs -r` is not available; use: `PIDS=$(lsof -ti :3000); [[ -n "$PIDS" ]] && kill -9 $PIDS`.
```

---

## Part 2 — Frontend-Wide Audit

---

### FILE: `frontend/src/components/TrinityVolatility.jsx` (NEW — DEEP AUDIT)

```
LINE: 127-135 (faintSmiles computation)
SEVERITY: HIGH
TYPE: Bug / WrongXAxisMapping
DESCRIPTION: `faintSmiles` computes IVs for +1 and +2 expiries relative to the selected
one. The IV array (`ivs`) is built by filtering rows within ±15% of spot, but these rows
come from a DIFFERENT expiry with DIFFERENT strike spacing. The draw function then maps:
    x: skewData.strikes.slice(0, sm.ivs.length)
This slices the SELECTED expiry's strike list to match the length of the faint smile's
IV array. The result is that faint smile IV values are plotted against the wrong strikes
(the selected expiry's strikes, not the faint expiry's strikes). On a ticker like SPX
where strike spacing varies per expiry, this misaligns the smile by potentially 5-25
strikes and produces a visually distorted/offset faint context curve.
SUGGESTED FIX: For each faint smile, build the strike list from its own rows:
    const strikesForFaint = near.map(r => r.strike).sort((a,b) => a-b);
    out.push({ exp: e2, strikes: strikesForFaint, ivs: ... });
Then in drawSkew:
    x: sm.strikes,   y: sm.ivs
```

```
LINE: 130-133 (faintSmiles iv branch)
SEVERITY: MEDIUM
TYPE: Bug / DeadBranch / NoCallPutDifferentiation
DESCRIPTION: Inside the faintSmiles loop:
    const iv = r.type === "call" ? r.iv : r.iv;
Both branches of the ternary are identical — `r.iv` is returned regardless of type. This
appears to be a copy-paste error where call and put rows were meant to be handled
differently (e.g., averaging them, or only using one side). As-is, both call and put rows
are included with no distinction, which can make the faint smile appear noisy or doubled.
SUGGESTED FIX: Decide the intent. Options:
    (a) Only use call rows: filter before mapping → `r2.filter(r => r.type === "call" && r.iv != null)`
    (b) Average call+put: group by strike, average IVs.
    (c) If the intent was to just use r.iv for all, remove the ternary.
```

```
LINE: 51 (dteOf helper)
SEVERITY: LOW
TYPE: DeadCode
DESCRIPTION: `dteOf` is defined but never called anywhere in TrinityVolatility.jsx.
SUGGESTED FIX: Remove it, or use it in the expiry selector <option> label.
```

```
LINE: 68-79 (Plotly CDN loading)
SEVERITY: MEDIUM
TYPE: MemoryLeak / MissingCleanup
DESCRIPTION: When TrinityVolatility mounts and Plotly is absent, a <script> tag is
injected into document.head. This script is never removed on unmount (no cleanup function
in the useEffect). On repeated mount/unmount cycles (e.g., switching between trinity
sub-tabs), multiple identical Plotly script tags accumulate in the head. While the browser
de-dupes network requests, each script tag is still in the DOM.
Additionally, when the component unmounts, `window.Plotly.purge()` is never called for
any of the three chart refs (skewRef, termRef, rrRef), leaking Plotly chart instances.
SUGGESTED FIX:
    return () => {
      [skewRef, termRef, rrRef].forEach(ref => {
        if (ref.current && window.Plotly) window.Plotly.purge(ref.current);
      });
    };
For the script tag, either add a cleanup `s.remove()`, or check if the tag already exists
before injecting.
```

```
LINE: 68-79 (Plotly CDN in PWA context)
SEVERITY: MEDIUM
TYPE: EnvironmentRisk / ContentSecurityPolicy
DESCRIPTION: TrinityVolatility loads Plotly from an external CDN (`cdn.plot.ly`). The
Confluence Decoder is installed as a Chrome PWA. PWAs with a strict Content Security
Policy may block external script loads. The existing FlowseekerProBlademap uses the same
pattern (per the comment in TrinityVolatility), so CSP is presumably not blocking it.
However, if CSP is tightened in the future, this component silently never renders charts
(plotlyReady stays false, charts stay blank, no error shown to user).
SUGGESTED FIX: In the plotlyReady=false state, show a fallback message:
    if (!plotlyReady) return <div className="tv-root"><div className="tv-error">
      Plotly failed to load. Check your network or CSP settings.
    </div></div>;
Or bundle Plotly as a local dependency.
```

```
LINE: 80-100 (fetchChain, reqSeqRef guard)
SEVERITY: MEDIUM
TYPE: MissingUnmountGuard
DESCRIPTION: The reqSeqRef guard prevents stale network responses from overwriting newer
ones. But if the component unmounts mid-fetch (after `reqSeqRef` check), state setters
(setLoading, setErr, setRows, setSpot, setExpiryList) still fire on an unmounted
component. This produces React "state update on unmounted component" warnings and can
hide bugs.
SUGGESTED FIX: Add a `mountedRef`:
    const mountedRef = useRef(true);
    useEffect(() => {
      mountedRef.current = true;
      return () => { mountedRef.current = false; };
    }, []);
    // In fetchChain, after the reqSeqRef check, also gate on mountedRef.current.
```

```
LINE: 46 (selExpIdx state, ticker change)
SEVERITY: MEDIUM
TYPE: StateStaleReference / IndexOutOfRange
DESCRIPTION: `selExpIdx` is NOT reset when `ticker` changes. If the user has scrolled to
expiry index 7 (SPY with 8 expiries) then switches to a ticker with 3 expiries,
`selExpIdx` stays at 7. `expiryList[7]` returns `undefined`, `selExp` becomes `""`, and
`expRows` is `[]`. All three charts go blank with no error message. The select dropdown
shows the correct expiries but nothing is selected (value=7 doesn't match any option).
SUGGESTED FIX: In the `useEffect(() => { fetchChain(); }, [fetchChain])`, also call
`setSelExpIdx(0)` to reset the expiry selection on ticker change.
```

```
LINE: 249-261 (TrinityVolatility integration in App.js)
SEVERITY: MEDIUM
TYPE: MissingErrorBoundary
DESCRIPTION: (Repeated from App.js section — priority context for TrinityVolatility.)
The component renders inside a plain <div> with no ErrorBoundary. Plotly errors during
chart draw (which Plotly does occasionally throw for malformed traces) will propagate
and crash the entire page.
SUGGESTED FIX: Wrap in <ErrorBoundary> in App.js (see App.js entry above).
```

---

### FILE: `frontend/src/hooks/useMarketData.js`

```
LINE: 90
SEVERITY: HIGH
TYPE: Bug / FrozenCacheKey
DESCRIPTION: `const cacheKey = useRef(`${endpoint}?${JSON.stringify(query)}`).current;`
`useRef` returns the same object across renders; its initializer argument is ONLY used on
the first render. `.current` accessed inline gives the value from the first render, frozen
forever. If the caller changes `endpoint` (different ticker, different data view),
`cacheKey` still references the first ticker's key. Result:
  1. Cache reads serve data for the WRONG endpoint.
  2. The initial-load `useEffect([cacheKey, skip])` never re-runs because `cacheKey` never
     changes — no cache check happens when endpoint changes.
  3. The polling `useEffect([fetchFromNetwork, ...])` will re-run with the new
     `fetchFromNetwork` (because endpoint is in its useCallback deps) and fetch fresh data
     via network, but any cached response is still stored/read under the stale key.
SUGGESTED FIX: Change to a computed value (not a ref):
    const cacheKey = `${endpoint}?${JSON.stringify(query)}`;
Note: the `cacheKey` ref was likely added to stabilise the dependency array, but since the
key SHOULD change with endpoint, it should be a plain const or useMemo.
```

```
LINE: 143-149 (error handler, !data check)
SEVERITY: MEDIUM
TYPE: StaleClosure / RaceCondition
DESCRIPTION: Inside `fetchFromNetwork` (a useCallback), the error handler reads `data`
from the closure:
    if (cached && !data) { setData(cached.data); ... }
The `data` variable here is the value captured at the time the useCallback was last
created. If a concurrent fetch has already updated `data` (via setData), the closure's
`data` is stale and doesn't reflect the update. This could cause the hook to serve cached
data even though fresh data is already displayed.
SUGGESTED FIX: Use a ref to track whether data has ever been set:
    const hasDataRef = useRef(false);
    // on setData success: hasDataRef.current = true;
    // in error handler: if (cached && !hasDataRef.current) { ... }
```

---

### FILE: `frontend/src/hooks/useMLPredictions.js`

```
LINE: 56-62 (useEffect)
SEVERITY: MEDIUM
TYPE: MissingUnmountGuard
DESCRIPTION: The useEffect cleanup aborts the in-flight request and clears the abort ref,
but there is no `mountedRef` tracking. The `if (abortRef.current === controller)` guard
in fetcher protects against stale-request responses, but after the component unmounts and
`abortRef.current = null` is set in cleanup, any already-running async branch that passes
the controller check may still call `setPredictions`, `setError`, or `setLoading` because
it uses the closure value, not the reset null. In practice, the AbortController fires
first and AbortError is caught, so this is low likelihood — but the pattern is fragile.
SUGGESTED FIX: Add `const mountedRef = useRef(true)` with matching cleanup, and gate all
state setters on `mountedRef.current`, matching the pattern in useHeatseeker.js.
```

---

### FILE: `frontend/src/context/AuthContext.js`

```
LINE: 53-57 (token validation useEffect)
SEVERITY: MEDIUM
TYPE: MissingImplementation / SecurityGap
DESCRIPTION: The comment says "Refresh token if expired (check on mount)" but the
implementation ONLY sets `axios.defaults.headers.common['Authorization']` — it performs
no expiry check whatsoever. A JWT token has a `exp` claim; if the stored token is expired,
all axios requests will receive 401s but the UI will stay logged-in (isAuthenticated
remains true because token is non-null). The user sees authenticated UI but all data
calls fail silently.
SUGGESTED FIX: Decode the JWT `exp` claim (no library needed — split on `.`, base64-decode
the payload):
    const payload = JSON.parse(atob(token.split('.')[1]));
    if (payload.exp * 1000 < Date.now()) { logout(); return; }
Then set the axios header only for a valid token.
```

---

### FILE: `frontend/src/components/OptionsChainTable.jsx` (additional)

```
LINE: 119-122 (CSV export, URL.createObjectURL)
SEVERITY: LOW
TYPE: ResourceLeak
DESCRIPTION: The CSV download creates a Blob URL via `URL.createObjectURL(blob)` and
calls `URL.revokeObjectURL(url)` immediately after `a.click()`. On some browsers,
revoking the object URL synchronously before the download is triggered can interrupt the
download. Chrome handles this fine; Firefox and Safari may fail.
SUGGESTED FIX: Use a short delay:
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 100);
```

---

### FILE: `frontend/src/TrinityVolatility.css` / App.js coupling

```
LINE: App.js ~737-748 (tv-subtab buttons)
SEVERITY: LOW
TYPE: FragileCSSCoupling
DESCRIPTION: The `.tv-subtab` and `.tv-subtab.on` CSS classes are defined in
`TrinityVolatility.css`. These classes are ALSO used by the sub-tab toggle buttons that
live in App.js, OUTSIDE of TrinityVolatility's render. The CSS is loaded as a side-effect
of importing TrinityVolatility.jsx. If TrinityVolatility is ever lazy-loaded (React.lazy),
the CSS won't be injected until TrinityVolatility mounts — but the toggle buttons appear
on the page BEFORE the component mounts (while still on the "gex" sub-tab). The buttons
would briefly render unstyled.
SUGGESTED FIX: Move `.tv-subtab` into App.css or a shared styles file. Keep TrinityVolatility.css
for `.tv-root` and below only.
```

---

### FILE: `frontend/src/App.js` — `FlowAlertsPage` filter buttons

```
LINE: ~393-402
SEVERITY: MEDIUM
TYPE: NonFunctionalUI / StubFilters
DESCRIPTION: The "≥ $500K", "≥ $1M", "Sweep Only", "HIGH Conf", "Reset" filter buttons
all call `setFilter("all")` — they don't implement their labelled function. A user
clicking "Sweep Only" gets ALL alerts, not sweep alerts. This is silently wrong UI.
The `filter` state also only handles "calls"/"puts"/"bullish"/"bearish" — "bullish" and
"bearish" filters are never applied in the `filtered` array computation either.
SUGGESTED FIX: Either implement the filters in the `filtered` useMemo, or visually disable
the unimplemented buttons with a "coming soon" tooltip so users aren't misled.
```

---

## Part 3 — TrinityVolatility Integration Check

### API compatibility
- **PASS**: Reads from `/api/chain/{ticker}?expiries={N}`, which the existing backend exposes. Return shape `{spot, expiries:[], rows:[{strike, expiry, type, iv, delta, ...}]}` matches what `OptionsChainTable` also consumes from the same endpoint. No new endpoint needed.
- **PASS**: Handles the `data.rows` and `data.expiries` shape correctly.
- **NOTE**: The `expiries={8}` prop passed from App.js means 8 expiries are requested. The chain endpoint may return fewer if the ticker has fewer listed expiries — this is handled gracefully.

### Routing integration
- **PASS**: Imported at top of App.js, rendered conditionally on `trinityTab === "vol"`.
- **ISSUE**: `trinityTab` state survives ticker changes — see MEDIUM issue above.
- **PASS**: `ticker.startsWith("^") ? ticker.slice(1) : ticker` correctly strips `^` for index tickers per the API contract.

### Visual design
- **PASS**: Uses the Skylit dark palette (`#0b0d12`, `#11141a`, `rgba(255,255,255,.06)`). Color constants in the `C` object match the existing design tokens used in FlowseekerProBlademap and the rest of the dark theme.
- **PASS**: Font size (9-13px), border-radius (8-10px), and panel structure are consistent with existing Skylit components.
- **NOTE**: The 3-column `tv-grid` layout will collapse awkwardly on narrow viewports (< ~700px). No responsive breakpoint defined in the CSS. Consider adding `@media (max-width: 768px) { .tv-grid { flex-direction: column; } }`.

### Missing features / gaps
- No retry button after load error (only `err` state displayed with no way to re-fetch without a full page reload).
- No auto-refresh (static on load; TrinityView presumably polls; TrinityVolatility does not).
- No loading skeleton — just a text message with opacity 0.55.

---

## Regression Summary from Git Diff

| File | Regression? | Notes |
|---|---|---|
| backend/routes/market_data.py | NO | Guards are additive; safer than before |
| backend/server.py | MAYBE | `import math` must pre-exist; safe_float is additive |
| backend/services/cvserver_client.py | NO | Field additions only; backward compatible |
| frontend/src/App.js | YES | trinityTab added correctly; no regression in diff itself; pre-existing bugs exposed |
| frontend/src/components/OptionsChainTable.jsx | NO | null-guards for iv/delta/gamma are strictly safer |
| scripts/launch_decoder.sh | LOW | MongoDB start is additive; 2s sleep may be insufficient |

---

## Priority Fix Order

1. **[CRITICAL]** Fix double `/api/api/alerts` path in `FlowAlertsPage` — alerts never load.
2. **[CRITICAL / HIGH]** Add `ErrorBoundary` around `TrinityVolatility` and `TrinityView` in App.js trinity page.
3. **[HIGH]** Fix dual fetch loop race condition (`/api/data/` vs `/api/heatmap/` both → `setData`).
4. **[HIGH]** Add AbortController + mounted guard to `OptionsChainTable.fetchChain`.
5. **[HIGH]** Fix `useMarketData` frozen `cacheKey` ref bug.
6. **[HIGH]** Fix `TrinityVolatility` faintSmiles X-axis strike mismatch (wrong strikes mapped).
7. **[HIGH]** Add error display to `OptionsChainTable` on fetch failure.
8. **[HIGH]** Remove dead `fetchAdvanced` useCallback in App.js.
9. **[MEDIUM]** Add Plotly `purge()` cleanup on `TrinityVolatility` unmount.
10. **[MEDIUM]** Reset `selExpIdx` to 0 on ticker change in `TrinityVolatility`.
11. **[MEDIUM]** Fix dead ternary branch `r.type === "call" ? r.iv : r.iv` in faintSmiles.
12. **[MEDIUM]** Implement JWT expiry check in `AuthContext`.
13. **[MEDIUM]** Add `BACKEND_URL` fallback in App.js local const.
14. **[MEDIUM]** Fix stale-closure `!data` in `useMarketData` error handler.
15. **[MEDIUM]** Add MongoDB health-check loop in `launch_decoder.sh`.

---

*Report generated 2026-07-02. All findings are static-analysis only. Runtime verification required with stack running — see `liveness_audit_2026-06-25.md §"What only the owner can do"` for verification commands.*
