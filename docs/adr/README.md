# Architecture Decision Records — Index

ADRs capture architecturally significant decisions with their context and
consequences. Numbered sequentially; never rewritten — supersede instead.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-model-promotion-policy.md) | Model promotion policy (4 gates) | Accepted | 2026-07 |

## Conventions

- Filename: `NNNN-short-title.md` (zero-padded, lowercase, hyphens)
- Sections: Status / Context / Decision / Consequences
- Superseding an ADR: mark the old one `Superseded by NNNN`, link both ways

## Candidate decisions worth recording (from BACKLOG / GSD CONCERNS)

- DuckDB engine lifecycle & teardown registry (`services/duckdb_engine.py`)
- Module-global singleton memoization pattern in routes (hazard documented in `.planning/LEARNINGS.md`)
- torch excluded from production image (`Dockerfile.backend`)
- Mongo FTDC disabled + healthcheck rationale (`deploy/free/docker-compose.yml`)
