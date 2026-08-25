# Testing Patterns

**Analysis Date:** 2026-08-24

## Test Framework

**Backend:**
- pytest with `asyncio_mode=auto` (pytest.ini uses `[pytest]` section — async tests need no decorators)
- Interpreter: always `backend/.venv/bin/python3`

**Frontend:**
- Jest via create-react-app + craco
- Canonical command: `npx craco test --watchAll=false`

**Run Commands:**
```bash
cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5        # full sweep + pass count
cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3 # collection check
cd backend && .venv/bin/python3 -m pytest tests/services/ -k <kw> -v       # targeted
cd frontend && npx craco test --watchAll=false                             # frontend suite
cd backend && .venv/bin/ruff check .                                       # lint (CI gate too)
```

## Test File Organization

```
backend/
  tests/
    conftest.py          # shared fixtures (architect-frozen; R10 P0.1 waiver)
    test_*.py            # top-level feature suites (e.g., test_heatseeker_v2.py)
    services/            # unit/service-layer tests (test_flow_desk.py, ...)
    routes/              # API endpoint tests (test_llm_endpoints.py, test_health.py)
    integration/         # cross-module integration tests
    stateful/            # stateful/session-persistence tests
frontend/
  src/
    __tests__/           # Jest component/util tests (*.test.js)
```

## Markers

- `flaky` — known-intermittent tests (e.g., used in `backend/tests/test_heatseeker_v2.py`, `backend/tests/test_vpin_toxicity.py`)
- `flaky_env` — environment-dependent failures; pass locally, may fail in CI (see CONCERNS.md)
- `slow` — long-running tests excluded from quick sweeps

Do NOT add skip/xfail markers to passing tests without architect approval.

## Key Fixtures (`backend/tests/conftest.py`)

- `fresh_engine` — isolated DuckDB engine per test (teardown registry closes it after each test; see `backend/services/duckdb_engine.py` line ~94)
- `seeded_quality_db` — pre-populated data-quality DB for quality-gate tests
- `aclient` — async httpx client bound to the FastAPI app for route tests

## Current Pass Counts (as of 2026-08-24)

- Backend: ~4,546 passed via `.venv/bin/python3 -m pytest -q`
- Frontend: ~277 passed via `npx craco test --watchAll=false`
- Known exceptions: 7 env-dependent failures that appear only in CI (see CONCERNS.md)

## Test Discipline (non-negotiable)

- A test you write MUST fail before your fix and pass after.
- Never mark a previously-passing test skip/xfail.
- Include the real pytest/curl output as verification evidence in commit bodies.

---

*Testing analysis: 2026-08-24*
*Update when test patterns change*
