---
id: O-MEMORY-UNIFY
title: Federated multi-modal memory
assignee: Agent 9
skill: mem0:mem0-cli + note-taking:obsidian + hermeshub:api-builder + swarmclaw:coding-agent
estimate_hours: 4
dependencies: [O-MEMORY-SYNC]
status: in_progress
last_update: 2026-05-20T00:00:00Z
commits: []
blockers: []
---

## Deliverable
Federated memory across Hermes instances + multi-modal embeddings (text, code, charts, audio).

## Tasks
1. [ ] Federated mem0 sync — file-based federation queue, LWW conflict resolution
2. [ ] Code embeddings — CodeBERT via sentence-transformers, chunk per def/class
3. [ ] Chart screenshot embeddings — CLIP, watch ~/Documents/floww-screenshots/
4. [ ] Voice memo transcription — Whisper, watch iCloud Voice Memos folder
5. [ ] Memory health monitor — /api/admin/memory/health endpoint + Prometheus metrics

## Acceptance Criteria
- [ ] 2-node federation converges with LWW conflict resolution
- [ ] ask-hermes "where is VPIN computed?" returns code pointers
- [ ] ask-hermes "show me GEX heatmap" retrieves matching screenshot
- [ ] Voice memo transcribes with >90% accuracy, searchable via ask-hermes
- [ ] /api/admin/memory/health < 50ms p99, Prometheus metrics emit
