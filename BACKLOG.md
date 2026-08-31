# BACKLOG.md — Confluence Decoder

> Synced with reality 2026-08-31 (post Phase 3/5 close + test fixes). Completed items
> moved to Done; resolved Discovered Issues annotated with their fix commits where known.
> Authoritative phase tracking now lives in `.planning/ROADMAP.md` (GSD).

## Active Phase: A — Data Layer ✅ COMPLETE

- [x] Data layer schema and migrations (`ad77c90` — versioned DuckDB migrations)
- [x] Repository pattern for MongoDB access (`d54395c`, `280890f`)
- [x] Data collection service with proper error handling (`640773c`)
- [x] Data quality checks and validation (`a34980f` — /api/data-quality/{ticker})

## Pending (promote to numbered phases via ROADMAP.md Phase 6)

### B — Quant analytics ⚠️ PARTIALLY BUILT

Much of the quant infrastructure already exists — this phase is mostly consolidation + exposure.

**Already in codebase:**
- `services/signal_translator.py` — Hermes signals → trade intent
- `services/flow_alerts.py` + `services/flow_quality.py` — institutional alert tiering
- `services/trading_signals.py` — VPIN_HFT signal generator (BUY/SELL)
- `services/hmm_regime.py` — Gaussian HMM regime detection
- `services/volume_clock.py` — volume clock analytics
- `services/composite_flow_score.py` — composite flow scoring
- `flashalpha_client.py` — FlashAlpha sentiment API client
- `scripts/backtest_regime_filtered.py` — regime-filtered signal backtest

**Still needed:**
- [ ] Central quant registry — single entry point for all signal producers
- [ ] Signal catalog endpoint (`/api/quant/signals` or similar) exposing available signals
- [ ] Factor/z-score normalization layer across signal types
- [ ] Signal backtest reports per signal type (Sharpe, hit rate, max-DD)

### C — ML pipeline ✅ MOSTLY BUILT

The ML pipeline is already operational. This phase is about hardening + exposing.

**Already in codebase:**
- `services/ml/` — full pipeline: inference.py (frozen), features.py, gate.py, backtest.py,
  health_monitor.py, registry.py, retrain.py, dashboard.py, gex_inference.py, outcomes.py, quality.py
- `scripts/train_*.py` — multiple training scripts (v2.0, v5, regime-enhanced, balanced ensemble, etc.)
- `scripts/backtest_model.py` + `scripts/walkforward_backtest_spy.py` — walk-forward backtest
- 5 production GBM models (SPY/QQQ/DIA/IWM/TLT) in `models/`
- ADR-0001 model promotion policy enforced

**Still needed:**
- [ ] OOS-locked backtest harness (`scripts/backtest_oos.py` — referenced but not verified present)
- [ ] Rolling OOS validation automation (daily retrain already exists)
- [ ] Model performance dashboard endpoint (ML dashboard UI exists but API exposure TBD)

### D — Backtester ⚠️ PARTIALLY BUILT

Backtest engine exists but needs completion + integration with alerts/ML gating.

**Already in codebase:**
- `services/backtest/engine.py` — event-driven backtest engine (note: known double-slippage issue
  per FINAL_AUDIT_2026-07-17; fix exists in reports but not verified applied)
- `services/backtest/report.py`, `signals.py`, `retail_flow_signal.py`
- `scripts/backtest_model.py`, `scripts/walkforward_backtest_spy.py`, `scripts/backtest_regime_filtered.py`
- `scripts/kelly_sizing_replay.py` — sizing policy comparison
- `reports/backtest_2024.md`, `reports/backtest_retail_20260523.md`, `reports/kelly_calibration_report.md`

**Still needed:**
- [ ] Verify/fix double-slippage bug in engine.py (audit found it; fix not confirmed applied)
- [ ] Event-driven backtest with realistic slippage/commission for alert gating
- [ ] `/api/backtest/*` routes exposing backtest results
- [ ] Per-alert backtest reports (every alert in `alerts/definitions/` gets a Sharpe/hit-rate/DD report)

### E — Alert DSL ⚠️ PARTIALLY BUILT

Alert system is largely built — YAML definitions + dispatcher + tuner + API routes exist.

**Already in codebase:**
- `alerts/definitions/gex_alerts.yaml` — alert rule definitions
- `routes/alerts_api.py` + `routes/alerts.py` — alert CRUD + status endpoints
- `services/alert_dispatcher.py` — severity/timing dispatch
- `services/alert_tuner.py` — configurable FPR tuner
- `services/flow_alerts.py` — GEX flow alert evaluation
- `server.py` — `_alert_rules` + `_alert_history` in-memory stores + CRUD routes

**Still needed:**
- [ ] Persist alert rules to MongoDB (currently in-memory — lost on restart)
- [ ] Alert DSL as a proper config format (YAML is good; need validation + schema)
- [ ] Backtest gating: every alert needs a backtest report before "live" status
- [ ] Alert quality dashboard (`/api/alert-quality` or similar)

### F — Trading execution ⚠️ BUILT (paper trading)

Paper trading is operational. Live execution is out of scope pending ADR.

**Already in codebase:**
- `paper_trading.py` — $100K paper trading engine
- `services/flow_trade_bridge.py` — alert → trade bridge
- `services/paper_trade_engine.py` — paper trade execution
- `services/execution_engine.py` — order execution
- `scripts/build_order_from_signal.py` — signal → order

**Still needed:**
- [ ] Live execution ADR (separate future decision — paper trading only for now)
- [ ] Trade journal / P&L tracking (overlaps with Phase G)

### G — Portfolio & P&L ❌ NOT STARTED

**Still needed:**
- [ ] Portfolio state service (positions, P&L, exposure)
- [ ] `/api/portfolio/*` routes
- [ ] P&L attribution (by ticker, by signal, by strategy)
- [ ] Equity curve + drawdown tracking

### H — Frontend architecture ⚠️ PARTIALLY BUILT

Frontend is functional (277 tests passing). Architecture improvements are incremental.

**Already done:**
- 277 frontend tests across 46 suites (OptionsChainTable 10/10, FlowseekerProBlademap 17/17)
- All 14 components resolve same-origin at runtime (fixed at `af4e254`)
- Caddy routing audited (312 backend paths; only /gex/*, /metrics, /health* outside /api)

**Still needed:**
- [ ] App.js decomposition (1128 lines — needs architect sign-off)
- [ ] TanStack Query / server-state library (open since ROUND10)
- [ ] Frontend test coverage expansion (currently 277 — goal TBD)

### I — Observability & ops ⚠️ PARTIALLY BUILT

Prometheus client is installed but no `/metrics` endpoint exposed.

**Already in codebase:**
- `prometheus_client` in requirements (installed)
- `services/ml/health_monitor.py` — model health monitoring (PSI drift, etc.)
- structlog JSON logging in production
- `/health` + `/api/health` endpoints

**Still needed:**
- [ ] `/metrics` endpoint exposing Prometheus gauges/histograms
- [ ] Request latency histogram, error rate counter, data source fallback counter
- [ ] MongoDB connection pool metrics
- [ ] yfinance-429 / provider fallback metrics (per RUNBOOK)

### J — Quality processes & ADRs ✅ MOSTLY DONE

**Already done:**
- ADR-0001 (model promotion policy) + ADR index at `docs/adr/`
- PR template at `.github/pull_request_template.md`
- Conventional commits documented in CLAUDE.md
- `.planning/codebase/` — 7 GSD codebase intel docs
- `.planning/LEARNINGS.md` — session learnings

**Still needed:**
- [ ] More ADRs (model quarantine, data source policy, deployment, etc.)
- [ ] Automated conventional commit enforcement (currently manual)
- [ ] Pre-commit hooks (ruff, mypy on non-frozen files)

## Done

- [x] Initial project setup
- [x] Security audit and fixes
- [x] ML training pipeline
- [x] Cron jobs for data collection
- [x] WebSocket improvements
- [x] Paper trading module
- [x] Morning briefing email system
- [x] Round 10 P0 tickets (conftest, fetch_spot_and_chains, STALE_IMPORT)
- [x] KillSwitch wired into auto-trade pipeline (`c5fe895`)
- [x] Columnar DuckDB bulk insert — ingestion 65x faster (`6648006`)
- [x] Rust decoder-core GEX path + volume-grid fallback (`98c8fd7`, `69691e4`)
- [x] Phase 3 — Public API Data Layer (94c3c89)
- [x] Phase 5 — Frontend Public API Wiring (c5e3b18, a1e69bc, dd14e32)
- [x] 3 pre-existing test failures resolved (caa3e77)

## Discovered Issues — status as of 2026-08-31

| Issue | Status |
|---|---|
| `iron_condible` typo in paper_trading.py | ✅ Fixed (comment at line 42 documents it) |
| App.js needs decomposition | Open — 1128 lines; Phase H |
| No server-state library (TanStack Query) | Open — Phase H |
| No frontend tests | ✅ Resolved — 277 tests across 46 suites |
| portfolio.py floats vs Decimal | Deferred — upstream prices are floats |
| Alert engine hardcodes alert types | ✅ Fixed (`beb02cc` — ALERT_TYPE_CATALOG) |
| No structured logging | ✅ Resolved — structlog JSON in prod |
| No Prometheus metrics | Open — Phase I (lib installed, no /metrics endpoint) |
| No ADRs | ✅ ADR-0001 + index shipped (`docs/adr/`) |
| No PR template | ✅ Shipped (`900130f`) |
| No conventional commits enforcement | Partially — documented in CLAUDE.md |
| BACKLOG.md stale (Phase A "Active" when complete) | ✅ Resolved in this sync |
| Double-slippage in backtest engine | Open — audit found it; fix not confirmed applied (Phase D) |

## Notes

- Deployment target: Oracle Always Free ARM. Runbook: `deploy/free/README.md`.
- Test posture: backend 4606 passed, 64 skipped, 1 xfailed, 0 failed · frontend 277 tests
  across 46 suites (OptionsChainTable 10/10 + FlowseekerProBlademap 17/17 passing).
- Backend health: `/health` + `/api/health` green on localhost:8000 (smoke-tested 2026-08-31).
- Local backend running: MongoDB + uvicorn on :8000 (launch via `scripts/launch_decoder.sh`).
