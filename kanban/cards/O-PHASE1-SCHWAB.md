---
id: O-PHASE1-SCHWAB
title: Phase 1 — Schwab WS ingestion
assignee: Agent 1
skill: swarmclaw:coding-agent + hermeshub:api-builder
estimate_hours: 4
dependencies: []
status: done
last_update: 2026-07-09T00:00:00Z
commits: [eb711f0, eb373a0, 91e4653, 66abeb6]
blockers: []
---

## Deliverable
Real WS feed pushing into DuckDB at 50ms batch intervals; mock feed for CI; 15+ tests

## Files
- `backend/services/schwab_streamer.py` (new)
- `backend/services/ingestion_pipeline.py` (new)
- `backend/services/mock_schwab_feed.py` (new)
- `backend/tests/services/test_ingestion_pipeline.py` (new)

## Reference
- `tylerebowers/Schwabdev` (clone into `data/github-repos/cloned/` if not present)

## Acceptance Criteria
- [ ] WebSocket connection to Schwab streaming API
- [ ] DuckDB writes at 50ms batch intervals
- [ ] Mock feed for CI testing
- [ ] 15+ tests passing
- [ ] All commits conventional: `feat(ingestion): ...`
