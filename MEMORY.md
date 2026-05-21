# MEMORY.md — Project Oracle (floww)

**CANONICAL FLOWW = /Users/nav/Documents/GitHub/floww**
See [CONSOLIDATION_REPORT.md](CONSOLIDATION_REPORT.md) for the full consolidation record.

This file is the canonical memory index for the floww project.
It is synced bidirectionally with mem0 and Obsidian.

## Project Tag
All entries in this project are tagged `project:floww`.

## Active Memory

- [Project Oracle directive](project_oracle.md) — May 2026 master directive; supersedes CLAUDE_REVIEW_PROMPT.md
- [Master plan operating laws](project_master_plan.md) — no synthetic data, baseline-first, OOS-locked
- [Skylit feature parity](project_skylit.md) — commercial target; gap list in SKYLIT_FEATURES.md
- [Research pipeline](project_research_pipeline.md) — arxiv discovery → URL extraction → clone → extract patterns
- [Herder swarm regime](reference_herder_swarm.md) — skill arsenal and dispatch patterns
- [Truth-audit](reference_truth_audit.md) — qc/audit/truth_audit.sh runs every session start
- [Tool boundaries](project_tool_boundaries.md) — CLI/Bash/Python/git only; Nav drives IDEs

## Cross-Project Memory

To query across all projects:
  ask-hermes --all-projects "query here"

To query floww only (default for trading queries):
  ask-hermes "query here"

## Memory System

- **Backend:** mem0 Platform (agent mode)
- **User ID:** user_c778280e23af
- **Agent caller:** hermes
- **Consolidation:** scripts/consolidate_memory_daily.py (daily @ 4am)
- **Pruning:** scripts/prune_memory.py (nightly, session entries > 30d)
- **Auto-tagging:** scripts/auto_tag_memory.py (on insert)
- **CLI:** scripts/ask_hermes.py (semantic search + git + kanban)
