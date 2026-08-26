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

## Phase 3 — Data Layer Hardening (BACKLOG Phase A)

- [ ] 3.1 Data-layer schema and migrations (R3.1)
- [x] 3.2 Repository pattern — `services/ml_repository.py` shipped; all ml_api.py sites migrated (`280890f`, agent 2)
- [ ] 3.3 Data collection service with proper error handling (R3.3)
- [x] 3.4 Data quality checks — /api/data-quality/{ticker} cross-source GEX consistency endpoint shipped (`a34980f`)

## Phase 4 — Code Hygiene Sweep

**Goal:** Burn down actionable discovered issues from `BACKLOG.md`.

- [x] 4.1 `iron_condible` typo — already fixed in paper_trading.py (verified: DEFAULT_STRATEGY="iron_condor")
- [ ] 4.2 `portfolio.py`: floats → Decimal per operating law 4 (R3.8)
- [x] 4.3 Alert engine de-hardcoding (R3.9) — done by agent 1 in `beb02cc` (ALERT_TYPE_CATALOG single-source, 12 types)
- [x] 4.4 Process hygiene: ADR index + PR template shipped (`900130f`)

## Phase 5 — Frontend Architecture (BACKLOG Phase H)

- [ ] 5.1 Decompose `App.js` (architect-approved, frozen-file constraint) (R3.6)
- [ ] 5.2 Introduce TanStack Query for server state (R3.7)

## Phase 6+ — Later Backlog Phases (unpromoted)

Quant analytics (B), ML pipeline (C), Backtester (D), Alert DSL (E), Trading
execution (F), Portfolio & P&L (G), Observability & ops incl. Prometheus (I),
Quality processes & ADRs (J) — from `BACKLOG.md` Pending list. Promote into
numbered phases when prioritized.
