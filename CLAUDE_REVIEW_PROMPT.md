# Confluence Decoder — Architecture, ML, & Continuous Development Plan

**Project owner:** Nav (Navdeep Kumar) — $5K account, SPY/QQQ day-trading on the Baby Billy DVT 4.5 framework, goal: profitable daily after Jefferson MRI graduation Aug 13, 2026.
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Executing agent:** Hermes (Claude Code), session-by-session.
**Status of this document:** the single source-of-truth for forward development. All older plan files (`PLAN.md`, `MASTER_PLAN.md`, `IMPLEMENTATION_PLAN.md`, `CLAUDE_REVIEW_ROUND2.md`, `SKYLIT_FEATURES.md`, `MORNING_BRIEFING.md`) are inputs to this plan and remain on disk for reference, but are no longer authoritative.

This plan is written to be executed by Hermes one phase at a time, with Nav's IDE stack — **PyCharm, WebStorm, DataGrip, IntelliJ** — used at every step, not just for sign-off.

---

## 0. Evidence: where the system is today (verified, not assumed)

Before planning forward, the facts on the ground (each line of this section references a file or command output, not memory):

### Backend, what's actually built

- **Institutional-grade analytics already present.** `backend/advanced_analytics.py` implements Breeden-Litzenberger implied PDF, hedge impulse curve (gamma+vanna), pressure cloud, charm integral, market regime detection. `backend/vol_analytics.py` implements IV surface (smile + term structure), 25-delta risk-reversal, butterfly, skew slope, Close / Parkinson / Garman-Klass realized vol, IV rank/percentile. `backend/bs_greeks.py` has Black-Scholes gamma, vanna, vega, charm, call price.
- **Provider integrations.** `data_providers.py` (Finnhub, Alpha Vantage, Polygon, yfinance), `flashalpha_client.py` (81 endpoints — exposure/flow/earnings/screener/historical/pricing/max-pain), `databento_provider.py`, `alpaca_client.py` (paper trading), `schwab.py` (OAuth scaffold).
- **Alert engine.** `backend/alert_engine.py` defines 7 alert types via dataclasses: `GAMMA_FLIP`, `WALL_BREACH`, `GAMMA_SQUEEZE`, `MOMENTUM_EXTREME`, `GEX_MAGNITUDE_SHIFT`, `PIN_RISK`, plus volume-spike. Compares snapshots over time.
- **ML, toy-level.** `ml_training.py` and `ml_price_prediction.py` extract features from a single GEX snapshot (`spot`, `total_gex`, `net_gex`, `king_strike`, `king_gex`, `top_floor/ceiling`, regime flags, simple GEX distribution stats) and train a sklearn model with no walk-forward CV, no calibration, no model registry, no SHAP, no trading-metric evaluation. **This is the largest forward-engineering opportunity in the project.**
- **Caching.** `backend/cache.py` provides a Redis async cache with graceful fallback when Redis is absent. Already has TTL conventions (GEX 5min, chain 1min, spot 10s, alerts 30s).
- **Cron pipeline.** `cron_config.py` defines four jobs: 5-min data collection during market hours (SPY/QQQ/IWM/DIA), 8 AM ET morning briefing email, 6 PM ET model retrain, hourly health check.
- **WebSocket streaming.** `@app.websocket("/ws/gex/{ticker}")` exists. Reconnection with exponential backoff added in commit `dca7dc0`.
- **Database.** MongoDB collections in use: `Historical`, `Live`, `databento_oi`, `live_policy`, `live_sessions`, `portfolios`, `snapshots`, `command`. Indexes created in code: **only two** — `snapshots(ticker, ts desc)` in `server.py:3299` and `databento_oi(parent, day)` unique in `databento_provider.py:146`. **Six collections are unindexed.** This is a performance time-bomb.

### Backend, what's brittle

- `backend/server.py` is **3,291 lines** with **74 route handlers** despite `backend/routes/` already having six router modules. Modularization stalled.
- `backend/paper_trading.py:21` has a hard-coded `DEFAULT_STRATEGY = "iron_condible"` — almost certainly a typo for `"iron_condor"`. **Live bug, in trading code.**
- Rate limiter (`data_providers.RateLimiter`) is in-process, asyncio-lock-based. Survives single-worker uvicorn; dies under multi-worker or horizontal scale.
- CI runs only `ruff check`. `mypy`, `bandit`, `pip-audit`, `pytest --cov`, frontend lint, `npm audit` are all dormant despite being listed in `requirements.txt`.

### Frontend, what's there

- React 19, axios 1.8, recharts 3.6. **No** TanStack Query / SWR (server-state library), **no** Zustand / Redux / Jotai (client-state library). Everything is `useState` + raw axios.
- `frontend/src/App.js` — **730 lines**, the root component is doing too many jobs.
- `frontend/src/components/` — 27 components.
- `frontend/src/hooks/` — three hooks (`use-toast.js`, `useDebounce.js`, `useWebSocketGex.jsx`).
- **Zero test files in `frontend/src/`.** Coverage = 0%.

### Feature roadmap signals (from prior plans, distilled)

From `IMPLEMENTATION_PLAN.md`, the Skylit / GitHub-research feature gaps that match Nav's trading model:

- VEX (vanna exposure) histogram — separate from GEX
- DEX (delta exposure) histogram
- Flip-zone indicator on the heatmap
- Four gamma/vanna states with trading prescriptions
- Vega Total tracking
- Gauge chart for snapshot
- Scenario matrix (price × time → expected moves)
- Tap probability bands (80 / 66 / 33 / 10)
- Stacked-node detection, tug-of-war zones
- Real-vs-hedge node distinction
- Replay mode

These are the high-leverage analytical additions, and they slot into Phase B below.

---

## 1. Target architecture

The system, drawn as bounded contexts. Forward work conforms to this map.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                FRONTEND (React)                              │
│ ┌────────────────┐ ┌──────────────┐ ┌───────────────┐ ┌─────────────────┐    │
│ │ Heatmap / GEX  │ │ Flow / Alerts│ │ Portfolio / P&L│ │ ML Insights    │    │
│ └──────┬─────────┘ └──────┬───────┘ └──────┬────────┘ └────────┬───────┘    │
│        │ TanStack Query (server state) + Zustand (UI state)                  │
│        │ WebSocket: live GEX, live flow, live alerts                          │
└────────┼─────────────────────────────────────────────────────────────────────┘
         │ REST + WS
┌────────▼─────────────────────────────────────────────────────────────────────┐
│                    FastAPI app (composition root only)                       │
│                            backend/server.py                                 │
│ ┌─────────────────────────────────────────────────────────────────────────┐  │
│ │  Routers (one module per context, under backend/routes/)                │  │
│ │  market_data │ analytics │ alerts │ ml │ trading │ portfolio │ admin    │  │
│ └────┬─────────┬─────────┬──────┬────────┬─────────┬────────┬─────────────┘  │
│      │         │         │      │        │         │        │                │
│ ┌────▼───┐ ┌───▼───┐ ┌───▼───┐ ┌▼──┐ ┌──▼───┐ ┌───▼────┐ ┌─▼──────────┐     │
│ │DataLake│ │ Quant │ │ Alert │ │ML │ │Trading│ │Portfolio│ │ Obs        │     │
│ │services│ │ engine│ │engine │ │svc│ │engine │ │ engine  │ │(logs/metr) │     │
│ └────┬───┘ └───┬───┘ └───┬───┘ └─┬─┘ └───┬───┘ └────┬────┘ └────────────┘     │
│      │         │         │       │       │          │                          │
│      ▼         ▼         ▼       ▼       ▼          ▼                          │
│ ┌────────────────────────────────────────────────────────────────────────┐    │
│ │ Persistence: MongoDB (snapshots, portfolios, alerts, predictions) +    │    │
│ │              Redis (hot cache) + filesystem (model registry, features) │    │
│ └────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘

  External: Finnhub │ Alpha Vantage │ Polygon │ FlashAlpha │ Databento │ Alpaca │ Schwab
            (each behind a provider port with circuit-breaker / fallback)
```

### Quality attributes the architecture must meet

| Attribute       | Target                                                                        | Why                                                |
|-----------------|-------------------------------------------------------------------------------|----------------------------------------------------|
| Correctness     | Greeks/GEX agree with canonical references to 1e-6 relative error             | Real money sits behind these numbers               |
| Determinism     | Same input → same output for analytics & ML inference                         | Auditable trades, reproducible research            |
| Idempotency     | Order placement safe under retry / crash mid-flight                           | No accidental double-fills                         |
| Latency         | GEX dashboard p95 < 1.5 s during market hours; alert delivery < 30 s          | Day-trading is time-sensitive                      |
| Observability   | Every error has a request ID; every model has a run ID; every order has IDs   | When things break you can find why                 |
| Reproducibility | `pip install -r requirements.txt && npm ci` produces identical builds         | CI green ≠ "works on my machine" green             |
| Testability     | Backend ≥ 80% line coverage; trading code ≥ 95%; ML pipeline fully unit-tested| Refactor without fear                              |
| Reversibility   | Every release rolls back via `git revert` and a Mongo migration script        | Failed deploys don't burn a trading day            |

---

## 2. Operating principles for Hermes

1. **Architecture is a contract.** New code conforms to the bounded contexts in §1. A handler that needs trading and ML logic lives in `routes/`, calls into `services/trading/` and `services/ml/`, and contains no business logic of its own.
2. **Tests live with code.** Every new module ships with a test file. Every bug fix lands as a failing test first.
3. **Math gets canonical vectors.** Any new numerical function (Greek, GEX variant, IV-surface fit, ML feature) has a unit test asserting agreement with a published reference (Hull, py_vollib, QuantLib) to a documented tolerance.
4. **Trading code is special.** Any path that places, modifies, or queries orders gets idempotency tests, replay tests, and pre-trade risk-gate tests.
5. **No half-finished refactors.** If `server.py` is being decomposed and the work won't fit one PR, the PR moves one router cleanly and the rest stay where they are. No "in-progress" mixed states.
6. **No new plan documents.** Tasks live in `BACKLOG.md`; architecture decisions live in `docs/adr/NNNN-title.md`; phase logs live in `REVIEW_LOG.md`. Stop spawning fresh `*_PLAN.md` files.
7. **IDE used as a code-quality instrument.** Each phase below names the JetBrains tool action that anchors the work. The IDE is not optional polish — it is part of the workflow.
8. **Evidence in PRs.** Every PR description shows: the verification commands run, the output, screenshots of any UI change, and the relevant inspection / profiler / coverage screenshot from the IDE.

---

## 3. Foundation — JetBrains workspace (one-time setup; used in every phase)

This precedes Phase A. Hermes asks Nav to do these once; Hermes verifies in subsequent sessions by reading the committed config under `.idea/` (selectively — see `.gitignore` notes below).

### 3.1 IntelliJ IDEA Ultimate (umbrella project)

- Open the repo as a multi-module project: backend (Python SDK), frontend (Node), docker (Docker plugin), `.github/workflows/` (YAML), Pine Script files if any.
- Enable plugins: **Python**, **JavaScript and TypeScript**, **React**, **Database Tools and SQL** (DataGrip), **Docker**, **HTTP Client**, **Markdown**, **.env files support**, **Pydantic**, **Mypy**.
- Commit a curated subset of `.idea/`: `runConfigurations/`, `codeStyles/`, `inspectionProfiles/`. Add the rest to `.gitignore`. This way new clones get the run configs, code style, and inspection profile for free.

### 3.2 PyCharm — backend run configurations and inspections

Create and commit under `.idea/runConfigurations/`:

| Name                     | Module / Command                                                                                                            | Purpose                              |
|--------------------------|-----------------------------------------------------------------------------------------------------------------------------|--------------------------------------|
| `backend-dev`            | `uvicorn server:app --reload --host 0.0.0.0 --port 8000` (cwd `backend/`)                                                   | Local dev server                     |
| `backend-prod-simulated` | `uvicorn server:app --workers 4 --port 8000`                                                                                | Multi-worker shake-out               |
| `pytest-all`             | `pytest -ra` (cwd `backend/`)                                                                                               | Full suite                           |
| `pytest-fast`            | `pytest -ra -m "not slow"`                                                                                                  | Pre-commit gate                      |
| `pytest-coverage`        | `pytest --cov=. --cov-report=html --cov-report=term-missing`                                                                | Coverage gutter source               |
| `cron-once`              | `python -c "import asyncio,cron_config; asyncio.run(cron_config.collect_data_job())"`                                       | Manual cron trigger                  |
| `ml-train-spy`           | `python -c "import asyncio; from ml_price_prediction import train_price_direction_model as t; print(asyncio.run(t('SPY')))"`| Train end-to-end                     |
| `mypy-strict`            | `mypy . --strict --ignore-missing-imports`                                                                                  | Type-check gate                      |

Inspection profile (`.idea/inspectionProfiles/Project_Default.xml`): enable PEP-8, Pydantic, Mypy as errors; enable security inspections; ratchet "Method too long" warning to **error** at 80 lines so server.py doesn't grow back.

Coverage integration: PyCharm reads `backend/.coverage` after `pytest-coverage` and shows gutter highlighting per line. **Use it before claiming a module is tested.**

Database tool: connect to (a) local Mongo via docker-compose, (b) Atlas (read-only credentials). Save under "Data Sources." Common queries committed to `qc/queries/*.mongo.json` and run from the IDE.

### 3.3 WebStorm — frontend run configurations and inspections

| Name              | Command                                              | Purpose                          |
|-------------------|------------------------------------------------------|----------------------------------|
| `frontend-dev`    | `npm start` (cwd `frontend/`)                        | Dev server with HMR              |
| `frontend-build`  | `npm run build`                                      | Production bundle                |
| `frontend-test`   | `npm test -- --watchAll=false`                       | Jest                             |
| `frontend-lint`   | `npm run lint`                                       | ESLint                           |
| `frontend-e2e`    | `npx playwright test`                                | E2E (added in Phase H)           |

Inspections: enable React hooks rules as **error** (`react-hooks/exhaustive-deps`, `react-hooks/rules-of-hooks`); enable accessibility inspections; enable "Unresolved variables" and "Unused symbol" as warnings escalating to error after Phase H.

Built-in HTTP Client: create `qc/http/backend.http` with named requests for every router. WebStorm executes them inline — replaces manual curl. Useful when stitching together backend and frontend changes.

### 3.4 DataGrip — MongoDB inspection (this is where indexing problems get fixed)

This is the IDE Nav will use the most for Phase A.

- Connect to local Mongo (docker-compose) **and** Atlas (separate session).
- For each collection (`snapshots`, `Historical`, `Live`, `databento_oi`, `live_policy`, `live_sessions`, `portfolios`, `command`):
  - Use **Schema → Diagram** to visualize document shape.
  - Use **Console** to run `db.<col>.getIndexes()` and copy output into `docs/data-model/indexes.md`.
  - Run `db.<col>.find(<a hot query from server.py>).explain('executionStats')` and check `totalDocsExamined / nReturned`. Any ratio worse than 10:1 on a query that runs on the request path is a Phase A finding.
- Save the explain queries as DataGrip "Saved Consoles" so anyone can re-run them.

### 3.5 Pre-commit + CI

Once-only setup (Hermes does this in Phase A):

- `.pre-commit-config.yaml`: `ruff`, `ruff-format`, `mypy` (warning), `bandit -ll`, `prettier`, `eslint`, plus a lightweight test smoke (`pytest -q -k "test_smoke" --maxfail=1`).
- Extend `.github/workflows/ci.yml` to gate every PR on: `ruff check`, `ruff format --check`, `mypy`, `bandit -r backend -ll`, `pip-audit -r backend/requirements.txt`, `pytest --cov=backend --cov-fail-under=60` (ratchets to 80 by Phase D), frontend `npm ci && npm run lint && npm audit --audit-level=high && npm test -- --watchAll=false`.
- Branch protection on `main`: require CI, require linear history, disallow force push.

---

# Phases A — J

Each phase has the same skeleton: **target**, **why now**, **current state**, **work units**, **JetBrains workflow specific to this phase**, **verification commands**, **exit criteria**. Hermes works one phase at a time. PRs reference the phase letter in the title.

---

## Phase A — Data Layer (providers, cache, indexing)

**Target.** Every external read goes through a typed provider port with a circuit breaker, a fallback chain, and a Pydantic response model. Every Mongo query uses an index. Redis is treated as authoritative for hot data with documented TTLs.

**Why now.** Everything downstream — analytics, ML, alerts — runs on this. Stabilize the foundation first.

**Current state.**
- Providers exist (Finnhub, Alpha Vantage, Polygon, yfinance, FlashAlpha, Databento, Alpaca, Schwab) but expose dict returns, not Pydantic.
- `RateLimiter` is in-process; no circuit breaker; fallback chains are ad-hoc inside callers.
- Mongo: **2 indexes total** across 8 collections.
- Redis cache exists; usage is patchy.

**Work units.**

1. **Provider port.** Define `backend/services/providers/base.py` with an abstract `MarketDataProvider` (methods: `get_quote`, `get_chain`, `get_history`, `health`). Each existing client implements the port. Callers depend on the port, never on the concrete client.
2. **Typed responses.** Pydantic models in `backend/services/providers/models.py`: `Quote`, `OptionContract`, `OptionChain`, `Bar`, `TradeTick`. Provider clients parse vendor JSON into these models. Vendor-specific shapes never escape the provider module.
3. **Circuit breaker + retry.** Wrap each provider call in a `tenacity`-driven retry (exponential backoff, max 3 attempts) and a circuit breaker (`pybreaker` or hand-rolled — opens after 5 failures in 60 s, half-opens after 30 s). Metrics counter per state transition.
4. **Fallback chain.** A `MarketDataRouter` that takes a list of providers per data kind and tries them in priority order, recording which one served the response. Returns the response + a provenance tag.
5. **Rate limiter — externalize.** Replace the in-process `RateLimiter` with Redis-backed token buckets (one bucket per `(provider, key_kind)`). Works under multi-worker uvicorn.
6. **Mongo indexes.** Author `backend/services/db/indexes.py` and call it from FastAPI's lifespan startup. At minimum:
   - `snapshots`: `(ticker, ts desc)` (exists), plus `(ticker, regime, ts desc)` for regime queries.
   - `Historical`: `(ticker, day desc)`, `(ticker, expiry, day)`.
   - `Live`: `(ticker, ts desc)`.
   - `databento_oi`: `(parent, day)` unique (exists), plus `(parent, expiry, day)`.
   - `portfolios`: `(user_id, name)` unique.
   - `live_sessions`: `(session_id)` unique, `(user_id, started_at desc)`, TTL on `expires_at`.
   - `live_policy`: `(name)` unique.
   - `command`: `(name, ts desc)` with TTL on old commands.

   Use DataGrip's explain plan to verify each query in `server.py` and `routes/` uses an index after this lands.
7. **Cache audit.** Every call site that touches a provider checks the cache first. Standardize keys: `cache:{kind}:{ticker}:{params_hash}`. TTLs documented in one place (`backend/services/cache/policy.py`).
8. **Provider health endpoint.** `GET /api/admin/providers/health` returns per-provider status: enabled, last success, last failure, circuit-breaker state, recent success rate. Wired into the existing `/health` payload too.

**JetBrains workflow.**
- **DataGrip:** run `explain('executionStats')` on every query in `server.py` referencing `find`/`aggregate`. Document each in `qc/queries/`. Add missing indexes via DataGrip's "Generate New Index" UI; commit the JS snippet.
- **PyCharm:** Refactor → Move to extract provider clients into `services/providers/`. Use Find Usages on `data_providers.RateLimiter` before deleting it — make sure every caller migrated to the Redis-backed limiter.

**Verification.**
```bash
# All providers expose Pydantic models
pytest backend/tests/services/providers/ -v

# Indexes all present (Python one-liner, run from repo root)
python - <<'PY'
import asyncio, os, motor.motor_asyncio
async def main():
    c = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    for col in ["snapshots","Historical","Live","databento_oi","portfolios","live_sessions","live_policy","command"]:
        idx = [i["name"] for i in await db[col].list_indexes().to_list(length=None)]
        print(f"{col}: {idx}")
asyncio.run(main())
PY
# Expect every collection to have ≥ 1 purpose-built index beyond _id_.
```

**Exit criteria.**
- Every external call routes through `MarketDataRouter`.
- All eight collections have purpose-built indexes; no hot query does a full collection scan in `explain` output.
- Provider health endpoint returns rich status; frontend has a small "providers" indicator.
- `RateLimiter` in-process class deleted; replaced by Redis token bucket.

---

## Phase B — Quantitative analytics extension (VEX, DEX, scenario matrix, regime states, replay)

**Target.** Match or exceed Skylit's analytical surface while keeping the math auditable. Add VEX, DEX, vega-total, flip-zone, scenario matrix, four gamma/vanna states, tap-probability bands, stacked-node detection, replay mode.

**Why now.** The math foundations (`advanced_analytics.py`, `vol_analytics.py`, `bs_greeks.py`) are solid; extending them is mostly composition, not new research. And these are the features that directly help Nav read the tape.

**Current state.**
- GEX, gamma flip, walls, max pain, hedge impulse, charm integral, implied PDF — present.
- VEX (vanna), DEX (delta), Vega Total — **not** present as separate histograms.
- Scenario matrix, gamma/vanna 4-state classifier, replay mode — absent.

**Work units.**

1. **VEX, DEX, Vega Total.** Add `calc_vex`, `calc_dex`, `calc_vega_total` to `advanced_analytics.py`. Each takes the same `contracts` shape used by GEX. Unit tests against a two-strike toy chain.
2. **Four gamma/vanna states.** Function `classify_state(gex_sign, vex_sign) -> Literal["range_bound", "vex_watch", "short_pos_gamma", "short_bounce"]` with the prescriptions from `IMPLEMENTATION_PLAN.md:43-48`. Return a structured `RegimeAdvice` object: state, description, suggested strategy, risk multiplier.
3. **Scenario matrix.** Given a snapshot, compute expected dealer-hedge flow for price moves in a grid of `(Δspot, Δt)` cells. Output a 2D array suitable for a heatmap. Each cell shows: implied dealer buy/sell volume, expected GEX-induced reflexivity, confidence band.
4. **Tap probability bands.** Using the implied PDF (`calc_implied_pdf`), compute strike-level probabilities of being touched (not just being above/below) for 80/66/33/10 bands. Render as horizontal lines on the price chart.
5. **Stacked nodes / tug-of-war.** A stacked node = strike where call wall and put wall coincide within a tight band. Tug-of-war = adjacent strikes with opposite-sign GEX above a magnitude threshold. Detection in `advanced_analytics.py`.
6. **Replay mode.** Backend reads historical `snapshots` for a chosen ticker/day at a chosen speed; emits over the WebSocket as if live. Frontend's existing heatmap becomes the replay viewer with no fork.
7. **Math correctness tests.** Each new function gets a unit test with hand-computed expected values and a property-based test (`hypothesis`) for invariants (e.g. GEX = call_gamma_sum - put_gamma_sum scaled; VEX flips sign with vanna sign).

**JetBrains workflow.**
- **PyCharm:** open `advanced_analytics.py`, use Tools → Run Python Console to interactively prototype each new function against a fixture chain. Move to a test file with Refactor → Extract.
- **PyCharm Profiler:** profile `calc_implied_pdf` and the scenario-matrix function on a realistic chain. Anything in the request path should be < 50 ms; if not, optimize before merge.

**Verification.**
```bash
pytest backend/tests/test_advanced_analytics.py backend/tests/test_vol_analytics.py -v
# Property-based tests must pass with default Hypothesis settings (100 examples per property).

# Replay round-trip
curl -fs 'http://localhost:8000/api/replay/start?ticker=SPY&day=2026-04-15&speed=10x'
# Open the frontend in Chrome; confirm WebSocket frames arrive in chronological order.
```

**Exit criteria.**
- VEX, DEX, Vega-Total exposed via routes and rendered on the frontend with toggleable histograms.
- Scenario matrix, tap-probability bands, stacked-node detection, tug-of-war zones each have a route, a test, and a UI component.
- Replay mode functional for any day in `snapshots`.

---

## Phase C — ML pipeline (the deep one)

**This phase is where the system stops being a dashboard and starts being a research platform.** It is broken into six sub-phases. Do not skip ahead.

**Target.** A reproducible ML pipeline with: a feature store, walk-forward training with purged K-fold + embargo, hyperparameter search, multiple model families, calibration, SHAP explanations, trading-metric evaluation, a model registry, and online inference with drift monitoring.

**Why now.** The current `ml_training.py` / `ml_price_prediction.py` produce a single sklearn model trained on a flat snapshot table with no temporal discipline. That model is not safe to trade on. Replacing it with a production pipeline is the single highest-leverage change in this project.

**Current state.** Toy features (10 fields per snapshot), no CV strategy, no model registry, no calibration, no monitoring.

### Phase C.1 — Feature store

**Work units.**

1. New module `backend/services/ml/features.py` exporting `compute_features(snapshot_window, market_window, flow_window, sentiment_window) -> FeatureRow` where each window is a list of records ending at time `t`.
2. **Feature taxonomy.** Cover:
   - **Price / vol features:** returns over 1m / 5m / 15m / 1h / 1d / 5d horizons; realized vol (Parkinson, Garman-Klass) over 5d / 20d / 60d; gap stats (overnight return, opening range).
   - **GEX / VEX / DEX features:** snapshot magnitude, normalized magnitude (z-score over 60d), rate of change, distance-to-flip in σ-units, wall density (ATM ± 1%), gamma concentration index (Herfindahl).
   - **IV features:** ATM IV, 25-delta risk reversal, 25-delta butterfly, IV term-structure slope (front/30d/60d/90d), IV rank, IV percentile.
   - **Flow features:** sweep frequency, block premium, bullish/bearish premium ratio over 5m / 30m / 1d.
   - **Macro features:** VIX, VIX9D/VIX ratio, DXY return, 10Y yield change.
   - **Sentiment features:** social-pipeline output from `social_flow_pipeline.py` aggregated to 5m bars.
   - **Calendar features:** day-of-week, day-of-month, day-to-OPEX, day-to-FOMC, earnings-season flag.
3. **Online / offline parity.** The same `compute_features` is called both by the training pipeline (over historical records) and by the inference service (over live records). One code path, never two.
4. **Feature versioning.** A `FEATURE_VERSION` constant. When the feature schema changes, the version increments and the model registry's compatibility check rejects mismatches.
5. **Storage.** Features written to MongoDB collection `ml_features` keyed by `(ticker, ts, version)`. Index `(ticker, version, ts desc)`.

**JetBrains workflow.** Use PyCharm's "Run Python Console" with `compute_features` interactively on a real snapshot pulled from DataGrip. Make sure every feature comes back finite and non-NaN.

### Phase C.2 — Targets and labels

**Work units.**

1. **Multi-task targets:** for each feature row at time `t`, compute and store:
   - `ret_1h` — log return over the next hour.
   - `ret_eod` — log return from `t` to that day's 16:00 ET close.
   - `dir_1h` — `1{ret_1h > τ}`, `-1{ret_1h < -τ}`, `0` otherwise (τ from realized vol — e.g. 0.25 × ATR).
   - `range_1h` — high–low over the next hour.
   - `regime_change_1h` — boolean: does the GEX regime flip?
2. **Label leakage prevention.** Features computed at `t` must use only data available at `t`. Tests assert no future value leaks (e.g. moving averages aligned right).
3. **Label embargo.** Define an embargo window equal to the longest target horizon (1h initially) — features generated within the embargo of any test fold are dropped.

### Phase C.3 — Training pipeline

**Work units.**

1. **Walk-forward CV.** Implement `WalkForwardSplit(n_splits, train_size, test_size, embargo)`. Each fold's test set is contiguous and strictly after its train set.
2. **Purged K-fold (optional).** For when the same target overlaps multiple feature rows (e.g. 1h targets at 5-min frequency). Purge the overlap.
3. **Models.** Train four families in parallel under the same CV harness:
   - Baseline: penalized logistic regression (sklearn).
   - Tree ensemble: XGBoost.
   - Tree ensemble: LightGBM.
   - Time-series: 1D-CNN with attention (PyTorch). Optional, gated by GPU availability.
4. **Hyperparameter search.** Optuna with `TPESampler`, 50 trials per model per ticker, inner CV inside each fold.
5. **Class imbalance.** Compute class weights for 3-way direction targets. Try focal loss for the CNN.
6. **Calibration.** Wrap each classifier in `CalibratedClassifierCV(cv='prefit', method='isotonic')` using a held-out calibration slice from each fold.
7. **Output.** Per fold: trained model artifact, predictions on test fold, feature-importance vector (SHAP for trees, integrated gradients for CNN), calibration curve.

**JetBrains workflow.**
- **PyCharm with scientific mode enabled.** Run training in a notebook-style Python file (`# %% cells`) so feature plots, prediction histograms, and SHAP plots render inline. Save the figures into `qc/ml-runs/<run_id>/`.

### Phase C.4 — Evaluation (ML metrics AND trading metrics)

**Work units.**

1. **ML metrics per fold:** accuracy, F1, ROC-AUC, log-loss, Brier score, calibration error.
2. **Trading metrics per fold:** simulate the obvious trading policy from the model (e.g. enter long if `P(dir=+1) > 0.6`, exit at horizon). Compute:
   - Hit rate
   - Average win / average loss
   - Profit factor
   - Sharpe (annualized)
   - Sortino
   - Calmar (return / max drawdown)
   - Max drawdown
   - Hold-time distribution
3. **Stability:** plot metric over time (rolling fold) — flag if Sharpe falls below the baseline policy for any quarter.
4. **Stress tests:** if historical data covers them, evaluate on:
   - Aug 2024 yen-carry unwind
   - 2022 rate-shock bear
   - 2020 COVID crash
   - 2018 Volmageddon
5. **Comparison report.** Markdown file under `qc/ml-runs/<run_id>/report.md` with tables and embedded plots. Top of report: a single verdict line — "ship / reject / iterate."

### Phase C.5 — Model registry

**Work units.**

1. **MLflow Tracking** (local file-backed; remote-ready). Each fold of each model logs params, metrics, artifacts, signatures.
2. **Registry table.** A MongoDB collection `ml_models` records: `model_id`, `ticker`, `feature_version`, `training_window`, `metrics_summary`, `path`, `created_at`, `status` (`shadow`, `active`, `retired`).
3. **Promotion flow.** A model moves `shadow → active` only via an explicit endpoint `POST /api/admin/ml/promote/{model_id}` gated by Nav's approval. The CI gate for promotion requires: positive walk-forward Sharpe, lower drawdown than the prior active model, calibration error below threshold.

### Phase C.6 — Inference + monitoring

**Work units.**

1. **Inference service.** New router `routes/ml.py` exposes `POST /api/ml/predict/{ticker}` returning `{prediction, probability, calibrated_probability, model_id, feature_version, request_id}`. Loads the active model lazily; cached in process.
2. **Latency.** Inference p95 < 100 ms locally for tree ensembles. Profile with PyCharm's profiler.
3. **Drift monitoring.** Hourly cron job computes population stability index (PSI) on each feature, comparing the last 24h to the training-window distribution. Alert (in-app, not email) when PSI > 0.25 for any feature.
4. **Prediction logging.** Every prediction is stored in `ml_predictions` (collection) with feature snapshot + outcome (filled in after the horizon). Powers continuous offline re-evaluation.
5. **Auto-retrain triggers.** If the last 7 days' walk-forward Sharpe falls below a threshold OR PSI alarms on ≥ 3 features, the system flags a retrain. Retraining still requires explicit promotion to active.

**Verification (whole Phase C).**
```bash
# Pipeline runs end-to-end
python -m backend.services.ml.pipeline --ticker SPY --since 2025-01-01 --until 2026-04-30 --run-id qc-001
# Produces qc/ml-runs/qc-001/{report.md, metrics.json, artifacts/, plots/}

# Inference works
curl -fs -X POST 'http://localhost:8000/api/ml/predict/SPY' -H 'Authorization: Bearer ...' | jq .
```

**Exit criteria for Phase C.**
- `compute_features` produces ≥ 40 features, all unit-tested for no-future-leakage.
- Walk-forward CV harness reproducible from a single command.
- Four model families train under one harness; calibration applied; SHAP/integrated-gradients available.
- Trading metrics computed alongside ML metrics; both must clear thresholds for shipping.
- MLflow tracking active; model registry collection live.
- Inference endpoint live with latency budget met; drift cron job running.

---

## Phase D — Backtesting & signal validation

**Target.** A reusable backtester that can score any signal (rule-based or ML) against historical bars/snapshots with realistic friction, used as the gate for what becomes a live alert or live trade.

**Why now.** Without it, "good alert" is opinion. With it, "good alert" is a Sharpe number.

**Work units.**

1. **Bar replay.** Reconstruct minute bars for SPY/QQQ from stored quote ticks (or fetch from Polygon if missing). Store under `backtest_bars` collection.
2. **Backtester core.** `backend/services/backtest/engine.py` — event-driven, no lookahead, fills at next-bar open with configurable slippage and commission (defaults: 0.05% slippage, $0.65 / contract).
3. **Signal interface.** Any signal implements `Signal.evaluate(snapshot_history, bar_history, position) -> Action`. The same interface is used by rule-based alerts (Phase E) and ML models (Phase C).
4. **Standard suites.** Three preset evaluations:
   - **In-sample / out-of-sample** with a 70/30 time split.
   - **Walk-forward** consistent with Phase C.
   - **Monte Carlo bootstrap** of the return path (1,000 trials) to put confidence bands on Sharpe and max-DD.
5. **Reports.** Each backtest writes a markdown + plots bundle under `qc/backtests/<id>/`.

**Verification.**
```bash
python -m backend.services.backtest.run --signal alert.gamma_flip --ticker SPY --window 2025-01-01:2026-04-30
# Produces qc/backtests/<id>/report.md with Sharpe, hit rate, max DD, sample trades.
```

**Exit criteria.** Every alert type in `alert_engine.py` has a backtest report on file. Any alert with a backtest Sharpe < 0 across walk-forward is downgraded or retired.

---

## Phase E — Alerts & signals (rule engine + ML enrichment)

**Target.** A small DSL for declarative alerts, fed by both rule-based predicates and ML predictions, with a history table and per-alert backtest-driven quality scores.

**Current state.** `alert_engine.py` hardcodes 7 alert types as Python methods. Adding a new alert requires editing the engine.

**Work units.**

1. **Alert DSL.** A YAML schema under `backend/alerts/definitions/*.yaml`. Each file: `name`, `priority`, `predicate` (a tiny boolean expression DSL over snapshot/feature fields), `cool_down`, `description`. Engine parses and evaluates.
2. **ML-enriched alerts.** A predicate may include `ml.dir_1h_proba > 0.65`. The engine fetches the prediction via the Phase C inference service.
3. **History table.** Collection `alerts_history` stores every fired alert with: trigger snapshot, predicate value, prediction (if any), realized outcome at horizon (filled later). Powers a "how is each alert performing" dashboard.
4. **Backtest-gated quality.** Each alert definition references its backtest report (Phase D). A `quality_score` is the report's Sharpe; the alert UI displays it next to the alert.
5. **Migration.** The 7 existing alerts move into YAML; the Python methods become reference implementations to be deleted.

**Exit criteria.** Adding a new alert is a YAML file + a backtest run, not a code change. Every alert has a `quality_score`. The frontend shows it.

---

## Phase F — Trading execution

**Target.** Order placement that is idempotent, replay-safe, and gated by pre-trade risk checks. Paper-vs-live separation enforced in code, not in convention.

**Current state.** `alpaca_client.py` plus `paper_trading.py`. `MAX_POSITION_SIZE = 1`. The typo `DEFAULT_STRATEGY = "iron_condible"` (`paper_trading.py:21`) is a real bug to fix in this phase.

**Work units.**

1. **Trade-intent model.** `backend/services/trading/intent.py` — a Pydantic `TradeIntent` (ticker, side, qty, strategy, max_slippage_pct, max_premium, expiry, strikes, time_in_force). `client_order_id` is a deterministic hash of the intent + a session salt — same intent submitted twice produces the same ID, Alpaca rejects the duplicate.
2. **Risk gate.** Before every `submit_order`, run `check_risk(intent, portfolio, account)`: max position size, max daily loss, concurrent-position limit, premium-as-fraction-of-equity cap, expiry hygiene (no held-through-expiry without explicit flag), regime override (size down in deep negative gamma).
3. **Paper-vs-live guard.** Alpaca base URL must come from env. Constructor asserts `"paper" in BASE_URL` unless `LIVE_TRADING_ENABLED=1` is set explicitly. CI runs with `LIVE_TRADING_ENABLED` unset; production env is whitelisted in code.
4. **Reconciliation loop.** Background task every 30 s: `list_orders` from Alpaca, diff against local `orders` collection, update statuses, alert on mismatches.
5. **Replay safety.** If the process crashes between `submit_order` and persisting locally, on restart the reconciliation loop's first run picks up the gap (because `client_order_id` was deterministic and is now stored Alpaca-side).
6. **Strategy library.** Replace the broken `iron_condible` with a real `Strategy` Pydantic discriminated union: `IronCondor`, `Straddle`, `Strangle`, `Vertical`, `Calendar`, `SingleLeg`. Each has its own validation. `paper_trading.build_order_from_signal` returns concrete strategies, not strings.

**JetBrains workflow.**
- **PyCharm Debug:** breakpoint on `submit_order`. Run the paper-trading integration test. Step through to verify `client_order_id` derivation.
- **WebStorm HTTP Client:** create `qc/http/trading.http` with sample order submissions; use it to exercise the API by hand.

**Verification.**
```bash
pytest backend/tests/services/trading/ -v
# Includes: idempotency_test (same intent → one fill), risk_gate_test (over-cap rejected), reconciliation_test.

# Fail-closed test
LIVE_TRADING_ENABLED= python -c "from alpaca_client import AlpacaClient; c = AlpacaClient(base_url='https://api.alpaca.markets'); c.assert_paper()"
# Expected: raises.
```

**Exit criteria.**
- Trade intent → order path is fully Pydantic, with risk gate.
- `iron_condible` typo removed; replaced with the `Strategy` union.
- Reconciliation loop running; mismatches alert in-app.
- Paper-vs-live guard cannot be bypassed by a typo.

---

## Phase G — Portfolio & P&L

**Target.** Tax-lot-accurate, multi-leg P&L with `Decimal` math throughout. Every position has a complete event history.

**Current state.** `portfolio.py` is 14.8 KB; uses floats; multi-leg handling unclear.

**Work units.**

1. **Money is `Decimal`.** Every currency value uses `decimal.Decimal` with explicit quantization. No float arithmetic for prices, premiums, P&L. Audit every `* 100`, `* 0.01`, `round()` in portfolio code.
2. **Tax-lot accounting.** Each fill creates a lot. Closes consume lots FIFO by default; LIFO and HIFO selectable per position.
3. **Multi-leg positions.** A `Position` aggregates `Leg`s. Greeks aggregate by signed sum across legs. P&L attribution: per leg, per Greek, per day.
4. **Event log.** Every state change to a position is an append-only event. Position snapshots derive from event replay. Auditable, reversible.
5. **End-of-day mark.** Cron job at 16:15 ET marks every position to the day's settlement and persists a daily snapshot. Powers the journal.

**Verification.**
```bash
pytest backend/tests/services/portfolio/ -v
# Includes: vertical_pnl, iron_condor_pnl, calendar_pnl, partial_close_pnl, tax_lot_fifo, decimal_no_float_leak.
```

**Exit criteria.** P&L correctness verified on six canonical fixtures (vertical, IC, straddle, strangle, calendar, partial close). Decimal-only math (`grep -rE 'float\(.*premium|premium.*float|\* 0\.01\b' backend/portfolio.py` returns nothing).

---

## Phase H — Frontend architecture

**Target.** A maintainable React app: server state separated from UI state, App.js as a 100-line composition root, hooks for every data feed, tests for every component.

**Current state.** `App.js` 730 lines. No server-state library. No tests.

**Work units.**

1. **Server state → TanStack Query.** Install `@tanstack/react-query`. Every fetch becomes a `useQuery` (or `useMutation`). Configure `staleTime`/`refetchInterval` per data kind. Devtools enabled in dev.
2. **UI state → Zustand.** A single `useUiStore` for cross-cutting UI state (current ticker, layout density, theme, color-blind mode flag). Component-local state stays local.
3. **Decomposition.** Split `App.js`:
   - `App.jsx` — providers (Query, Router, Theme), routes only.
   - `layouts/DashboardLayout.jsx` — grid.
   - `pages/HeatmapPage.jsx`, `pages/FlowPage.jsx`, `pages/PortfolioPage.jsx`, `pages/MLPage.jsx`, `pages/ReplayPage.jsx`, `pages/SettingsPage.jsx`.
   - Data hooks: `useGex(ticker)`, `useFlow(ticker)`, `useAlerts()`, `usePortfolio()`, `useMlPrediction(ticker)`.
4. **Hook audit.** Enforce `react-hooks/exhaustive-deps: error`. Every WebSocket / interval / subscription has a cleanup function.
5. **Charts.** Keep recharts for histograms; evaluate `lightweight-charts` (TradingView) for the heatmap and replay — better at high-frequency redraws. Memoize chart components aggressively.
6. **Tests.** React Testing Library for components, `@testing-library/react-hooks` (or React-18 equivalent) for hooks, Playwright for one happy-path E2E.
7. **A11y.** axe-core in dev; fix all serious violations.

**JetBrains workflow.**
- **WebStorm Refactor → Extract Component** for the App.js split.
- **WebStorm built-in Profiler** + React DevTools to identify expensive renders before/after memoization.
- **WebStorm HTTP Client** to exercise the API while building components; create `qc/http/` request files.

**Verification.**
```bash
wc -l frontend/src/App.js   # ≤ 100
(cd frontend && npm run lint && npm test -- --coverage --watchAll=false)
# Coverage gate: ≥ 60% lines, raising to ≥ 75% by Phase J.
```

**Exit criteria.** App.js ≤ 100 lines; every page route renders independently; TanStack Query Devtools shows clean cache state; lint passes with `exhaustive-deps: error`; ≥ 60% frontend coverage.

---

## Phase I — Observability, SLOs, ops

**Target.** When something breaks, you find out in seconds and you know exactly which request did it.

**Work units.**

1. **Structured logs.** `structlog` JSON output. Every log line has `timestamp, level, request_id, user_id?, route, message, extra`.
2. **Request IDs.** Middleware assigns/propagates `X-Request-ID`; surfaced in error response bodies; included in error tracker reports.
3. **Metrics.** Prometheus client. Counters per provider call (success/fail/timeout); histograms per route; gauges for WebSocket connections, active orders, cron-job last-success-age. Endpoint `/metrics` gated by an env flag.
4. **Traces.** OpenTelemetry SDK; export to OTLP. Local dev: Jaeger via docker-compose. Trace IDs link logs ↔ metrics ↔ traces.
5. **Error tracker.** `error_tracking.py` exists — wire it to Sentry's free tier (or Glitchtip self-hosted). Test with a deliberate `/api/admin/debug/raise`.
6. **Dashboards.** Grafana panels: (a) data-collection success per ticker per 5-min window, (b) WebSocket connection count, (c) backend latency p50/p95/p99, (d) ML inference latency, (e) alert fire rate by type, (f) order placement success/fail.
7. **SLOs (`docs/SLO.md`).** Initial:
   - GEX dashboard load p95 < 1.5 s in market hours.
   - Alert delivery (snapshot → frontend) < 30 s p95.
   - Inference p95 < 100 ms.
   - Uptime 99% during 09:30–16:00 ET; 95% off-hours.
   - Data freshness: < 6 min behind real-time for any tracked ticker.
8. **Runbooks (`docs/runbooks/*.md`).** "Mongo Atlas down", "FlashAlpha 5xx", "Alpaca rate-limit storm", "model drift alarm", "WebSocket fanout >500".

**Exit criteria.** Killing Mongo locally surfaces a Grafana red and an in-app banner within 60 s. Every runbook is exercised once in a tabletop drill.

---

## Phase J — Quality processes, ADRs, release discipline

**Target.** Hermes ships continuously with low risk, and architectural decisions are durably recorded.

**Work units.**

1. **ADRs.** Folder `docs/adr/`. Template: context, decision, status, consequences. First ADRs to retroactively record: "TanStack Query for server state," "Walk-forward CV with embargo," "Pydantic discriminated unions for strategies," "Redis for cross-worker rate limiting," "MLflow for model registry."
2. **PR template.** `.github/pull_request_template.md` with: scope, verification commands run, screenshots if UI, ADR reference if architectural, risk assessment, rollback plan.
3. **Conventional commits.** Enforce via commitlint in pre-commit. Subject types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `chore`. Scope is the bounded context (`(ml)`, `(trading)`, `(frontend)`, …).
4. **Branching.** Trunk-based with short-lived feature branches. `main` is always deployable. No long-running branches.
5. **Release tags.** Semver: `v0.x.y`. Each release has a `CHANGELOG.md` entry generated from conventional commits.
6. **Coverage ratchet.** CI's `--cov-fail-under` increases by 5 every two weeks until 85% (backend) / 75% (frontend) is reached.
7. **Dependency review.** Monthly `pip list --outdated` and `npm outdated`; minor/patch upgrades land same-week unless they break tests.

**Exit criteria.** Every PR follows the template. ADR folder is non-empty and growing. Coverage ratchet is live.

---

## 4. Roadmap & sequencing

The phases have dependencies. The minimum-risk ordering:

```
       Foundation (§3)
              │
              ▼
            [A] Data layer
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
 [B] Quant   [F] Trading  [H] Frontend
  analytics   execution    (can start in parallel after A)
   │              │
   ▼              ▼
 [D] Backtester  [G] Portfolio (after F)
   │
   ▼
 [C] ML pipeline (needs B, A, D)
   │
   ▼
 [E] Alerts (needs C and D)
   │
   ▼
 [I] Observability (touches everything — start partial in A, finish here)
   │
   ▼
 [J] Quality processes (start partial in A, formalize here)
```

**Suggested calendar shape** (Nav's life context: heavy clinical Mon–Thu, work shifts overlap days, MRI graduation Aug 13):

| Block (calendar weeks) | Focus            | Why this fits Nav's schedule                                                                                  |
|------------------------|------------------|---------------------------------------------------------------------------------------------------------------|
| Now → mid-June         | §3 + Phase A     | Foundational; mostly mechanical refactoring; can be done in 1–2 hr evening chunks                              |
| Mid-June → mid-July    | Phases B + H     | Visible features; good motivation; backend analytics + frontend split run in parallel safely                   |
| Mid-July → mid-Aug     | Phases D + F + G | Pre-graduation; build the trading-safety scaffolding before going live post-graduation                         |
| Aug → Sep              | Phase C          | Post-graduation, full attention available; ML pipeline is the most cognitively demanding work                  |
| Sep → Oct              | Phase E + I + J  | Operationalize: alerts, observability, release discipline, before scaling capital                              |

This isn't a deadline; it's a default sequencing. Slip is fine. Skipping is not.

---

## 5. Hermes operating contract (how to actually work, session by session)

Every Hermes session follows this loop:

1. **Orient.** Read `REVIEW_LOG.md` last entry. Read this plan's current phase. Open today's `BACKLOG.md` and pick the next task within the phase.
2. **Branch.** `git checkout -b feat/<phase>/<short-description>` from `main`.
3. **Plan locally.** Write a `TodoWrite` list for this session's task. Tasks ≤ 30 min each.
4. **TDD.** Failing test → minimal fix → green → refactor under green.
5. **IDE pass.** Before opening a PR: run the JetBrains inspection for the changed files; address every "error" severity finding (warnings noted in the PR description).
6. **Verify.** Run the phase's verification commands. Paste output into the PR description.
7. **PR.** Title `[Phase X] <short description>`. Body uses the template. Include screenshots for UI changes.
8. **Log.** Append to `REVIEW_LOG.md`: `<date> <commit-sha> <one-line summary>`.

**Do not:**

- Cross phase boundaries in a single PR.
- Refactor outside the phase's scope just because the file is open.
- Add new external dependencies without an ADR.
- Take destructive actions (force-push, drop collection, delete branch) without Nav's explicit OK in-session.
- Use `--no-verify` to bypass hooks. If the hook complains, fix what it's complaining about.

**Do:**

- Ask Nav questions when a design choice is irreversible.
- Surface dead code, unused config, and confusing patterns as `BACKLOG.md` items instead of fixing inline.
- Pair every fix to trading code with a regression test that would have caught the bug.

---

## 6. Verification quick-reference

Save as `qc/verify.sh` (Hermes creates it in Phase A):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "─ pre-commit ─";  pre-commit run --all-files
echo "─ ruff ─";        (cd backend && ruff check . && ruff format --check .)
echo "─ mypy ─";        (cd backend && mypy . --ignore-missing-imports)
echo "─ bandit ─";      (cd backend && bandit -r . -ll -ii)
echo "─ pip-audit ─";   (cd backend && pip-audit -r requirements.txt)
echo "─ pytest ─";      (cd backend && pytest --cov=. --cov-fail-under=60)
echo "─ npm lint ─";    (cd frontend && npm run lint)
echo "─ npm audit ─";   (cd frontend && npm audit --audit-level=high)
echo "─ npm test ─";    (cd frontend && npm test -- --coverage --watchAll=false)
echo "─ ALL GREEN ─"
```

---

## 7. What this plan deliberately does NOT cover

- **Live trading.** Phase F builds the scaffolding; flipping `LIVE_TRADING_ENABLED=1` is a decision Nav makes after the system has demonstrated a positive walk-forward Sharpe over an out-of-sample window he believes in.
- **Production infrastructure tuning.** Azure deployment scaffold exists from prior commits; productionizing (HA, scaling, blue/green) is post-Phase-J work.
- **Secrets rotation procedures.** Per Nav: account is private, single-user. Standard env-file hygiene only.
- **Mobile native app.** Mobile-responsive web is sufficient (already delivered in commit `be49dd5`).
- **Multi-user / team features.** Single-user product.

If any of these become relevant later, they get their own ADR + addendum phase.

---

## 8. Open questions for Nav (resolve before Phase C)

These shape the ML phase enough that Hermes shouldn't pick defaults silently:

1. **Universe.** SPY/QQQ only for ML, or include IWM/DIA/sector ETFs? (Default: SPY + QQQ only; more tickers = more training data but more regime variance.)
2. **Prediction horizon priority.** Intraday (1h) vs end-of-day vs next-day? (Default: 1h primary, EOD secondary.)
3. **Risk per trade.** Is the existing 1–2% rule the cap once live, or does the regime multiplier dynamically widen it? (Default: hard 2% cap, regime can only reduce.)
4. **Hardware.** GPU available for the CNN family, or skip it? (Default: skip until GPU available; XGBoost+LightGBM are enough.)
5. **Data history.** How far back is reliable? Pre-2020 markets behave differently; pre-2018 0DTE didn't exist. (Default: 2020-01-01 onwards.)

Hermes asks these as `AskUserQuestion` at the start of Phase C, captures answers in `docs/adr/0001-ml-scope.md`.

---

*This document supersedes all prior plan files. Treat it as code: PR changes against it, ADRs justify major edits, version it with the rest of the repo.*
