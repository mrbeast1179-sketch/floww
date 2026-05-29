# Confluence Decoder / floww — Comprehensive Deep Dive Audit

**Date:** 2026-07-17  
**Scope:** Full codebase audit — backend (Python/FastAPI), frontend (React/CRA), ML pipeline (sklearn), tests (pytest)  
**Repo:** `/Users/nav/GitHub/floww` (branch `main`, up to date with origin/main)  
**Last commit:** `be9ed3e feat(ml): MlDashboard integration + regime-filtered backtest`

---

## Executive Summary

**Severity breakdown: 7 critical runtime crashes, 2 high-severity functional bugs, 1 security issue, 15 medium-severity issues, 20+ code quality/debt items.** The test suite is 98.5% broken (2,343 of 2,378 tests fail) due to a single event-loop fixture conflict. The ML inference engine is completely non-functional (stale MODEL_REGISTRY). Multiple backend routes will crash on first hit. The frontend fetches silently hang in browsers due to a non-standard `fetch()` option.

---

## 🔥 CRITICAL — Runtime Crashes (7)

These WILL crash when the route is hit:

| # | File:Line | Issue |
|---|-----------|-------|
| 1 | `routes/heatseeker.py:119` | `_fetch_history()` defined with 1 param (`ticker`), called with 2 (`ticker.upper(), lookback_mins=lookback_mins`). TypeError on every `/api/heatseeker/node-lifecycle` call. |
| 2 | `routes/ml_api.py:206-207` | `os.path.exists(artifact_path)` — `import os` is missing. NameError on `POST /api/ml/register`. |
| 3 | `routes/admin.py:37` | `db.errors.delete_many(...)` — missing `await` on AsyncIOMotorCollection coroutine. `result.deleted_count` fails. `/api/errors/clear` broken. |
| 4 | `routes/admin.py:28` | `__import__("server")._start_time` — `_start_time` never defined in server.py. `uptime_seconds` always 0. |
| 5 | `routes/admin.py:115` | `from server import _schwab_streamer` — variable never defined. ImportError on `/api/admin/schwab/health`. |
| 6 | `routes/ml_training.py:13-80` | ALL 10 routes call functions that DON'T EXIST in server.py (`train_model_endpoint`, `predict_endpoint`, etc.). Every route crashes with AttributeError. Entire file is dead code. |
| 7 | `server.py:2879-2881` | Duplicate `replay_router` wiring — imported at line 2748 AND again at line 2879. FastAPI warnings + undefined behavior. |

## 🔥 CRITICAL — ML Inference Completely Broken

| # | File:Line | Issue |
|---|-----------|-------|
| 8 | `services/ml/inference.py:40-45` | `MODEL_REGISTRY` hardcodes filenames like `SPY_rf_20260524_020801.joblib` that DON'T EXIST on disk. Actual models are `SPY_gbm_production.joblib`. Every inference call raises `DegenerateModelError`. |

## 🚨 HIGH — Functional/Learning Bugs

| # | File:Line | Issue |
|---|-----------|-------|
| 9 | `frontend/hooks/useMarketData.js:124` | `fetch(url, { timeout: 30000 })` — `timeout` is NOT a standard browser fetch option. **Silently ignored.** Requests can hang indefinitely. Fix: `AbortSignal.timeout(30000)`. |
| 10 | `services/ml/retrain.py:305-309` | Label (`spot.pct_change().shift(-1)`) computed on ENTIRE dataframe before temporal train/test split. Lookahead bias: future returns leak into training features. |
| 11 | `services/ml/features.py:893-896` | Target-based row filter `if targets["directional_move"][i] != 0 or targets["return_pct"][i] != 0` — drops rows based on future label → selection bias in training. |
| 12 | `retrain.py:227` | Models saved directly via `joblib.dump()` without running quality gates (`_save_with_gates` never called). Degenerate models can enter the registry. |

## 🔴 MEDIUM — Frontend Issues

| # | File:Line | Issue |
|---|-----------|-------|
| 13 | `App.js:800` | `<iframe src="http://localhost:8099/" ...>` — hardcoded to localhost:8099. Won't work in production. |
| 14 | `App.js:48` + 15 other files | `const BACKEND_URL = process.env.REACT_APP_BACKEND_URL` — NO fallback (`\|\| ""`). When env var is missing, `API = "undefined/api"`. Affects: App.js, PortfolioPanel, TradeJournal, TradeEntry, FlowTicker, PaperTrade, MlDashboard, AlertsPanel, PositionSizing, SocialFlowPanel, OptionsChainTable, TrinityView, MorningBriefing. |
| 15 | `AlertsPanel.jsx:52,61,74,81,100` | All 5 API calls have empty `catch (e) {}` — every error silently swallowed. No user feedback on failure. |
| 16 | `FlowTicker.jsx:82` | `connect` callback depends on `paused` state. Toggling pause regenerates function → stale closures with EventSource. |
| 17 | `App.js:318,403,733` | Silent `.catch(() => {})` on ticker fetch, ensemble fetch, and ToxicityGauge refresh. Network failures invisible. |
| 18 | `App.js:349-354` | `fetchAdvanced` defined with `useCallback` but NEVER CALLED anywhere. Dead code. |
| 19 | `App.js:5,37` | Unused imports: `DEFAULT_TICKERS`, `SocialFlowPanel`. |
| 20 | `TradeEntry.jsx:74`, `MlDashboard.jsx:79,94`, `SocialFlowPanel.jsx:14`, `MorningBriefing.jsx:14` | Use raw `fetch()` instead of `axios` — inconsistent with rest of app. No axios interceptors/timeouts. |
| 21 | `CharmChart.jsx, VannaChart.jsx` | via `useMarketData` hook — same `timeout` bug as #9. |
| 22 | `service-worker.js:277` | Hardcoded `/api/trades` endpoint — doesn't use env var. |
| 23 | `PositionSizing.jsx:57,62,67` | Hardcoded cost estimates (`icMaxLoss=300`, `straddleCost=500`) — not market-derived. |

## 🔴 MEDIUM — ML Pipeline Issues

| # | File:Line | Issue |
|---|-----------|-------|
| 24 | `inference.py` vs `train_real_ml.py` vs `features.py` | Feature computation logic CLONED 3+ times with subtly different `min_periods` values (1 vs 14 vs 5/21). Different NaN behavior → silent prediction differences. |
| 25 | `inference.py:192-194` | `is_month_end`/`is_month_start` computed INSIDE the vol window loop — recomputed 4x, wasteful. |
| 26 | `inference.py:301-310` | Dead code: tuple unpacking logic that's never used (MODEL_REGISTRY is `Dict[str, str]`, not tuples). |
| 27 | `features.py:483-608` | Multiple functions return `float("nan")` for missing data → NaNs stored to MongoDB, never cleaned for downstream drift monitoring. |
| 28 | `outcomes.py:115` | Mongo query `{"realized_outcome": {"$eq": None}}` — won't match documents where the field is MISSING (vs set to null). |
| 29 | `outcomes.py:91` | yfinance download `period="5d"` — if prediction date is Friday, 5 days might not cover Monday's open. |
| 30 | `models/` NOT in `.gitignore` | 11+ MB of binary .joblib files tracked in git. Should be gitignored. |
| 31 | `dashboard.py:47` | MongoDB URL with credentials was apparently committed to source (now redacted). Check git history. |

## 🔴 MEDIUM — Test Infrastructure

| # | Issue |
|---|-------|
| 32 | `backend/tests/conftest.py:28-81` autouse `_reset_event_loop_and_motor` fixture manually closes/recreates event loop BEFORE every test. Conflicts with pytest-asyncio's own loop management. **Single root cause: 2,343 of 2,378 tests fail (98.5%).** |
| 33 | 18 tests `@pytest.mark.skip` — disabled due to "needs network access" / "live MongoDB required" |
| 34 | 6 flaky tests marked `@pytest.mark.flaky` — heatseeker, anomaly training |
| 35 | `@pytest.mark.requires_artifacts` in `test_inference.py:432` — **NOT registered in pytest.ini** → `PytestUnknownMarkWarning` |
| 36 | `stateful/test_ingestion_state_machine.py` — entire file skipped (dead code) |
| 37 | `tests/conftest.py` lines 42-43, 65-67, 71-72 — `except: pass` swallowing errors in event loop teardown |
| 38 | `slow` marker registered in pytest.ini but NEVER used on any test |

## 🟡 LOW — Security / Data Safety

| # | File:Line | Issue |
|---|-----------|-------|
| 39 | `routes/alpha_advantage.py:52-252` | ALL routes take API key as URL query parameter (`api_key: str = Query(...)`). Logged in access logs, visible in browser history, cached by proxies. Should use server-side env variable or header-based auth. |
| 40 | `server.py:65` | `MONGO_URL = os.environ["MONGO_URL"]` — bare access, crashes on startup if not set. At minimum should have a helpful error message. |

## 🟡 LOW — Code Quality / Technical Debt

| # | File:Line | Issue |
|---|-----------|-------|
| 41 | `server.py` | 2,890-line monolithic file with route wiring, analytics, helpers, middleware, error handlers, startup logic. Should be decomposed. |
| 42 | `server.py:2610,2770,2795,2839` | FOUR `@app.on_event("startup")` handlers — deprecated in FastAPI. Should use lifespan context manager. |
| 43 | `server.py:581-586` | Module-level imports (bs_greeks functions) placed 581 lines into the file after code that uses them. Extremely fragile. |
| 44 | `server.py:481-540` vs `server.py:1404-1439` | Near-duplicate GEX computation functions (`compute_gex_by_strike` vs `compute_gex_by_strike_volume`) — ~90% identical. |
| 45 | `server.py:1573` | `asyncio.create_task(save_snapshot(...))` — fire-and-forget with NO error handler. Unhandled exception warning in Python 3.12+. |
| 46 | `routes/microstructure.py:34-101` | 5 unbounded dicts (`_vpin_engines`, `_hawkes_processes`, etc.) that grow forever. Memory leak. |
| 47 | Hardcoded dividend yields | DUPLICATED in 5 locations: `server.py:232`, `server.py:254`, `advanced_analytics.py:254`, `advanced_analytics.py:536`, `advanced_analytics.py:626` |
| 48 | `bs_greeks.py:9` vs `advanced_analytics.py` | Risk-free rate: 5% vs 4.5% — inconsistent. |
| 49 | `server.py:1599-1612` | No-op stub cache decorator when Redis is unavailable — silently does nothing. Should warn. |
| 50 | `server.py:1208` | Polygon API call with only 10s timeout — concurrent calls exhaust asyncio threads. |
| 51 | `routes/retail_flow.py:207` | `np.datetime64("now")` — may not serialize to JSON without custom encoder. |
| 52 | `routes/social_flow.py:96` | `datetime.utcnow()` — deprecated in Python 3.12+. |
| 53 | `routes/greeks.py:56` | Synchronous `duckdb.connect()` inside async route handler. Blocks event loop. |
| 54 | `routes/morning_briefing_api.py:78` | `import server as srv` imports entire 2,890-line module at request time. |

## Project Stats Summary

| Category | Count |
|----------|-------|
| Backend server.py | 2,890 lines |
| Backend route files | 44 files, 6,481 lines |
| ML service files | 9 files, 3,458 lines |
| Analytics/helpers | 4 files, 1,321 lines |
| Frontend src (React) | ~13,184 lines |
| Frontend components | 20+ significant component files |
| Test files | 138 files, 33,242 lines |
| Working tests | **15 passed / 2,378 total** (0.6%) |
| Git branches (remote) | 14 branches |
| Uncommitted changes | 14 modified, 3 untracked |
| Skill pitfall entries | 193 |
| Critical runtime crashes | 7 |
| ML inference dead | 1 (models don't match registry) |
| Security issues | 1 (API keys in URL params) |

---

**Written for the main architect.** Priority order to fix:

1. **P0 - Fix conftest.py event loop fixture** → restores 2,363 tests
2. **P0 - Fix inference.py MODEL_REGISTRY** → restores ML inference
3. **P0 - Fix routes/heatseeker.py:119** → node-lifecycle endpoint crash
4. **P0 - Fix routes/ml_api.py:206** → add `import os`
5. **P0 - Fix routes/admin.py:37** → add `await`
6. **P0 - Fix routes/ml_training.py** → either wire to real functions or remove dead routes
7. **P1 - Fix useMarketData.js timeout** → all 4 components using it silently hang in browser
8. **P1 - Fix silent error catches** → 12+ empty catch blocks across 6 components
9. **P2 - Add BACKEND_URL fallback** → 16 files affected
10. **P2 - Remove hardcoded localhost:8099** → use env var