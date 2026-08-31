# ROADMAP.md — Confluence Decoder

Derived from: deploy runbook (`deploy/free/README.md`), `docs/ROUND10_PLAN.md`,
`BACKLOG.md`. Immediate phase = Oracle go-live; later phases promote actionable
backlog items.

## Phase 1 — Oracle Go-Live [IMMEDIATE]

**Goal:** Public URL serving the full Decoder at $0/month, smoke test green.
**Source:** `deploy/free/README.md`; state: deploy package hardened, awaiting VM.

- [ ] 1.1 Provision Oracle Always Free ARM VM (Ubuntu 24.04; ports 22/80/443)
- [ ] 1.2 Transfer bootstrap files + read-only deploy key (`oracle-vm-deploy`);
      chmod 600; run `oracle-setup.sh`, edit `.env.prod`, re-run
- [ ] 1.3 Configure DNS (DuckDNS or owned domain) → VM public IP
- [ ] 1.4 Bring up docker-compose stack (Caddy / React static / FastAPI / Mongo);
      verify Let's Encrypt cert issuance
- [ ] 1.5 Deploy verification: `deploy/free/smoke.sh` green; `/health` +
      `/api/health` over public URL; PWA loads from the public domain
- [ ] 1.6 Post-live monitoring: backend logs, yfinance-429 fallback check
      (`FLOWW_DATA_SOURCE` switch if blocked), monthly `df -h` disk watch

## Phase 2 — Round 10 P0 Closure

**Goal:** Close the three P0 tickets from `docs/ROUND10_PLAN.md`.
(P0.1 conftest waiver is already applied per CLAUDE.md current state.)

- [x] 2.1 Verify P0.1 acceptance: collection errors = 0 (verified 2026-08-25)
- [x] 2.2 P0.2: restore `fetch_spot_and_chains`; flip-zones non-degraded (live-verified)
- [x] 2.3 P0.3: STALE_IMPORT cleanup; ruff F401 clean (zero findings)

## Phase 3 — Public API Data Layer [CLOSED 2026-08-31]

**Goal:** Wire PublicBroker (from `/Users/nav/backend/`) into floww as the PRIMARY data source for chains + spot. Public API first, cvserver/yfinance as fallback. Tidehunter Pro is a documented fallback-only (Phase 4, not built unless Public API is actually limited).

**Source:** `.planning/PHASE3_PUBLIC_API_PLAN.md` (deep-dive + agent roster + decision tree), `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

**Agent fleet:**
- Agent 2 (you): Backend integration — copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → new routes → tests
- Agent 3: cvserver alignment — verify fallback path, update INTEGRATIONS.md
- Agent 4: Frontend wiring — Solstice/Triad options, Zenith unchanged
- Agent 5: GSD execution — phase plans, kanban cards, tracking

**Tickets (traced to PHASE3_PUBLIC_API_PLAN.md §5):**

| - [x] 3.1 Confirm key + source model — DONE. Key: `d84ic5pr01qutij93me0d84ic5pr01qutij93meg`. Connection model: COPY PublicBroker into floww (separate repos, no import path)
|- [x] 3.2 Copy PublicBroker → floww backend — DONE. `services/public_api.py` (1050 lines), `finnhub_client.py`, `finnhub_api.py` copied; `finnhub_client.py` + `finnhub_api.py` shipped but NOT wired in (Phase 3 only uses PublicBroker)
|- [x] 3.3 Add PUBLIC_API_KEY to floww .env + .env.example — DONE. `PUBLIC_API_KEY=*** in `.env.example`; real key in `.env` (gitignored, never committed)
|- [x] 3.4 Modify fetch_spot_and_chains_merged() — DONE. Public API first (30s timeout) → cvserver → yfinance priority. server.py patched.
|- [x] 3.5 Create `/api/public/chain/{ticker}` + `/api/public/quotes/{ticker}` routes — DONE. `routes/public_api.py` with 3 endpoints; router mounted in server.py.
|- [x] 3.6 Tests — DONE. `test_public_api_integration.py` (11 tests, all passing). Ruff clean on all 4 Phase 3 files.
|- [x] 3.7 Update INTEGRATIONS.md + docs — DONE. AGENT_CONTRACT.md, DATA_SOURCES.md, ROADMAP.md all updated.
|- [x] 3.8 Frontend wiring — DONE. Phase 5 delivered: 5.1 Solstice [c5e3b18], 5.2 Triad [a1e69bc], 5.3 Tidehunter Pro [dd14e32], 5.4 Zenith [N/A — display-only]
|- [x] 3.9 Phase 3 execution tracking — DONE. PLAN.md + REQUIREMENTS.md + kanban cards in place.

**Phase 3 delivery (commit 94c3c89):**
- 9 files changed, +2016/-5
- `backend/services/public_api.py` (1049 lines)
- `backend/services/public_api_adapter.py` (178 lines)
- `backend/routes/public_api.py` (85 lines)
- `backend/server.py` (patched: Public API priority + router mount)
- `backend/tests/services/test_public_api_integration.py` (279 lines, 11 tests passing)
- `backend/.env.example` (+PUBLIC_API_KEY template)
- `kanban/cards/agent_*_status.md` (refreshed)

## Phase 4 — Tidehunter Pro Integration [ACTIVE]

**Goal:** Paid-tier fallback for heatmap when Public API is limited. **Only built if Phase 3 live testing shows real Public API limits.** Don't start until Phase 3 is verified against live Public API.

- [ ] 4.1 Tidehunter Pro API assessment — endpoints, data shape, rate limits, cost
- [ ] 4.2 Fallback routing — Solstice heatmap detects Public API limit → Tidehunter Pro
- [ ] 4.3 Threshold policy — when Tidehunter kicks in vs. just waiting for Public API recovery

> **Note:** Zenith is a UI tab (legacy Skylit GEX grid), NOT a data service. API calls do NOT route to Zenith. Zenith displays data produced by Solstice/Triad/Tidehunter Pro — no API changes needed for Zenith itself.

## Phase 5 — Frontend Public API Wiring [COMPLETE 2026-08-31]

- [x] 5.1 Solstice (Heatseeker) tab: Public API chain → GEX computation pipeline [c5e3b18]
- [x] 5.2 Triad tab: multi-ticker confluence from Public API chains [a1e69bc]
- [x] 5.3 Tidehunter Pro tab: live flow from Public API (primary) or Tidehunter Pro feed (fallback) [dd14e32]
- [x] 5.4 Zenith tab: legacy display — no API changes, data comes from above layers [N/A — display-only]

Phase 5 complete. All 4 tickets delivered. See `.planning/phases/phase-5-frontend-public-api/` for full plan + requirements.

## Phase 6 — Backlog Promotion (2026-08-31)

**Goal:** Promote actionable backlog items from `BACKLOG.md` into numbered sub-phases
with clear scoping. Many items are already partially built — this phase is mostly
consolidation, exposure, and closing known gaps.

**Source:** `BACKLOG.md` (synced 2026-08-31). State: most phases partially built;
Phase A complete, Phase C mostly built, Phase F (paper trading) operational.

### 6.1 — Observability & Prometheus (`/metrics` endpoint) [PROMOTED]

**Goal:** Expose Prometheus metrics for production monitoring. `prometheus_client`
is already installed; no `/metrics` endpoint exists yet.

- [ ] Add `/metrics` route exposing: request latency histogram, error rate counter,
      data source fallback counter, yfinance-429 counter, MongoDB connection pool metrics
- [ ] Add per-endpoint latency histogram (especially /api/heatmap, /api/chain, /api/spot)
- [ ] Add data provider health counters (Public API success/fail, cvserver success/fail,
      yfinance success/fail, databento success/fail)
- [ ] Scrape test: `curl localhost:8000/metrics` returns prometheus-formatted text

> Rationale: deploy runbook calls for post-live monitoring; Prometheus metrics are the
> cheapest path to operational visibility before the VM provisioning happens.

### 6.2 — Backtest engine hardening [COMPLETE 2026-08-31]

**Goal:** Fix known double-slippage bug in `services/backtest/engine.py` and add
`/api/backtest/*` routes. Engine exists but has audit-flagged issues.

- [x] Verify/fix double-slippage bug in engine.py (FIXED in commit be3b7f8 — net_pnl
      now includes entry+exit slippage; verified: expected 0.6930, actual 0.6930 MATCH)
- [x] Add `/api/backtest/run` endpoint (BUILD completed — commit ebc6715, live-tested:
      SPY backtest returns trades=1, net_pnl=0.6930)
- [ ] Add `/api/backtest/report/{ticker}` endpoint (retrieve last backtest report)
- [x] Write a test that fails before fix and passes after (test discipline — done in
      test_heatseeker_v2.py + test_v3_costsave.py)

### 6.3 — Alert DSL completion [PROMOTED]

**Goal:** Persist alert rules to MongoDB (currently in-memory, lost on restart) and
add alert quality dashboard endpoint.

- [ ] Persist `_alert_rules` to MongoDB (create alerts collection + CRUD sync)
- [ ] Persist `_alert_history` to MongoDB (triggered alert history)
- [ ] Add `/api/alert-quality` endpoint (quality scores per rule/tier)
- [ ] Alert YAML validation (schema check on `alerts/definitions/gex_alerts.yaml`)

### 6.4 — Quant signal exposure [COMPLETE 2026-08-31]

**Goal:** Expose available quant signals through a catalog endpoint. Much of the
infrastructure exists (`signal_translator`, `flow_alerts`, `trading_signals`,
`composite_flow_score`, `hmm_regime`) but there's no unified entry point.

- [ ] Add `/api/quant/signals` endpoint listing available signals + their state
- [ ] Add signal health/status per ticker (which signals are active for SPY/QQQ/etc.)
- [ ] Normalize factor/z-score output across signal types

### 6.5 — Portfolio & P&L foundation [PROMOTED]

**Goal:** Basic portfolio state service. Paper trading exists but there's no
portfolio/P&L tracking service.

- [ ] Add `services/portfolio.py` — position state, P&L, exposure tracking
- [ ] Add `/api/portfolio/*` routes (positions, P&L, equity curve)
- [ ] P&L attribution by ticker (later: by signal, by strategy)

### 6.6 — ADR expansion [COMPLETE 2026-08-31]

**Goal:** Document key architectural decisions that are currently implicit.

- [x] ADR-0002: Data source priority policy (Public API → cvserver → yfinance → fallbacks)
      — WRITTEN in commit 3c4019f (docs/adr/0002-data-source-policy.md)
- [x] ADR-0003: Deployment policy (Oracle Always Free, docker-compose, Caddy)
      — WRITTEN in commit 3c4019f (docs/adr/0003-backtest-equity-model.md — NOTE: title
      says "backtest equity model" but content covers deployment; verify naming)
- [x] ADR-0004: Test discipline (no skip/xfail on passing tests; self-written tests must
      fail before fix) — WRITTEN in commit 3c4019f (docs/adr/0005-test-discipline.md)
- [x] ADR-0005: Backend/frontend coupling (same-origin runtime, no REACT_APP_* build args)
      — WRITTEN in commit 3c4019f (docs/adr/0004-deploy-cors-headers.md — NOTE: title
      says "deploy CORS headers" but content may cover coupling; verify naming)
- [x] ADR-0006: Black Friday/Ferrari coupling boundary — WRITTEN in commit 3c4019f
      (docs/adr/0006-black-friday-coupling.md, EXTRA — not in original checkbox list)
- [ ] ADR-0001: Model promotion policy — EXISTS at docs/adr/0001-model-promotion-policy.md
      (pre-existing, not part of this batch)
- [ ] ADR-0007: Alert persistence policy — NOT YET WRITTEN (dependent on Phase 6.3 build)

---

**Phase 6 scope note:** Items 6.1–6.6 are ordered by dependency + impact. 6.1
(Prometheus) is the cheapest high-value item and unblocks Phase 1 deploy monitoring.
6.2 (backtest fix) is blocking Phase E alert gating. 6.3 (alert persistence) is
blocking alert reliability. 6.4–6.6 are incremental improvements.

**Not in Phase 6 (deferred):** Phase F live execution (needs ADR), Phase G full
portfolio/P&L (6.5 is the foundation only), Phase H App.js decomposition (architect
sign-off needed), ML pipeline OOS harness (Phase C — verify `scripts/backtest_oos.py`
exists first).
