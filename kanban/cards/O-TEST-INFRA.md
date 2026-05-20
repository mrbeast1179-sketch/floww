---
id: O-TEST-INFRA
title: Test infrastructure — close remaining event-loop failures
assignee: Agent 4
skill: swarmclaw:coding-agent + hermeshub:agent-hardening
estimate_hours: 2
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
581 pass / 0 fail / 15 skipped + CI coverage gate at 70%

## Files
- `backend/tests/conftest.py` (extend)
- `backend/tests/test_portfolio.py` (convert to AsyncClient)
- `backend/tests/test_v3_costsave.py` (same)
- `backend/tests/test_heatseeker_v2.py` (same)

## Diagnosis
Singleton in `backend/data_providers.py` (likely a `RateLimiter` with `asyncio.Lock` baked in at module load) holds stale loop ref

## Acceptance Criteria
- [ ] All event-loop RuntimeError failures resolved
- [ ] 581+ tests passing
- [ ] CI coverage gate at 70%
- [ ] All commits conventional: `test(infra): ...`
