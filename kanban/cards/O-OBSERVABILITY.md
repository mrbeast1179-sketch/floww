---
id: O-OBSERVABILITY
title: Observability + alerting
assignee: Agent 10
skill: swarmclaw:coding-agent + mlops:evaluating-llms-harness
estimate_hours: 3
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
`docker-compose up observability` brings Prometheus + Grafana with pre-built Oracle dashboards

## Files
- `backend/services/observability.py` (new)
- `docker-compose.observability.yml` (new)
- Prometheus/Grafana configs

## Metrics
- messages/sec ingested
- DuckDB queue depth
- VPIN current value per ticker
- Trinity score
- Anomaly detector latency
- FastAPI request rate + p99 latency

## Acceptance Criteria
- [ ] Prometheus metrics endpoints working
- [ ] Grafana dashboards pre-built
- [ ] All metrics listed above available
- [ ] All commits conventional: `feat(observability): ...`
