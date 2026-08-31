# External Integrations

**Analysis Date:** 2026-08-24

## APIs & External Services

**Market Data — Options Chains:**
- Public API (Public.com via `PublicBroker`) — primary options-chain and spot source when `PUBLIC_API_KEY` is configured
  - Client: `backend/services/public_api.py` + adapter `backend/services/public_api_adapter.py`
- cvserver (CVForge / ConvexValue) — secondary options-chain source: 32 expiries, 171 strikes, greeks included
  - Client: `backend/services/cvserver_client.py` (`fetch_chain_from_cvserver`, `fetch_chain_for_heatmap`)
  - Endpoint: MCP-style API at `https://tap.convexvalue.com/api/data/mcp` (override via `CVSERVER_URL` env var)
  - Auth: Bearer token in `CVSERVER_API_KEY`
  - Fallback chain on timeout/failure: yfinance → Databento (`backend/server.py:549`)
- yfinance 1.3.0 — fallback underlying prices and chains
  - SDK: `yfinance` package, used directly in `backend/server.py` and `backend/data_providers.py`
  - Auth: none (public Yahoo endpoints)

**Market Data — Paid/Keyed:**
- Databento — historical options data, open-interest, EOD chains, tick/DBN ingestion
  - SDK: `databento >=0.34.0`; integration in `backend/databento_provider.py`, `backend/services/databento_oi.py`
  - Auth: `DATABENTO_API_KEY`
- Polygon.io — daily stock aggs for strike-touch counts and top movers
  - Integration method: REST via httpx in `backend/server.py` (`https://api.polygon.io/v2/aggs/ticker/...`)
  - Auth: `POLYGON_API_KEY`
- Alpha Vantage — supplementary quote data with circuit breaker
  - Integration: REST at `https://www.alphavantage.co/query` via `backend/routes/alpha_advantage.py` + `backend/services/alpha_vantage_client.py`
  - Auth: `ALPHA_VANTAGE_KEY` as `apikey` query param; rate limits handled by circuit breaker
- Finnhub — secondary market data provider (key provisioned in `backend/.env`, `deploy/free/.env.prod`, `docker-compose.yml`)
  - Auth: `FINNHUB_API_KEY`
- FlashAlpha — additional data feed
  - Client: `backend/flashalpha_client.py`; REST base `https://lab.flashalpha.com`
  - Auth: `FLASHALPHA_API_KEY`

**Brokerage / Trading:**
- Schwab Trader API — OAuth2 + live WebSocket streaming quotes
  - OAuth2 client: `backend/schwab.py` (authorize/token at `https://api.schwabapi.com/v1/oauth/*`; redirect URI in `SCHWAB_REDIRECT_URI`; tokens persisted to `SCHWAB_TOKEN_PATH`, default `~/.hermes/schwab_token.json`, chmod 600)
  - WebSocket streamer: `backend/services/schwab_streamer.py` → `wss://streamerapi.schwabapi.com/ws/v1/stream` via `websockets` lib; reconnect chaos-tested in `backend/tests/schwab/`
- Alpaca — free paper trading (account, positions, orders, market data)
  - Client: `backend/alpaca_client.py` (aiohttp); `https://paper-api.alpaca.markets` + `https://data.alpaca.markets`
  - Auth: `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`

**LLM / AI:**
- OpenRouter — default LLM provider (free-model router)
  - Client: OpenAI SDK pointed at `https://openrouter.ai/api/v1` in `backend/services/llm.py`; model via `OPENROUTER_MODEL` (default `openrouter/free`), provider switch via `LLM_PROVIDER`
  - Auth: `OPENROUTER_API_KEY`
- Google Gemini — analyzer fallback
  - SDK: `google-genai` in `backend/gemini_analyzer.py` (model `gemini-1.5-flash`)
  - Auth: `GEMINI_API_KEY`

## Data Storage

**Databases:**
- MongoDB 7 (async Motor client) — primary document store
  - Connection: `MONGO_URL` (default `mongodb://localhost:27017`), database `DB_NAME=confluence_decoder`; clients built in `backend/server.py` and `backend/deps.py`
  - Collections used (scanned across `backend/**/*.py`): `alerts_history`, `databento_eod_chains`, `feature_manifests`, `gex_enhanced_snapshots`, `gex_features`, `gex_llm_patterns_outcomes`, `ml_features`, `ml_models`, `ml_predictions`, `ml_retrain`, `ml_retraining_log`, `orders_dry_run`, `snapshots`, `underlying_bars`
- DuckDB (embedded) — tick/Lob/analytics engine
  - Engine: `backend/services/duckdb_engine.py` (path via `GFLOWS_DUCKDB_PATH`, default `backend/data/gflows.duckdb`)
  - Tables created: `ticks`, `lob_snapshots`, `lob_depth`, `flow_prints`, `vpin_buckets`, `chains`

**File Storage:**
- Local disk only — model artifacts under `backend/models/`, data/cache under `backend/data/`, `cache/`, `logs/`; no cloud object storage

**Caching:**
- In-process caches (`backend/cache.py`, `backend/services/cache_router.py`, TTL chain cache in `backend/server.py`); no Redis

## Authentication & Identity

**Auth Provider:**
- Custom API-key auth — `backend/auth.py`: mutating HTTP methods require `X-API-Key` header matching `API_SECRET_KEY` (hmac.compare_digest); explicit public-path allowlist for read-only dashboard GETs
- JWT secrets: `JWT_SECRET_KEY` env var (pyjwt in `backend/requirements.txt`)
- WebSocket auth: `WS_API_TOKEN` (empty = dev mode, allow all)

**OAuth Integrations:**
- Schwab OAuth2 (see above) — the only external OAuth flow; credentials via Schwab app registration, tokens on local disk

## Monitoring & Observability

**Metrics:**
- Prometheus — `prometheus-client` counters/gauges in `backend/services/observability.py` (e.g. `websocket_connections`), scraped endpoint via `/metrics`; scrape config in `prometheus/`, dashboards in `grafana/`, stack in `docker-compose.observability.yml`

**Error Tracking / Logs:**
- Structured logging with correlation-ID middleware: `backend/services/logging_config.py`; error tracking helper `backend/error_tracking.py`. stdout/file logs only (no SaaS APM)

## CI/CD & Deployment

**Hosting:**
- Single-host Docker deployment — `docker-compose.yml` (dev) / `docker-compose.prod.yml`; backend on :8000, frontend on :3000, mongo:7 container
- Free-tier server provisioning: `deploy/free/` (Caddy reverse proxy `deploy/free/Caddyfile`, `server-setup.sh`, `oracle-setup.sh`, smoke tests `smoke.sh`), systemd units in `deploy/systemd/`, scheduled jobs in `deploy/cron.d` plus in-app cron (`backend/cron_runner.py`, `backend/cron_config.py`)

**CI Pipeline:**
- GitHub Actions — `.github/workflows/lint.yml` (ruff: E/E722/F/W/I, ignore E501); tests run locally via pytest

## Environment Configuration

**Development:**
- Required env vars: `MONGO_URL`, `DB_NAME`, `API_SECRET_KEY`; data providers as available: `CVSERVER_API_KEY`, `DATABENTO_API_KEY`, `POLYGON_API_KEY`, `ALPHA_VANTAGE_KEY`, `FINNHUB_API_KEY`, `FLASHALPHA_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `LLM_PROVIDER`, `WS_API_TOKEN`, `JWT_SECRET_KEY`, `FLOWW_DATA_SOURCE`
- Secrets location: `backend/.env` (gitignored); template in `backend/.env.example`
- Degraded mode: Public API falls back to cvserver, then yfinance→Databento; every keyed provider has a no-key fallback path

**Production:**
- Secrets management: `deploy/free/.env.prod` (adds `DOMAIN`, `ADMIN_EMAIL`, `CORS_ORIGINS`); never committed values

## Webhooks & Callbacks

**Incoming:**
- None observed (no third-party webhook receivers)

**Outgoing:**
- None (alert dispatch is in-app via `backend/services/alert_dispatcher.py` to Mongo/UI channels, not external webhooks)

## WebSockets

**Server-side routes (FastAPI):**
- `/ws/signals` — flow-signal push (`backend/routes/alerts.py:43`)
- `/ws/gex/{ticker}` — per-ticker GEX streaming (`backend/server.py:1935`)
- `/ws/{topic}` — generic topic multiplexer backed by connection manager `backend/services/websocket_streamer.py` (`backend/server.py:2639`)

**Client-side connections:**
- Schwab Streamer `wss://streamerapi.schwabapi.com/ws/v1/stream` — `backend/services/schwab_streamer.py`

---
*Integration audit: 2026-08-24*
*Update when adding/removing external services*
