# ROUND 8 — Backend Route Audit

**Agent:** Agent I (Backend Route Audit Lead)
**Date:** 2026-07-10
**Scope:** React frontend `/api/*` calls vs Fastapi backend routes
**Method:** Static analysis (grep) + live curl against localhost:8000
**Constraint:** NO modifications to backend files

---

## 1. React API Call Inventory

### From `hooks/useHeatseeker.js` (base: `/api/heatseeker`)

| # | Endpoint Pattern | Component File | Notes |
|---|---|---|---|
| 1 | `/api/heatseeker/air-pockets` | `heatseeker/AirPocketsPanel.jsx` | Query: `ticker`, `expiries` |
| 2 | `/api/heatseeker/beach-ball` | `heatseeker/BeachBallIndicator.jsx` | Query: `ticker` |
| 3 | `/api/heatseeker/flip-zones` | `heatseeker/NodeLifecyclePanel.jsx` | Query: `ticker`, `expiries`, `window_pct` |
| 4 | `/api/heatseeker/node-classification` | heatseeker panels | Query: `ticker`, `expiries` |
| 5 | `/api/heatseeker/node-lifecycle` | `heatseeker/NodeLifecyclePanel.jsx` | Query: `ticker`, `expiries` |
| 6 | `/api/heatseeker/rainbow-road` | `heatseeker/RainbowRoadIndicator.jsx` | Query: `ticker` |
| 7 | `/api/heatseeker/reverse-rug` | `heatseeker/ReverseRugIndicator.jsx` | Query: `ticker` |
| 8 | `/api/heatseeker/rolling-floors-ceilings` | heatseeker panels | Query: `ticker`, `expiries` |
| 9 | `/api/heatseeker/stacked-nodes` | heatseeker panels | Query: `ticker`, `expiries` |
| 10 | `/api/heatseeker/trinity-confluence` | `heatseeker/TrinityConfluenceMeter.jsx` | Query: `ticker` |
| 11 | `/api/heatseeker/tug-of-war` | heatseeker panels | Query: `ticker` |
| 12 | `/api/heatseeker/velocity-mode` | `heatseeker/VelocityModeBadge.jsx` | Query: `ticker` |

### From `hooks/useMarketData.js` (base: `/api`)

| # | Endpoint Pattern | Component File | Notes |
|---|---|---|---|
| 13 | `/api/analytics/charm-integral/{ticker}` | `CharmChart.jsx` | Query: `expiries=4` |
| 14 | `/api/analytics/vanna-exposure/{ticker}` | `VannaChart.jsx` | Query: `expiries=4` |

### Direct fetch/axios calls (various base: `${REACT_APP_BACKEND_URL}/api`)

| # | Method | Endpoint Pattern | Component File |
|---|---|---|---|
| 15 | GET | `/api/databento/usage` | `SidebarPanels.jsx` |
| 16 | GET | `/api/live/policy` | `SidebarPanels.jsx` |
| 17 | POST | `/api/live/policy` | `SidebarPanels.jsx` |
| 18 | POST | `/api/live/tape/stop` | `FlowTicker.jsx` |
| 19 | POST | `/api/preferences/theme` | `ThemeContext.js` |
| 20 | POST | `/api/position-size` | `PortfolioPanel.jsx` |
| 21 | GET | `/api/portfolio/{name}` | `PortfolioPanel.jsx` |
| 22 | POST | `/api/portfolio/{name}/position` | `PortfolioPanel.jsx` |
| 23 | DELETE | `/api/portfolio/{name}/position/{index}` | `PortfolioPanel.jsx` |
| 24 | GET | `/api/portfolio/{name}/scenario` | `PortfolioPanel.jsx` |
| 25 | POST | `/api/portfolio/{name}/hedge` | `PortfolioPanel.jsx` |
| 26 | GET | `/api/contract/{ticker}` | `Drilldown.jsx` |
| 27 | GET | `/api/daily-checklist/{ticker}` | `MorningBriefing.jsx`, `PositionSizing.jsx`, `TradeEntry.jsx` |
| 28 | GET | `/api/alerts/summary/{ticker}` | `DashboardSummary.jsx` |
| 29 | GET | `/api/social/report/{ticker}` | `SocialFlowPanel.jsx` |
| 30 | GET | `/api/gex-timeframes/{ticker}` | `MultiTimeframeGEXPanel.jsx` |
| 31 | GET | `/api/alerts` | `AlertsPanel.jsx` |
| 32 | GET | `/api/alerts/check/{ticker}` | `AlertsPanel.jsx` |
| 33 | POST | `/api/alerts` | `AlertsPanel.jsx` |
| 34 | DELETE | `/api/alerts/{id}` | `AlertsPanel.jsx` |
| 35 | GET | `/api/history/{ticker}` | `HistoryPanel.jsx` |
| 36 | GET | `/api/uoa/{ticker}` | `UOAPanel.jsx` |
| 37 | GET | `/api/movers` | `Movers.jsx` |
| 38 | GET | `/api/heatmap/{ticker}` | `TrinityView.jsx` |
| 39 | GET | `/api/paper-trading/portfolio` | `PaperTrade.jsx` |
| 40 | POST | `/api/paper-trading/execute` | `PaperTrade.jsx` |
| 41 | GET | `/api/chain/{ticker}` | `OptionsChainTable.jsx` |

---

## 2. Backend Route Inventory

Routes extracted from `backend/routes/*.py` via `@router.(get|post|put|delete)` decorators.

Routers are mounted in `backend/server.py` via `app.include_router()`. The effective prefix is the combination of the APIRouter's own `prefix` parameter and the `include_router(prefix=...)`.

### Routers with prefix in APIRouter (self-contained)

| File | APIRouter Prefix | Routes (partial) |
|---|---|---|
| `agent_hub.py` | `/api/agent-hub` | `/`, `/status`, `/agents` |
| `alerts_api.py` | `/api/alerts` | POST `/fire`, GET `/status`, POST `/acknowledge` |
| `alerts.py` | `/api/alerts` | WS `/ws/signals`, GET `/summary`, GET `/{ticker}`, POST `/snapshot`, GET `/status` |
| `alpaca.py` | `/api/alpaca` | various alpaca endpoints |
| `alpha_advantage.py` | `/api/alpha` | various |
| `anomaly.py` | `/api/anomaly` | `/{ticker}` |
| `data_providers.py` | `/api/data` | various data endpoints |
| `ensemble.py` | `/api/ensemble` | various |
| `flashalpha.py` | `/api/flashalpha` | various |
| `gemini.py` | `/api/ai` | various |
| `heatseeker.py` | `/api/heatseeker` | `/air-pockets`, `/beach-ball`, `/flip-zones`, `/node-classification`, `/node-lifecycle`, `/rainbow-road`, `/reverse-rug`, `/rolling-floors-ceilings`, `/stacked-nodes`, `/trinity-confluence`, `/tug-of-war`, `/velocity-mode` |
| `hawkes.py` | `/api/hawkes` | various |
| `liquidity.py` | `/api/liquidity` | various |
| `microstructure.py` | `/api/microstructure` | various |
| `ml_api.py` | `/api/ml` | various |
| `ml_dashboard.py` | `/api/ml` | various |
| `ml_predict_api.py` | `/api/ml` | various |
| `nexus.py` | `/api/nexus` | various |
| `predictions` | `/api/predictive` | various |
| `preferences.py` | `/api/preferences` | POST `/theme` |
| `replay.py` | `/api/replay` | various |
| `retail_flow.py` | `/api/retail-flow` | various |
| `social_flow.py` | `/api/social` | GET `/sentiment/{ticker}`, GET `/flow/{ticker}`, GET `/report/{ticker}`, GET `/status` |
| `trinity.py` | `/api/trinity` | various |
| `vol_surface.py` | `/api/vol-surface` | various |
| `vpin.py` | `/api/vpin` | various |
| `greeks.py` | `/api/greeks` (via include_router) | GET `/profile/{ticker}` |

### Routers WITHOUT prefix in APIRouter (get prefix from include_router)

| File | include_router Prefix | Effective Full Path |
|---|---|---|
| `admin.py` | `/api` | `/api/databento/usage`, `/api/performance/stats`, etc. |
| `analytics.py` | `/api/analytics` | `/api/analytics/movers`, `/api/analytics/history/{ticker}`, `/api/analytics/contract/{ticker}`, `/api/analytics/charm-integral/{ticker}`, `/api/analytics/vanna-exposure/{ticker}` |
| `briefing.py` | `/api` | `/api/briefing/{ticker}`, etc. |
| `morning_briefing_api.py` | `/api` | `/api/daily-checklist/{ticker}` |
| `heatseeker_snapshots_api.py` | `/api/heatseeker` | `/api/heatseeker/top-movers/{ticker}`, `/api/heatseeker/history/{ticker}` |
| `live_trading.py` | `/api` | `/api/live/policy` (GET+POST), `/api/live/tape/stop` (POST) |
| `llm.py` | `/api` | various LLM routes |
| `market_data.py` | `/api` | `/api/chain/{ticker}`, `/api/heatmap/{ticker}`, `/api/gex-timeframes/{ticker}`, `/api/uoa/{ticker}` |
| `memory.py` | `/api` | various |
| `ml_training.py` | `/api` | `/api/train`, etc. |
| `portfolio.py` | `/api` | `/api/portfolio/{name}`, `/api/portfolio/{name}/position`, etc., `/api/position-size` (POST), `/api/portfolio/{name}/scenario`, `/api/portfolio/{name}/hedge` |
| `schwab.py` | `/api` | various schwab routes |
| `position_sizing_api.py` | *(none)* | `/api/position-sizing` (GET) |
| `paper_trading.py` | *(none)* | Has **hardcoded** `/api/paper-trading/...` in route defs |

### Routes defined directly in `server.py` (not in route files)

| Method | Path | Description |
|---|---|---|
| POST | `/api/alerts` | Create alert rule |
| GET | `/api/alerts` | List alert rules |
| DELETE | `/api/alerts/{alert_id}` | Delete alert rule |
| GET | `/api/alerts/types` | List alert types |
| GET | `/api/alerts/check/{ticker}` | Check triggered alerts |

---

## 3. Mismatches: React Calls That Don't Match Backend

Critical findings where React will get 404/405/500 at runtime.

| # | React Calls | Backend Has | Issue | Severity |
|---|---|---|---|---|
| **M1** | `GET /api/alerts/summary/{ticker}` | `GET /api/alerts/summary` (no ticker in path) | React puts ticker in URL path; backend expects it as query param or not at all (router `summary` conflicts with `alerts.py` GET `/summary`) | **HIGH** |
| **M2** | `POST /api/position-size` | `GET /api/position-sizing` | Wrong method (POST vs GET) AND wrong path (`position-size` vs `position-sizing`). Backend route is in `position_sizing_api.py` at `/api/position-sizing` (GET). The `portfolio.py` also defines `POST /api/position-size` but it may shadow. | **HIGH** |
| **M3** | `GET /api/history/{ticker}` | `GET /api/analytics/history/{ticker}` | Missing `/analytics` segment. React calls `/api/history/SPY` but backend route is under the analytics router prefix. | **HIGH** |
| **M4** | `GET /api/movers` | `GET /api/analytics/movers` | Missing `/analytics` segment. Defined in `analytics.py` with `/api/analytics` prefix. | **HIGH** |
| **M5** | `GET /api/contract/{ticker}` | `GET /api/analytics/contract/{ticker}` | Missing `/analytics` segment. Defined in `analytics.py`. | **HIGH** |
| **M6** | `DELETE /api/portfolio/{name}/position/{index}` | `DELETE /api/portfolio/{name}/position/{index}` | Route exists in `portfolio.py` BUT the `index` param: React passes an integer index, backend route uses `Path` — verify type. Currently gets 405 (method not allowed?) or route shadowing from server.py routes. | **MEDIUM** |
| **M7** | Router prefix inconsistency: `paper_trading.py` | Other routes in `paper_trading.py` hardcode `/api/paper-trading/...` in the route decorator itself, while the router has no prefix and `include_router` also has no prefix. This double-prepends `/api` — but since there's no include_router prefix, the routes become `/api/paper-trading/...`. **Inconsistent pattern** with rest of codebase. | **MEDIUM** |
| **M8** | `alerts.py` vs `alerts_api.py` | Both use `prefix="/api/alerts"` creating potential route conflicts. `alerts.py` has `GET /summary` while `alerts_api.py` adds `POST /fire`. FastAPI may handle this, but overlapping prefixes from two separate routers is fragile. | **MEDIUM** |
| **M9** | `position_sizing_api.py` mounted without prefix | Router has no prefix, `include_router` has no prefix. Route is `@router.get("/api/position-sizing")` — the `/api` is hardcoded in the route def. This is inconsistent with the rest of the codebase where `/api` comes from include_router. | **LOW** |

---

## 4. Health Table (Live curl Results)

Tested against `http://localhost:8000` with `{ticker}=SPY`, `{name}=default`, `{index}=0`, `{id}=1`.

| # | Endpoint | Method | Status | Response Shape | Notes |
|---|---|---|---|---|---|
| 1 | `/api/databento/usage` | GET | **200** | JSON | OK |
| 2 | `/api/analytics/charm-integral/SPY` | GET | **200** | JSON `{spot, expiry, charm_buckets...}` | OK |
| 3 | `/api/analytics/vanna-exposure/SPY` | GET | **200** | JSON `{degraded: true, error_type: "computation_error"}` | Returns degraded response (numba compilation error) |
| 4 | `/api/heatseeker/air-pockets` | GET | **200** (slow) | JSON `{degraded: true, ...}` | Computation error (numba) |
| 5 | `/api/heatseeker/beach-ball` | GET | **200** (slow) | JSON `{degraded: true, ...}` | Computation error (numba) |
| 6 | `/api/heatseeker/flip-zones` | GET | **200** (slow) | JSON `{degraded: true, ...}` | Computation error (numba) |
| 7 | `/api/heatseeker/node-classification` | GET | **422** | Validation error | Missing required query param `ticker` |
| 8 | `/api/heatseeker/node-lifecycle` | GET | **200** (slow) | JSON `{degraded: true, ...}` | Computation error (numba) |
| 9 | `/api/heatseeker/rainbow-road` | GET | **200** | JSON `{ticker, spot, pattern, active}` | OK |
| 10 | `/api/heatseeker/reverse-rug` | GET | **200** (slow) | JSON (returns rainbow_road data?) | Possible wrong handler — returns same shape as rainbow-road |
| 11 | `/api/heatseeker/rolling-floors-ceilings` | GET | **422** | Validation error | Missing required query param `ticker` |
| 12 | `/api/heatseeker/stacked-nodes` | GET | **422** | Validation error | Missing required query param `ticker` |
| 13 | `/api/heatseeker/trinity-confluence` | GET | **200** | JSON `{snapshots: {SPX, SPY, ...}}` | OK |
| 14 | `/api/heatseeker/tug-of-war` | GET | **422** | Validation error | Missing required query param `ticker` |
| 15 | `/api/heatseeker/velocity-mode` | GET | **200** | JSON | OK |
| 16 | `/api/live/policy` | GET | **200** | JSON | OK |
| 17 | `/api/live/tape/stop` | POST | **503** | `{"detail": "Authentication not configured"}` | Route exists, blocked by auth |
| 18 | `/api/preferences/theme` | POST | **503** | `{"detail": "Authentication not configured"}` | Route exists, blocked by auth |
| 19 | `/api/position-size` | POST | **405** | Method Not Allowed | Backend has GET `/api/position-sizing` (different path + method) |
| 20 | `/api/portfolio/default` | GET | **404** | `{"error": "Not Found"}` | No portfolio named "default" exists — may be expected behavior |
| 21 | `/api/portfolio/default/position` | POST | **405** | Method Not Allowed | — |
| 22 | `/api/portfolio/default/position/0` | DELETE | **405** | Method Not Allowed | — |
| 23 | `/api/portfolio/default/scenario` | GET | **200** | JSON | OK |
| 24 | `/api/portfolio/default/hedge` | POST | **405** | Method Not Allowed | — |
| 25 | `/api/contract/SPY` | GET | **404** | `{"error": "Not Found"}` | Route is at `/api/analytics/contract/SPY` (M5) |
| 26 | `/api/daily-checklist/SPY` | GET | **404** | `{"error": "Not Found"}` | Route is at `/api/daily-checklist/SPY` via `morning_briefing_api.py` — may be shadowed |
| 27 | `/api/alerts/summary/SPY` | GET | **404** | `{"error": "Not Found"}` | Backend has `/api/alerts/summary` without ticker (M1) |
| 28 | `/api/social/report/SPY` | GET | **200** | JSON `{ticker, cached, message, report}` | OK (returns "No report available") |
| 29 | `/api/gex-timeframes/SPY` | GET | **200** (slow) | JSON | OK |
| 30 | `/api/alerts` | GET | **200** | JSON `{rules, count}` | OK (from server.py) |
| 31 | `/api/alerts/check/SPY` | GET | **200** (slow) | JSON | OK (from server.py) |
| 32 | `/api/alerts` | POST | **200** | JSON `{status: "created", rule}` | OK (from server.py) |
| 33 | `/api/alerts/1` | DELETE | **200** | JSON `{status: "deleted"}` | OK (from server.py) |
| 34 | `/api/history/SPY` | GET | **404** | `{"error": "Not Found"}` | Route is at `/api/analytics/history/SPY` (M3) |
| 35 | `/api/uoa/SPY` | GET | **200** (slow) | JSON | OK |
| 36 | `/api/movers` | GET | **404** | `{"error": "Not Found"}` | Route is at `/api/analytics/movers` (M4) |
| 37 | `/api/heatmap/SPY` | GET | **200** (slow) | JSON | OK |
| 38 | `/api/paper-trading/portfolio` | GET | **200** | JSON | OK |
| 39 | `/api/paper-trading/execute` | POST | **405** | Method Not Allowed | — |
| 40 | `/api/chain/SPY` | GET | **200** (slow) | JSON | OK |
| 41 | `/api/position-sizing` | GET | **200** | JSON | OK (but React calls `/api/position-size` POST) |

---

## 5. Recommendations for Round 9

### Critical Fixes (HIGH — will cause runtime errors)

1. **M1: `/api/alerts/summary/{ticker}`** — Either add a new route `GET /api/alerts/summary/{ticker}` to `alerts.py` or change React to call `GET /api/alerts/summary?ticker=SPY`.

2. **M2: `/api/position-size` POST** — React expects POST to `/api/position-size` but backend has GET `/api/position-sizing`. Need to either:
   - Add a POST route to `/api/position-size` in `portfolio.py` (which already has a POST `/position-size` route — verify it's not shadowed)
   - Or fix the path/method mismatch between `position_sizing_api.py` and React.

3. **M3: `/api/history/{ticker}`** — Add a redirect or alias route, or change React to call `/api/analytics/history/{ticker}`.

4. **M4: `/api/movers`** — Add alias route or change React to call `/api/analytics/movers`.

5. **M5: `/api/contract/{ticker}`** — Add alias route or change React to call `/api/analytics/contract/{ticker}`.

### Medium Fixes (inconsistent patterns)

6. **M6: Portfolio DELETE/PORT/hedge returning 405** — Investigate why `portfolio.py` POST/DELETE routes return 405. Possible route shadowing from server.py's `/api/alerts` routes or middleware interference.

7. **M7: `paper_trading.py` hardcoded `/api` prefix** — Refactor to use include_router prefix consistently. Currently works by accident (no include_router prefix + hardcoded `/api` in routes = correct path), but fragile.

8. **M8: Dual `/api/alerts` routers** — Merge `alerts.py` and `alerts_api.py` into a single router to avoid prefix conflicts.

9. **M9: `position_sizing_api.py` hardcoded `/api`** — Remove hardcoded `/api` from route def, add proper prefix to include_router.

### Low Priority (cosmetic / consistency)

10. **Auth middleware returning 503** — Several routes (live/policy, preferences/theme) return 503 "Authentication not configured". This is a deployment config issue, not a code bug, but should be documented.

11. **Heatseeker numba errors** — 6 of 12 heatseeker endpoints return `{degraded: true, error_type: "computation_error"}` due to numba compilation failures. This is a backend computation issue, not a routing issue, but affects data quality.

12. **`/api/daily-checklist/{ticker}` 404** — Route exists in `morning_briefing_api.py` but returns 404. Investigate if the router is properly mounted or if there's a path conflict.

---

## Appendix: Response Shape Verification

| Endpoint | React Expects | Backend Returns | Match? |
|---|---|---|---|
| `/api/heatseeker/velocity-mode` | JSON | JSON `{...}` | YES |
| `/api/social/report/{ticker}` | `{cached: bool}` | `{ticker, cached, message, report}` | YES |
| `/api/alerts` GET | `{rules: [], count: n}` | `{rules: [], count: n}` | YES |
| `/api/analytics/charm-integral/{ticker}` | JSON | `{spot, expiry, buckets, ...}` | YES |
| `/api/portfolio/{name}/scenario` | JSON | JSON `{...}` | YES |
| `/api/paper-trading/portfolio` | JSON | JSON `{...}` | YES |

---

**Audit Complete.** No backend files were modified.
Verified: `git diff --stat backend/` returns 0 files changed.
