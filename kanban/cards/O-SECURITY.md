---
id: O-SECURITY
title: Security audit / godmode red-team pass
assignee: Agent 7
skill: red-teaming:godmode + hermeshub:agent-hardening
estimate_hours: 3
dependencies: []
status: ready
last_update: 2026-05-19T20:30:00Z
commits: []
blockers: []
---

## Deliverable
SECURITY_AUDIT.md updated with findings + severity (Critical / High / Medium / Low) + concrete fixes for Criticals + Highs

## Files
- `SECURITY_AUDIT.md` (extend)
- `qc/audit/security_*.sh` (new)
- `backend/middleware/` (potentially new)

## Scope
- .env exposure (verify; `git log --all --full-history -- backend/.env`)
- All routes for auth/authz gaps (mutating endpoints especially)
- Rate-limiter resilience (race conditions, bypass paths)
- Input validation on every POST/PUT/PATCH (Pydantic models present?)
- CORS configuration (no `*` with credentials)
- WebSocket auth (the new `/ws/{topic}` endpoint must authenticate)
- Mongo/Schwab credential handling in process memory
- Dash UI access control (anyone on the LAN should not see Schwab data)

## Acceptance Criteria
- [ ] All scope items audited
- [ ] Findings documented with severity
- [ ] Critical + High fixes implemented
- [ ] All commits conventional: `chore(security): ...`
