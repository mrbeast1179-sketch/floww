---
id: O-KANBAN-ORCH
title: Kanban orchestrator + agent-hardening continuous loop
assignee: Agent 8
skill: devops:kanban-orchestrator + autonomous-ai-agents:kanban-codex-lane + hermeshub:agent-hardening
estimate_hours: -1
dependencies: []
status: in_progress
last_update: 2026-05-19T20:30:00Z
commits: []
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
- [ ] Board state fully YAML + markdown
- [ ] Watcher loop running (5-min cadence)
- [ ] WIP limit enforcement (max 6 in_progress)
- [ ] Auto-archive after 24h
- [ ] 10+ tests on schema + transitions
- [ ] All commits conventional: `chore(kanban): ...` / `feat(kanban): ...`
