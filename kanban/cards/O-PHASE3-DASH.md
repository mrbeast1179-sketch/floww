---
id: O-PHASE3-DASH
title: Phase 3 — Dash UI real-time data binding
assignee: Agent 3
skill: swarmclaw:coding-agent + creative:architecture-diagram
estimate_hours: 4
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
/dashboard/ at parity with Skylit's commercial Heatseeker/Flowseeker

## Files
- `backend/services/dash_ui.py` (extend)
- `backend/tests/services/test_dash_ui.py` (new)

## Tabs to make live
- Heatseeker (GEX heatmap + King Nodes + Air Pockets)
- Flowseeker (scrolling ticker)
- Toxicity Gauge (VPIN+QI)
- Vol Surface (3D SABR/SVI)
- Trinity Alignment

## Acceptance Criteria
- [ ] All 5 tabs rendering live data
- [ ] WebSocket data binding working
- [ ] Tests for dash_ui service
- [ ] All commits conventional
