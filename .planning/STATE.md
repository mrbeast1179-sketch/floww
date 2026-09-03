# STATE.md — Confluence Decoder

**Last updated:** 2026-08-31
**Branch:** `main` @ 79b047e (docs(gsd): Phase 5 complete — all 4 tickets delivered, planning + kanban closed)
**Tests:** backend 4606 passed, 64 skipped, 1 xfailed, 0 failed · frontend OptionsChainTable 10/10 + FlowseekerProBlademap 17/17 passing
**Lint:** ruff (E, E722, F, W, I; ignore E501)

## Project position

Deploy package hardened and ready: Oracle Always Free runbook
(`deploy/free/README.md`), `oracle-setup.sh` + read-only deploy key
`oracle-vm-deploy`, docker-compose stack behind Caddy. **Awaiting Nav's VM
provisioning** — Phase 1 of ROADMAP.md starts the moment the VM exists.

**Last updated:** 2026-08-31
**Branch:** `main` @ 7e6ac70 (chore(kanban): refresh bottleneck alerts timestamp)
**Tests:** backend 4543 passed, 53 skipped, 1 xfailed, 6 pre-existing failures · frontend OptionsChainTable 10/10 + FlowseekerProBlademap 17/17 passing
**Lint:** ruff (E, E722, F, W, I; ignore E501)

## Project position

Deploy package hardened and ready: Oracle Always Free runbook
(`deploy/free/README.md`), `oracle-setup.sh` + read-only deploy key
`oracle-vm-deploy`, docker-compose stack behind Caddy. **Awaiting Nav's VM
provisioning** — Phase 1 of ROADMAP.md starts the moment the VM exists.

## Current phase

Phase 6 — Backlog Promotion [ACTIVE]. Phase 4 (Tidehunter Pro) is gating-only scaffolding. Phase 3 [CLOSED 2026-08-31]. Phase 5 [COMPLETE 2026-08-31]. Phase 6.2/6.4/6.6 done; 6.1/6.3/6.5 remaining.

## Key context

- Round 9 closed at `4e1c1b8`; Round 10 plan at `docs/ROUND10_PLAN.md`
  (P0.1 conftest waiver applied; P0.2 fetch_spot_and_chains restore and P0.3
  STALE_IMPORT cleanup tracked in Phase 2).
- Forbidden files per CLAUDE.md: `ml/inference.py`, `dash_ui.py`,
  `backend/tests/conftest.py` (R10 waiver), model artifacts under `backend/models/`,
  `frontend/.env`, `package.json`, `craco.config.js`, `frontend/src/App.js`.
- pytest.ini uses `[pytest]` header with asyncio_mode=auto; flaky_env marker
  registered (see `.planning/LEARNINGS.md` for why).
- Codebase intel: `.planning/codebase/` (7 GSD map docs).

## Log

- 2026-08-24 — Ingest-docs bootstrap: PROJECT.md / REQUIREMENTS.md / ROADMAP.md /
  STATE.md / config.json created from curated manifest (8 docs); round transcripts
  excluded as historical noise.
- 2026-08-31 — Phase 3 closed, Phase 5 complete (all 4 tickets delivered). 7 files
  damaged by commit 79b047e (ROADMAP.md shred to 7 lines) — restored + all stale
  kanban/planning docs refreshed.
- 2026-09-03 — Phase 7 complete (public-api-only + trade-direct): Schwab/Alpha
  Vantage retired (410s, disabled stubs, fail-closed client); new
  /api/public/{bars,history,technical,expirations}; Triad row-click enriched
  with Public OSI+prices → real order path; fallback public→cvserver→yfinance
  reaffirmed. 7.5 (Heatseeker submit in frozen App.js) flagged for Nav.
- 2026-09-03 — Phase 8 complete (open universe + Meridian fixes): PAID gate
  removed, greeks/flow opened, ticker-bar free-text search; Dual-GEX numba
  gamma, IV-Mid reason codes + T floor, Wheel 30s cache + 429 exemption;
  Solstice band behind Signals toggle, grid expand overlay, toolbar buttons
  live. 8.6 (App.js-owned leftovers) flagged for Nav.
