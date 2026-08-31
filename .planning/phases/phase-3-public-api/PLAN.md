# Phase 3 — Public API Data Layer

## Phase Overview

**Goal:** Wire PublicBroker (from `/Users/nav/backend/`) into floww as the PRIMARY data source for options chains + spot prices. Replace cvserver as primary chain source. Fallback chain: Public API → cvserver → yfinance + Databento. Tidehunter Pro is Phase 4 only.

**Status:** PLANNING → EXECUTION

**Source of truth:** `.planning/PHASE3_PUBLIC_API_PLAN.md`, `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

## Requirements (traced from ROADMAP.md §3)

| Ticket | Requirement | Owner | Status |
|---|---|---|---|
| 3.1 | Public API key confirmed | — | DONE |
| 3.2 | Copy PublicBroker → floww backend | Agent 2 | TODO |
| 3.3 | Add PUBLIC_API_KEY to .env + .env.example | Agent 2 | TODO |
| 3.4 | Modify fetch_spot_and_chains_merged() priority | Agent 2 | TODO |
| 3.5 | Create /api/public/chain/{ticker} + /api/public/quotes/{ticker} | Agent 2 | TODO |
| 3.6 | Tests: chain + fallback routing | Agent 2 | TODO |
| 3.7 | Update INTEGRATIONS.md docs | Agent 3 | TODO |
| 3.8 | Frontend wiring (Solstice/Triad) | Agent 4 | TODO |
| 3.9 | Phase tracking | Agent 5 | IN PROGRESS |

## Verification Loop

1. Unit tests: `python3 -m pytest tests/services/test_public_api_integration.py -v` (≥5 tests, must fail before fix, pass after)
2. Integration test: curl `/api/public/chain/SPY` returns structured chain data
3. ruff: `ruff check backend/services/public_api.py backend/routes/public_api.py`
4. No existing tests broken: `pytest -q` ≥ 4546 passed

## Key Decisions

- Connection model: COPY (not import) — two separate repos
- PublicBroker data shape must be adapted to match cvserver_client.py output format for backward compatibility with existing consuming code
- New routes under /api/public/ namespace — does NOT change existing /api/chain route
