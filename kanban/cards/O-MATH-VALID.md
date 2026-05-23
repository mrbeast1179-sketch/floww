---
id: O-MATH-VALID
title: Mathematical validation + ARCHITECTURE.md + RUNBOOK.md
assignee: Agent 5
skill: gbrain:academic-verify + data-science:jupyter-live-kernel + creative:architecture-diagram
estimate_hours: 3
dependencies: []
status: done
last_update: 2026-07-09T00:00:00Z
commits: [bf67257, 57ad384, 45bfbc4, c253856]
blockers: []
---

## Deliverable
Math validation suite extended, ARCHITECTURE.md, RUNBOOK.md, OpenAPI spec, walkthrough notebook

## Files
- `backend/tests/services/test_microstructure_math.py` (extend)
- `ARCHITECTURE.md` (new)
- `RUNBOOK.md` (new)
- `docs/api/openapi.json` (new)
- `docs/api/README.md` (new)
- `docs/notebooks/oracle_walkthrough.ipynb` (new)

## Validation Gaps
- Node lifecycle state machine
- MarketFragilityIndex composite
- Anomaly detector recall
- Trinity (2 skipped tests now know the signature)
- GEX zero-gamma detection
- VolSurfaceConstructor term structure monotonicity

## Acceptance Criteria
- [ ] All validation gaps covered by tests
- [ ] ARCHITECTURE.md with mermaid data-flow diagrams
- [ ] RUNBOOK.md with operational procedures
- [ ] OpenAPI spec for all routes
- [ ] Walkthrough notebook executable
- [ ] All commits conventional
