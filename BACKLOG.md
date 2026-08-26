# BACKLOG.md — Confluence Decoder

> Synced with reality 2026-08-26 (GSD Phase 4.4 follow-up). Completed items moved to Done;
> resolved Discovered Issues annotated with their fix commits where known.
> Authoritative phase tracking now lives in `.planning/ROADMAP.md` (GSD).

## Active Phase: A — Data Layer ✅ COMPLETE

- [x] Data layer schema and migrations (`ad77c90` — versioned DuckDB migrations, agent 3)
- [x] Repository pattern for MongoDB access (`d54395c`, `280890f` — services/ml_repository.py, agent 2)
- [x] Data collection service with proper error handling (`640773c` — services/retry.py, jittered backoff)
- [x] Data quality checks and validation (`a34980f` — /api/data-quality/{ticker} cross-source GEX check)

## Pending

- [ ] Phase B: Quant analytics
- [ ] Phase C: ML pipeline
- [ ] Phase D: Backtester
- [ ] Phase E: Alert DSL
- [ ] Phase F: Trading execution
- [ ] Phase G: Portfolio & P&L
- [ ] Phase H: Frontend architecture
- [ ] Phase I: Observability & ops
- [ ] Phase J: Quality processes & ADRs

## Done

- [x] Initial project setup
- [x] Security audit and fixes
- [x] ML training pipeline
- [x] Cron jobs for data collection
- [x] WebSocket improvements
- [x] Paper trading module
- [x] Morning briefing email system
- [x] Round 10 P0 tickets (conftest, fetch_spot_and_chains, STALE_IMPORT)
- [x] KillSwitch wired into auto-trade pipeline (`2d23602`)
- [x] Columnar DuckDB bulk insert — ingestion 65x faster (`6648006`)
- [x] Rust decoder-core GEX path + volume-grid fallback (`98c8fd7`, `69691e4`)

## Discovered Issues — status as of 2026-08-26

| Issue | Status |
|---|---|
| `iron_condible` typo in paper_trading.py | ✅ Fixed (comment at line 42 documents it) |
| App.js needs decomposition | Open — 1128 lines; needs architect sign-off (ROADMAP 5.1) |
| No server-state library (TanStack Query) | Open (ROADMAP 5.2) |
| No frontend tests | Partially resolved — 277 tests across 46 suites |
| portfolio.py floats vs Decimal | Deferred by architect decision — upstream prices are floats; conversion adds risk without benefit for a research tool |
| Alert engine hardcodes alert types | ✅ Fixed (`beb02cc` — ALERT_TYPE_CATALOG single-source) |
| No structured logging | Open (structlog still absent; flagged in INGEST-CONFLICTS W1) |
| No Prometheus metrics | Open (Phase I) |
| No ADRs | ✅ ADR-0001 + index shipped (`docs/adr/`) |
| No PR template | ✅ Shipped (`900130f`) |
| No conventional commits enforcement | Partially — convention documented in CLAUDE.md; automated enforcement not added |

## Notes

- Deployment target: Oracle Always Free ARM (deferred — awaiting payment method).
  Runbook: `deploy/free/README.md` + Obsidian "Meridian Oracle Deploy".
- Test posture: backend ~4550 passed (~6.5 min), frontend 277 passed.
