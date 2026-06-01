# floww / Confluence Decoder — Remaining Fixes (DeepSeek Pro execution prompt)

> **For the executing agent (DeepSeek Pro):** This is your complete brief. You have ZERO prior context. Work ONE task at a time, top to bottom. Each task is self-contained with exact files, line numbers, code, a failing test, a verification command, and a commit. Do not skip ahead. Estimated total: **10–12 hours.**

---

## 0. ROLE + ANTI-HALLUCINATION PROTOCOL (READ TWICE — NON-NEGOTIABLE)

You are a senior engineer on **floww** (a.k.a. "Confluence Decoder"), a FastAPI + React options-intelligence app. You are known to hallucinate and over-claim. The following rules exist specifically to catch that. Violating any rule = the task is failed and must be redone.

1. **Evidence before assertion. ALWAYS.** Never say a thing works, exists, passes, or is fixed without pasting the literal command output that proves it. No output = it did not happen.
2. **Prove a symbol exists before you reference it.** Before you call/import/edit any function, class, route, or field, run `grep -n "<name>" <file>` and paste the result. If grep finds nothing, STOP — your assumption is wrong; re-investigate. Do NOT invent file paths, function names, or line numbers.
3. **Do NOT fabricate SHAs, test counts, or curl output.** If you didn't run it, you don't have it. Copy real terminal output verbatim.
4. **TDD is mandatory.** For every behavior change: write a test that FAILS first (run it, paste the FAIL), then implement, then run it again (paste the PASS). A test that passes before your change tests nothing — fix the test.
5. **Never** add `@pytest.mark.skip`, `@pytest.mark.xfail`, `it.skip`, or delete/loosen a passing assertion to make things green. If your change breaks a previously-passing test, your change is wrong — revert and find the real cause.
6. **One task = one commit.** Commit message uses a HEREDOC with the verification commands + their real output pasted inline (see the commit template at the end). Push and verify on origin after each commit.
7. **If a task's premise turns out false** (the bug is already fixed, the file differs, grep finds nothing), STOP and write "PREMISE MISMATCH: <what you found>" — do not improvise a different change to look productive.
8. **Ask-don't-assume on frozen files.** The files listed in §1 "Frozen files" must NOT be edited without an explicit note to the human (Nav). One task (T6) touches `package.json` — it is gated on Nav's approval; do not proceed past the gate without it.

---

## 1. PROJECT CONTEXT (memorize this)

**Canonical clone (the ONLY one — others are stale and cause incidents):**
```
/Users/nav/Documents/GitHub/floww
```
If `pwd` does not end in `Documents/GitHub/floww`, `cd` there. Do NOT touch `/Users/nav/floww` or `/Users/nav/GitHub/floww`.

**Stack:** FastAPI backend (`backend/server.py`, port 8000) · React SPA (`frontend/`, port 3000 — the real UI) · MongoDB (Motor) · DuckDB (in-memory) · sklearn ML. The decoder "tabs" are React pages in `frontend/src/App.js` switched by a `page` state string: `heatseeker`, `skylit`, `trinity`, `portfolio`, `journal`, `swarmspx`.

**Run the backend (always from `backend/`, never a bare nohup without cd):**
```bash
cd /Users/nav/Documents/GitHub/floww/backend
pkill -9 -f "uvicorn server:app" 2>/dev/null
nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn.log 2>&1 &
# WAIT for readiness — startup is SLOW right now (see Databento note). Poll:
curl -s --retry-connrefused --retry 200 --retry-delay 1 --max-time 240 \
  http://localhost:8000/api/tickers -o /dev/null -w "ready: HTTP %{http_code}\n"
grep -c "Application startup complete" /tmp/uvicorn.log   # must be >= 1
```

**Run tests (in-process, fast, no live server needed):**
```bash
cd /Users/nav/Documents/GitHub/floww/backend
.venv/bin/python3 -m pytest <path> -v          # always use the venv python, never system python
```

**Lint (ONLY these rules are enforced — I001 import-order is NOT enforced, ignore it):**
```bash
cd /Users/nav/Documents/GitHub/floww/backend && .venv/bin/ruff check --select F,E722 .
```

**Frozen files — do NOT edit without an explicit note to Nav:**
`backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, `frontend/src/App.js` (surgical edits only, with approval).

**Git rules:** Never `git push --force`, `--no-verify`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`. Work on the branch `fix/skylit-tab-restore` (already exists, already pushed — `git switch fix/skylit-tab-restore`). After each commit: `git push origin fix/skylit-tab-restore` then `git fetch origin && git log origin/fix/skylit-tab-restore --oneline -1` and confirm your subject appears.

**THE GAMMA GOTCHA (this masks bugs — internalize it):** Contracts returned by `fetch_spot_and_chains_merged` (`backend/server.py:748-751`) contain only `expiry, T, type, strike, oi, iv, volume` — **NO `gamma`**. Gamma is computed on the fly everywhere. BUT the test fixtures `_fake_chain` (`backend/tests/test_api.py:~61`) and `_chain_fixture` (`backend/tests/test_heatseeker_routes.py:~75`) hard-code `"gamma": 0.04`. So a GEX bug can be green in tests and broken in prod. **When testing any GEX/greek path, `.pop("gamma", None)` from the fixture contracts to reproduce production.**

**DATABENTO IS LOCKED:** Every chain fetch tries Databento OI for `PAID_TICKERS={"SPY"}` (`server.py:298`) and gets `403 auth_account_locked`, falling back to yfinance (data is fine, just slow — startup ~2.5 min, first cold panel ~30s, then cached). T2 addresses this.

---

## 2. ALREADY DONE — on branch `fix/skylit-tab-restore` / PR #1 (do NOT redo; build on it)

Verify these are present with the grep in each line before starting; if any is missing, the branch is not checked out.
- `fix(skylit)` — Vanna/CharmChart call bare `/api/{vanna-exposure,charm-integral}` (no `analytics/` prefix). `grep -n "vanna-exposure" frontend/src/components/VannaChart.jsx`
- `fix(analytics)` — vanna passes `float(spot)` (not `np.array`) into `bs_vanna_vec`; T from `c["T"]`; `/contract` computes gamma. `grep -n "float(spot)," backend/routes/analytics.py`
- `fix(heatseeker)` — `_ensure_gamma` enriches contracts at `_fetch_chain`; degraded-path keys fixed. `grep -n "_ensure_gamma" backend/routes/heatseeker.py`
- `fix(api)` — read-only dashboard GETs exempt from the rate limiter. `grep -n "Read-only dashboard GETs" backend/server.py`

---

## TASK 1 — Verify the rate-limit (429) fix end-to-end

**Why:** The fix (exempt read GETs) is committed but was NOT verified against a running server. The Skylit dashboard was showing `HTTP 429` on nearly every panel.

**Files:** `backend/server.py:~96-108` (already edited — verify only).

- [ ] **Step 1 — confirm the exemption code is present**
  Run: `grep -n "Read-only dashboard GETs" /Users/nav/Documents/GitHub/floww/backend/server.py`
  Expected: one match around line 98. If none: `git switch fix/skylit-tab-restore` first.

- [ ] **Step 2 — restart the backend** (use the run block in §1; wait for `ready: HTTP 200`).

- [ ] **Step 3 — hammer an exempted endpoint 40× rapidly; expect ZERO 429**
  ```bash
  for i in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code} " "http://localhost:8000/api/heatseeker/beach-ball?ticker=SPY"; done; echo
  ```
  Expected: all `200` (no `429`). Paste the output. If any `429`: the path prefix is wrong — grep the actual request path in `/tmp/uvicorn.log` and widen the exemption tuple.

- [ ] **Step 4 — confirm a MUTATING route is still limited** (security check)
  ```bash
  for i in $(seq 1 70); do curl -s -o /dev/null -w "%{http_code} " -X POST "http://localhost:8000/api/heatseeker/snapshot/SPY"; done; echo
  ```
  Expected: a `429` appears before the 70th request (POST is NOT exempt). Paste output.

- [ ] **Step 5 — commit** (only if you changed anything; otherwise note "already committed as 71e2c98, verified").

**Estimate: 30 min** (mostly the slow restart).

---

## TASK 2 — Make startup + panels fast despite the locked Databento key

**Why:** Backend startup takes ~2.5 min and the first cold panel ~30s because every SPY chain fetch hammers a locked Databento account (`403 auth_account_locked`). yfinance fallback already supplies the data.

**Decision for Nav (ask before coding):** real fix = unlock/rotate the Databento key. Until then, disable the paid-OI path. Two safe options — implement **(a)**, document **(b)**:

**Files:**
- Modify: `backend/server.py:88` (add an env-gated kill switch) and `backend/server.py:~2108` (`_prefetch_paid_oi`).
- Test: `backend/tests/test_databento_disable.py` (create).

- [ ] **Step 1 — find the prefetch + gate**
  Run: `grep -n "PAID_TICKERS\|_prefetch_paid_oi\|DEFAULT_PAID_TICKERS" backend/server.py`
  Paste output. Confirm `DEFAULT_PAID_TICKERS = {"SPY"}` near line 298.

- [ ] **Step 2 — write the failing test** `backend/tests/test_databento_disable.py`:
  ```python
  import importlib, os
  def test_paid_tickers_empty_when_disabled(monkeypatch):
      monkeypatch.setenv("DISABLE_DATABENTO", "1")
      import server
      importlib.reload(server)
      assert server.PAID_TICKERS == set(), "DISABLE_DATABENTO=1 must empty PAID_TICKERS"
  ```
  Run: `.venv/bin/python3 -m pytest tests/test_databento_disable.py -v` → expect FAIL.
  (Note: reloading `server` is heavy; if reload is impractical in this codebase, instead assert the gate logic in a small helper you extract. Adapt, but keep a real failing-then-passing test.)

- [ ] **Step 3 — implement the gate.** At `server.py:299` change:
  ```python
  PAID_TICKERS: set = set(DEFAULT_PAID_TICKERS)
  ```
  to:
  ```python
  PAID_TICKERS: set = (
      set() if os.environ.get("DISABLE_DATABENTO", "").lower() in ("1", "true", "yes")
      else set(DEFAULT_PAID_TICKERS)
  )
  ```
  Confirm `import os` is already at the top: `grep -n "^import os" backend/server.py`.

- [ ] **Step 4 — run the test** → expect PASS. Paste output.

- [ ] **Step 5 — verify live speed.** Restart with the flag and time a cold panel:
  ```bash
  cd backend && pkill -9 -f "uvicorn server:app"; DISABLE_DATABENTO=1 nohup .venv/bin/python3 -m uvicorn server:app --port 8000 >/tmp/uvicorn.log 2>&1 &
  curl -s --retry-connrefused --retry 60 --retry-delay 1 --max-time 90 http://localhost:8000/api/tickers -o /dev/null -w "ready %{http_code}\n"
  grep -c "auth_account_locked" /tmp/uvicorn.log   # expect 0
  curl -s -o /dev/null -w "flip-zones cold: %{time_total}s\n" "http://localhost:8000/api/heatseeker/flip-zones?ticker=SPY"
  ```
  Expected: startup in seconds, `auth_account_locked` count `0`, flip-zones well under 5s. Paste output.

- [ ] **Step 6 — commit.** Document in the body that the REAL fix is to unlock/rotate the Databento key; `DISABLE_DATABENTO=1` is the interim demo switch. Add it to the launch docs (`grep -n "uvicorn server:app" backend/CLAUDE.md docs/*.md 2>/dev/null`).

**Estimate: 1 hour.**

---

## TASK 3 — Snapshots: velocity-mode / top-movers / history are empty

**Why:** `velocity-mode` returns `n_snapshots:0` ("calm"), and `top-movers`/`history` are blank. Three real bugs.

**Files:**
- Modify: `backend/server.py:638` (write side field name), or `backend/routes/heatseeker.py:226` (read side) — fix ONE so they match.
- Modify: `backend/routes/heatseeker_snapshots_api.py:~170-191` (snapshot POST writes to a throwaway `:memory:` DB).
- Test: `backend/tests/test_heatseeker_routes.py` (add) and/or `backend/tests/services/test_heatseeker_snapshots.py`.

- [ ] **Step 1 — confirm the field-name mismatch**
  ```bash
  grep -n "king_strike\|king_node_strike" backend/server.py backend/routes/heatseeker.py
  ```
  Expected: write side `server.py:~638` uses `"king_strike"`; read side `routes/heatseeker.py:~226` reads `doc.get("king_node_strike")`. Paste output. If they already match, PREMISE MISMATCH — stop and report.

- [ ] **Step 2 — write the failing test** (velocity-mode computes from snapshots that use the writer's field name). In `backend/tests/test_heatseeker_routes.py`:
  ```python
  def test_velocity_mode_reads_writer_field(client):
      """save_snapshot writes 'king_strike'; the velocity-mode read path must
      read the SAME field, or n_snapshots is always 0."""
      import inspect, server, routes.heatseeker as hr
      write_src = inspect.getsource(server.save_snapshot)
      read_src = inspect.getsource(hr._fetch_king_node_history)
      import re
      written = set(re.findall(r'"(king[_a-z]*)"', write_src))
      read = set(re.findall(r'"(king[_a-z]*)"', read_src))
      assert written & read, f"writer fields {written} and reader fields {read} do not overlap"
  ```
  Run it → expect FAIL. Paste. (Confirm the two function names exist first: `grep -n "def save_snapshot\|def _fetch_king_node_history" backend/server.py backend/routes/heatseeker.py`.)

- [ ] **Step 3 — fix the field name.** Prefer fixing the READER to match the writer (less blast radius). At `routes/heatseeker.py:226` change `doc.get("king_node_strike")` → `doc.get("king_strike")` (use the exact key the writer at `server.py:638` uses — verify it). Also update any sibling reads in that function (`grep -n "king_node_strike" backend/routes/heatseeker.py`).

- [ ] **Step 4 — run the test** → PASS. Paste.

- [ ] **Step 5 — fix the throwaway `:memory:` snapshot writer.** Read `backend/routes/heatseeker_snapshots_api.py:170-200` and `grep -n "_get_duckdb_conn\|:memory:\|snapshot_chain" backend/routes/heatseeker_snapshots_api.py`. The POST handler calls `snapshot_chain(..., db_path=":memory:")`, which writes to a fresh DB that is discarded. Change it to write into the SHARED connection returned by `_get_duckdb_conn()` (which is `duckdb_engine.conn`). Concretely: have the handler (a) fetch the chain via `fetch_spot_and_chains_merged`, (b) call `create_snapshot_table(conn)` and `bulk_insert(conn, batch)` from `services.heatseeker_snapshots` on the shared `conn`. Verify those helper names exist: `grep -n "def create_snapshot_table\|def bulk_insert\|def get_top_movers_from_db" backend/services/heatseeker_snapshots.py`.

- [ ] **Step 6 — write a test** that POSTs a snapshot then reads top-movers back from the SAME shared conn and gets ≥1 row. (Patch `fetch_spot_and_chains_merged` with the `_chain_fixture` so it is deterministic and offline.) Red → implement → green. Paste both.

- [ ] **Step 7 — seed one snapshot for the demo + live-verify**
  ```bash
  curl -s -X POST "http://localhost:8000/api/heatseeker/snapshot/SPY" | head -c 120; echo
  curl -s "http://localhost:8000/api/heatseeker/top-movers/SPY" | python3 -c "import sys,json;print('rows',len(json.load(sys.stdin) or []))"
  ```
  Expected: top-movers rows ≥ 1. Paste.

- [ ] **Step 8 — commit.**

**Estimate: 2.5 hours.**

---

## TASK 4 — swarmspx tab shows a blank / "refused to connect" iframe

**Why:** `frontend/src/App.js:~800` hardcodes `<iframe src="http://localhost:8099/">`, but nothing in this repo serves port 8099 (`grep -rn "8099" backend/ | head` → expect zero Python). `App.js` is a frozen/surgical file — get Nav's OK for the one-line edit.

**Files:** Modify (surgical, with approval): `frontend/src/App.js:~797-806`. Create: `frontend/src/components/SwarmFrame.jsx`.

- [ ] **Step 1 — confirm nothing serves 8099**
  `grep -rn "8099" backend/ frontend/src/ | grep -v node_modules` → paste. If a server is found, PREMISE MISMATCH.

- [ ] **Step 2 — make the iframe URL env-driven with a graceful fallback.** Create `frontend/src/components/SwarmFrame.jsx`:
  ```jsx
  import React, { useState } from "react";
  const SWARM_URL = process.env.REACT_APP_SWARM_URL || "http://localhost:8099/";
  export default function SwarmFrame() {
    const [failed, setFailed] = useState(false);
    if (failed) {
      return (
        <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
          SwarmSPX service not running ({SWARM_URL}). Set REACT_APP_SWARM_URL or start the service.
        </div>
      );
    }
    return (
      <iframe src={SWARM_URL} title="SwarmSPX Neural Intelligence"
        onError={() => setFailed(true)}
        style={{ flex: 1, border: "none", width: "100%", height: "100%" }}
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups" />
    );
  }
  ```
  (Note: iframe `onError` is unreliable cross-origin; the value here is the env var + a clear message, not perfect detection. Keep it simple.)

- [ ] **Step 3 — wire it in App.js (surgical, with Nav approval).** Replace the inline iframe block (`grep -n "localhost:8099" frontend/src/App.js`) with `<SwarmFrame />` and add `import SwarmFrame from "./components/SwarmFrame";` near the other imports.

- [ ] **Step 4 — verify it compiles** (after T6 fixes jest) or at minimum `grep -n "SwarmFrame" frontend/src/App.js`. Commit.

**Estimate: 45 min.**

---

## TASK 5 — `react-plotly.js` missing from package.json (latent chart breakage)

**GATE: `frontend/package.json` is FROZEN. Get Nav's explicit "yes" before this task. Do not proceed otherwise.**

**Why:** `VannaChart.jsx:11` and `CharmChart.jsx:14` import `react-plotly.js`, which is present in `node_modules` now but ABSENT from `package.json` — a clean `yarn install` deletes it and blanks both charts.

- [ ] **Step 1 — confirm absence:** `grep -n "plotly" frontend/package.json` (expect nothing) and `ls frontend/node_modules/react-plotly.js >/dev/null && echo present`.
- [ ] **Step 2 (after approval) — add the deps:** `cd frontend && yarn add react-plotly.js plotly.js` (or `npm install --save`). Paste the resulting `package.json` diff.
- [ ] **Step 3 — verify:** `grep -n "plotly" frontend/package.json` shows both. Commit (note: touches the frozen file, approved by Nav on <date>).

**Estimate: 20 min.**

---

## TASK 6 — Frontend test harness can't parse JSX (entire FE suite runs 0 tests)

**Why:** `npx jest` fails with `Add @babel/preset-react ... to enable JSX transformation` — so there is currently ZERO frontend test coverage. This project uses CRA + craco. `craco.config.js` and `package.json` are frozen — prefer adding a Babel config file that does NOT touch them.

**Files:** Create `frontend/babel.config.js` (or `.babelrc.js`); possibly `frontend/jest.config.js`. Do NOT edit `package.json`/`craco.config.js` without approval.

- [ ] **Step 1 — reproduce:** `cd frontend && CI=true npx jest src/components/heatseeker/HeatseekerDashboard.test.jsx 2>&1 | tail -20` — paste the `preset-react` error.
- [ ] **Step 2 — inspect existing config:** `ls -la frontend/{babel.config.js,.babelrc,.babelrc.js,jest.config.js} 2>/dev/null; grep -n "jest\|babel" frontend/package.json frontend/craco.config.js`. Paste. Understand how jest is currently invoked.
- [ ] **Step 3 — add a Babel config** `frontend/babel.config.js`:
  ```js
  module.exports = {
    presets: [
      ["@babel/preset-env", { targets: { node: "current" } }],
      ["@babel/preset-react", { runtime: "automatic" }],
    ],
  };
  ```
  Confirm the presets are installed: `ls frontend/node_modules/@babel/preset-react >/dev/null && echo ok` (if missing AND Nav approved package.json edits, `yarn add -D @babel/preset-react @babel/preset-env`).
- [ ] **Step 4 — verify a test now executes:** `cd frontend && CI=true npx jest src/components/heatseeker/HeatseekerDashboard.test.jsx 2>&1 | tail -15`. Expected: the suite RUNS (passes or has real assertion failures — NOT a parse error). Paste.
- [ ] **Step 5 — if the babel.config.js breaks the real CRA build**, revert and instead get approval for a `jest` transform in package.json. Verify the build still works: `cd frontend && CI=true npx craco build 2>&1 | tail -5` (or the project's build command — `grep -n '"build"' frontend/package.json`).
- [ ] **Step 6 — commit.**

**Estimate: 1.5 hours** (config interactions are fiddly — go slow, verify the production build still works).

---

## TASK 7 — Frontend resilience: lazy-load Plotly + isolate chart failures

**Why:** Both charts import a ~3MB Plotly bundle at module top-level. If Plotly throws at load (or is missing), the single ErrorBoundary around the whole dashboard blanks ALL panels. Isolate each chart so a chart failure can't take down the GEX panels.

**Files:** Modify `frontend/src/components/heatseeker/HeatseekerDashboard.jsx` (NOT frozen) — wrap VannaChart/CharmChart in `React.lazy` + `Suspense` + a small local ErrorBoundary. Requires T6 (jest) for the test.

- [ ] **Step 1 — confirm current import style:** `grep -n "VannaChart\|CharmChart\|ErrorBoundary\|lazy" frontend/src/components/heatseeker/HeatseekerDashboard.jsx`. Paste.
- [ ] **Step 2 — write a failing test** (after T6): render `HeatseekerDashboard` with a mocked VannaChart that throws; assert the other panels (e.g. `getByText(/Node Lifecycle/i)`) still render. Red.
- [ ] **Step 3 — implement:** convert the two chart imports to `const VannaChart = React.lazy(() => import("../VannaChart"))` etc., wrap each in `<Suspense fallback={<div className="panel p-4 text-slate-500 text-xs">Loading chart…</div>}>` and a minimal class ErrorBoundary that renders "Chart unavailable" on error. Reuse the existing `ErrorBoundary` if one is importable (`grep -rn "class ErrorBoundary" frontend/src`).
- [ ] **Step 4 — test green; verify build** (`craco build`). Commit.

**Estimate: 1.5 hours.**

---

## TASK 8 — Full backend test suite + lint green (regression sweep)

**Why:** Lock in everything above and catch collateral damage.

- [ ] **Step 1 — collection:** `cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -5`. Expected: 0 collection errors (the project had ~2655 tests collecting clean). Paste. If there are collection errors introduced by your work, fix them.
- [ ] **Step 2 — full run:** `.venv/bin/python3 -m pytest -q --tb=short 2>&1 | tail -20`. Paste the summary line. Any test your changes broke must be root-caused and fixed (NOT skipped).
- [ ] **Step 3 — lint:** `.venv/bin/ruff check --select F,E722 .` → "All checks passed!". Paste.
- [ ] **Step 4 — commit** any fixes.

**Estimate: 1.5 hours** (full suite is large; investigate failures honestly).

---

## TASK 9 — Final live smoke of the Skylit tab + update the PR

- [ ] **Step 1 — restart** with `DISABLE_DATABENTO=1` (from T2). Wait for ready.
- [ ] **Step 2 — hit every Skylit endpoint once; expect 200 + non-degraded:**
  ```bash
  for u in flip-zones node-lifecycle air-pockets beach-ball reverse-rug rainbow-road velocity-mode trinity-confluence rolling-floors-ceilings node-classification stacked-nodes tug-of-war; do
    code=$(curl -s -o /tmp/r.json -w "%{http_code}" "http://localhost:8000/api/heatseeker/$u?ticker=SPY")
    deg=$(python3 -c "import json;print(json.load(open('/tmp/r.json')).get('status',''))" 2>/dev/null)
    echo "$u -> $code $deg"
  done
  for u in vanna-exposure charm-integral; do
    curl -s -o /dev/null -w "$u -> %{http_code}\n" "http://localhost:8000/api/$u/SPY?expiries=4"; done
  ```
  Expected: all `200`, none `degraded`. Paste.
- [ ] **Step 3 — Nav does the visual PWA review** (`decoder`). You CANNOT click in the PWA; report the endpoint evidence and ask Nav to confirm visually.
- [ ] **Step 4 — push; comment on PR #1** with the final evidence block. Do NOT merge (Nav merges).

**Estimate: 30 min.**

---

## COMMIT TEMPLATE (use for every task)

```bash
git add <only the files for THIS task>
git commit -m "$(cat <<'EOF'
fix(<scope>): <one-line>

<what + why in 2-3 lines>

Verification:
$ <command you ran>
<REAL pasted output>
$ <test command>
<REAL pasted output: "N passed">
EOF
)"
git push origin fix/skylit-tab-restore
git fetch origin && git log origin/fix/skylit-tab-restore --oneline -1   # confirm your subject
```

## SELF-REVIEW BEFORE YOU SAY "DONE"
- [ ] Every task's verification output is REAL terminal output you pasted (not described).
- [ ] No test was skipped/xfail'd; no passing assertion was loosened.
- [ ] `ruff check --select F,E722 .` passes.
- [ ] Full `pytest` summary pasted, with any breakage root-caused.
- [ ] Frozen-file edits (package.json) happened ONLY with Nav's recorded approval.
- [ ] PR #1 updated; not merged.

**If you cannot complete a task honestly, write exactly what blocked you and stop. A truthful "blocked at T3 step 5 because X" is worth more than a fabricated success.**
