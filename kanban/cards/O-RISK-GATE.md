---
id: O-RISK-GATE
title: Risk gate module with circuit breakers + kill switch + Kelly sizer
assignee: Agent 8
skill: software-development:systematic-debugging + software-development:test-driven-development
estimate_hours: 4
dependencies: []
status: in_progress
created_at: 2026-05-22T02:30:00Z
last_update: 2026-05-22T02:30:00Z
commits: []
blockers: []
---

## Goal
Extract risk gates from signal_translator.py into dedicated modules with circuit breaker pattern.
Port swarmSPX's risk architecture to floww.

## Files to Create
- `backend/services/risk/gate.py` — Pre-trade risk gate with multi-trigger circuit breakers
- `backend/services/risk/killswitch.py` — Daily loss kill switch
- `backend/services/risk/sizer.py` — Kelly position sizer with daily lock
- `backend/services/risk/__init__.py` — Package init
- `backend/tests/services/risk/test_gate.py` — 15+ tests
- `backend/tests/services/risk/test_killswitch.py` — 10+ tests
- `backend/tests/services/risk/test_sizer.py` — 10+ tests

## Reference
- swarmSPX: risk/gate.py, risk/sizer.py, risk/killswitch.py
- Almgren-Chriss (2001) for sizing
- Reports: reports/lesson_transfer.md

## Acceptance Criteria
- [ ] Risk gate rejects trades exceeding position limits
- [ ] Circuit breaker triggers after 3 consecutive losses
- [ ] Daily loss lock prevents trading after -2% daily P&L
- [ ] Kelly sizer computes optimal position size
- [ ] All 35+ tests pass
- [ ] signal_translator.py imports from risk/ instead of inline checks
