# Frontend Bug Fixes — 2026-07-02

Applied 2026-07-03. All CRITICAL and HIGH severity issues resolved.

---

## CRITICAL Fixes

### FIX 1 — Double `/api` path (alerts never load)
**File:** `frontend/src/App.js` ~line 339
**Problem:** `FlowAlertsPage` built URL as `${base}/api/alerts` where `base = API = ${BACKEND_URL}/api`, producing `/api/api/alerts` — always 404.
**Fix:** Changed `${base}/api/alerts?...` → `${base}/alerts?...`
**Verification:** `grep -n "base}/api/" App.js` → 0 results ✓

### FIX 2 — ErrorBoundary wrapping TrinityVolatility
**File:** `frontend/src/components/TrinityVolatility.jsx` (top of file + main return)
**Problem:** Any runtime error inside the Trinity charts crashed the parent page silently.
**Fix:** Added `ErrorBoundary` class component after imports; wrapped main JSX return with `<ErrorBoundary>`.

### FIX 3 — BACKEND_URL missing fallback
**File:** `frontend/src/App.js` ~line 61
**Problem:** `const BACKEND_URL = process.env.REACT_APP_BACKEND_URL` — undefined if env var not set, making all API calls go to `undefined/api/...`.
**Fix:** Added `|| "http://localhost:8000"` fallback so dev mode works without a `.env`.

---

## HIGH Fixes

### FIX 4 — Dead call/put IV ternary
**File:** `frontend/src/components/TrinityVolatility.jsx` (faintSmiles computation)
**Problem:** `const iv = r.type === "call" ? r.iv : r.iv` — both branches identical, never used type-specific fields.
**Fix:** `const iv = r.type === "call" ? r.call_iv ?? r.iv : r.put_iv ?? r.iv` — uses `call_iv`/`put_iv` if present, falls back to `iv`.

### FIX 5 — `selExpIdx` not reset on ticker change
**File:** `frontend/src/components/TrinityVolatility.jsx` (`fetchChain` callback)
**Problem:** Switching from a ticker with 8 expiries to one with 3 left `selExpIdx` at e.g. 7, causing `expiryList[7]` to be `undefined` and all expiry-scoped chart data to be empty.
**Fix:** Added `setSelExpIdx(0)` immediately after `setExpiryList(...)` inside `fetchChain`.

### FIX 6 — Plotly instances leak on unmount
**File:** `frontend/src/components/TrinityVolatility.jsx`
**Problem:** `Plotly.react()` calls registered WebGL contexts and event listeners but nothing purged them on component unmount, leaking memory each time the Trinity panel was toggled.
**Fix:** Added a dedicated unmount-only `useEffect(() => () => { [skewRef, termRef, rrRef].forEach(ref => { if (ref.current && window.Plotly) window.Plotly.purge(ref.current); }); }, [])`.

### FIX 7 — Production `console.log`
**File:** `frontend/src/components/TrinityVolatility.jsx`
**Result:** No `console.log("[Trinity] Trade submitted", ...)` found in file — already clean. No change needed.

### FIX 8 — Filter buttons all called `setFilter("all")`
**File:** `frontend/src/App.js` (FlowAlertsPage filter bar)
**Problem:** "≥ $500K", "≥ $1M", "Sweep Only", and "HIGH Conf" buttons all hardcoded `setFilter("all")` — clicking them was a no-op.
**Fixes applied:**
- "≥ $500K" → `setFilter("500k")` + active class binding
- "≥ $1M" → `setFilter("1m")` + active class binding
- "Sweep Only" → `setFilter("sweep")` + active class binding
- "HIGH Conf" → `setFilter("high")` + active class binding
- "Reset" → remains `setFilter("all")` (correct)

Also extended the `filtered` computation to actually apply these cases:
```js
if (filter === "500k" && (a.premium || 0) < 500000) return false;
if (filter === "1m"   && (a.premium || 0) < 1000000) return false;
if (filter === "sweep" && (a.execution || a.exec_type || a.exec || "").toLowerCase() !== "sweep") return false;
if (filter === "high"  && (a.confidence || a.conf || "").toLowerCase() !== "high") return false;
```

### FIX 9 — Missing AbortController in OptionsChainTable
**File:** `frontend/src/components/OptionsChainTable.jsx`
**Problem:** The `fetchChain` useCallback + separate `useEffect` pattern did not cancel in-flight requests when the ticker or filters changed rapidly, causing stale responses to overwrite current state.
**Fix:** Replaced `useCallback` + `useEffect` pair with a single `useEffect` that creates an `AbortController`, passes `{ signal }` to axios, and cleans up with `controller.abort()` + `mounted = false` on dependency change or unmount.

---

## Verification

```bash
# FIX 1 — no double /api
grep -n "base}/api/\|API}/api/" frontend/src/App.js
# Expected: (empty)

# FIX 7 — no console.log Trade submitted
grep -n "console.log.*Trade submitted" frontend/src/components/TrinityVolatility.jsx
# Expected: (empty)
```

Both checks returned 0 results ✓
