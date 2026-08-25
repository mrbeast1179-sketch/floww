# REQUIREMENTS.md — Confluence Decoder

Sources: `docs/ROUND10_PLAN.md` (P0 tickets), `BACKLOG.md`, `deploy/free/README.md`,
`CLAUDE.md`, `ARCHITECTURE.md`, `.planning/LEARNINGS.md`. Every requirement cites its source.

## v1 Requirements (ingested 2026-08-24)

### R1 — Go live on free infrastructure (deploy/free/README.md)

- **R1.1** Provision an Oracle Cloud ARM Always Free VM (4 cores / 24 GB; Azure B1s
  is the documented alternative) with ports 22/80/443 open.
- **R1.2** Deploy via the private-repo path: read-only deploy key
  `oracle-vm-deploy` + `deploy/free/oracle-setup.sh` + `server-setup.sh`
  (`curl | bash` bootstrap does NOT work on a private repo).
- **R1.3** Configure `deploy/free/.env.prod`: DOMAIN, fresh API_SECRET_KEY /
  JWT_SECRET_KEY, provider keys copied from local `backend/.env` (FINNHUB,
  ALPHA_VANTAGE, POLYGON, DATABENTO, OPENROUTER, CVSERVER, FLASHALPHA).
- **R1.4** DNS via DuckDNS (or owned domain) A record → VM IP; Caddy auto-HTTPS
  must issue a Let's Encrypt cert.
- **R1.5** Stack topology: Caddy :80/:443 → static React build, `/api/*` → FastAPI
  :8000, `/ws/*` → websockets, `/dashboard/*` → Dash; Mongo container internal-only.
- **R1.6** Verification: `DOMAIN=... bash deploy/free/smoke.sh` green;
  `/api/health` and lightweight `/health` liveness alias respond over public URL.
- **R1.7** ML models ship with the repo (71MB joblib artifacts are git-tracked) —
  no extra upload step on the server.
- **R1.8** Cloud data-source resilience: if yfinance 429s on datacenter IPs,
  switch `FLOWW_DATA_SOURCE` to finnhub and/or add a Polygon starter.

### R2 — Round 10 P0 remediation (docs/ROUND10_PLAN.md)

- **R2.1** (P0.1) conftest.py freeze waiver applied: defer `from server import app`;
  pytest collection errors ~23 → 0. *(Done per CLAUDE.md current state.)*
- **R2.2** (P0.2) Restore `fetch_spot_and_chains`; `/api/heatseeker/flip-zones?ticker=SPY`
  returns non-degraded response.
- **R2.3** (P0.3) A9 STALE_IMPORT cleanup: `ruff check --select F401 backend/` shows
  0 new unused imports.

### R3 — Backlog promotion candidates (BACKLOG.md)

Active phase A (data layer), in progress:
- **R3.1** Data-layer schema and migrations
- **R3.2** Repository pattern for MongoDB access
- **R3.3** Data collection service with proper error handling
- **R3.4** Data quality checks and validation

Discovered issues (actionable, promoted to later phases):
- **R3.5** Fix `DEFAULT_STRATEGY = "iron_condible"` typo in paper_trading.py
- **R3.6** Decompose 730+ line `App.js` *(constrained by CLAUDE.md frozen-file rule)*
- **R3.7** Introduce server-state library (TanStack Query)
- **R3.8** `portfolio.py`: floats → Decimal *(per ARCHITECTURE operating law 4)*
- **R3.9** Alert engine: un-hardcode the 7 alert types
- **R3.10** Structured logging (structlog) *(note: ARCHITECTURE.md states it as an
  operating law already — see INGEST-CONFLICTS.md)*
- **R3.11** Prometheus metrics / observability (Phase I)
- **R3.12** Process hygiene: ADRs, PR template, conventional-commits enforcement

### R4 — Ongoing constraints carried as requirements

- **R4.1** Test suites stay green after every change (backend ~4546 / frontend 277);
  no skip/xfail on previously-passing tests (CLAUDE.md test discipline).
- **R4.2** Forbidden files untouched without architect approval (CLAUDE.md).
- **R4.3** Model promotions gated per ADR-0001; quarantines preserved.
- **R4.4** Post-live maintenance: monthly `df -h` disk watch; `git pull` +
  docker compose rebuild for updates (deploy runbook Maintenance section).
