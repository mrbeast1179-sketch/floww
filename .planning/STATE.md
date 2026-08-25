# STATE.md — Confluence Decoder

**Last updated:** 2026-08-24
**Branch:** `main` @ latest (origin/main)
**Tests:** backend ~4546 passed (full suite ~6.5 min) · frontend 277 passed
(`npx craco test --watchAll=false`)
**Lint:** ruff (E, E722, F, W, I; ignore E501)

## Project position

Deploy package hardened and ready: Oracle Always Free runbook
(`deploy/free/README.md`), `oracle-setup.sh` + read-only deploy key
`oracle-vm-deploy`, docker-compose stack behind Caddy. **Awaiting Nav's VM
provisioning** — Phase 1 of ROADMAP.md starts the moment the VM exists.

## Current phase

Phase 1 — Oracle Go-Live (pending VM). No phase plans yet.

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
