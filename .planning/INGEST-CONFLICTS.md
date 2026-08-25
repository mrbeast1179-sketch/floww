# INGEST-CONFLICTS.md

Ingest run: 2026-08-24 · mode=new · manifest=`.planning/ingest-manifest.yml` (8 docs)

### BLOCKERS (0)

None.

### WARNINGS (3)

**W1 — structlog status contradiction (ARCHITECTURE.md vs BACKLOG.md).**
ARCHITECTURE.md Operating Law 5 states "All services use `structlog` with JSON
output in production" as an existing law; BACKLOG.md Discovered Issues lists "No
structured logging (need structlog)". Resolution recorded here rather than chosen:
REQUIREMENTS.md R3.10 keeps the backlog item flagged; treat ARCHITECTURE.md as
aspirational or partially adopted until audited.

**W2 — Frontend tests existence contradiction (BACKLOG.md vs CLAUDE.md).**
BACKLOG.md says "No frontend tests"; CLAUDE.md current state reports 277 frontend
tests passing via craco. CLAUDE.md (2026-08-24, more recent) wins; BACKLOG.md line
is stale. No requirement created for adding frontend tests.

**W3 — Deploy target naming (deploy/free/README.md vs task identity).**
The runbook presents Azure B1s and Oracle Always Free as equal options ("pick one")
and is titled "Going Live Free", while project identity and current state fix the
target as **Oracle Always Free ARM**. Roadmap Phase 1 follows the fixed target;
Azure path retained in REQUIREMENTS R1.1 as documented fallback only.

### INFO (4)

**I1 — IMPLEMENTATION_PLAN.md type mismatch.** Manifest declares it `PLAN`, but it
is a Skylit/GitHub competitive-research findings doc with an older feature
implementation plan (VEX/DEX histograms etc.). Used only as historical feature
context; not promoted into requirements (traceability rule).

**I2 — ROUND10 P0.1 already applied.** ROUND10_PLAN lists P0.1 as open work;
CLAUDE.md current state records the conftest waiver as applied (23 → 0 collection
errors). Recorded as done in ROADMAP Phase 2 with a verification step.

**I3 — App.js decomposition vs frozen-file rule.** BACKLOG.md wants App.js
decomposed; CLAUDE.md freezes App.js to surgical edits with approval. Kept as a
later phase gated on architect approval.

**I4 — ~40 round-transcript MD files excluded.** DEEPSEEK_*, ROUND8/9_*,
DISPATCH_* files at repo root and docs/ are historical session noise per manifest
intent and were not ingested.
