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

## Phase 3 — Public API Data Layer [NEXT]

**Goal:** Replace mock/Schwab-dependent chain data with Public API brokerage feeds. Heatmap (Solstice) uses Public API as primary, Tidehunter Pro as fallback. Building all data flow around Public API — not Schwab, not Zenith.

**Source:** `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

|- [ ] 3.1 Confirm which Public API key is active — user-provided `d84ic5pr01qutij93me0d84ic5pr01qutij93meg` vs env.example `PkdDGcMzqMie0f6I823q6nHtmkGJyRsu`; the user-provided key supersedes
|- [ ] 3.2 Audit `/Users/nav/backend/services/public_api.py` — existing `PublicBroker` class, full chain/quotes/portfolio/orders/greeks/bars pipeline, tested in `test_public_api.py` (547 lines)
|- [ ] 3.3 Decide connection model — copy/import PublicBroker into floww backend vs. HTTP service vs. new data provider alongside cvserver_client
|- [ ] 3.4 Wire Public API as primary chain source for Solstice heatmap (replace/augment cvserver as primary)
|- [ ] 3.5 Add `/api/public/chain/{ticker}` endpoint to floww backend using PublicBroker
|- [ ] 3.6 Add `/api/public/quotes/{ticker}` endpoint for spot price
|- [ ] 3.7 Rate-limit / degradation handling — Public API limit → Tidehunter Pro fallback; yfinance spot fallback

## Phase 4 — Tidehunter Pro Integration

**Goal:** Paid-tier fallback for heatmap when Public API is limited. Only built if Public API has real limits — don't over-build before knowing the constraints.

- [ ] 4.1 Tidehunter Pro API assessment — endpoints, data shape, rate limits, cost
- [ ] 4.2 Fallback routing — Solstice heatmap detects Public API limit, switches to Tidehunter Pro seamlessly
- [ ] 4.3 Threshold policy — when does Tidehunter kick in vs. just waiting for Public API recovery

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
