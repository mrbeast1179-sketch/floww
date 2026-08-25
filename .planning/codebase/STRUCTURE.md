# Codebase Structure

**Analysis Date:** 2026-08-24

## Directory Layout

```
floww/
├── backend/            # FastAPI application (Python 3.12 venv at backend/.venv)
│   ├── routes/         # ~50 APIRouter modules (HTTP layer)
│   ├── services/       # Business logic (~90 modules + ml/, alerts/, causal/ subpackages)
│   ├── domain/         # Pure quant math (no I/O)
│   ├── tests/          # pytest suite (unit, integration, e2e, perf, chaos)
│   ├── models/         # ML artifacts (.joblib, manifests — frozen)
│   ├── config/         # Backend configuration
│   └── server.py       # App entry point (uvicorn :8000)
├── frontend/           # React 18 SPA (CRA + craco), port 3000
│   ├── src/components/ # UI components by page/feature
│   ├── src/hooks/      # Data-fetch hooks (useHeatseeker, useFlowseeker…)
│   ├── src/context/    # AuthContext, ThemeContext
│   ├── src/lib/        # Query helpers (heatmapQuery.js)
│   ├── src/shell/      # Navigation config
│   └── src/index.js    # SPA entry point
├── rust/
│   └── decoder-core/   # PyO3 crate → `decoder_core` Python package
│       └── src/        # greeks.rs, gex.rs, iv.rs, bindings.rs…
├── deploy/             # free/ (docker-compose), cron.d/, systemd/
├── scripts/            # launch_decoder.sh, stop_decoder.sh, utilities
├── tests/              # Top-level integration tests
├── docs/               # Round plans and retrospectives
└── docker-compose.yml  # Root compose (plus .prod.yml / .observability.yml)
```

## Directory Purposes

**backend/routes/**
- Purpose: HTTP route handlers (thin; delegate to services)
- Contains: ~50 router modules (`heatseeker.py`, `flowseeker.py`, `ml_api.py`, `gex_analysis.py`, …)
- Key files: `steal_three.py` (2203 lines), `flowseeker.py` (1813), `ml_api.py` (981), `heatseeker.py` (661)

**backend/services/**
- Purpose: business logic, data clients, GEX/flow/briefing computation
- Contains: `*.py` service modules plus subpackages `ml/`, `ml/backtest/`, `alerts/`, `agent_hub/`, `causal/`, `kanban/`, `memory/`
- Key files: `gex_paper_accurate.py` (2464), `dash_ui.py` (1638, frozen), `realized_volatility.py` (1233), `heatseeker.py` (1044), `duckdb_engine.py` (460), `bs_calculator.py` (148)

**backend/domain/**
- Purpose: pure math kernels, unit-testable without I/O
- Contains: `sabr.py`, `hawkes.py`, `vpin.py`, `almgren_chriss.py`, `kelly_replay.py`, `position_sizing.py`, `greek_scalers.py`

**backend/tests/**
- Purpose: pytest suite (asyncio auto mode); mirrors production layout with subdirectories `routes/`, `services/`, `server/`, `integration/`, `e2e/`, `perf/`, `chaos/`
- Key files: `conftest.py` (freeze waived for R10 P0.1), `test_bs_greeks_canonical.py`

**frontend/src/components/**
- Purpose: React components organized by page/feature
- Contains: heatmap family (`GridHeatmap.jsx`, `DomHeatmap.jsx`, `BarHeatmap.jsx`, `MultiTickerHeatmap.jsx`), panels (`MLPredictionsPanel.jsx`, `MorningBriefing.jsx`, `PortfolioPanel.jsx`, `TrinityVolatility.jsx`), and the `flowseeker/` feature directory (`FlowEngine.js`, `scanLogic.js`, `useAlertStream.js`)
- Tests: co-located `*.test.jsx` siblings

**rust/decoder-core/src/**
- Purpose: Rust numerics compiled via maturin/pyo3 into `decoder_core`
- Contains: `bindings.rs` (745 lines, pyo3 surface), `greeks.rs`, `gex.rs`, `iv.rs`, `probdist.rs`, `vpin.rs`, `term.rs`, `grid.rs`, `curve.rs`, `nodes.rs`, `chain.rs`, `rvol.rs`, `tests.rs`, `lib.rs`

## Key File Locations

**Entry Points:**
- `backend/server.py` — FastAPI app, router registration, startup (uvicorn :8000)
- `frontend/src/index.js` — React root (port 3000)
- `deploy/free/docker-compose.yml` — free-tier deployment compose

**Configuration:**
- `backend/pyproject.toml`, `backend/requirements.txt` — Python deps
- `backend/pytest.ini` — pytest config
- `frontend/package.json`, `frontend/craco.config.js` — React build (frozen)
- `rust/decoder-core/Cargo.toml` — crate manifest
- `Makefile`, `.github/workflows/lint.yml` — tasks and CI

**Core Logic:**
- `backend/services/gex_paper_accurate.py` — paper-accurate GEX conventions
- `backend/services/ml/inference.py` — frozen ML inference gate
- `backend/services/duckdb_engine.py` — DuckDB wrapper
- `backend/bs_greeks.py` — canonical Black-Scholes Greeks

**Testing:**
- `backend/tests/` — backend suite (`cd backend && .venv/bin/python3 -m pytest -q`)
- `frontend/src/**/*.test.{js,jsx}` — jest suite (`cd frontend && npx jest`)

**Documentation:**
- `README.md`, `CLAUDE.md`, `RUNBOOK.md`, `docs/`

## Naming Conventions

**Files:**
- snake_case.py: all Python modules (`duckdb_engine.py`, `bs_greeks.py`)
- PascalCase.jsx/jsx: React components (`GridHeatmap.jsx`, `MorningBriefing.jsx`)
- camelCase.js: frontend helpers/hooks (`useHeatseeker.js`, `heatmapQuery.js`)
- test_* prefix: backend tests (`test_bs_greeks_canonical.py`)
- *.test.js(x) suffix: co-located frontend tests

**Directories:**
- snake_case everywhere in backend/rust
- kebab-case for the rust crate (`decoder-core`) and deploy dirs (`cron.d`, `systemd`, `free`)

**Special Patterns:**
- `index.js` for frontend entry
- Feature subdirectory per page under `frontend/src/components/` (e.g. `flowseeker/`)
- Subpackage-per-area under `backend/services/` (`ml/`, `alerts/`, `causal/`)

## Where to Add New Code

**New Feature:**
- Primary code: service module in `backend/services/{feature}.py`
- Route: `backend/routes/{feature}.py`, registered in `backend/server.py`
- Tests: `backend/tests/test_{feature}.py` (or `backend/tests/services/`)
- Frontend: component in `frontend/src/components/` + hook in `frontend/src/hooks/`

**New Domain Math:**
- Implementation: `backend/domain/{algorithm}.py`; hot path → new module in `rust/decoder-core/src/` exposed via `bindings.rs`
- Tests: `backend/tests/test_{algorithm}.py`

**New Route/Command:**
- Definition: `backend/routes/{name}.py` with an APIRouter
- Registration: `app.include_router(...)` in `backend/server.py`
- Tests: `backend/tests/routes/`

**Utilities:**
- Shared backend helpers: existing service modules or `backend/deps.py`
- Shared frontend helpers: `frontend/src/lib/`, `frontend/src/utils/`

## Special Directories

**backend/models/**
- Purpose: ML artifacts (.joblib, *_manifest.json, *_meta.json)
- Source: produced by retraining (`backend/services/ml/retrain.py`)
- Committed: Yes, but architect-frozen — never hand-edit

**backend/.venv/**
- Purpose: project virtualenv (Python 3.12) including the installed `decoder_core` package
- Source: built from requirements + `rust/decoder-core`
- Committed: No

---

*Structure analysis: 2026-08-24*
*Update when directory structure changes*
