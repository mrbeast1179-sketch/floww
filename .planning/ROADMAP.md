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

## Phase 3 — Public API Data Layer [ACTIVE]

**Goal:** Wire PublicBroker (from `/Users/nav/backend/`) into floww as the PRIMARY data source for chains + spot. Public API first, cvserver/yfinance as fallback. Tidehunter Pro is a documented fallback-only (Phase 4, not built unless Public API is actually limited).

**Source:** `.planning/PHASE3_PUBLIC_API_PLAN.md` (deep-dive + agent roster + decision tree), `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

**Agent fleet:**
- Agent 2 (you): Backend integration — copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → new routes → tests
- Agent 3: cvserver alignment — verify fallback path, update INTEGRATIONS.md
- Agent 4: Frontend wiring — Solstice/Triad options, Zenith unchanged
- Agent 5: GSD execution — phase plans, kanban cards, tracking

**Tickets (traced to PHASE3_PUBLIC_API_PLAN.md §5):**

|- [ ] 3.1 Confirm key + source model — DONE. Key: `d84ic5pr01qutij93me0d84ic5pr01qutij93meg`. Connection model: COPY PublicBroker into floww (separate repos, no import path)
|- [ ] 3.2 Copy PublicBroker → floww backend — Agent 2 (`services/public_api.py`, 1050 lines; also `finnhub_client.py`, `finnhub_api.py`, `tests/services/test_public_api.py`)
|- [ ] 3.3 Add PUBLIC_API_KEY to floww .env + .env.example — Agent 2 (key confirmed, NOT committed — .env gitignored)
|- [ ] 3.4 Modify fetch_spot_and_chains_merged() — Agent 2 (Public API → cvserver → yfinance priority)
|- [ ] 3.5 Create `/api/public/chain/{ticker}` + `/api/public/quotes/{ticker}` routes — Agent 2 (new file `routes/public_api.py`)
|- [ ] 3.6 Tests — Agent 2 (test_public_api_integration.py: Public API success → cvserver fallback; ruff + pytest green)
|- [ ] 3.7 Update INTEGRATIONS.md + docs — Agent 3 (Public API = primary; cvserver = fallback)
|- [ ] 3.8 Frontend wiring — Agent 4 (Solstice/Triad options, spot price, Zenith unchanged)
|- [ ] 3.9 Phase 3 execution tracking — Agent 5 (phase plans + kanban cards)

## Phase 4 — Tidehunter Pro Integration

**Goal:** Paid-tier fallback for heatmap when Public API is limited. **Only built if Phase 3 live testing shows real Public API limits.** Don't start until Phase 3 is verified against live Public API.

- [ ] 4.1 Tidehunter Pro API assessment — endpoints, data shape, rate limits, cost
- [ ] 4.2 Fallback routing — Solstice heatmap detects Public API limit → Tidehunter Pro
- [ ] 4.3 Threshold policy — when Tidehunter kicks in vs. just waiting for Public API recovery

> **Note:** Zenith is a UI tab (legacy Skylit GEX grid), NOT a data service. API calls do NOT route to Zenith. Zenith displays data produced by Solstice/Triad/Tidehunter Pro — no API changes needed for Zenith itself.

## Phase 5 — Frontend Public API Wiring

- [ ] 5.1 Solstice (Heatseeker) tab: Public API chain → GEX computation pipeline
- [ ] 5.2 Triad tab: multi-ticker confluence from Public API chains
- [ ] 5.3 Tidehunter Pro tab: live flow from Public API (primary) or Tidehunter Pro feed (fallback)
- [ ] 5.4 Zenith tab: legacy display — no API changes, data comes from above layers

## Phase 6 — Later Backlog Phases (unpromoted)

Quant analytics (B), ML pipeline (C), Backtester (D), Alert DSL (E), Trading
execution (F), Portfolio & P&L (G), Observability & ops incl. Prometheus (I),
Quality processes & ADRs (J) — from `BACKLOG.md` Pending list. Promote into
numbered phases when prioritized.
