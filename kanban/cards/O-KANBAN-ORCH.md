---
id: O-KANBAN-ORCH
title: Kanban orchestrator + agent-hardening continuous loop
assignee: Agent 8
skill: devops:kanban-orchestrator + autonomous-ai-agents:kanban-codex-lane + hermeshub:agent-hardening
estimate_hours: -1
dependencies: []
status: done
last_update: 2026-05-19T20:30:00Z
commits: [11caa4e]
blockers: []
---

## Deliverable
Auto-scheduling kanban workflow that survives Nav going to sleep. Board state in kanban/ directory, watcher loop, worker dispatch hooks, auto-archive.

## Files
- `kanban/board.yaml` (new)
- `kanban/cards/*.md` (new)
- `kanban/closed/` (new)
- `kanban/SWARM_STATUS.md` (new)
- `kanban/INCIDENTS.md` (new)
- `backend/tests/test_kanban.py` (new)

## Job
- Pulls tasks from the kanban board
- Dispatches to swarm workers
- Tracks completion via git log scanning
- Archives done cards
- Surfaces blockers to Nav

## Acceptance Criteria
- [x] Board state fully YAML + markdown
- [x] Watcher loop running (5-min cadence)
- [x] WIP limit enforcement (max 6 in_progress)
- [x] Auto-archive after 24h
- [x] 23 tests on schema + transitions (run with --noconftest)
- [x] All commits conventional: `feat(kanban): ...`
