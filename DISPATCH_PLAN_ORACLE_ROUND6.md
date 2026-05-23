# Project Oracle — Round 6 Dispatch Plan

**Date:** 2026-05-23
**Status of baseline:** `6208bed` on `main`. 1882 backend tests pass / 0 fail. Alpha Vantage live data confirmed at `5549e3a` via `routes/data_providers.py`. Cache-first routing (`CacheRouter` + `FetchCoordinator`) wired through analytics endpoints. Risk gate hardened against NaN/boundary bugs.

**Theme:** Move from "infrastructure built" to "live trading viability." Round 5 shipped the pipes; Round 6 makes them carry water in production. Every task either (a) gets live data flowing into a feature the UI consumes, (b) validates a model against held-out data, or (c) hardens a failure mode that would page-out a real desk at 9:30am ET.

**Operating laws (still in force):**
- No synthetic data in validation paths.
- Baseline-first: every new model must beat a documented baseline.
- OOS-locked: train/test split is the wall of separation. No peeking.
- TDD: failing test before implementation.
- Single canonical clone: `/Users/nav/Documents/GitHub/floww`. The Round 5 fiasco (parallel work in `/Users/nav/GitHub/floww`) MUST NOT REPEAT.

**Common preamble for every agent:**
```
You are working in /Users/nav/Documents/GitHub/floww — DO NOT cd into /Users/nav/GitHub/floww (that is a stale checkout that caused Round 5 conflicts).
Before any commit, `git pull --rebase origin main`. Before any push, run the relevant test slice.
Write a failing test BEFORE the implementation. Cite a paper or stdlib doc if you invent a formula.
Standing rule: no /api/X prefix in router handlers when the router is mounted with prefix="/api" — that double-prefixes everything.
```

---

## Agent 1 — Live Alpha Vantage Wiring (Backend → UI)

**Identity:** Hermes Agent 1, live data integration lead.

**Context:** Alpha Vantage routes live at `backend/routes/data_providers.py`. UI does NOT consume them. Old UI components still hit `/api/heatmap/SPY` which reads from the Schwab/databento path. Need to wire the live AV feed into the UI's data layer with a feature flag so we can A/B without breaking existing screens.

**Tasks:**

1. **AV adapter for chain shape compatibility** (`backend/services/av_adapter.py` + tests)
   Convert AV's option chain response → the canonical `{spot, contracts: [{strike, type, expiry, T, oi, gamma, iv, ...}]}` shape the analytics layer expects. Include Greeks from AV if present, else fall back to `services.numba_greeks.bs_*` to fill them.
   Verification: feed a real AV response (capture one to `backend/tests/fixtures/av_chain_spy.json`), assert all canonical keys present, Greeks numeric and non-NaN.

2. **Feature-flagged data source switch** (`backend/services/data_source_router.py`)
   Env `FLOWW_DATA_SOURCE` ∈ {`schwab`, `databento`, `alpha_vantage`, `auto`}. `auto` = AV during market hours if key present, else databento, else schwab. Mode is logged to Prometheus (`floww_data_source_active`).
   Verification: tests cover each branch + the auto fallback chain.

3. **Frontend hook + indicator badge** (`frontend/src/hooks/useDataSource.js` + a small `<DataSourceBadge>`)
   Reads `/api/admin/data-source` (new endpoint, returns active source + delay seconds). Badge shows "AV — 15min delay" or "Schwab — live" so the user always knows what's on screen.
   Verification: Jest tests on the hook with mocked fetch; manual click-through showing the badge updates when the env flips.

**Acceptance:** Setting `FLOWW_DATA_SOURCE=alpha_vantage`, restarting backend, loading the SPY heatmap returns AV-sourced data and the badge says so. No 500s.

**Skills:** `data-providers:alpha-vantage`, `swarmclaw:coding-agent`, `frontend:hooks`

---

## Agent 2 — Numba JIT Greeks (Performance Pillar)

**Identity:** Hermes Agent 2, performance engineer.

**Context:** `services/numba_greeks.py` exists but only `bs_charm` and `bs_vanna` are JITted. The hot path through `calc_charm_integral` iterates Python-side over the full chain. Profile shows ~80ms per SPY call. Project Oracle's Pillar 2 demands C-level speeds.

**Tasks:**

1. **Vectorize the full Greek family under @numba.njit** (`backend/services/numba_greeks.py`)
   Add `bs_delta_vec`, `bs_gamma_vec`, `bs_theta_vec`, `bs_vega_vec`, `bs_vomma_vec` taking ndarray inputs. Match the math in `AmirDehkordi/OptionGreeks` exactly — cite the paper section per function in a docstring.
   Verification: property-based tests via hypothesis: put-call parity, monotone delta wrt spot, gamma symmetric around ATM, vega non-negative.

2. **Migrate calc_charm_integral and calc_pressure_cloud to vectorized path** (`backend/advanced_analytics.py`)
   Replace per-contract Python loops with single ndarray ops. Keep the public function signature unchanged.
   Verification: regression tests against snapshot of current output (within 1e-9 tolerance). Benchmark: `pytest --benchmark` shows >10x speedup.

3. **AOT compilation for cold start** (`backend/services/numba_greeks_compile.py`)
   Use `cc = CC('numba_greeks_aot')` to pre-compile the JIT functions at build time. Wire into the test/build pipeline so prod doesn't pay the warmup cost on first request.

**Acceptance:** `calc_charm_integral("SPY", 4)` runs in <8ms cold, <1ms warm. Property tests green.

**Skills:** `mlops:numba-jit`, `hermeshub:performance`

---

## Agent 3 — DuckDB OLAP Hot Path (Pillar 3)

**Identity:** Hermes Agent 3, data engineer.

**Context:** Currently every analytics endpoint round-trips through `_cache.get_chain → coordinator → live fetch`. DuckDB exists but is barely used as the primary read path. The Oracle directive says: "No Pandas in hot paths. Sub-millisecond analytical queries over local columnar storage."

**Tasks:**

1. **Ticks/chains writers operating at 50-100ms batch cadence** (`backend/services/duckdb_writer.py`)
   Async writer that consumes from an in-process queue and flushes batches every 50ms or 1000 rows, whichever comes first. Use `executemany` not row-by-row.
   Verification: benchmark — 10k ticks/sec sustained throughput on M1 hardware.

2. **OLAP-first read path for `/api/heatmap`, `/api/chain`, `/api/history`** (`backend/services/chain_repository.py`)
   Replace the live-fetch-then-aggregate pattern with a "read from DuckDB, fall back to live only if data older than N seconds" pattern. The live fetch becomes the writer, not the query handler.
   Verification: chain endpoint p99 latency < 20ms in `tests/perf/test_chain_latency.py`.

3. **Time-range index on (timestamp, symbol)** + pruning policy for ticks older than 30d → cold parquet on disk.
   Verification: query plan analysis shows index usage; `du -sh data/duckdb/` stays bounded.

**Acceptance:** Heatmap endpoint serves entirely from DuckDB during market hours, falls back to AV only when cache age > 60s. Latency: p99 < 20ms.

**Skills:** `data:duckdb`, `data:sql-queries`

---

## Agent 4 — Dash/Plotly Heatseeker Replica (Pillar 4)

**Identity:** Hermes Agent 4, viz engineer.

**Context:** UI today is React + a few chart components. Project Oracle directive specifies a Dash/Plotly heatmap layer with **algorithmic King-Node and Air-Pocket detection**. Skylit's visual is the target. Currently we have heatmap data but no automated structural-level annotations.

**Tasks:**

1. **King-Node detector** (`backend/services/structural_levels.py`)
   Local maxima of `|GEX(strike)|` with prominence > 2σ of the GEX distribution. Return `[{strike, magnitude, persisted_intraday_hours}]` sorted by magnitude.

2. **Air-Pocket detector** (same file)
   Contiguous strike ranges where `|GEX(strike)| < ε * max_gex` and `range_pct_of_spot > 0.5%`. Return `[{strike_low, strike_high, pct_of_spot}]`.

3. **Dash heatmap component** (`backend/dash_app/heatmap.py`) overlaid with king-node lines (`hlines` with magnitude-scaled opacity) and air-pocket bands (`add_vrect`). Use the structural_levels API.

4. **Node-lifecycle state machine** (per Project Oracle directive)
   Track how many times spot has touched each king-node. On each touch, decay opacity by ~25% on the heatmap. Store touch counts in DuckDB (`king_node_touches` table) so the state survives restarts.

**Acceptance:** SPY heatmap on the local Dash app at `localhost:8050/heatseeker` shows ≥3 detected king-nodes with correctly-positioned hlines + faded opacity for previously-tested levels.

**Skills:** `design:design-handoff`, `data:create-viz`, `swarmclaw:coding-agent`

---

## Agent 5 — Paper-Trading Validation & OOS Backtest

**Identity:** Hermes Agent 5, quant validator.

**Context:** `RetailFlowSignal` strategy exists with mocked backtest results from Round 5. Before any live trading switch flip, we need **real OOS validation**: train on 2024-Q1..Q3, test on Q4, never peek. The Master Plan says baseline-first; the baseline is buy-and-hold SPY.

**Tasks:**

1. **OOS-locked backtest harness** (`scripts/backtest_oos.py`)
   Hard split at `2024-09-30`. Anything after is sealed; the script refuses to run if the train set's max date ≥ test set's min date. Walks one bar at a time, no look-ahead. Logs every signal + every fill.

2. **Baseline calibration** (`backend/services/baselines/buy_hold.py` + `backend/services/baselines/simple_mean_reversion.py`)
   Implement two baselines. Any new strategy must beat both on Sharpe AND on max drawdown to be considered viable.

3. **Paper-trading runner** (`backend/services/paper_trader.py`)
   Connects to live data via Agent 1's source router, runs the strategy in dry-run mode, writes fills to MongoDB `paper_fills` collection. State survives restarts (resume from last fill).

4. **Promotion gate** (`scripts/promote_strategy.py`)
   Checklist: OOS Sharpe > baseline Sharpe by ≥0.3, max DD < 2× baseline DD, ≥30 paper-trading days, no >2% single-trade loss. Refuses to promote without all five.

**Acceptance:** `python scripts/promote_strategy.py --strategy RetailFlowSignal` either passes (writes `strategies/promotion_log/RetailFlowSignal_<date>.md`) or fails with the specific gate that blocked.

**Skills:** `mlops:backtest`, `mlops:evaluating-l...`, `data:statistical-analysis`

---

## Agent 6 — FastAPI Lifespan Migration + Production Hardening

**Identity:** Hermes Agent 6, platform engineer.

**Context:** `backend/server.py` has 5 `@app.on_event("startup")` and `@app.on_event("shutdown")` handlers. FastAPI emits DeprecationWarnings on each one. The server is 2864 lines; the boot path is scattered. Hard to reason about startup ordering bugs.

**Tasks:**

1. **Lifespan context manager** (`backend/lifespan.py`)
   Single `@asynccontextmanager async def lifespan(app)` that runs all startup + yields + all shutdown in deterministic order: DuckDB → Mongo → scheduler → metrics → routers. Document the dependency DAG in the docstring.

2. **Delete all `@app.on_event` handlers** in server.py. Replace with calls inside `lifespan`. Zero behavior change.
   Verification: existing tests pass; DeprecationWarnings drop to 0 in CI output.

3. **Graceful-shutdown timeout** — 10s max for in-flight requests before SIGKILL. Implement via uvicorn `--timeout-graceful-shutdown 10` in `Procfile`/docker-compose, plus internal task tracking so we don't drop fills mid-write.

4. **Healthcheck split** — `/health/live` (process up) vs `/health/ready` (DuckDB + Mongo + AV reachable). K8s/ECS-friendly.

**Acceptance:** No DeprecationWarnings on startup. `/health/ready` returns 503 if AV unreachable but `/health/live` stays 200.

**Skills:** `vercel:deployments-cicd`, `software-development:fastapi-lifespan`

---

## Agent 7 — Causal Inference on Signals (Pearl + Granger)

**Identity:** Hermes Agent 7, causality lead.

**Context:** We generate signals (RetailFlowSignal, IV Skew, CPR, etc.) and observe price changes. **Correlation is not causation.** Before a strategy can be trusted in live, we need evidence the signal actually CAUSES the price reaction rather than co-moving with a confounder.

**Tasks:**

1. **Granger causality test runner** (`backend/services/causal/granger.py`)
   Wraps statsmodels `grangercausalitytests`. Inputs: signal series, price series, lag set. Output: per-lag F-stat + p-value + conclusion. Bonferroni-corrected across lags.

2. **Double Machine Learning (DML) for treatment effect** (`backend/services/causal/dml.py`)
   Uses `econml.DML` to estimate ATE of signal-fires on next-bar return, controlling for VIX level + spot momentum + time-of-day. Cite Chernozhukov 2018.

3. **Causality report dashboard** (`backend/routes/causal.py` + Dash panel)
   For each shipped signal, surface: Granger F/p, DML ATE + 95% CI, whether the CI excludes zero. Refresh weekly.

4. **Promotion-gate integration** with Agent 5: a strategy can't promote if DML CI for its key signal includes zero.

**Acceptance:** `/api/causal/report/RetailFlowSignal` returns Granger + DML results with p-values and CI. Numbers are sane (e.g., obvious noise signal returns p > 0.5; obvious cause returns p < 0.01).

**Skills:** `bio-research:scientific-problem-selection`, `mlops:causal-inference`

---

## Agent 8 — Chaos Engineering & Failover Drills

**Identity:** Hermes Agent 8, reliability engineer.

**Context:** We have rate limits, stale-data alerts, kill switches in code — but they've never been **tested under realistic failure**. A real outage at 09:31 ET would burn credits or, worse, fire spurious signals on cached data while the model is "asleep."

**Tasks:**

1. **Toxiproxy-style chaos toolkit** (`backend/tests/chaos/`)
   Wrappers that simulate: AV 429 storm, AV timeout, Mongo disconnect, DuckDB file lock, network partition (block egress), clock skew (jump system time forward).

2. **Failover drill scenarios** (`backend/tests/chaos/scenarios/`)
   - `av_outage.py`: AV down 5min → system serves stale + flips `data_source_active=stale_av`
   - `partial_chain.py`: AV returns half the strikes → analytics still produce numeric output (no NaN propagation)
   - `clock_skew.py`: system clock jumps +1h → DuckDB queries don't mis-window
   - `disk_full.py`: writer queue backs up → no silent data loss; alert fires

3. **Auto-recovery** (`backend/services/auto_recover.py`)
   Watchdog: if a critical service (writer, scheduler) hasn't heartbeated in 60s, restart it. Bounded retries (3 attempts) with exponential backoff.

4. **Chaos test in CI** (`.github/workflows/chaos.yml`) — runs nightly, posts pass/fail to kanban.

**Acceptance:** All four scenarios green in CI. The system survives a 30-minute AV outage without producing a single spurious signal.

**Skills:** `mlops:chaos-engineering`, `devops:auto-recovery`

---

## Agent 9 — Knowledge Graph & Memory Hygiene

**Identity:** Hermes Agent 9, memory architect.

**Context:** Round 5 left memory in good shape (`reference_memory_system.md`) but the Round-5 salvage session exposed a gap: there's no graph linking COMMITS ↔ INCIDENTS ↔ KANBAN_CARDS ↔ TESTS. When something breaks, you can't trace "what commit introduced this test failure?" without manual `git bisect`.

**Tasks:**

1. **Neo4j or DuckDB-graph backend** (`backend/services/knowledge_graph.py`)
   Node types: Commit, IncidentReport, KanbanCard, TestCase, ServiceModule, Signal, Strategy.
   Edge types: `INTRODUCED_BY`, `BLOCKED_BY`, `TESTED_BY`, `DEPENDS_ON`, `AUTHORED_BY`.
   Auto-ingest: every commit triggers a post-commit hook that extracts touched files + linked card IDs and adds edges.

2. **`ask-hermes graph` CLI** (`scripts/ask_hermes_graph.py`)
   Usage: `ask-hermes graph "what introduced test_charm_integral_spy failure?"`. Walks the graph: failed test → tested module → most-recent commit touching it → linked card → author.

3. **Round 5 backfill** — Run the ingester over all commits from `09b64f3` to `HEAD`. Document the salvage chain visually (graph viz dumped to `docs/round5_salvage_graph.png`).

4. **Cross-repo edges** — Link Hermes commits to upstream papers (arxiv IDs in commit bodies). When a paper cites another, follow the edge. Useful for "what's the lineage of the VPIN logic we use?"

**Acceptance:** `ask-hermes graph "show all tests that depend on services.risk.gate"` returns the correct set (17 tests in `test_gate.py`).

**Skills:** `mem0:mem0-integrate`, `data:graph-database`, `bio-research:scientific-problem-selection`

---

## Agent 10 — Pre-Mortem & Live-Trading Switch Discipline

**Identity:** Hermes Agent 10, risk officer.

**Context:** The Round 3 plan mentioned a "live-trading switch with 2FA-verified manual confirmation." It exists in code but has never been exercised end-to-end. Before we ever flip it, we need a pre-mortem: enumerate every way the system could lose money or fire a bad order, with a documented mitigation.

**Tasks:**

1. **Pre-mortem document** (`docs/PRE_MORTEM_LIVE_TRADING.md`)
   Brainstorm 20+ failure modes (data delay misinterpretation, signal during halt, fat-finger size, broker rejection, position size cap bypass via NaN, etc.). For each: Severity, Likelihood, Detection, Mitigation, Test. The pre-mortem skill applies.

2. **Live-switch ceremony** (`scripts/live_switch.py`)
   CLI prompts for: (a) typed acknowledgment of pre-mortem version hash, (b) 2FA code from authenticator app, (c) max-daily-loss USD limit (must be ≤ 1% of account equity per the master plan), (d) ticker whitelist, (e) "READY" typed verbatim. Refuses to proceed if any check fails.

3. **Audit log** — every state transition (paper→live, live→paper, kill-switch trip) writes to immutable append-only log (`data/audit/live_state.jsonl`). Includes git commit hash of the running binary.

4. **Kill-switch UI button** — single-button frontend control that calls `POST /api/live/halt`. Halts new positions instantly, lets existing ones close gracefully. The button must be visible at all times when in live mode.

**Acceptance:** Dry-run of `live_switch.py` produces a complete audit-log entry. Pre-mortem doc reviewed by Agent 7 (causality) and Agent 8 (chaos) — both must sign off in PR review.

**Skills:** `hermeshub:agent-hardening`, `legal:legal-risk-assessment` (for the pre-mortem rigor)

---

## Inter-Agent Dependency Graph

```
Agent 1 (AV→UI)  ─────┐
Agent 2 (Numba)  ─────┼──→ Agent 3 (DuckDB) ──→ Agent 4 (Heatseeker UI)
Agent 5 (Backtest) ←──┤                          │
Agent 6 (Lifespan) ───┘                          ▼
                                          Agent 7 (Causality)
                                                 │
Agent 8 (Chaos)  ←─────────── needs all of 1-7 ──┤
Agent 9 (KG)    ←─────────── observes all ──────┤
Agent 10 (Risk) ←─────────── gates promotion ───┘
```

**Critical path** to live-trading-viability: 1 → 5 → 7 → 10. Agents 2, 3, 4, 6, 8, 9 are parallelizable enablers.

## Stop Conditions (Round 6)

Each agent halts when:
- Their acceptance criterion is met AND tests are green AND committed AND pushed, OR
- They've made 3 consecutive failed attempts at the same sub-task (open a kanban card for human triage), OR
- They detect they're working in `/Users/nav/GitHub/floww` instead of `/Users/nav/Documents/GitHub/floww`.

## Verification Standard

No agent considers a task complete without:
1. A test that would have failed before the change.
2. The same test passing after the change.
3. Full `pytest backend/tests/` green.
4. Manual smoke test via `curl` against the running server (where applicable).
5. A line in `docs/ROUND6_COMPLETION_LOG.md` linking commit SHA + test name + brief insight.
