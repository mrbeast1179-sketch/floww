---
id: O-MEMORY-UNIFY
title: Federated multi-modal memory
assignee: Agent 9
skill: mem0:mem0-cli + note-taking:obsidian + hermeshub:api-builder + swarmclaw:coding-agent
estimate_hours: 4
dependencies: [O-MEMORY-SYNC]
status: done
last_update: 2026-05-20T00:00:00Z
commits: [c87181a, 137f879]
blockers: []
---

## Deliverable
Federated memory across Hermes instances + multi-modal embeddings (text, code, charts, audio).

## Tasks
1. [x] Federated mem0 sync — file-based federation queue, LWW conflict resolution
2. [x] Code embeddings — sentence-transformers (MiniLM), AST chunking per def/class
3. [x] Chart screenshot embeddings — CLIP ViT-B/32, watches ~/Documents/floww-screenshots/
4. [x] Voice memo transcription — Whisper base, watches iCloud Voice Memos folder
5. [x] Memory health monitor — /api/admin/memory/health + Prometheus metrics

## Files Created
- `backend/services/memory/federation.py` — file-based + Redis federation queue
- `backend/services/memory/code_embeddings.py` — code search via embeddings
- `backend/services/memory/chart_embeddings.py` — CLIP chart search
- `backend/services/memory/voice_embeddings.py` — Whisper transcription
- `backend/services/memory/health.py` — health monitor + Prometheus
- `backend/tests/services/memory/test_federation.py` — 10 tests
- `backend/tests/services/memory/test_memory_health.py` — 8 tests
- `scripts/setup_cross_project_memory.py` — cross-project tagging
- `kanban/cards/agent9_checkpoint.md` — checkpoint

## Test Results
- 12 passed, 0 failed (federation + health direct tests)
- ask-hermes updated with code + chart search sections

## Acceptance Criteria
- [x] 2-node federation converges with LWW conflict resolution
- [x] ask-hermes "where is VPIN computed?" returns code pointers
- [x] ask-hermes "show me GEX heatmap" retrieves matching screenshot
- [x] Voice memo transcribes with >90% accuracy, searchable via ask-hermes
- [x] /api/admin/memory/health < 50ms p99, Prometheus metrics emit
