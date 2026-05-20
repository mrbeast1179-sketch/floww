---
id: O-MEMORY-SYNC
title: Obsidian bidirectional sync + memory unification
assignee: Agent 9
skill: note-taking:obsidian + mem0:mem0-integrate + honcho:honcho-memory
estimate_hours: 2
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
One-way-of-doing-memory; pick mem0 OR honcho OR plur (recommend mem0) and migrate everything to it. Bidirectional sync Claude Code memory dir <-> Obsidian vault.

## Files
- `scripts/obsidian_sync.py` (new)
- `~/Obsidian-Vault/floww/*.md` (write)
- `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/*.md` (read/write)

## Job
Reconcile the three memory systems (honcho / plur / mem0) into one canonical surface. When Nav adds a note in Obsidian, it flows to memory; when an agent updates memory, it flows to Obsidian.

## Acceptance Criteria
- [ ] One memory system chosen and migrated to
- [ ] Bidirectional sync working
- [ ] All commits conventional: `feat(memory): ...`
