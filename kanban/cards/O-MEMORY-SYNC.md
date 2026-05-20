---
id: O-MEMORY-SYNC
title: Obsidian bidirectional sync + memory unification
assignee: Agent 9
skill: note-taking:obsidian + mem0:mem0-integrate + honcho:honcho-memory
estimate_hours: 2
dependencies: []
status: done
last_update: 2026-05-19T22:10:00Z
commits: [d181391, 88a2bfea]
blockers: []
---

## Deliverable
Memory system upgraded: consolidation, auto-tagging, CLI query, pruning, cross-project support.

## Files Created
- `scripts/consolidate_memory_daily.py` — daily dedup + stale ref detection
- `scripts/auto_tag_memory.py` — auto-tag on insert with controlled taxonomy
- `scripts/ask_hermes.py` — CLI for semantic search over mem0 + git + kanban
- `scripts/prune_memory.py` — nightly pruning of old session entries
- `scripts/install_ask_hermes.py` — installer for ask-hermes command
- `memory/_tag_taxonomy.yaml` — controlled tag vocabulary
- `MEMORY.md` — canonical memory index
- `deploy/cron.d/hermes-memory` — cron definitions
- `~/Library/LaunchAgents/com.hermes.memory.consolidate.plist` — launchd agent
- `~/Library/LaunchAgents/com.hermes.memory.prune.plist` — launchd agent

## Acceptance Criteria
- [x] Consolidation script with dry-run mode
- [x] Auto-tagger with taxonomy and review queue
- [x] ask-hermes CLI with JSON output
- [x] Pruning policy preserving durable types
- [x] Cross-project tagging (floww/gflows/baby-billy-dvt/personal)
- [x] launchd agents installed and loaded
- [x] All commits conventional: `feat(memory): ...` / `feat(cli): ...`
