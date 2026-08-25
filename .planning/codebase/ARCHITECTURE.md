# Architecture

**Analysis Date:** 2026-08-24

## Pattern Overview

**Overall:** Modular monolith — a single FastAPI application with route modules, a services layer, a pure domain-math layer, and Rust acceleration via PyO3.

**Key Characteristics:**
- One FastAPI app (`backend/server.py`) mounting ~50 routers under `/api/*`
- Clear layering: routes → services → domain (pure math)
- Hot-path quant math offloaded to a compiled Rust crate (`rust/decoder-core`, pyo3 bindings installed as the `decoder_core` package in `backend/.venv`)
- Dual persistence: MongoDB (Motor async) for documents/state, DuckDB for tick/ingestion analytics
- React 18 SPA (CRA + craco) on :3000 is the real UI; an embedded Dash app (`backend/services/dash_ui.py`) lives at `/dashboard/` as a tab inside it
- ML layer: 5 production gbm models per ticker (SPY/QQQ/DIA/IWM/TLT) with walk-forward CV, inference gated behind `backend/services/ml/inference.py` (architect-frozen)

## Layers

**Routes layer (`backend/routes/`):**
- Purpose: HTTP handlers, request validation, response shaping; thin wrappers over services
- Contains: ~50 APIRouter modules (`heatseeker.py`, `flowseeker.py`, `gex_analysis.py`, `ml_api.py`, `briefing.py`, …)
- Depends on: services layer, `backend/deps.py` for shared dependencies
- Used by: mounted by `backend/server.py` via `app.include_router(...)` (mostly under `/api` prefix)

**Services layer (`backend/services/`):**
- Purpose: business logic and orchestration — GEX aggregation, heatseeker snapshots, flow alerts, ingestion, ML pipeline, broker/data clients
- Contains: ~90 modules plus subpackages `ml/`, `ml/backtest/`, `alerts/`, `agent_hub/`, `causal/`, `kanban/`, `memory/`
- Depends on: domain layer, DuckDB/Mongo engines, external APIs (Schwab, Alpaca, Databento, cvserver)
- Used by: route handlers and cron runners

**Domain layer (`backend/domain/`):**
- Purpose: pure quant math with no I/O — SABR, Hawkes processes, VPIN, Almgren-Chriss, Kelly sizing, greek scalers
- Contains: `sabr.py`, `hawkes.py`, `vpin.py`, `almgren_chriss.py`, `kelly_replay.py`, `position_sizing.py`, `greek_scalers.py`
- Depends on: nothing but numpy/scipy (testable in isolation)
- Used by: services layer

**Rust acceleration (`rust/decoder-core/src/`):**
- Purpose: performance-critical Greeks/GEX/IV computation compiled via PyO3/maturin into the `decoder_core` Python package
- Contains: `greeks.rs`, `gex.rs`, `iv.rs`, `probdist.rs`, `vpin.rs`, `term.rs`, `grid.rs`, `curve.rs`, `bindings.rs` (pyo3 surface), `lib.rs`
- Depends on: Rust-only numerics
- Used by: `backend/services/gex_core.py`, `backend/services/gex_paper_accurate.py`, `backend/services/gex_term_structure.py`, `backend/routes/steal_three.py`

## Data Flow

**Market-data ingestion → heatmap/briefing flow:**

1. Sources: cvserver client (`backend/services/cvserver_client.py`) and yfinance-style fallbacks (`backend/services/data_fallback.py`, `backend/data_providers.py`) pull spot + option chains; Databento/Schwab stream ticks
2. Ingestion pipeline normalizes chains and writes to DuckDB (`backend/services/duckdb_engine.py`, `backend/services/ingestion_pipeline.py`) and Mongo (Motor, `from server import db`)
3. Services compute derived metrics: GEX (paper-accurate conventions per Ni–Pearson and Barbon–Buraschi in `backend/services/gex_paper_accurate.py`, 2464 lines), heatseeker flip zones (`backend/services/heatseeker.py`), flow scores, morning briefing (`backend/services/morning_briefing.py`)
4. Route modules expose results as JSON endpoints (e.g. `GET /api/heatseeker/flip-zones?ticker=SPY` via `backend/routes/heatseeker.py`)
5. React SPA consumes them through hooks (`frontend/src/hooks/useHeatseeker.js`, `useFlowseeker.js`, `useMarketData.js`) and renders heatmap components (`frontend/src/components/GridHeatmap.jsx`, `DomHeatmap.jsx`)

**State Management:**
- Stateless request handling; per-ticker caches in `backend/cache.py` / `backend/services/cache_router.py`
- Persistent state in Mongo (documents, journals, outcomes) and DuckDB (ticks, chain history); model artifacts under `backend/models/`

## Key Abstractions

**DuckDBEngine wrapper (`backend/services/duckdb_engine.py`, 460 lines):**
- Single access point for tick/chain storage and analytical queries over DuckDB

**BSCalculator / decoder-core Greeks:**
- Python reference: `backend/bs_greeks.py` (332 lines) and `backend/services/bs_calculator.py` (148 lines) — Black-Scholes pricing/Greeks with characterization tests (`backend/tests/test_bs_greeks_canonical.py`, `_hull_table.py`, `_fd_oracle.py`)
- Rust fast path: `rust/decoder-core/src/greeks.rs` exposed through `bindings.rs` as the installed `decoder_core` package

**Paper-accurate GEX metrics (`backend/services/gex_paper_accurate.py`, 2464 lines):**
- Implements Ni–Pearson and Barbon–Buraschi gamma-exposure conventions; supported by `gex_aggregator.py`, `gex_dual.py`, `gex_term_structure.py`, `gex_vex_calculator.py`

**ML inference gate (`backend/services/ml/inference.py`, frozen):**
- Sole entry point for 5-per-ticker gbm predictions; registry/retrain/health in `registry.py`, `retrain.py`, `health_monitor.py`

## Entry Points

- **Backend:** `backend/server.py` → `uvicorn server:app --port 8000` (~50 routers registered near line 2280+)
- **Frontend:** `frontend/src/index.js` → CRA dev server on :3000 (`npm start` via craco, `frontend/craco.config.js`)
- **Deployment:** `deploy/free/docker-compose.yml` (free-tier stack); repo-root `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.observability.yml`; Dockerfiles at `Dockerfile.backend` / `Dockerfile.frontend`; cron/systemd units in `deploy/cron.d/` and `deploy/systemd/`
- **Local launcher:** `scripts/launch_decoder.sh` (alias `decoder`)

---

*Architecture analysis: 2026-08-24*
