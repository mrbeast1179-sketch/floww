# Project Oracle — Round 6 Technical Brief & Agent Charter

**Document Type:** Internal architecture briefing & multi-agent dispatch specification
**Repository:** `github.com/JattMoosewala5911/floww` (canonical clone: `/Users/nav/Documents/GitHub/floww`)
**Branch State:** `main @ 9594258` (post-Round-5 salvage)
**Test Baseline:** 1,882 passing / 0 failing / 34 skipped (94 s wall-time, Python 3.13, MacOS arm64)
**Date:** 2026-05-23
**Document Owner:** Architect (Nav)
**Audience:** Qwen-driven LLM prompt generator → 10 autonomous coding agents

---

## §0  Reader's Guide

This document is the **single source of truth** for Round 6 of the Project Oracle build-out. It is structured so that an LLM acting as a prompt-generator (Qwen) can:

1. Read §1–§5 to internalize the existing system, invariants, and the lessons of Round 5.
2. Read §6 to understand each of the ten agent identities, their file ownership, dependencies, and acceptance criteria.
3. Read §7–§9 for operating protocols and verification standards that every prompt must propagate.
4. Use §10 to mechanically expand each charter into a complete, paste-ready agent prompt.

Sections labelled **NORMATIVE** use RFC-2119 keywords (MUST, SHOULD, MAY) and may not be relaxed by Qwen.

---

## §1  System State (as of 2026-05-23, `9594258`)

### 1.1 Architectural pillars (Project Oracle directive, May 2026)

| Pillar | Technology | Status | Open Work |
|---|---|---|---|
| **Real-time ingestion** | FastAPI + WebSocket (Schwabdev) | Polling fallback active (Schwab L2 unavailable); Alpha Vantage live at 60-s poll | Pillar reinstated via WS once entitlements return |
| **Mathematical engine** | Numba JIT (`backend/services/numba_greeks.py`) | `bs_vanna`, `bs_charm` JIT-compiled; rest in pure Python | Full vector family + AOT compilation (Round 6, Agent 2) |
| **Storage layer** | DuckDB OLAP (`backend/services/duckdb_engine.py`) | Schema live, 16-column `ticks`, 18-column `chains`, dual-write pattern | Hot-path OLAP-first reads (Round 6, Agent 3) |
| **Visualization** | React (production) + Dash/Plotly (planned) | React UI live at `frontend/`; Dash app skeleton present, no auto-detection of king-nodes | King-node / air-pocket detection + heatmap overlay (Round 6, Agent 4) |

### 1.2 Live data pipeline

```
                ┌──────────────────────┐
                │ Alpha Vantage API    │  (15-min delay, key set in .env)
                │ key = ALPHAVANTAGE…  │
                └─────────┬────────────┘
                          │ 60-s poll
                          ▼
   ┌─────────────────────────────────────────────────┐
   │ backend/routes/data_providers.py                │  (committed at 5549e3a)
   │   - /api/data/quote/{ticker}                    │
   │   - /api/data/options/{ticker}                  │
   │   - /api/data/technical/{ticker}/{indicator}    │
   └─────────┬───────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────┐
   │ backend/services/fetch_coordinator.py           │  (request coalescing)
   │ backend/services/cache_router.py                │  (cache-first routing)
   └─────────┬───────────────────────────────────────┘
             │
             ▼
   ┌─────────────────────────────────────────────────┐
   │ backend/routes/analytics.py                     │  19 endpoints, all
   │   - /api/implied-pdf/{ticker}                   │  cache-first now
   │   - /api/regime/{ticker}                        │
   │   - /api/hedge-impulse/{ticker}                 │
   │   - /api/pressure-cloud/{ticker}                │
   │   - /api/charm-integral/{ticker}                │
   │   - /api/vanna/{ticker}                         │
   │   - /api/advanced/{ticker}, …                   │
   └─────────────────────────────────────────────────┘
```

**Cache hit budget:** the system aims for ≥80 % cache hit ratio on UI-triggered analytics requests. Externally observable via Prometheus `floww_cache_hit_ratio`.

### 1.3 Risk infrastructure

| Component | File | Coverage |
|---|---|---|
| Pre-trade gate | `backend/services/risk/gate.py` | 17 tests pass; NaN-aware on `conviction`, `sentiment_z`, `kyle_lambda`; inclusive boundaries (`<=`) on equity, daily-loss |
| Kill switch | `backend/services/risk/killswitch.py` | Trip + reset + audit trail |
| Position sizer | `backend/services/risk/sizer.py` | Kelly-fractional with floor/ceiling |
| Credit/budget monitor | `backend/services/credit_monitor.py` | 80 % MEDIUM / 95 % CRITICAL alerts |
| Staleness alerts | `backend/services/staleness_alerts.py` | 15 min MEDIUM / 60 min CRITICAL on cache age |
| Meta-observability | `backend/services/meta_observability.py` | Isolation-forest anomaly detector on 5 system metrics; trained model checkpoint at `project_oracle/models/meta_anomaly_v1.pt` |

### 1.4 Strategy + backtest layer

| Component | File | Status |
|---|---|---|
| Retail-flow signal | `backend/services/retail_flow_score.py` | Composite (CPR, OI-Δ, IV-skew), 27 tests pass |
| Backtest harness | `scripts/backtest_2024.py` | Walk-forward; **not yet OOS-locked** (Round 6, Agent 5) |
| Regime filter | `backend/services/regime_filter.py` | SMA-21 trend gate, 11 tests pass |
| Throughput predictor | `backend/scripts/predict_throughput.py` | Linear ensemble + drift detector (distribution-shift signal); 11 tests pass |

### 1.5 Observability stack

- **Metrics**: Prometheus exposition via `backend/services/observability.py`. Histograms for request latency, DuckDB batch size, fill slippage (bps). Counters for `rate_limit_429_total`, `fills_total`. Gauges for `cache_hit_ratio`, schwab_token_expires_in_seconds.
- **Dashboards**: Grafana provisioned dashboards at `grafana/dashboards/sla_cost.json`.
- **Incidents**: Templated post-mortems at `docs/INCIDENTS/_template.md`; CLI generator at `scripts/start_incident.py` (15 tests pass; idempotent by `alert_id`).
- **Kanban watcher**: `kanban/watcher.py` enforces WIP limits, auto-archives done cards >24 h, logs blockers to `kanban/INCIDENTS.md`.

---

## §2  Operating Invariants (NORMATIVE)

The following constraints have not changed since Project Oracle's inception and **MUST NOT be relaxed** by any agent or by Qwen when generating prompts.

| ID | Invariant | Rationale |
|---|---|---|
| I-1 | **No synthetic data in validation paths.** Train, validate, and report only on real recorded market data or paper-traded data. | Synthetic training data masks specification bugs and biases. |
| I-2 | **Baseline-first.** Every new model or signal MUST publish a baseline comparison (buy-and-hold SPY + simple mean-reversion) before promotion. | Detects models that have less alpha than holding cash. |
| I-3 | **OOS-locked.** Train/test split is a wall. Test data MUST NOT inform any hyperparameter choice, feature engineering decision, or model selection. | Eliminates the look-ahead family of bugs. |
| I-4 | **TDD discipline.** Failing test first, then implementation, then refactor. No exceptions. | Makes the spec executable and protects the regression contract. |
| I-5 | **Tool boundaries.** Agents use CLI / Bash / Python / git only. The user (Nav) operates PyCharm, DataGrip, WebStorm. | Prevents IDE state pollution and merge-time surprises. |
| I-6 | **Single canonical clone.** All work occurs under `/Users/nav/Documents/GitHub/floww`. Agents that find themselves under `/Users/nav/GitHub/floww` MUST stop and emit a "wrong-clone" error. | Round 5 lost an entire day to parallel commits in two clones to the same origin. |
| I-7 | **No double-prefix routes.** When a router is mounted with `prefix="/api"`, handler paths MUST NOT begin with `/api/...`. | Round 5 produced `/api/api/analytics/X` (broken) for every analytics endpoint. |
| I-8 | **Numeric guard.** Any comparison against a feature that may be `NaN` MUST be `math.isnan(x) or x op limit`, not bare `x op limit`. | IEEE-754 NaN comparisons return `False`, silently bypassing safety checks. Discovered in Round 5 risk-gate audit. |
| I-9 | **No background polling for completed work.** Agents that delegate must wait for completion signals, not sleep-and-poll. | Cache invalidation, latency, observability noise. |
| I-10 | **Atomic commits with descriptive bodies.** Each commit covers one logical change; commit body explains WHY, not WHAT. | `git log` becomes the executive summary; bisect remains useful. |

---

## §3  Round 5 Post-Mortem (Lessons Encoded)

### 3.1 Incident summary

Ten agents were dispatched on 2026-05-22 to deliver the retail-pivot infrastructure (API validation, cache-first routing, request coalescing, predictive alerting, memory consolidation). Six of ten produced usable work. Four of ten (Agents 3, 4, 7, parts of 10) were unknowingly checked out under `/Users/nav/GitHub/floww` — a stale parallel clone to the same origin. Their commits pushed bug-bearing changes that were invisible to the canonical-clone agents until the rebase.

### 3.2 Root causes

1. **Workspace ambiguity.** Two clones, same origin, no machine-enforceable preference. Agents' working directory was decided by orchestrator config that drifted out of sync.
2. **Implicit file ownership.** `services/cache_router.py` was modified by Agents 1, 3, 4, and 7 in overlapping windows. Each rewrite undid prior work because no agent owned the file outright.
3. **Route-mount confusion.** Stale-clone agents wrote handlers with full paths `/api/analytics/X` but did not realize the router was already mounted at `/api`. Double-prefix bugs were invisible to local-only manual tests because the test client traversed both paths in some setups.
4. **Drift detector overfit.** Linear regression on small data + brittle MAPE criterion → false-positive drift alerts. Detector lost trust before any real drift could occur.
5. **NaN propagation in safety gates.** Risk gate used bare comparison; NaN inputs silently passed every check. No alert fired.

### 3.3 Fixes deployed in salvage (`7124dfa`, `834e654`, `6208bed`)

| Fix | Commit | Verification |
|---|---|---|
| NaN guards on conviction / sentiment_z / kyle_lambda | `7124dfa` | 17/17 gate tests pass |
| Inclusive boundaries (`<=`) for equity, daily-loss | `7124dfa` | Boundary tests added |
| `yoptions` optional import with `HAS_YOPTIONS` flag | `7124dfa` | Suite collection no longer blocked |
| `__init__.py` files in `tests/services/{risk,ml}/` | `7124dfa` | `test_gate.py` module collision resolved |
| `start_incident.py` TDD spec alignment | `7124dfa` | 15/15 incident tests pass |
| `charm_integral` return shape uniformity | `834e654` | API contract consistent across early-exit and happy paths |
| `semantic_search` backward-compat `trade` alias | `834e654` | 4 search tests pass |
| `/api/databento/usage` adds `cached_days` + `recent` | `834e654` | `test_databento_usage` passes |
| `kanban.parse_card` defaults `id` to filename stem | `834e654` | Auto-archive resilient to stray files |
| Route prefix de-duplication (19 paths) | `6208bed` | All 21 `test_api.py` tests pass |
| `CacheRouter.degraded_response` instance method | `6208bed` | All analytics endpoints serve degraded payload on failure |
| `_priority_to_float` label coercion | `6208bed` | Throughput predictor accepts "medium"/"high"/"low" |
| Distribution-shift drift detector | `6208bed` | 11/11 throughput tests pass |

### 3.4 Encoded preventatives (carried into Round 6 below)

- **§2 invariants I-6 through I-8** codify the bugs above. Agents MUST reject prompts that would violate them.
- **§6 file ownership matrix** ensures no two agents write the same file in the same round.
- **§7 verification protocol** requires every agent to (a) write a failing test first, (b) prove regressions stayed green, (c) curl-smoke-test their endpoint, (d) log a one-line entry in `docs/ROUND6_COMPLETION_LOG.md`.

---

## §4  Round 6 Mission

> **From infrastructure to viability.** Round 5 shipped the pipes. Round 6 makes them carry water in production.

Every task delivered in Round 6 MUST satisfy at least one of:

- **(D)** Live-data integration. Get Alpha Vantage data flowing into a feature the UI consumes.
- **(V)** Model validation. Prove a signal causes (not merely correlates with) the outcome on OOS data.
- **(H)** Failure hardening. Validate a specific failure mode by inducing it and observing graceful degradation.

Tasks failing all three tests are **out of scope** for Round 6 and should be queued to Round 7.

The **critical path** to live-trading viability is:

```
   Agent 1 (Live data → UI)
        │
        ▼
   Agent 5 (OOS-locked backtest + paper trading)
        │
        ▼
   Agent 7 (Causal inference: signal causes outcome?)
        │
        ▼
   Agent 10 (Live-trading switch ceremony)
```

The remaining six agents (2, 3, 4, 6, 8, 9) are **parallelizable enablers**. They may proceed independently provided they respect the file ownership matrix in §6.

---

## §5  Architecture Reference (Read Before Generating Prompts)

### 5.1 Repository layout (canonical)

```
/Users/nav/Documents/GitHub/floww/
├── backend/
│   ├── server.py                       # 2,864 lines; 5 on_event handlers (Agent 6 migrates)
│   ├── advanced_analytics.py           # GEX/VEX/Charm/Vanna math
│   ├── data_providers.py               # AV adapter for quotes
│   ├── routes/
│   │   ├── analytics.py                # 19 cache-first endpoints; DO NOT prefix /api
│   │   ├── data_providers.py           # AV REST proxy
│   │   ├── alpha_advantage.py          # NEW Round 5 work, AV REST
│   │   ├── admin.py                    # databento usage, schwab health
│   │   ├── heatseeker.py
│   │   ├── nexus.py
│   │   └── live.py
│   ├── services/
│   │   ├── cache_router.py             # Cache-first; method degraded_response()
│   │   ├── fetch_coordinator.py        # Per-ticker asyncio.Lock for coalescing
│   │   ├── duckdb_engine.py            # 16-col ticks, 18-col chains
│   │   ├── numba_greeks.py             # bs_charm, bs_vanna JITted
│   │   ├── retail_flow_score.py        # CPR + OI-Δ + IV-skew composite
│   │   ├── regime_filter.py            # SMA-21 trend filter
│   │   ├── iv_skew_analyzer.py
│   │   ├── greek_aggregator.py
│   │   ├── credit_monitor.py
│   │   ├── staleness_alerts.py
│   │   ├── meta_observability.py
│   │   ├── observability.py            # Prometheus exposition
│   │   ├── anomaly_detector.py         # Conv1DAutoencoder gated on HAS_TORCH
│   │   ├── fill_monitor.py             # Slippage histogram emission
│   │   ├── semantic_search.py
│   │   └── risk/
│   │       ├── gate.py                 # PreTradeRiskGate (NaN-aware)
│   │       ├── killswitch.py
│   │       └── sizer.py
│   ├── scripts/
│   │   ├── predict_throughput.py       # Drift detector (distribution-shift)
│   │   ├── acquire_hf_assets.py
│   │   ├── train_anomaly_detector.py
│   │   ├── train_patchtst_vpin.py
│   │   └── backtest_2024.py
│   └── tests/                          # 1,882 passing
│       ├── services/risk/__init__.py   # REQUIRED (Round 5 lesson)
│       ├── services/ml/__init__.py     # REQUIRED (Round 5 lesson)
│       └── …
├── frontend/                            # React + Vite
│   ├── src/
│   │   ├── hooks/                       # useMarketData, etc.
│   │   ├── components/                  # CharmChart, VannaChart, …
│   │   └── App.js
├── scripts/
│   └── start_incident.py                # Idempotent incident bootstrapper
├── kanban/
│   ├── board.yaml
│   ├── cards/                           # 32 cards
│   ├── watcher.py                       # WIP enforcement, auto-archive
│   ├── BOTTLENECK_ALERTS.md
│   └── SWARM_STATUS.md
├── grafana/dashboards/sla_cost.json
├── docs/INCIDENTS/_template.md
├── project_oracle/models/                # Trained model artifacts
│   └── meta_anomaly_v1.pt
└── DISPATCH_PLAN_ORACLE_ROUND{,2,3,6}.md
```

### 5.2 Conventions agents MUST respect

| Concern | Convention |
|---|---|
| Python version | 3.13 (the venv at `backend/.venv` is the canonical interpreter) |
| Type hints | Use `Optional[X]` not `X | None` for compatibility with older importers |
| Logging | `logger = logging.getLogger(__name__)`; structured fields preferred to f-strings |
| Async | All I/O is async (FastAPI, httpx, aiofiles). Use `asyncio.Lock` not `threading.Lock` |
| Time | UTC everywhere. `datetime.now(timezone.utc)`. Never `datetime.utcnow()` (deprecated) |
| Caching | Through `CacheRouter`, never ad-hoc dicts at module scope |
| Test path | `backend/tests/services/<subpath>/test_<file>.py` mirrors `backend/services/<subpath>/<file>.py` |
| Test isolation | Tests that touch shared registries (Prometheus, DuckDB connection pool) MUST snapshot state and assert deltas, not absolute values |
| Commit signature | `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` line included |

### 5.3 Existing public interfaces (do not break)

```python
# Routes (mounted with prefix="/api")
GET  /api/health                            -> {"ok": true, ...}
GET  /api/implied-pdf/{ticker}              -> implied PDF object
GET  /api/regime/{ticker}                   -> regime classification
GET  /api/hedge-impulse/{ticker}            -> hedge-impulse curve
GET  /api/pressure-cloud/{ticker}           -> pressure cloud
GET  /api/charm-integral/{ticker}           -> {"total_charm_to_close": float, "direction": str, "buckets": [...]}
GET  /api/vanna/{ticker}                    -> vanna exposure
GET  /api/advanced/{ticker}                 -> all advanced analytics
GET  /api/data/quote/{ticker}               -> {"price": float, "change": float, ...}
GET  /api/admin/databento/usage             -> {"cached_days": int, "recent": [...], "budget_pct_used": float, ...}

# Service interfaces
CacheRouter.get_chain(ticker: str, expiries: int, max_age_seconds: int, coordinator: FetchCoordinator) -> dict
CacheRouter.degraded_response(reason: str, detail: str) -> dict
FetchCoordinator.fetch(ticker: str, expiries: int, fetcher: Callable) -> dict
PreTradeRiskGate.evaluate(...) -> RiskResult
KillSwitch.trip(reason: str), KillSwitch.is_tripped() -> bool, KillSwitch.reset()
```

---

## §6  Agent Charter (the heart of the document)

Each agent has:

- **Identity** — what they are
- **Mission** — one-sentence outcome
- **Mission class** — (D), (V), or (H) from §4
- **Primary file ownership** — the only agent permitted to write these files
- **Read-only dependencies** — files they read but do not modify
- **Interface contract** — public API they expose
- **Acceptance criterion** — falsifiable, measurable
- **Stop conditions** — when to halt
- **Skills** — Claude Code skills relevant to the work

### Agent 1 — Live Data → UI Integration Lead

| Field | Value |
|---|---|
| Mission | Get Alpha Vantage live data rendering in the React UI behind a feature flag |
| Class | (D) |
| Primary ownership | `backend/services/av_adapter.py` (new), `backend/services/data_source_router.py` (new), `frontend/src/hooks/useDataSource.js` (new), `frontend/src/components/DataSourceBadge.jsx` (new), `backend/routes/admin.py` (extends; adds `/api/admin/data-source`) |
| Read-only | `backend/routes/data_providers.py`, `backend/services/cache_router.py`, `backend/services/numba_greeks.py` |
| Interface | `GET /api/admin/data-source -> {"active": str, "delay_seconds": int, "key_present": bool}`; env `FLOWW_DATA_SOURCE ∈ {schwab, databento, alpha_vantage, auto}` |
| Acceptance | Setting `FLOWW_DATA_SOURCE=alpha_vantage` then `curl /api/heatmap/SPY` returns AV-sourced data; the UI badge reads "AV — 15 min delay"; 0 unhandled exceptions in 100 requests |
| Stop on | Three failed attempts to normalize AV chain shape (escalate to architect) |
| Skills | `data-providers:alpha-vantage`, `swarmclaw:coding-agent`, `frontend:hooks` |

### Agent 2 — Numba JIT Performance

| Field | Value |
|---|---|
| Mission | Bring full Greek family to JIT-compiled vectorized speed; AOT compile for cold start |
| Class | (D) — enables real-time analytics under live load |
| Primary ownership | `backend/services/numba_greeks.py` (extends), `backend/services/numba_greeks_compile.py` (new) |
| Read-only | `backend/advanced_analytics.py` |
| Interface | `bs_delta_vec(S, K, T, sigma, q, r, kind) -> np.ndarray`; same signature pattern for gamma/theta/vega/vomma |
| Acceptance | `calc_charm_integral("SPY", 4)` p99 < 8 ms cold / < 1 ms warm on M1; property-based tests (hypothesis) verify put-call parity, monotone delta, vega ≥ 0 |
| Stop on | Numba compilation failure on three consecutive nightlies |
| Skills | `mlops:numba-jit`, `hermeshub:performance` |

### Agent 3 — DuckDB OLAP Hot Path

| Field | Value |
|---|---|
| Mission | Replace per-request live-fetch with DuckDB-first reads; live fetch becomes the writer |
| Class | (D), (H) — both lower latency and degrade gracefully when AV drops |
| Primary ownership | `backend/services/duckdb_writer.py` (new), `backend/services/chain_repository.py` (new), `backend/services/duckdb_engine.py` (extends with index DDL) |
| Read-only | `backend/services/cache_router.py`, `backend/routes/analytics.py` |
| Interface | `ChainRepository.get_latest(ticker: str, max_age_seconds: int) -> Optional[ChainSnapshot]` |
| Acceptance | Heatmap endpoint p99 < 20 ms during market hours; `data/duckdb/` size bounded ≤ 2 GB by 30-day pruning policy |
| Stop on | Writer queue depth > 10,000 sustained (back-pressure unresolvable) |
| Skills | `data:duckdb`, `data:sql-queries` |

### Agent 4 — Dash/Plotly Heatseeker Visualization

| Field | Value |
|---|---|
| Mission | Algorithmic king-node + air-pocket detection with node-lifecycle state on a Dash heatmap |
| Class | (D) |
| Primary ownership | `backend/services/structural_levels.py` (new), `backend/dash_app/heatmap.py` (new), `backend/dash_app/__init__.py` |
| Read-only | `backend/advanced_analytics.py`, `backend/services/numba_greeks.py` |
| Interface | `detect_king_nodes(strikes: np.ndarray, gex: np.ndarray, prominence_sigma: float = 2.0) -> List[KingNode]`; `detect_air_pockets(strikes, gex, eps_ratio: float = 0.05, min_pct_of_spot: float = 0.005) -> List[AirPocket]` |
| Acceptance | `localhost:8050/heatseeker?ticker=SPY` renders heatmap with ≥3 detected king-nodes (magnitude-scaled hlines) and any air-pockets as `add_vrect`; touched levels show ~25 % opacity decay |
| Stop on | Dash app fails to render under uvicorn + dash composition |
| Skills | `design:design-handoff`, `data:create-viz`, `swarmclaw:coding-agent` |

### Agent 5 — Out-of-Sample Backtest & Paper-Trading Harness

| Field | Value |
|---|---|
| Mission | Lock train/test split at 2024-09-30; install promotion gate against documented baselines |
| Class | (V) |
| Primary ownership | `scripts/backtest_oos.py` (new), `backend/services/baselines/buy_hold.py` (new), `backend/services/baselines/simple_mean_reversion.py` (new), `backend/services/paper_trader.py` (new), `scripts/promote_strategy.py` (new) |
| Read-only | `backend/services/retail_flow_score.py`, `backend/services/regime_filter.py`, `backend/services/risk/*` |
| Interface | `python scripts/backtest_oos.py --strategy NAME --train-end 2024-09-30 --test-start 2024-10-01` produces `strategies/results/NAME_<date>.json`; `python scripts/promote_strategy.py --strategy NAME` returns 0 on pass, 1 + reason on fail |
| Acceptance | Promotion gate enforces (a) OOS Sharpe ≥ baseline Sharpe + 0.3, (b) max drawdown < 2 × baseline max DD, (c) ≥30 paper-trading days, (d) no single-trade loss > 2 %, (e) data integrity check passes |
| Stop on | OOS split detected with leakage (test data informs training) |
| Skills | `mlops:backtest`, `mlops:evaluating-l...`, `data:statistical-analysis` |

### Agent 6 — FastAPI Lifespan + Production Hardening

| Field | Value |
|---|---|
| Mission | Eliminate `on_event` deprecation; split readiness/liveness; bound shutdown |
| Class | (H) |
| Primary ownership | `backend/lifespan.py` (new), `backend/server.py` (removes 5 `@app.on_event` blocks; replaces with lifespan call) |
| Read-only | `backend/services/duckdb_engine.py`, `backend/services/observability.py` |
| Interface | `GET /health/live -> 200 if process up`; `GET /health/ready -> 200 only if Mongo + DuckDB + AV reachable` |
| Acceptance | `pytest backend/tests/` shows 0 `DeprecationWarning` from `on_event`; SIGTERM during in-flight request drains within 10 s without 5xx |
| Stop on | Lifespan ordering produces a startup deadlock |
| Skills | `vercel:deployments-cicd`, `software-development:fastapi-lifespan` |

### Agent 7 — Causal Inference Layer

| Field | Value |
|---|---|
| Mission | Move from correlation to causation: Granger + DML for every promoted signal |
| Class | (V) |
| Primary ownership | `backend/services/causal/__init__.py` (new), `backend/services/causal/granger.py` (new), `backend/services/causal/dml.py` (new), `backend/routes/causal.py` (new) |
| Read-only | `backend/services/retail_flow_score.py`, `backend/services/iv_skew_analyzer.py`, all signal modules |
| Interface | `GET /api/causal/report/{signal} -> {"granger_p_min": float, "dml_ate": float, "dml_ci": [lo, hi]}` |
| Acceptance | For obvious noise signal (random), Granger p > 0.5 and DML CI includes 0; for a known causal signal (e.g., upcoming-earnings flag → next-day volatility), p < 0.01 and CI excludes 0 |
| Stop on | Lack of statsmodels / econml in environment (pip-install with care) |
| Skills | `bio-research:scientific-problem-selection`, `mlops:causal-inference` |

### Agent 8 — Chaos Engineering & Failover Drills

| Field | Value |
|---|---|
| Mission | Validate the system survives the specific failure classes that would page a live desk |
| Class | (H) |
| Primary ownership | `backend/tests/chaos/__init__.py` (new), `backend/tests/chaos/scenarios/*.py` (new, four scenarios minimum), `backend/services/auto_recover.py` (new), `.github/workflows/chaos.yml` (new) |
| Read-only | All service modules; chaos tests MUST NOT modify them |
| Interface | `pytest backend/tests/chaos/ -m chaos` runs the full suite; `auto_recover.watch(service_name)` restarts crashed worker tasks |
| Acceptance | All four scenarios (`av_outage.py`, `partial_chain.py`, `clock_skew.py`, `disk_full.py`) pass; mean-time-to-recovery < 60 s; zero spurious BUY/SELL signals fired during simulated AV outage |
| Stop on | Chaos injection cascades into unrelated test failures (isolation breach) |
| Skills | `mlops:chaos-engineering`, `devops:auto-recovery` |

### Agent 9 — Knowledge Graph & Memory Hygiene

| Field | Value |
|---|---|
| Mission | Make the codebase queryable: commits ↔ tests ↔ incidents ↔ kanban-cards |
| Class | (V) — enables future debugging at scale |
| Primary ownership | `backend/services/knowledge_graph.py` (new), `scripts/ask_hermes_graph.py` (new), `scripts/ingest_commits.py` (new), `.git/hooks/post-commit` (new) |
| Read-only | All other modules (graph is observational) |
| Interface | `ask-hermes graph "what introduced test_X failure?"` returns commit SHA + author + linked card; `ask-hermes graph "tests depending on services.risk.gate"` returns the dependent test set |
| Acceptance | Query "tests depending on services.risk.gate" returns ≥17 tests (the size of `test_gate.py`); Round 5 salvage chain renders to `docs/round5_salvage_graph.png` with all four commits + their fixes |
| Stop on | Graph backend (Neo4j or DuckDB-graph) installation friction |
| Skills | `mem0:mem0-integrate`, `data:graph-database`, `bio-research:scientific-problem-selection` |

### Agent 10 — Live-Trading Switch Ceremony

| Field | Value |
|---|---|
| Mission | Build the irreversible-action discipline around the live-trading flip |
| Class | (H) — risk-officer role |
| Primary ownership | `docs/PRE_MORTEM_LIVE_TRADING.md` (new), `scripts/live_switch.py` (new), `backend/services/audit_log.py` (new), `frontend/src/components/KillSwitchButton.jsx` (new), `backend/routes/live.py` (extends with `/api/live/halt`) |
| Read-only | All risk modules; depends on Agent 7's causal sign-off and Agent 8's chaos sign-off |
| Interface | `python scripts/live_switch.py --to live` runs the ceremony; `POST /api/live/halt` triggers immediate position-no-new-orders halt; audit log at `data/audit/live_state.jsonl` is append-only |
| Acceptance | Pre-mortem document enumerates ≥20 failure modes each with (Severity, Likelihood, Detection, Mitigation, Test); dry-run of `live_switch.py` requires (a) typed acknowledgment of pre-mortem hash, (b) 2FA code, (c) max-daily-loss USD ≤ 1 % account equity, (d) ticker whitelist, (e) "READY" typed verbatim; the audit log entry includes git commit hash of the running binary |
| Stop on | Any check in the ceremony bypass-able |
| Skills | `hermeshub:agent-hardening`, `legal:legal-risk-assessment` |

---

### 6.1 File Ownership Matrix (cross-reference)

If two agents need to touch the same file, the matrix below resolves the conflict by **declaring one owner**. Other agents propose changes via PR to the owner.

| File | Primary Owner |
|---|---|
| `backend/server.py` | Agent 6 (lifespan migration only) |
| `backend/routes/analytics.py` | none modifies in Round 6 (frozen baseline) |
| `backend/routes/admin.py` | Agent 1 (adds `/api/admin/data-source`) |
| `backend/routes/live.py` | Agent 10 (adds `/api/live/halt`) |
| `backend/routes/causal.py` | Agent 7 (new) |
| `backend/services/numba_greeks.py` | Agent 2 |
| `backend/services/duckdb_engine.py` | Agent 3 (index DDL only) |
| `backend/services/cache_router.py` | none modifies (frozen baseline) |
| `backend/services/fetch_coordinator.py` | none modifies (frozen baseline) |
| `backend/services/risk/*` | none modifies (Round 5 baseline locked) |
| `backend/lifespan.py` | Agent 6 (new) |
| `backend/services/structural_levels.py` | Agent 4 (new) |
| `backend/services/causal/*` | Agent 7 (new) |
| `backend/services/baselines/*` | Agent 5 (new) |
| `backend/services/paper_trader.py` | Agent 5 (new) |
| `backend/services/auto_recover.py` | Agent 8 (new) |
| `backend/services/knowledge_graph.py` | Agent 9 (new) |
| `backend/services/audit_log.py` | Agent 10 (new) |
| `backend/services/av_adapter.py` | Agent 1 (new) |
| `backend/services/data_source_router.py` | Agent 1 (new) |
| `backend/dash_app/*` | Agent 4 (new) |
| `frontend/src/hooks/useDataSource.js` | Agent 1 (new) |
| `frontend/src/components/DataSourceBadge.jsx` | Agent 1 (new) |
| `frontend/src/components/KillSwitchButton.jsx` | Agent 10 (new) |
| `scripts/backtest_oos.py` | Agent 5 (new) |
| `scripts/promote_strategy.py` | Agent 5 (new) |
| `scripts/live_switch.py` | Agent 10 (new) |
| `scripts/ask_hermes_graph.py` | Agent 9 (new) |
| `scripts/ingest_commits.py` | Agent 9 (new) |
| `docs/PRE_MORTEM_LIVE_TRADING.md` | Agent 10 (new) |
| `docs/ROUND6_COMPLETION_LOG.md` | all agents append |
| `.github/workflows/chaos.yml` | Agent 8 (new) |
| `.git/hooks/post-commit` | Agent 9 (new) |

### 6.2 Dependency DAG

```
                 ┌──────────────────────────────────┐
                 │  Agent 1 (live data → UI)        │
                 └──────┬───────────────────────────┘
                        │ env FLOWW_DATA_SOURCE
                        ▼
   ┌──────────┐  ┌────────────────────────────────┐
   │ Agent 2  │  │  Agent 3 (DuckDB hot path)     │ ◄── Agent 1 writes;
   │ (Numba)  │  └──────┬─────────────────────────┘     Agent 3 indexes
   └────┬─────┘         │
        │               ▼
        │     ┌──────────────────────────────────┐
        └────►│  Agent 4 (Dash + king-nodes)     │
              └──────────────────────────────────┘
              ┌──────────────────────────────────┐
              │  Agent 5 (OOS backtest)          │ ◄── needs paper data
              └──────┬───────────────────────────┘     from Agent 1 path
                     │
                     ▼
              ┌──────────────────────────────────┐
              │  Agent 7 (causal inference)      │ ◄── gates promotion
              └──────┬───────────────────────────┘
                     │
                     ▼
              ┌──────────────────────────────────┐
              │  Agent 10 (live-switch ceremony) │ ◄── final gate
              └──────────────────────────────────┘

   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Agent 6  │  │ Agent 8  │  │ Agent 9  │   (parallelizable)
   │ lifespan │  │ chaos    │  │ kg       │
   └──────────┘  └──────────┘  └──────────┘
```

---

## §7  Standing Operating Protocol (NORMATIVE for every agent prompt)

Every agent prompt generated by Qwen MUST include the following preamble verbatim:

```
You are operating in /Users/nav/Documents/GitHub/floww (canonical clone).
If `pwd` resolves anywhere else, especially /Users/nav/GitHub/floww, STOP immediately
and emit "WRONG_CLONE" — do not commit, do not push.

Before any commit:
  - `git pull --rebase origin main` (resolve conflicts before staging)
  - run the relevant test slice; ALL must pass
  - run `git diff --stat` and confirm only files in your PRIMARY OWNERSHIP changed

Before any push:
  - `git log origin/main..HEAD --oneline` (sanity-check your queue)
  - `git push origin main` (no force)

Standing invariants you MUST NOT violate:
  - I-1 (no synthetic data)
  - I-2 (baseline-first)
  - I-3 (OOS-locked)
  - I-4 (TDD: failing test FIRST)
  - I-6 (single canonical clone)
  - I-7 (no double-prefix routes)
  - I-8 (NaN-aware numeric guards)

Commit body MUST end with:
  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>

Every commit appends one line to docs/ROUND6_COMPLETION_LOG.md:
  - <SHA> | <agent-id> | <acceptance criterion satisfied> | <one-line insight>
```

---

## §8  Verification Standard (per task)

A task is complete when, and only when:

1. **Test-first executed.** A test exists that would have failed before the change and passes after. The test name appears in `docs/ROUND6_COMPLETION_LOG.md`.
2. **Suite regression-free.** `pytest backend/tests/` (or the relevant slice) shows ≥ 1,882 passing and 0 newly-failing tests.
3. **Smoke test recorded.** A `curl` invocation against a running server (or `python -c "..."` for non-route work) produced expected output. Output snippet pasted into the commit body.
4. **Documentation updated.** Any public interface change updates either the relevant docstring or `docs/API.md` if it is a route.
5. **Acceptance criterion ticked.** The agent quotes the §6 acceptance criterion verbatim in the commit body and explains how it is satisfied.

A task that ships without items 1–5 is **rejected** by the architect and rolled back. No exceptions.

---

## §9  Failure Handling

When an agent encounters a blocker:

- **Three-strike rule.** Three consecutive failed attempts at the same sub-task → halt, open a kanban card with reproduction steps in `kanban/cards/AGENT-N-blocker-<timestamp>.md`, ping `kanban/INCIDENTS.md`.
- **Wrong-clone error.** Immediately stop. Do not commit. Do not push. Emit `WRONG_CLONE` to stdout.
- **Test regression.** If your change introduces a regression (any test that passed at HEAD now fails), do not commit. Revert your local changes (`git checkout -- .`), re-read the failure, retry from a clean state.
- **Ownership conflict.** If you find yourself needing to modify a file owned by another agent, do not modify it. Open a kanban card describing the change and continue with parallel work.

---

## §10  Qwen Generation Instructions

Qwen, your task is to expand each of the ten agent charters in §6 into a complete, paste-ready coding-agent prompt. For each agent, produce:

### Section A: Agent prompt header
```
[paste standing preamble from §7]

ROUND-6 IDENTITY: Hermes Agent <N>, <Mission tag from §6>.
CONTEXT: <Synthesize §1 + §3 context relevant to this agent's mission. ~150 words.>
GOAL: <Restate the §6 mission as a single declarative sentence.>
```

### Section B: Task breakdown
For each charter, generate **3–5 numbered tasks** that progressively build the deliverable. Each task MUST include:

```
N. <Task title>
   Files:
     - <primary ownership file 1> (new | extends)
     - <primary ownership file 2> (new | extends)
     - <test file path> (new, ≥ N tests)
   Spec:
     - <bullet 1, specific behavior>
     - <bullet 2, specific behavior>
     - <bullet 3, edge case>
   Verification:
     - <command or curl that proves it works>
     - <expected output snippet>
   Acceptance:
     - <one-line falsifiable criterion>
```

### Section C: Acceptance (copy from §6 verbatim)

### Section D: Stop conditions (copy from §6 verbatim)

### Section E: Skills (copy from §6 verbatim, formatted as bullet list)

### Section F: Inter-agent contract
For each agent, list:
- **Upstream dependencies**: which agents must complete first
- **Downstream consumers**: which agents depend on this agent's deliverable
- **Coordination touchpoints**: kanban cards, completion-log entries, or interface freezes

### Format requirements
- Use markdown
- Use code blocks (```) for paths and commands
- Each agent prompt should be 600–1,000 words
- Total document length: ~7,000–10,000 words
- Section dividers between agents (horizontal rule `---`)

### Things Qwen MUST NOT do
- Invent files or modules not listed in §6 or §5.1
- Suggest agents touch files outside their primary ownership
- Relax any I-1 through I-10 invariant
- Add tasks classified outside (D), (V), (H) per §4
- Skip the standing preamble on any agent prompt

---

## §11  Appendix: Quick Reference Card

| Quantity | Value |
|---|---|
| Canonical repo | `/Users/nav/Documents/GitHub/floww` |
| Wrong-clone path (NEVER) | `/Users/nav/GitHub/floww` |
| Origin | `git@github.com:JattMoosewala5911/floww.git` |
| Python interpreter | `backend/.venv/bin/python` (3.13) |
| Test command | `backend/.venv/bin/python -m pytest backend/tests/` |
| Baseline tests passing | 1,882 |
| Baseline tests failing | 0 |
| Active commit at start of Round 6 | `9594258` |
| AV API key env | `ALPHAVANTAGE_API_KEY` |
| Data source env (Agent 1 introduces) | `FLOWW_DATA_SOURCE ∈ {schwab, databento, alpha_vantage, auto}` |
| Live-switch ceremony script (Agent 10 introduces) | `python scripts/live_switch.py` |
| Round 6 completion log | `docs/ROUND6_COMPLETION_LOG.md` |

---

**End of brief. Qwen: proceed to generate the ten prompts per §10.**
