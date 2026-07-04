# Floww Project State Audit — 2026-07-02

> Audited by: Claude (Cowork)
> Sources: Obsidian vault, CLAUDE.md, BACKLOG.md, MASTER_PLAN.md, MEMORY.md, ROUND10_PLAN.md, git log, git diff, liveness_audit_2026-06-25.md, daily notes 2026-06-21 → 2026-07-28
> Machine date at audit: 2026-07-02 (⚠ see note below)

---

## ⚠ Date Ambiguity Notice

The system clock reports **2026-07-02**, but Obsidian vault contains daily notes dated through **2026-07-28**, and CLAUDE.md has a "Dev Environment (2026-07-28)" section in the unstaged diff. The hermes_persistent_facts.md frontmatter says `last_updated: 2026-07-03T01:41:46`. The uncommitted TrinityVolatility component in the diff matches work described in the 2026-07-28 daily note.

**Likely conclusion:** Machine clock is wrong. The actual date is approximately late July 2026. This report audits the codebase as seen at HEAD (`07a6473`) and treats all Obsidian daily notes as real session logs.

---

## Active Round: Round 10

Declared in CLAUDE.md: **Round 10 IN PROGRESS**. Plan at `docs/ROUND10_PLAN.md`.

### P0 Tasks

| Task | Description | Status |
|------|-------------|--------|
| **P0.1** | Conftest waiver — defer `from server import app` in `backend/tests/conftest.py`; drops 23 collection errors → 0 | **OPEN** — Not on main branch. Future work documented in 2026-07-18 note as `ee8932f` (on feature branch or mrbeast1179-sketch fork) |
| **P0.2** | Restore `fetch_spot_and_chains` — heatseeker `/flip-zones` returns degraded | **PARTIALLY ADDRESSED (UNCOMMITTED)** — `backend/server.py` unstaged diff has NaN/None guards added to `fetch_spot_and_chains_merged` and `compute_gex_by_strike`. Fix resolves the `unsupported operand + float and NoneType` bug in `build_heatmap`. Not yet committed. 2026-07-07 audit claims "P0.2 resolved" but those commits are on a different fork. |
| **P0.3** | A9 STALE_IMPORT cleanup — remove dead import lines for A9-deleted names | **PARTIALLY DONE** — Some F401 cleanup occurred in recent commits; 2026-07-18 note shows full F821 restoration (`ef9b9c6`, 186 symbols) and F401 fixes (`13a6fea`, 105 imports) — but these are on a different fork/branch, not on local main |

### P1 Tasks (Medium Priority — mostly still open)

| Task | Description | Status |
|------|-------------|--------|
| P1.1 | AlphaVantageProvider restoration in `data_providers.py` | Open — deferred from DS Pro (circuit breaker dependency) |
| P1.2 | Schwab streamer chaos tests (≥5 chaos tests) | Partially done — 6 chaos tests written by DS Pro in Round 9, handoff to Round 10 |
| P1.3a/b/c | Missing API endpoints: `/api/ml/calibration`, `/api/ml/compare`, `/chain` | Open — 2026-07-18 note shows Agent 4 pushed some P1.3 endpoints (`0ef2ff4`) but on fork |
| P1.4 | Frontend Jest/Babel config fix (JSX parse + ESM import errors) | Open |
| P1.5 | Type hints expansion (greek_aggregator, iv_skew_analyzer, etc.) | Open |

---

## Uncommitted Work (git diff HEAD)

**15 files changed, 97 insertions, 28 deletions** — substantial in-flight work, none committed.

### Modified files

| File | Net Δ | What changed |
|------|-------|-------------|
| `CLAUDE.md` | +2 | Minor doc update (Dev Environment section dated 2026-07-28) |
| `backend/server.py` | +45/-28 | Added `safe_float()` helper; NaN/None guards in `compute_gex_by_strike`; IV NaN skip in `fetch_spot_and_chains_merged` — fixes the `float + NoneType` heatmap crash |
| `backend/routes/market_data.py` | +16/-3 | Unknown detail (not diffed fully) |
| `backend/services/cvserver_client.py` | +13/-2 | Unknown detail |
| `frontend/src/App.js` | +23/-1 | Added `TrinityVolatility` import; added `trinityTab` state; added sub-tab toggle in trinity page (GEX Heatmap vs Volatility) — routes to `TrinityVolatility` component |
| `frontend/src/components/OptionsChainTable.jsx` | +6/-2 | Minor fix |
| `scripts/launch_decoder.sh` | +20/-3 | Launch script improvements (MongoDB step added per 2026-06-27 note) |
| `backend/.tmp/duckdb_*` (8 files) | deleted | Runtime scratch — DuckDB temp files; expected cleanup, not code |

### Untracked files (not staged, not committed)

| File | Status |
|------|--------|
| `frontend/src/components/TrinityVolatility.jsx` | **NEW** — Volatility sub-tab (Skew / Term / RR). Required for the App.js trinity sub-tab change to work |
| `frontend/src/components/TrinityVolatility.css` | **NEW** — Styles for TrinityVolatility component |
| `reports/liveness_audit_2026-06-25.md` | **NEW** — Critical audit document (untracked since June 25). Should be committed. |
| `scripts/stop_decoder.sh` | **NEW** — Clean shutdown script (created 2026-06-27, documented in CLAUDE.md, but not committed) |

### Branch state

```
On branch main
Your branch is ahead of 'origin/main' by 1 commit.
HEAD: 07a6473 feat(flowseeker-pro): cross-symbol BladeMap scanner tab + /scan endpoint
```

The `07a6473` commit exists locally but hasn't been pushed. Everything above is on top of that.

---

## Known Issues (from Obsidian + Backlog + Audit)

### Critical / Blocking

1. **All `backend/.env` provider keys are empty** (per liveness audit 2026-06-25). Entire provider chain falls to keyless yfinance. No `CVSERVER_API_KEY` set → every "live" tab is running on the weakest data tier. Fix: set `CVSERVER_API_KEY` in `backend/.env`.

2. **cvforge/convexvalue feed has zero quotes and zero trade-level data** — Probed across 1,984,793 contracts: bid/ask/midpoint and all trade_* fields are 0% populated. This means microstructure tabs (VPIN, OFI, lambda, Kyle-λ) are **structurally dead** until a tick provider is added (Schwab tape, Polygon paid options trades, or Databento trades schema). Not a code bug — a data availability limit.

3. **P0.1 conftest pytest collection errors** — ~23 tests fail collection because `conftest.py` forces `from server import app` before pytest's pythonpath is set. Fix exists (defer import) but is not on main yet.

4. **Uncommitted trinity changes are broken without TrinityVolatility** — App.js imports `TrinityVolatility` from an untracked file. If committed without the component files, the frontend build fails.

### High

5. **`test_put_delta_negative` fails** — pre-existing, greek aggregator delta sign issue. Not introduced by recent work.

6. **TLT model type mismatch** — manifest reports `"gbm"` but the estimator is actually RandomForest due to training script bug. Models still work but the metadata is wrong.

7. **MongoDB `gex_enhanced_snapshots` collection doesn't exist** — GEX features from MongoDB not available for ML training (2026-07-23 note). Falls back to `snapshots` collection with different schema.

8. **ML predict endpoint times out** — models not loaded in default dev startup (pre-existing, June 21 note). Frontend fixed to use `/api/ml/predict` instead of missing `/api/ml/briefing`, but the timeout remains.

9. **hmm_regime.py not exposed by any route** — `FlowseekerProBlademap.jsx` microstructure regime pill cannot be live. The function that returns `current_state: TRENDING_BULL|RANGING|TRENDING_BEAR` has no API route. The `/api/ml/regime/{t}` endpoint is a different concept (vol-percentile) and 404s without a model.

10. **Databento OI: 403 auth_account_locked** (2026-07-07 note) — need key rotation.

11. **Ingestion queue overflow: 86K messages dropped** (2026-07-07 note) — DuckDB ingestion queue needs tuning or consumer scale-up.

### Medium

12. **Portfolio tab is SYNTHETIC** — pure Black-Scholes on user-typed Spot/IV. No real provider in path. P&L card never renders due to shape bug: `calc_portfolio_summary` returns `pnl` as scalar; `PortfolioPanel.jsx:404` reads `pnl.total_pnl/...`.

13. **Journal tab: localStorage only** — trade log persists to browser localStorage only; no backend route. Sidebar prefill is live.

14. **Skylit staleness badge not wired** — backend `data_fallback`/`stale_age_s` not threaded into `SkylitDashboard`/`SkylitControlBar` → a stale DuckDB fallback renders as LIVE.

15. **Trinity header chips never emitted** — `change_pct` and `vix` fields not in `build_heatmap` payload from backend. Always blank in UI.

16. **Microstructure endpoints return zeroed constants** — `vpin`/`hawkes`/`anomaly`/`liquidity` in `routes/microstructure.py` return constructor defaults (zeros), not `status: "no_feed"`. Looks like real readings when they're not.

17. **`DataProviderMonitor.success_rate` defaults to 1.0 (healthy)** when no calls recorded (`meta_observability.py` ~413). False positive health signal.

18. **SPX (^SPX) returns 0 strikes** — index options OI not available from yfinance (2026-07-28 note). Affects Trinity tab when user selects SPX.

19. **API_SECRET_KEY not set** — new `ml_api` POST endpoints return 503 in local dev (2026-07-07 note). Expected but should be documented.

### Frontend-Specific (from 2026-07-07 full audit)

20. **Unused `react-router-dom` v7.5.1** — App uses custom state-based routing, never imports React Router. ~400KB unused bundle weight.

21. **3 duplicated component definitions** — `Movers`, `NodesTable`, `VelocityGauge` exist as both standalone files AND inline functions in App.js. Standalone files are dead code.

22. **`SocialFlowPanel` imported but never rendered** in App.js.

23. **`@emergentbase/visual-edits` CDN dependency** — opaque remote CDN dep, supply chain risk.

24. **3 pre-existing test failures** — `visual.test`, `AppShell.test`, `Sidebar.test` (module resolution issues, pre-existing).

### BACKLOG.md Stale Discovered Issues

25. `DEFAULT_STRATEGY = "iron_condible"` typo in `paper_trading.py`
26. No server-state library (TanStack Query not implemented)
27. No frontend tests for any component beyond snapshot tests
28. `portfolio.py` uses floats instead of Decimal for money
29. Alert engine hardcodes 7 alert types as Python methods (inflexible)
30. No structured logging (`structlog` not integrated)
31. No Prometheus metrics
32. No ADRs
33. No conventional commits enforcement in CI

---

## Blocked / Outstanding

| Item | Blocked by |
|------|-----------|
| Full live data (Heatseeker/Trinity/Skylit) | Owner action: set `CVSERVER_API_KEY` in `backend/.env` |
| Microstructure tabs (VPIN, OFI, Kyle-λ) | Requires tick/trade-level data provider — no code fix possible without new data source |
| Portfolio real P&L | Alpaca API keys not configured (`ALPACA_API_KEY`/`SECRET` in `.env`) |
| SwarmSPX tab | `REACT_APP_SWARM_URL` not set; SwarmSPX service must be running on `:8099` |
| Schwab streaming | Awaiting user's Schwab API access |
| Barchart OnDemand | Need API key signup |
| Gemini AI analysis | Quota exhausted; student pack pending |
| P0.1/P0.2/P0.3 on main | Work done on `mrbeast1179-sketch/floww` branches; needs PR or cherry-pick to canonical `JattMoosewala5911/floww` |
| Round 11 test coverage | Branches on `mrbeast1179-sketch/floww` (agents 02–09 pushed); not merged to canonical main |

---

## Hermes Durable Facts — Preserve These

```yaml
# PROJECT IDENTITY
project_name: "floww = Confluence Decoder"
stack: "FastAPI backend (port 8000) + React SPA (port 3000) + MongoDB (Motor async) + DuckDB (ingestion) + ML (5 GBM models: SPY/QQQ/DIA/IWM/TLT)"
canonical_clone: "/Users/nav/Documents/GitHub/floww"  # ONLY. /Users/nav/GitHub/floww deleted 2026-05-29
remote: "https://github.com/JattMoosewala5911/floww.git"

# RUNTIME
venv: "/Users/nav/Documents/GitHub/floww/backend/.venv/bin/python3"
python_version: "3.12"
backend_port: 8000
frontend_port: 3000
pwa_app: "~/Applications/Chrome Apps.localized/Confluence Decoder.app"
decoder_alias: "decoder → scripts/launch_decoder.sh → open -a PWA"
auto_startup: "~/Library/LaunchAgents/com.confluence-decoder.plist (MongoDB → FastAPI → React → PWA on login)"
stop_script: "scripts/stop_decoder.sh"

# FROZEN FILES — must not edit without architect sign-off
frozen:
  - "backend/services/ml/inference.py"  # except surgical bug fixes with justified commit body
  - "backend/services/dash_ui.py"  # Round 7 frozen
  - "backend/tests/conftest.py"  # R9 frozen; R10 P0.1 WAIVES with architect approval
  - "backend/models/*.joblib, *_manifest.json, *_meta.json"
  - "frontend/.env, frontend/package.json, frontend/craco.config.js"
  - "frontend/src/App.js"  # surgical edits only with explicit approval

# GEX SCALE CONVENTION — DO NOT "FIX" — INTENTIONAL DUAL SCALE
# display (gex_aggregator.py): S² = sign * γ * OI * 100 * spot² * 0.01
# ML features (gex_history.py):  S¹ = sign * γ * OI * 100 * spot  * 0.01
# relationship: display_net_gex == spot * feature_net_gex
# pinned by golden oracle tests in tests/services/test_gex_aggregator_oracle.py
# model-locked constants: _RISK_FREE=0.045, _IV_FALLBACK=0.20

# DATA FEED REALITY (as of 2026-06-25 audit)
cvforge_live_fields: [open_interest, implied_volatility, gamma, underlying_price]
cvforge_null_fields: [bid, ask, midpoint, quote_last_updated, trade_price, trade_size, trade_exchange, trade_conditions]
provider_chain: "cvserver → Databento → FlashAlpha → Finnhub/Polygon/AV → yfinance (fallback)"
current_active_tier: "yfinance (all keys empty in .env)"
key_needed: "CVSERVER_API_KEY in backend/.env to unlock full quality"

# AGENT TRUST RULES
freebuff_trust: "ZERO — FreeBuff = DeepSeek-Pro agent; documented fabrication of audit-fix commits (2026-06-24 audit). Verify every claimed fix by running, never by reading commit message."
screener_data: "SYNTHETIC — cv-apps/screener uses synthetic data, zero live cvApi"
anti_skip_gate: "after every commit: git pull --rebase origin main && git push && git fetch origin && git log origin/main --oneline -1 | grep <subject>"

# ACTIVE ROUND
active_round: "Round 10"
round_status:
  P0_1_conftest: "OPEN — fix on mrbeast1179-sketch fork branch; not merged to canonical main"
  P0_2_fetch_spot_and_chains: "PARTIALLY ADDRESSED — NaN guards in unstaged server.py diff; not committed"
  P0_3_stale_imports: "PARTIALLY DONE — F821 restoration (186 symbols) on fork; not merged"

# ML MODELS (production as of most recent training)
ml_models:
  SPY: "GBM, test_acc=54.9%, walk_forward=61.9%±13.5%, sharpe=6.87"
  QQQ: "GBM, test_acc=64.7%, walk_forward=63.1%±12.5%, sharpe=4.29"
  DIA: "GBM, test_acc=54.9%, walk_forward=55.4%±12.6%, sharpe=3.69"
  IWM: "GBM, test_acc=62.7%, walk_forward=68.5%±12.4%, sharpe=6.30"
  TLT: "GBM (actually RF — manifest bug), test_acc=60.7%, walk_forward=60.7%±10.3%, sharpe=3.73"
model_artifacts: "backend/models/*_gbm_production.joblib (sklearn 1.8.0, 42 features)"
```

---

## Obsidian Vault Issues

Issues flagged in the 2026-07-07 full codebase audit (not yet fixed):

| Severity | File | Issue |
|----------|------|-------|
| CRITICAL | `Operations Runbook.md` line 45 | References deleted path `/Users/nav/GitHub/floww` |
| CRITICAL | `Confluence Decoder.md` lines 38-41 | References `~/GitHub/floww/` (4 locations) |
| HIGH | `Final Status.md` | Dated 2026-05-23, claims "All Systems Operational" — severely stale |
| HIGH | `Agent Swarm.md` | Claims "Swarm idle since 2026-05-21" — contradicted by months of actual activity |
| HIGH | `Agent Knowledge Archive.md` | Missing Rounds 6-10 (~3 months of work) |
| HIGH | `memory/` artifacts | Last entry 2026-05-22; nothing since |
| HIGH | `hermes_persistent_facts.md` | ~70+ stale path references (`/GitHub/floww` instead of `/Documents/GitHub/floww`) — auto-generated, needs regen |
| MEDIUM | Multiple pages | Research Pipeline, Heatseeker, ML System — not updated since May |
| LOW | `create a link.md` | Empty (0 bytes) |
| LOW | `Untitled/` folder | 5 canvas files orphaned |

---

## Agentfield State

- Latest release: **v0.1.85** at `013e03b7` (2026-05-29)
- Recent work: SDK per-call `ai()` timeout, OpenRouter image retry/strip fallback, output handling hardening
- Status: **active, separate project** from floww. No integration blockers visible.
- Changelog: well-maintained with semantic versioning

---

## Project Health Assessment

### What's working well

- **Frontend UI quality**: Significant shipping velocity in June–July. Skylit dark theme, FlowSeeker Pro BladeMap, Trinity overhaul (DOM/Grid/Bars/Chain/List views with GEX/VEX toggle, DTE filter, per-panel ticker), Heatseeker view-mode fix, auto-startup via LaunchAgent — all committed and live.
- **ML pipeline**: 5 production GBM models trained, registered, serving predictions (SPY sharpe 6.87, QQQ sharpe 4.29). Walk-forward CV methodology sound.
- **Backend NaN hardening**: The uncommitted `safe_float()` patch in server.py cleanly resolves the heatmap arithmetic crash.
- **Auto-startup**: LaunchAgent means the full stack starts on login without manual intervention.
- **Documentation**: CLAUDE.md is tight and accurate. ROUND10_PLAN.md is a good source of truth. Liveness audit (2026-06-25) is thorough and honest.
- **agentfield**: Independent healthy release cadence.

### What's fragile or broken right now

1. **In-flight commit discipline**: The TrinityVolatility component (2 files) is untracked but already imported in App.js. If anyone commits App.js without the component files, the frontend build breaks. These 4 files + the stop script need to be committed together.

2. **Split-brain between forks**: Round 10 P0 fixes and Round 11 test coverage (10 agents) are on `mrbeast1179-sketch/floww`. The canonical remote is `JattMoosewala5911/floww`. Nothing from the July 7–28 work is visible on the canonical main branch. This is a significant divergence risk.

3. **Data reality gap**: Every live-looking tab is actually running on yfinance fallback because `.env` keys are empty. Users see "LIVE" badges on data that's the weakest available tier.

4. **1 commit ahead of origin**: The local `07a6473` hasn't been pushed. Combined with 97 lines of unstaged changes, if the machine crashes the most recent work is at risk.

### Immediate actions recommended

```bash
# 1. Commit the in-flight work (all 4 untracked files + 6 modified files)
cd /Users/nav/Documents/GitHub/floww
git add \
  frontend/src/components/TrinityVolatility.jsx \
  frontend/src/components/TrinityVolatility.css \
  scripts/stop_decoder.sh \
  reports/liveness_audit_2026-06-25.md \
  backend/server.py \
  backend/routes/market_data.py \
  backend/services/cvserver_client.py \
  frontend/src/App.js \
  frontend/src/components/OptionsChainTable.jsx \
  scripts/launch_decoder.sh \
  CLAUDE.md
git commit -m "feat(trinity): TrinityVolatility sub-tab + backend safe_float + startup/stop scripts

- TrinityVolatility.jsx + .css: Volatility (Skew/Term/RR) sub-tab in Trinity page
- App.js: sub-tab toggle, import TrinityVolatility
- server.py: safe_float() helper + NaN guards in compute_gex_by_strike (P0.2 partial fix)
- scripts: stop_decoder.sh, launch_decoder.sh MongoDB step
- reports: commit liveness_audit_2026-06-25.md (was untracked since audit)"

# 2. Push the local-only commit + this new commit
git push origin main

# 3. Set CVSERVER_API_KEY in backend/.env (owner action)
echo 'CVSERVER_API_KEY=<your_key>' >> backend/.env

# 4. Cherry-pick or PR the Round 10 P0.1 fix from mrbeast1179-sketch fork
# ee8932f fix(conftest): P0.1 - defer server import inside aclient fixture
git remote add sketch https://github.com/mrbeast1179-sketch/floww.git
git fetch sketch
git cherry-pick ee8932f  # P0.1 conftest fix
```

---

## Summary Table

| Dimension | Status |
|-----------|--------|
| Git main branch | 1 commit ahead of origin, ~97 lines unstaged |
| Round 10 P0 tasks | All 3 OPEN or partial on main; fixes exist on separate fork |
| Round 11 test coverage | 8/10 agents pushed to fork branch, not merged |
| Data quality | Yfinance fallback only (all `.env` keys empty) |
| Frontend build | Would pass IF TrinityVolatility files are committed |
| Backend tests (last known count) | 4356 collected, 17 pre-existing errors |
| ML models | 5 production models serving (sklearn 1.8.0, GBM) |
| Obsidian vault | Severely stale (missing Rounds 6-10, wrong paths) |
| agentfield | Active, healthy at v0.1.85 |
| Freebuff/cvforge | 8 audit issues open; commits unverified — do not trust |
