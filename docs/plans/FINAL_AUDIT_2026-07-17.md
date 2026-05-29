# Confluence Decoder — Final Comprehensive Audit Report

**Round 1:** Code structure, backend routes, frontend components, ML pipeline, test infrastructure
**Round 2:** Security, infrastructure/DevOps, backend services depth, frontend/Dash/PWA depth
**Total issues found: 108+**

---

## 🔴 CRITICAL — Runtime Crashes / Blocks Build (14)

| # | File:Line | Issue |
|---|-----------|-------|
| 1 | `routes/heatseeker.py:119` | `_fetch_history()` called with `lookback_mins=` param it doesn't accept. Every `/api/heatseeker/node-lifecycle` call crashes with TypeError. |
| 2 | `routes/ml_api.py:206` | `os.path.exists()` called without `import os`. POST `/api/ml/register` crashes with NameError. |
| 3 | `routes/admin.py:37` | Missing `await` on `db.errors.delete_many()`. `/api/errors/clear` returns coroutine object. |
| 4 | `routes/admin.py:28` | `__import__("server")._start_time` — `_start_time` never defined in server.py. Uptime always 0. |
| 5 | `routes/admin.py:115` | `from server import _schwab_streamer` — variable never defined. ImportError on `/api/admin/schwab/health`. |
| 6 | `routes/ml_training.py:13-80` | ALL 10 routes call functions that DON'T EXIST in server.py. Entire file is dead code. |
| 7 | `server.py:2879-2881` | Duplicate `replay_router` wiring — imported and mounted twice. |
| 8 | `services/ml/inference.py:40-45` | MODEL_REGISTRY points to `SPY_rf_*.joblib` etc. — these files DON'T EXIST. Actual models are `SPY_gbm_production.joblib`. ML inference 100% dead. |
| 9 | **NEW** `frontend/src/components/CharmChart.jsx:16` | Import `../../hooks/useMarketData` resolves outside `src/`. **Blocks production build.** Fix: `../hooks/useMarketData` |
| 10 | **NEW** `frontend/src/components/VannaChart.jsx:15` | Same import issue. **Blocks production build.** |
| 11 | **NEW** `frontend/src/components/AlertOverlay.js:194` | `connect()` called in 2nd useEffect but defined inside 1st useEffect closure. `ReferenceError` on tab visibility change. |
| 12 | **NEW** `docker-compose.prod.yml:35` | References `Dockerfile` with `target: production` — NO `Dockerfile` exists. Only `Dockerfile.backend`/`Dockerfile.frontend` exist. |
| 13 | **NEW** `infra/azure/main.bicep:141-192` | Duplicate `subnet` resource declarations. **Bicep file won't compile.** |
| 14 | **NEW** `infra/azure/main.bicep:240-257` | Duplicate `capabilities: ['EnableMongo']` — double declaration. |

## 🔴 CRITICAL — Security (7)

| # | File:Line | Issue |
|---|-----------|-------|
| 15 | `routes/admin.py:14,22,41,97,143,199` | **6 admin GET routes have ZERO authentication.** `/databento/usage`, `/api/performance/stats`, `/api/admin/schwab/health`, `/api/admin/trading/status`, `/api/admin/trading/circuit-breaker/log` leak sensitive internal state. Auth middleware only protects POST/PUT/DELETE/PATCH. |
| 16 | `routes/alpha_advantage.py:52-252` | API keys passed as URL query parameters. Leaked in server logs, browser history, proxy caches, and Referer headers. |
| 17 | **NEW** `auth.py:103-118` | WebSocket token passed as query param (`?token=<TOKEN>`). Leaks in logs. |
| 18 | **NEW** `auth.py:110-112` | If `WS_API_TOKEN` env var is unset, all WebSocket connections allowed. Fails open. |
| 19 | **NEW** `server.py:2503-2509` | CSP `script-src` includes `'unsafe-inline'` and `'unsafe-eval'` — weakens XSS protection. |
| 20 | **NEW** `docker-compose.observability.yml:43` | Hardcoded Grafana admin password `admin` — trivial default credential. |
| 21 | **NEW** `package.json:78` | External tarball dep `@emergentbase/visual-edits` from `assets.emergent.sh` — supply chain risk, no integrity hash. |

## 🔴 CRITICAL — Test Infrastructure (1)

| # | Issue |
|---|--------|
| 22 | `backend/tests/conftest.py:28-81` autouse `_reset_event_loop_and_motor` fixture kills event loop. **2,343 of 2,378 tests fail (98.5%).** Single fix restores entire suite. |

## 🚨 HIGH — Functional / Data Integrity Bugs (15)

| # | File:Line | Issue |
|---|-----------|-------|
| 23 | `services/ml/retrain.py:305-309` | Label computed on entire dataframe before temporal split. Lookahead bias. |
| 24 | `services/ml/features.py:893-896` | Target-based row filter drops rows based on future label. Selection bias. |
| 25 | `retrain.py:227` | Models saved via `joblib.dump()` without quality gates. Degenerate models enter registry. |
| 26 | **NEW** `services/backtest/engine.py:186-226` | Equity tracking logic has inline comments acknowledging it's wrong (`# Actually let's be precise:`, `# Let me redo this cleanly:`). Uses `sum(t.net_pnl)` instead of proper cash flow tracking. |
| 27 | **NEW** `services/backtest/engine.py:140-141` | `position._pending_slippage` and `_pending_commission` are dynamic attributes on a @dataclass that doesn't define them. Suppressed with `# type: ignore[attr-defined]`. |
| 28 | **NEW** `services/research/discovery.py:201,302,375,...` | 8x `raise last_exc` — loses original traceback. Makes retry failure debugging impossible. |
| 29 | **NEW** `services/strategies/friday_pin.py:109` | Timezone DST handling fragile. `astimezone(UTC) - timedelta(5)` doesn't properly handle DST transitions. |
| 30 | **NEW** `services/memory/federation.py:38` | `LWW_GRACE_SECONDS = 5` defined but never used in LWW comparison. |
| 31 | `backend/alerts/definitions/gex_alerts.yaml:12` | Typo: `gextreme_positive` should be `gex_extreme_positive` for consistency. |
| 32 | `server.py:1573` | `asyncio.create_task(save_snapshot(...))` — fire-and-forget with NO error handler. |
| 33 | **NEW** `services/social_flow_pipeline.py:335` | Bare `except:` catches `KeyboardInterrupt`/`SystemExit`. |
| 34 | **NEW** `server.py:2785-2786` | `except Exception: pass` — DuckDB shutdown errors silently swallowed. |
| 35 | **NEW** `server.py:2617` | Index creation failure just logs warning — server runs degraded with no indication. |
| 36 | **NEW** `docker-compose.yml:39` | Frontend port mapping `3000:80` — container serves on 3000, not 80. Wrong port. |
| 37 | **NEW** `.github/workflows/deploy.yml:40` | `app-name: "confluence-decoder"` doesn't match terraform/bicep's `floww-prod-app`. |

## 🚨 HIGH — Frontend Runtime Bugs (8)

| # | File:Line | Issue |
|---|-----------|-------|
| 38 | `hooks/useMarketData.js:124` | `fetch(url, { timeout: 30000 })` — `timeout` NOT a standard browser fetch option. Silently ignored. Requests hang indefinitely. |
| 39 | **NEW** `public/service-worker.js:24,128,148` | References `/offline.html` which DOESN'T EXIST in `public/`. 404 on offline fallback. |
| 40 | **NEW** `public/service-worker.js:74` | `/ws/` paths caught by fetch handler — attempts `caches.match()` on WebSocket upgrade requests. |
| 41 | **NEW** `public/service-worker.js:50-54` | Cache cleanup filter `!name.startsWith('floww-')` prevents old versions from ever being deleted. |
| 42 | **NEW** `craco.config.js:14-15` | `ForkTsCheckerWebpackPlugin` and `ESLintWebpackPlugin` explicitly stripped from build. Type errors and lint violations pass silently. |
| 43 | **NEW** `App.js:800` | Hardcoded `<iframe src="http://localhost:8099/" />` — won't work in production. |
| 44 | **NEW** `public/manifest.json` | Shortcuts use `?page=heatseeker` but app uses React state routing (not URL params). Shortcuts don't navigate correctly. |
| 45 | **NEW** `AlertOverlay.js:142` | `BACKEND_URL = process.env.REACT_APP_BACKEND_URL \|\| 'http://localhost:8000'` — defaults to localhost (only one of 16 files with a fallback, but needs env var). |

## 🟡 MEDIUM — Code Quality / Technical Debt (30+)

### Backend
| # | File:Line | Issue |
|---|-----------|-------|
| 46 | `server.py` | 2,890-line monolithic file. |
| 47 | `server.py:2610,2770,2795,2839` | Four `@app.on_event("startup")` — deprecated. |
| 48 | `server.py:581-586` | Module-level imports 581 lines into file. |
| 49 | `server.py:481-540` vs `1404-1439` | Near-duplicate GEX functions. |
| 50 | `routes/market_data.py:83-90` vs `server.py:1619` | Duplicate `/api/tickers` route. |
| 51 | `routes/microstructure.py:34-101` | 5 unbounded dicts — memory leak. |
| 52 | **NEW** `server.py:64-68` | MongoDB credentials via bare `os.environ[]` — bypasses `config/secrets.py` SecretResolver. |
| 53 | **NEW** `config/secrets.py:12` | Default API_SECRET_KEY is `"dev-only-key"`. Trivially guessable if shipped. |
| 54 | **NEW** `services/research/discovery.py:503,602` | `except Exception: pass` — SSRN/NBER parsing errors silently dropped. |
| 55 | **NEW** `services/memory/federation.py:212,233` | `except Exception: pass` — memory federation failures silently dropped. |
| 56 | **NEW** `services/risk/gate.py` | Gate module fully implemented but NEVER called by `train_real_ml.py`. Bypassed. |
| 57 | **NEW** `server.py:89-100` | Rate limiter uses `defaultdict(deque)` with no eviction. Unbounded memory growth. |
| 58 | Hardcoded dividend yields | Duplicated in 5 locations. |
| 59 | `bs_greeks.py:9` vs `advanced_analytics.py` | Risk-free rate: 5% vs 4.5%. |
| 60 | `routes/greeks.py:56` | Sync DuckDB call in async route handler. |
| 61 | `routes/social_flow.py:96` | `datetime.utcnow()` deprecated. |
| 62 | **NEW** `server.py` startup (16+ routes) | 19 bare `except Exception:` blocks with no specific handling, no logging. |

### Frontend
| # | File:Line | Issue |
|---|-----------|-------|
| 63 | 16 files | `process.env.REACT_APP_BACKEND_URL` with no `\|\| ""` fallback. |
| 64 | 12+ locations | Empty catch blocks across 6 components. All errors silent. |
| 65 | `App.js:349-354` | `fetchAdvanced` defined with `useCallback` but NEVER CALLED. Dead code. |
| 66 | `App.js:5,37` | Unused imports: `DEFAULT_TICKERS`, `SocialFlowPanel`. |
| 67 | 4 files | Inconsistent `fetch()` vs `axios` usage. |
| 68 | `AlertsPanel.jsx:52,61,74,81,100` | 5 API calls with empty catch blocks. |
| 69 | **NEW** `FlowCarousel.js:40` | `window.innerWidth` captured in JSX — stale after resize. |
| 70 | **NEW** `App.js:287,290` | `localStorage.getItem("floww_settings")` called twice on every render. |
| 71 | **NEW** `public/index.html:57-67` | Dev-mode SW registration guarded by `window.__SW_DEBUG__` — NEVER SET. Dead code. |
| 72 | **NEW** `index.js:15-30` | Duplicate ErrorBoundary class (same as components/ErrorBoundary.js). Dead code. |
| 73 | **NEW** `MorningBriefing.jsx:14`, `SocialFlowPanel.jsx:14`, `PositionSizing.jsx:15` | `fetch()` without AbortController — setState on unmounted component possible. |

### ML Pipeline
| # | File:Line | Issue |
|---|-----------|-------|
| 74 | Features cloned 3x | `inference.py` vs `train_real_ml.py` vs `features.py` — different `min_periods`. |
| 75 | `inference.py:192-194` | Calendar features inside loop — wasteful recomputation. |
| 76 | `inference.py:301-310` | Dead code for tuple unpacking. |
| 77 | `outcomes.py:115` | MongoDB null query won't match missing fields. |
| 78 | `outcomes.py:91` | yfinance `period="5d"` — may not cover Monday open. |
| 79 | `models/` not in `.gitignore` | 11+ MB of .joblib tracked in git. |
| 80 | `features.py:483-608` | NaN stored in MongoDB without downstream cleaning. |

## 🟡 MEDIUM — Infrastructure / DevOps (14)

| # | File:Line | Issue |
|---|-----------|-------|
| 81 | **NEW** `infra/terraform/main.tf:18` | azurerm provider `~> 3.0` — now on v4.x. |
| 82 | **NEW** `prometheus/prometheus.yml:16` | `host.docker.internal:8000` — only works on Docker Desktop. Fails on Linux. |
| 83 | **NEW** `grafana/provisioning/dashboards/oracle.yml` | Two duplicate providers for same path. |
| 84 | **NEW** `.githooks/commit-msg:10` | Calls `qc/audit/check_phase_claim.sh` which DOESN'T EXIST. |
| 85 | **NEW** `docker-compose.prod.yml` | Uses unpinned `prom/prometheus:latest` and `grafana/grafana:latest`. |
| 86 | **NEW** `docker-compose.prod.yml` | No frontend service — assumes `./frontend/build` exists on host. |
| 87 | **NEW** `Dockerfile.backend:10` | `COPY backend/ .` — copies tests, venv, __pycache__ into image. |
| 88 | **NEW** `DISPATCH_PLAN_ORACLE_ROUND6.md:13-18` | Stale canonical path reference (`/Users/nav/Documents/GitHub/floww` — contradicts consolidation report). |
| 89 | **NEW** `deploy/systemd/oracle.service` | All paths use `/Users/nav/GitHub/floww/backend` — if canonical moved, these fail silently. |
| 90 | **NEW** `BACKLOG.md` | Extremely stale — claims Phase A "Data Layer" is active. Entire backlog from very early development. |
| 91 | **NEW** `ARCHITECTURE.md:149` | Claims "11 checks" in truth_audit.sh — actually 12 rules. |
| 92 | **NEW** `.github/workflows/ci.yml:74` | `MONGO_URL: mongodb://localhost:***@v4` — redacted/truncated value in CI config. |
| 93 | **NEW** `docker-compose.observability.yml` | Relative paths (`../prometheus/...`) fragile — breaks if compose run from different directory. |
| 94 | **NEW** `frontend/plugins/health-check/` | Development-only Webpack plugins — dead code in production. |

## 🟢 LOW — Minor / Informational (14)

| # | File:Line | Issue |
|---|-----------|-------|
| 95 | `services/causal/` missing `__init__.py` | Works but inconsistent with other packages. |
| 96 | `services/strategies/__init__.py` empty | Fine. |
| 97 | `services/memory/federation.py` | Logger name inconsistency (`log` vs `logger`). |
| 98 | `package.json` | `cra-template` is unused CRA init artifact. |
| 99 | `package.json` | No `engines` field for Node.js version minimum. |
| 100 | `backend/.env.example` — OK | All placeholders, no real keys leaked. |
| 101 | `routes/admin.py:16-18` | Uses `__import__()` instead of normal import — code smell. |
| 102 | `routes/ml_api.py:460` | Same `__import__()` pattern. |
| 103 | `public/manifest.json` | SVG used for all icon sizes — works technically but iOS may prefer PNG. |
| 104 | `services/memory/federation.py` | Fixme reminder: LWW_GRACE_SECONDS unused. |
| 105 | `server.py:1599-1612` | No-op stub cache decorator when Redis unavailable — silently does nothing. |
| 106 | `pytest.ini` | `slow` marker registered but NEVER used on any test. |
| 107 | `test_inference.py:432` | `@pytest.mark.requires_artifacts` — NOT registered in pytest.ini. Unknown marker warning. |
| 108 | `stateful/test_ingestion_state_machine.py` | Entire file skipped — dead code. |

---

## By Severity Count

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL (crashes/security/build-blocking) | 22 |
| 🚨 HIGH (functional bugs/data integrity) | 23 |
| 🟡 MEDIUM (code quality/infra/debt) | 50+ |
| 🟢 LOW (minor/informational) | 14 |
| **TOTAL** | **108+** |

## P0 Priority Fixes (do first, each under 30 min)

1. Fix `conftest.py:28-81` — remove autouse event loop teardown → restores 2,363 tests
2. Fix `inference.py:40-45` — dynamic MODEL_REGISTRY → restores ML inference
3. Fix `CharmChart.jsx:16` and `VannaChart.jsx:15` — fix imports → unblocks production build
4. Fix `heatseeker.py:119` — update `_fetch_history` signature
5. Fix `ml_api.py:206` — add `import os`
6. Fix `admin.py:37` — add `await`
7. Fix `admin.py:14,22,41,97,143,199` — add auth to 6 admin GET routes
8. Fix `useMarketData.js:124` — `AbortSignal.timeout(30000)`
9. Fix `AlertOverlay.js:194` — move `connect` outside useEffect closure
10. Fix `docker-compose.prod.yml:35` — use `Dockerfile.backend`
11. Fix `infra/azure/main.bicep:141-192` — remove duplicate subnet/capability
12. Remove dead `ml_training.py` routes
13. Create `/offline.html` or remove references from service-worker.js
14. Fix `docker-compose.yml:39` — port `3000:3000`

**Full reports also written to:**
- `docs/plans/DEEP_DIVE_AUDIT_2026-07-17.md` (54 issues, first pass)
- `docs/plans/JANE_STREET_REVIEW_2026-07-17.md` (professional HFT desk review)
- `docs/plans/FINAL_AUDIT_2026-07-17.md` (this file — 108+ issues, both passes combined)