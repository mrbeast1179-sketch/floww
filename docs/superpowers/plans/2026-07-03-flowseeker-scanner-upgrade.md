# FlowSeeker Pro Scanner Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Scanner tab actually market-wide (fix the silent 429→fallback collapse), make its data source visible, upgrade the Flow Score with regime awareness + delta estimation, and add custom universes with threshold alerts.

**Architecture:** Backend `/api/flowseeker/scan` gains a 60s cache + exponential 429 backoff + a free per-ticker gamma-regime map read from the existing heatmap cache. Frontend extracts all scanner math into a pure `scanLogic.js` module (tested), gates polling to the visible tab, surfaces a source/coverage badge, persists filters, and marks new/alert rows client-side. No new services, no new deps.

**Tech Stack:** FastAPI + httpx (backend), React 18 CRA/craco + plain fetch (frontend), pytest + Jest/craco test.

**Current state (verified 2026-07-03):** `GET /api/flowseeker/scan` returns 502 (`cvserver returned 429`) — no cache, no backoff, so the UI silently falls back to an 18-symbol client-side chain loop that itself polls every 20s even when the Scanner tab is hidden, feeding the rate limit. `/chain/{t}` returns no spot/delta, so Lean/OTM degrade to contract-type bias. Path A rows carry `underlying_price` at index 9 but the frontend ignores it.

---

## File Structure

- **Create:** `frontend/src/components/flowseeker/scanLogic.js` — all pure scanner math (DTE, flow-type, score, delta estimate, row builder, formatters). Mirrors the existing `flowHighlights.js` pattern.
- **Create:** `frontend/src/components/flowseeker/scanLogic.test.js` — Jest tests for the above.
- **Create:** `backend/tests/routes/test_flowseeker_scan.py` — pytest for cache/backoff/regimes.
- **Modify:** `backend/routes/flowseeker.py:394-442` — `/scan` cache, backoff, stale-serve, regimes map.
- **Modify:** `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` — import scanLogic, tab-gated polling, source meta, presets, persistence, universe editor, NEW/alert marking, row tags.
- **Modify:** `frontend/src/components/flowseeker/FlowseekerProBlademap.css` — badge, preset chips, new/alert row styles, γ tag.

---

### Task 1: Extract scanner math into `scanLogic.js` (TDD)

**Files:**
- Create: `frontend/src/components/flowseeker/scanLogic.js`
- Test: `frontend/src/components/flowseeker/scanLogic.test.js`
- Modify: `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx:63-112` (delete moved code, import instead)

- [ ] **Step 1: Write the failing tests**

```js
// frontend/src/components/flowseeker/scanLogic.test.js
import {
  bizDTE, scanTypeOf, scanScoreOf, estimateDelta, approxSpot, mkScanRow,
  fmtUSD, fmtK, fmtIV, scoreGradeOf,
} from "./scanLogic";

describe("estimateDelta", () => {
  it("is ~±0.5 at the money", () => {
    expect(Math.abs(estimateDelta(100, 100, "call"))).toBeCloseTo(0.5, 1);
    expect(Math.abs(estimateDelta(100, 100, "put"))).toBeCloseTo(0.5, 1);
  });
  it("calls: deep ITM → +1ish, deep OTM → 0ish; puts mirror negatively", () => {
    expect(estimateDelta(50, 100, "call")).toBeGreaterThan(0.9);
    expect(estimateDelta(150, 100, "call")).toBeLessThan(0.1);
    expect(estimateDelta(150, 100, "put")).toBeLessThan(-0.9);
    expect(estimateDelta(50, 100, "put")).toBeGreaterThan(-0.1);
  });
  it("returns null without a spot", () => {
    expect(estimateDelta(100, null, "call")).toBeNull();
  });
});

describe("approxSpot", () => {
  it("is the median strike", () => {
    expect(approxSpot([90, 100, 110])).toBe(100);
    expect(approxSpot([])).toBeNull();
    expect(approxSpot(null)).toBeNull();
  });
});

describe("scanTypeOf thresholds", () => {
  it("classifies by volume magnitude then vol/OI", () => {
    expect(scanTypeOf({ vol: 30000, volOI: 1 })).toBe("sweep");
    expect(scanTypeOf({ vol: 9000, volOI: 1 })).toBe("block");
    expect(scanTypeOf({ vol: 500, volOI: 2.5 })).toBe("unusual");
    expect(scanTypeOf({ vol: 500, volOI: 1.2 })).toBe("split");
    expect(scanTypeOf({ vol: 500, volOI: 0.2 })).toBe("regular");
  });
});

describe("scanScoreOf regime nudge", () => {
  const base = { volOI: 2, vol: 5000, notional: 5e6, dte: 2, delta: 0.3 };
  it("negative gamma boosts short-dated flow", () => {
    const plain = scanScoreOf({ ...base });
    const nudged = scanScoreOf({ ...base }, "negative");
    expect(nudged).toBeGreaterThan(plain);
    expect(nudged).toBeLessThanOrEqual(100);
  });
  it("positive gamma boosts fresh positioning (vol/OI ≥ 2)", () => {
    expect(scanScoreOf({ ...base }, "positive")).toBeGreaterThan(scanScoreOf({ ...base }));
  });
});

describe("mkScanRow", () => {
  it("computes notional, volOI, dte, score and estimates delta from spot", () => {
    const r = mkScanRow("NVDA", "call", 120, "2099-01-08", 10000, 4000, 0.5, null, 118, "negative");
    expect(r.notional).toBe(10000 * 100 * 120);
    expect(r.volOI).toBeCloseTo(2.5);
    expect(r.deltaEst).toBe(true);
    expect(r.delta).not.toBeNull();
    expect(r.regime).toBe("negative");
    expect(r.score).toBeGreaterThan(0);
    expect(r._parts).toBeDefined();
  });
  it("keeps a real delta when provided", () => {
    const r = mkScanRow("SPY", "put", 740, "2099-01-08", 2000, 1000, 0.2, -0.35, 744, null);
    expect(r.delta).toBe(-0.35);
    expect(r.deltaEst).toBe(false);
  });
});

describe("formatters", () => {
  it("fmtUSD / fmtK / fmtIV / scoreGradeOf", () => {
    expect(fmtUSD(2.5e9)).toBe("$2.50B");
    expect(fmtK(1500)).toBe("2k");
    expect(fmtIV(0.42)).toBe("42.0%");
    expect(scoreGradeOf(85)).toBe("crit");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/GitHub/floww/frontend && CI=true npx craco test --watchAll=false --testPathPattern="scanLogic" 2>&1 | tail -15`
Expected: FAIL — `Cannot find module './scanLogic'`

- [ ] **Step 3: Create `scanLogic.js`**

Move these VERBATIM from `FlowseekerProBlademap.jsx:69-112`: `fmtUSD`, `fmtK`, `fmtIV`, `bizDTE`, `scanTypeOf`, `scoreGradeOf`. Replace `scanScoreOf` and `mkScanRow` with the versions below; add `estimateDelta` and `approxSpot`:

```js
// frontend/src/components/flowseeker/scanLogic.js
// Pure scanner math for FlowSeeker Pro — no React, no fetch. Tested in scanLogic.test.js.

export const fmtUSD = (v) => { const n = Math.abs(Number(v) || 0); if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`; if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`; return `$${Math.round(n)}`; };
export const fmtK = (v) => { const n = Number(v) || 0; if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`; if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`; return String(Math.round(n)); };
export const fmtIV = (v) => (v == null ? "—" : `${(Number(v) < 1 ? Number(v) * 100 : Number(v)).toFixed(1)}%`);

// Trading-day DTE — calendar days minus weekends.
export function bizDTE(expStr) {
  if (!expStr) return null;
  const end = new Date(`${expStr}T16:00:00Z`), now = Date.now();
  if (end <= now) return 0;
  const full = Math.min(Math.floor((end - now) / 86400000), 800); let d = 0; const cur = new Date(now);
  for (let i = 0; i < full; i++) { cur.setUTCDate(cur.getUTCDate() + 1); const wd = cur.getUTCDay(); if (wd !== 0 && wd !== 6) d++; }
  return d;
}

// Flow-type by volume magnitude + vol/OI — the only signals a print-less feed supports.
export function scanTypeOf(r) {
  if (r.vol >= 25000) return "sweep";
  if (r.vol >= 8000) return "block";
  if (r.volOI >= 2) return "unusual";
  if (r.volOI >= 1) return "split";
  return "regular";
}

export const scoreGradeOf = (s) => (s >= 80 ? "crit" : s >= 65 ? "high" : s >= 50 ? "elev" : "norm");

// |delta| estimate from moneyness when the feed omits delta. Logistic squash of
// signed distance-to-spot in ~8%-of-spot units — labeled as an ESTIMATE in the UI.
export function estimateDelta(strike, spot, type) {
  if (!spot || !strike) return null;
  const isCall = String(type || "").toLowerCase().startsWith("c");
  const x = (spot - strike) / (spot * 0.08);
  const d = 1 / (1 + Math.exp(-1.7 * (isCall ? x : -x)));
  const abs = Math.max(0.02, Math.min(0.98, d));
  return isCall ? abs : -abs;
}

// Median strike ≈ spot (chains are built around the money). Fallback-path only.
export function approxSpot(strikes) {
  if (!strikes || !strikes.length) return null;
  const s = [...strikes].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

// Flow Score 0-100 — positioning freshness, size, notional, urgency, OTM lean,
// plus a small gamma-regime nudge when the ticker's regime is known:
// negative gamma amplifies short-dated aggressive flow (dealers chase moves);
// positive gamma pins — fresh positioning (vol/OI ≥ 2) matters more.
export function scanScoreOf(r, regime = null) {
  const dl = Math.abs(r.delta || 0);
  const pos = Math.min(r.volOI / 3, 1);
  const size = Math.min(Math.log(Math.max(r.vol, 1)) / Math.log(50000), 1);
  const notl = Math.min(Math.log(Math.max(r.notional, 1)) / Math.log(50e6), 1);
  const urg = r.dte == null ? 0.3 : (r.dte <= 2 ? 1 : r.dte <= 7 ? 0.7 : r.dte <= 30 ? 0.4 : 0.15);
  const otm = r.delta == null ? 0.3 : Math.max(0, Math.min((0.5 - dl) / 0.4, 1));
  let s = (pos * 0.34 + size * 0.24 + notl * 0.18 + urg * 0.14 + otm * 0.10) * 100;
  let nudge = 0;
  if (regime === "negative" && r.dte != null && r.dte <= 7) nudge = 5;
  else if (regime === "positive" && r.volOI >= 2) nudge = 3;
  s += nudge;
  r._parts = { pos: +(pos * 34).toFixed(1), size: +(size * 24).toFixed(1), notl: +(notl * 18).toFixed(1), urg: +(urg * 14).toFixed(1), otm: +(otm * 10).toFixed(1), nudge };
  return Math.max(0, Math.min(100, Math.round(s)));
}

// Build one scanner row. spot enables delta estimation when the feed omits
// delta; regime (from the backend heatmap cache) feeds the score nudge.
export function mkScanRow(under, type, strike, exp, vol, oi, iv, delta, spot = null, regime = null) {
  const stk = Number(strike) || 0;
  const volOI = oi > 0 ? vol / oi : (vol > 0 ? 99 : 0);
  const given = delta == null ? null : Number(delta);
  const est = given == null ? estimateDelta(stk, spot, type) : null;
  const r = {
    under, type: String(type || "").toLowerCase().startsWith("c") ? "call" : "put",
    strike: stk, exp, vol, oi, iv,
    delta: given != null ? given : est,
    deltaEst: given == null && est != null,
    spot, regime,
    volOI, notional: vol * 100 * stk, dte: bizDTE(exp),
  };
  r.score = scanScoreOf(r, regime); r.ftype = scanTypeOf(r);
  return r;
}
```

- [ ] **Step 4: Update `FlowseekerProBlademap.jsx` to import from scanLogic**

Delete lines 69-112 (the moved `fmtUSD/fmtK/fmtIV/bizDTE/scanTypeOf/scanScoreOf/scoreGradeOf/mkScanRow` definitions — keep `SCAN_UNIVERSE` and the comment block at 63-68). Add to the imports region:

```js
import { bizDTE, scanTypeOf, scanScoreOf, estimateDelta, approxSpot, mkScanRow, fmtUSD, fmtK, fmtIV, scoreGradeOf } from "./scanLogic";
```

(`bizDTE` is also used by the flow feed section — verify with grep that all former call sites still resolve.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Documents/GitHub/floww/frontend && CI=true npx craco test --watchAll=false --testPathPattern="scanLogic" 2>&1 | tail -15`
Expected: PASS (all suites)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/flowseeker/scanLogic.js frontend/src/components/flowseeker/scanLogic.test.js frontend/src/components/flowseeker/FlowseekerProBlademap.jsx
git commit -m "refactor(flowseeker): extract tested scanLogic module + delta estimate + regime-aware score"
```

---

### Task 2: Backend `/scan` — cache, 429 backoff, stale-serve, regimes map (TDD)

**Files:**
- Modify: `backend/routes/flowseeker.py:394-442`
- Test: `backend/tests/routes/test_flowseeker_scan.py`

- [ ] **Step 1: Write the failing tests**

Mirror the import/client pattern of `backend/tests/routes/test_heatseeker_degraded.py` (check its conftest usage first; adapt the app/client fixture to match). Test the route module directly with a fake httpx client:

```python
# backend/tests/routes/test_flowseeker_scan.py
"""/api/flowseeker/scan: cache, 429 backoff, stale-serve, regimes map."""
import asyncio
import json
import time

import pytest

import routes.flowseeker as fs


class FakeResp:
    def __init__(self, status_code=200, rows=None):
        self.status_code = status_code
        self._rows = rows or [["SPY", "SPY260706C00745000", "call", 745, "2026-07-06", 50000, 10000, 0.2, 0.5, 744.5]]
    def json(self):
        return {"result": {"content": [{"type": "text", "text": json.dumps({"rows": self._rows})}]}}


class FakeClient:
    calls = 0
    status = 200
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, *a, **k):
        FakeClient.calls += 1
        return FakeResp(FakeClient.status)


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(fs, "CVFORGE_API_KEY", "test-key")
    monkeypatch.setattr(fs.httpx, "AsyncClient", FakeClient)
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})
    FakeClient.calls = 0
    FakeClient.status = 200
    yield


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_success_returns_rows_with_source_and_asof():
    out = run(fs.market_scan(min_volume=1000, limit=300))
    assert out["count"] == 1 and out["source"] == "cvserver-screen"
    assert out["stale"] is False and out["asof"]
    assert "regimes" in out


def test_second_call_within_ttl_hits_cache():
    run(fs.market_scan(min_volume=1000, limit=300))
    run(fs.market_scan(min_volume=1000, limit=300))
    assert FakeClient.calls == 1


def test_429_with_warm_cache_serves_stale_and_backs_off():
    run(fs.market_scan(min_volume=1000, limit=300))
    fs._scan_cache["1000:300"]["ts"] = time.time() - 999   # expire the cache entry
    FakeClient.status = 429
    out = run(fs.market_scan(min_volume=1000, limit=300))
    assert out["stale"] is True and out["count"] == 1
    assert fs._scan_backoff["until"] > time.time()
    calls_after_429 = FakeClient.calls
    run(fs.market_scan(min_volume=1000, limit=300))        # inside backoff window
    assert FakeClient.calls == calls_after_429              # upstream NOT re-hit


def test_429_with_no_cache_returns_503():
    FakeClient.status = 429
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        run(fs.market_scan(min_volume=1000, limit=300))
    assert e.value.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Documents/GitHub/floww/backend && python3 -m pytest tests/routes/test_flowseeker_scan.py -x -q 2>&1 | tail -8`
Expected: FAIL — `AttributeError: module 'routes.flowseeker' has no attribute '_scan_cache'`

- [ ] **Step 3: Implement in `routes/flowseeker.py`**

Insert module state above the `/scan` route and rewrite its body (keep the existing `columns` list and cvserver payload exactly):

```python
# ── /scan cache + 429 backoff ──
_scan_cache: dict[str, dict] = {}          # "min_volume:limit" → {ts, data}
_SCAN_TTL = 60                              # seconds
_scan_backoff = {"until": 0.0, "delay": 30.0}   # exponential, capped at 600s


def _cached_regimes() -> dict[str, str]:
    """Per-ticker gamma regime from the heatmap cache — cache-only, no fetches."""
    try:
        import server  # deferred: circular import
        out: dict[str, str] = {}
        now = time.time()
        for key, entry in list(getattr(server, "_BUILD_HEATMAP_CACHE", {}).items()):
            if now - entry.get("ts", 0) > 900:
                continue
            reg = ((entry.get("data") or {}).get("nodes") or {}).get("regime")
            if reg:
                out[key.split(":", 1)[0]] = reg
        return out
    except Exception:
        return {}


def _scan_payload(rows: list, stale: bool, asof: str, columns: list) -> dict:
    return {
        "columns": columns, "rows": rows, "count": len(rows),
        "source": "cvserver-screen", "stale": stale, "asof": asof,
        "regimes": _cached_regimes(),
    }
```

New `/scan` body (same signature; replace lines after the `columns = [...]` block):

```python
    if not CVFORGE_API_KEY:
        raise HTTPException(503, "cvserver API key not configured")

    cache_key = f"{min_volume}:{limit}"
    now = time.time()
    cached = _scan_cache.get(cache_key)
    if cached and now - cached["ts"] < _SCAN_TTL:
        return _scan_payload(cached["data"], False, cached["asof"], columns)

    def _stale_or(status: int, detail: str):
        best = cached or (max(_scan_cache.values(), key=lambda e: e["ts"]) if _scan_cache else None)
        if best:
            return _scan_payload(best["data"], True, best["asof"], columns)
        raise HTTPException(status, detail)

    if now < _scan_backoff["until"]:
        return _stale_or(503, f"cvserver rate-limited; retrying after {int(_scan_backoff['until'] - now)}s")

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CVFORGE_API_KEY}"}
    payload = { ... }   # UNCHANGED from current lines 411-424
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code == 429:
                _scan_backoff["until"] = now + _scan_backoff["delay"]
                _scan_backoff["delay"] = min(_scan_backoff["delay"] * 2, 600.0)
                logger.warning("cvforge scan 429 — backing off %ss", int(_scan_backoff["delay"]))
                return _stale_or(503, "cvserver rate-limited (429), no cached scan yet")
            if resp.status_code != 200:
                return _stale_or(502, f"cvserver returned {resp.status_code}")
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            d = json.loads(content[0]["text"]) if content and content[0].get("type") == "text" else result.get("result", {})
            rows = d.get("rows", [])
            _scan_backoff["delay"] = 30.0
            asof = datetime.now().isoformat()
            _scan_cache[cache_key] = {"ts": now, "data": rows, "asof": asof}
            return _scan_payload(rows, False, asof, columns)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"cvforge scan failed: {e}")
        return _stale_or(502, f"scan failed: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Documents/GitHub/floww/backend && python3 -m pytest tests/routes/test_flowseeker_scan.py -x -q 2>&1 | tail -6` and `python3 -m py_compile routes/flowseeker.py`
Expected: 4 passed; compile clean

- [ ] **Step 5: Commit**

```bash
git add backend/routes/flowseeker.py backend/tests/routes/test_flowseeker_scan.py
git commit -m "feat(flowseeker): /scan 60s cache + 429 exponential backoff + stale-serve + cached regimes map"
```

---

### Task 3: Frontend data plumbing — tab gating, source meta, spot/regime wiring

**Files:**
- Modify: `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (scan effect at ~218-266, state at ~126-133)

- [ ] **Step 1: Add state + prefs helpers** (below the existing scan state, ~line 133)

```js
  const PREFS_KEY = "fsb-scan-prefs-v1";
  const prefs = useMemo(() => { try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; } }, []);
  const [scanMeta, setScanMeta] = useState({ mode: null, stale: false, symbols: 0 });
  const [universe, setUniverse] = useState(prefs.universe || SCAN_UNIVERSE);
  const [universeOnly, setUniverseOnly] = useState(!!prefs.universeOnly);
  const [alertScore, setAlertScore] = useState(prefs.alertScore ?? 85);
  const prevKeysRef = useRef(null);
```

Also seed the four existing filter states from prefs: `useState(prefs.scanTypeF || "all")`, `useState(prefs.scanMinVol || 0)`, `useState(prefs.scanMinScore || 0)`, `useState(prefs.scanSort || { key: "score", dir: "desc" })`, and add a save effect:

```js
  useEffect(() => {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify({ scanTypeF, scanMinVol, scanMinScore, scanSort, universe, universeOnly, alertScore })); } catch { /* private mode */ }
  }, [scanTypeF, scanMinVol, scanMinScore, scanSort, universe, universeOnly, alertScore]);
```

- [ ] **Step 2: NEW-row marker helper** (module level, above the component)

```js
// Mark rows unseen in the previous refresh (drives NEW flash + alerts).
function markNew(rows, prevKeysRef) {
  const keys = new Set(rows.map((r) => `${r.under}|${r.type}|${r.strike}|${r.exp}`));
  if (prevKeysRef.current) {
    for (const r of rows) r._new = !prevKeysRef.current.has(`${r.under}|${r.type}|${r.strike}|${r.exp}`);
  }
  prevKeysRef.current = keys;
  return rows;
}
```

- [ ] **Step 3: Rewrite the scan effect** — gate on tab, wire spot (`r[9]`) + regimes into Path A, custom universe + approxSpot into Path B:

```js
  useEffect(() => {
    if (!active || tab !== "scanner") return;      // ← poll only when the Scanner tab is visible
    let cancelled = false;
    const ctrl = new AbortController();
    const run = async () => {
      try {
        const d = await getJSON(`${API}/scan?limit=300`, ctrl.signal);
        if (!cancelled && d && Array.isArray(d.rows) && d.rows.length) {
          const regimes = d.regimes || {};
          const rows = d.rows.map((r) => mkScanRow(r[0], r[2], r[3], r[4], Number(r[5]) || 0,
            Number(r[6]) || 0, r[7], r[8], Number(r[9]) || null, regimes[r[0]] || null));
          setScan(markNew(rows, prevKeysRef));
          setScanMeta({ mode: "market", stale: !!d.stale, symbols: new Set(rows.map((x) => x.under)).size });
          setScanAt(new Date().toLocaleTimeString());
          return;
        }
      } catch { /* endpoint down — fall through to the chain loop */ }
      try {
        const results = await Promise.all(universe.map((t) =>
          getJSON(`${API}/chain/${t}?fields=oi,volume,iv,delta`, ctrl.signal)
            .then((d) => ({ t, d })).catch(() => null)));
        if (cancelled) return;
        const rows = [];
        for (const res of results) {
          if (!res || !res.d) continue;
          const params = res.d.params || [];
          const vi = (name) => { const i = params.indexOf(name); return i > 0 ? i - 1 : -1; };
          const iVol = vi("volume"), iOI = vi("openInterest"), iIV = vi("impliedVolatility"), iDelta = vi("delta");
          const allStrikes = [];
          for (const exp of (res.d.chain || [])) for (const s of (exp.strikes || [])) allStrikes.push(s[0]);
          const spotEst = approxSpot(allStrikes);
          for (const exp of (res.d.chain || [])) {
            for (const s of (exp.strikes || [])) {
              const strike = s[0];
              for (const [sideU, vals] of [["call", s[1] || []], ["put", s[2] || []]]) {
                const vol = Number(vals[iVol]) || 0;
                if (vol < 1000) continue;
                rows.push(mkScanRow(res.t, sideU, strike, exp.expiration, vol,
                  Number(vals[iOI]) || 0, Number(vals[iIV]) || 0,
                  iDelta >= 0 ? Number(vals[iDelta]) : null, spotEst, null));
              }
            }
          }
        }
        rows.sort((a, b) => b.vol - a.vol);
        const top = rows.slice(0, 300);
        setScan(markNew(top, prevKeysRef));
        setScanMeta({ mode: "fallback", stale: false, symbols: universe.length });
        setScanAt(new Date().toLocaleTimeString());
      } catch { /* keep last data on a transient hiccup */ }
    };
    run();
    const id = setInterval(run, 20000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, tab, universe]);
```

- [ ] **Step 4: Universe filter in `scanRows`** — add as the FIRST predicate inside the existing filter (line ~321):

```js
      if (universeOnly && !universe.includes(r.under)) return false;
```

and add `universe, universeOnly` to that memo's dependency array.

- [ ] **Step 5: Compile check** — CRA dev server output or `npx @babel/parser` parse. Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/flowseeker/FlowseekerProBlademap.jsx
git commit -m "feat(flowseeker): tab-gated scan polling, source meta, Path-A spot+regime wiring, custom universe fallback"
```

---

### Task 4: Scanner UX — source badge, alerts KPI, presets, universe editor, row tags + CSS

**Files:**
- Modify: `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (scanner view JSX ~652-718)
- Modify: `frontend/src/components/flowseeker/FlowseekerProBlademap.css`

- [ ] **Step 1: KPI bar** — replace the array at lines 656-663 with:

```js
              {[
                ["Source", scanMeta.mode === "market" ? `LIVE · mkt-wide ·${scanMeta.symbols}` : scanMeta.mode === "fallback" ? `FALLBACK ·${scanMeta.symbols} sym` : "—",
                  scanMeta.stale ? "y" : scanMeta.mode === "market" ? "g" : scanMeta.mode ? "y" : ""],
                ["Contracts", `${scanRows.length} / ${scan.length}${scanRows.length > 200 ? " ·top200" : ""}`, "b"],
                ["Notional Σ", fmtUSD(scanStats.notl), ""],
                ["Call/Put Vol", scanStats.tv > 0 ? `${scanStats.cpct}% / ${100 - scanStats.cpct}%` : "—", scanStats.cpct >= 50 ? "g" : "r"],
                ["Unusual (≥2×)", String(scanStats.unusual), "y"],
                ["⚡ Alerts", String(scanStats.alerts), scanStats.alerts ? "r" : ""],
                ["Updated", (scanMeta.stale ? "STALE · " : "") + (scanAt || "—"), scanMeta.stale ? "y" : ""],
              ].map(([l, v, c]) => (
```

and extend `scanStats` (line ~338) with `alerts`: count `r._new && r.score >= alertScore` inside the loop, return it, and add `alertScore` to the memo deps.

- [ ] **Step 2: Presets + universe editor row** — insert directly under the `fsb-scanctrl` div's existing children (after the Ticker… input, before `fsb-scannote`):

```js
              <span className="fsb-presets">
                {[["Top Score", { key: "score", dir: "desc" }], ["Big Money", { key: "notional", dir: "desc" }],
                  ["Unusual", { key: "volOI", dir: "desc" }], ["Short Fuse", { key: "dte", dir: "asc" }]].map(([l, s]) => (
                  <button key={l} className={`fsb-preset${scanSort.key === s.key && scanSort.dir === s.dir ? " on" : ""}`}
                    onClick={() => setScanSort(s)}>{l}</button>
                ))}
              </span>
              <label className="fsb-uonly"><input type="checkbox" checked={universeOnly} onChange={(e) => setUniverseOnly(e.target.checked)} /> My universe</label>
              <input className="fsb-univ" defaultValue={universe.join(",")} placeholder="Universe…" title="Comma-separated tickers — fallback scan + 'My universe' filter"
                onBlur={(e) => { const u = (e.target.value || "").toUpperCase().split(/[,\s]+/).filter(Boolean); if (u.length) setUniverse(u); }} />
              <input className="fsb-alertn" type="number" min="50" max="100" value={alertScore} title="Alert when a NEW contract scores ≥ this"
                onChange={(e) => setAlertScore(Math.max(50, Math.min(100, parseInt(e.target.value, 10) || 85)))} />
```

- [ ] **Step 3: Row rendering** (lines ~695-709) — add classes + tags:

```js
                        <tr key={`${r.under}-${r.strike}-${r.type}-${r.exp}-${i}`}
                            className={`${r.under === ticker ? "sel " : ""}${r._new ? "new " : ""}${r._new && r.score >= alertScore ? "alert" : ""}`.trim()}
                            onClick={() => { setTicker(r.under); setTab("flow"); }}>
                          <td><span className={`fsb-sc ${scoreGradeOf(r.score)}`} title={r._parts ? `vol/OI ${r._parts.pos} · size ${r._parts.size} · notional ${r._parts.notl} · urgency ${r._parts.urg} · OTM ${r._parts.otm}${r._parts.nudge ? ` · γ-nudge +${r._parts.nudge}` : ""}` : ""}>{r.score}</span></td>
                          <td className="l"><span className="tk">{r.under}</span>{r.regime ? <sup className={`fsb-gtag ${r.regime === "positive" ? "gp" : "gn"}`}>{r.regime === "positive" ? "γ+" : "γ−"}</sup> : null} <span className="fsb-sub">{(r.exp || "").slice(5)}</span></td>
```

and the Lean cell's OTM tag becomes estimate-aware:

```js
                          <td className="l"><span className={`fsb-lean ${isCall ? "bull" : "bear"}`}>{isCall ? "▲ BULL" : "▼ BEAR"}</span>{otm ? <span className="fsb-sub"> {r.deltaEst ? "~" : ""}{otm}</span> : null}</td>
```

(`otm` at line ~693 already handles `delta == null` → `""`; with estimation it now usually resolves.)

- [ ] **Step 4: CSS** — append to `FlowseekerProBlademap.css`:

```css
/* ── Scanner upgrade: presets, universe, alerts, tags ── */
.fsb-presets { display: inline-flex; gap: 4px; }
.fsb-preset { background: #131722; border: 1px solid #2a2e39; color: #9aa0ae; font-size: 10px; padding: 3px 8px; border-radius: 4px; cursor: pointer; }
.fsb-preset.on, .fsb-preset:hover { color: #e6e8ee; border-color: #29c5e0; }
.fsb-uonly { font-size: 10px; color: #9aa0ae; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.fsb-univ { min-width: 180px; }
.fsb-alertn { width: 56px; }
.fsb-gtag { font-size: 8px; margin-left: 2px; }
.fsb-gtag.gp { color: #19d27c; }
.fsb-gtag.gn { color: #ff4d5e; }
.fsb-stab tr.new td { animation: fsbNewRow 1.6s ease-out 1; }
.fsb-stab tr.alert td:first-child { box-shadow: inset 3px 0 0 #f5b042; }
@keyframes fsbNewRow { from { background: rgba(41, 197, 224, 0.16); } to { background: transparent; } }
```

- [ ] **Step 5: Compile + eyeball** — CRA hot-reload; check the Scanner tab renders, badge shows FALLBACK or LIVE, presets click-sort.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/flowseeker/FlowseekerProBlademap.jsx frontend/src/components/flowseeker/FlowseekerProBlademap.css
git commit -m "feat(flowseeker): scanner source badge, alerts, sort presets, universe editor, regime/estimate tags"
```

---

### Task 5: Restart backend, verify live, full test sweep, push

- [ ] **Step 1: Restart backend only** (CRA hot-reloads): kill the PID on :8000, relaunch `nohup uvicorn server:app --port 8000` from `backend/.venv` (mirror `scripts/launch_decoder.sh:99`).
- [ ] **Step 2: `curl -s localhost:8000/api/flowseeker/scan?limit=5`** — expect either `{"source":"cvserver-screen",...}` or, if cvserver is still 429ing with no cache, a clean 503 with the retry message (NOT a 502 loop). Wait 60s and retry once — backoff should recover when cvserver does.
- [ ] **Step 3: Browser-verify the Scanner tab** (localhost:3000 → Flowseeker Pro → Scanner): source badge, presets, NEW flash on refresh, alert KPI, γ tags (SPY/QQQ should have cached regimes), ~OTM estimates on fallback rows.
- [ ] **Step 4: Run both test suites** — backend `pytest tests/routes/test_flowseeker_scan.py`, frontend `craco test --testPathPattern="scanLogic|flowHighlights"` (guard against regressions in the sibling module).
- [ ] **Step 5: Push** — `git push origin main`.

---

## Self-Review (done at write time)

- **Spec coverage:** Track 1 → Tasks 2+3 (cache/backoff/stale, tab gating, honest fallback). Track 2 → Task 4 (badge, truncation note, persistence in Task 3 Step 1, presets). Track 3 → Task 1 (regime nudge, estimateDelta, ~OTM tag, score tooltip). Track 4 → Tasks 3+4 (universe editor + threshold alerts). ✓
- **Placeholder scan:** the one intentional ellipsis (`payload = { ... }` in Task 2) is annotated "UNCHANGED from current lines 411-424" — the code already exists in the file. ✓
- **Type consistency:** `mkScanRow(under, type, strike, exp, vol, oi, iv, delta, spot, regime)` matches all three call sites (test, Path A, Path B); `_parts`/`deltaEst`/`regime`/`_new` consumed in Task 4 exactly as produced in Tasks 1+3; `_scan_cache` entry shape `{ts, data, asof}` consistent between route and tests. ✓
