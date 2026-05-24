---
card_id: R7-AGENT6-KNOWLEDGE
title: "R7: Agent 6 — Knowledge Graph & Semantic Search"
status: done
assignee: Agent 6
round: 7
sha: 4c8df63
subject: "feat(retail-flow): add retail flow score nodes, price movements, and semantic search"
acceptance: "36 tests (19 graph + 17 search); Neo4j retail flow nodes with 11 metrics; NL query interface working"
insight: "Semantic search v2 over flow data enables NL questions like 'show me unusual SPY call activity' without SQL"
upstream: []
downstream: [R7-AGENT2-ML]
---

# R7: Agent 6 — Knowledge Graph & Semantic Search

## Summary
Neo4j knowledge graph with retail flow score nodes, price movements, and semantic search v2. 11 metrics tracked. Natural language query interface over flow data.

## Commits
- `4c8df63` — feat(retail-flow): add retail flow score nodes, price movements, and semantic search
- `e55b1ef` — fix(duckdb): update retail flow schema + load test report
- `2f6ac30` — feat(retail-flow): API route + Dash UI integration

## Acceptance Criteria
- [x] 36 tests (19 graph + 17 search) pass
- [x] 11 metrics tracked in Neo4j
- [x] NL query interface functional
- [x] 3 edge types defined
