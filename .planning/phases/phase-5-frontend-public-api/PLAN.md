"""
.planning/phases/phase-5-frontend-public-api/PLAN.md

Phase 5 — Frontend Public API Wiring

**Status:** [ACTIVE] — 5.1 Solstice chain table Public API direct path IMPLEMENTED
**Parent:** ROADMAP.md §Phase 5
**Source:** `.planning/PHASE3_PUBLIC_API_PLAN.md` §5 (frontend section)

Goal:
  Wire the new /api/public endpoints into the React frontend.
  Public API becomes the primary chain source for Solstice/Triad.
  Zenith stays display-only — no API changes.

Don't start until:
  - Backend live-tested with real PUBLIC_API_KEY (curl /api/public/chain/SPY green)
  - Public API rate limits or data gaps verified in production logs

Tickets:
  5.1 Solstice (Heatseeker) tab: use /api/public/chain for options data
  5.2 Triad tab: multi-ticker confluence from Public API chains
  5.3 Tidehunter Pro tab: live flow from Public API (primary) or Tidehunter Pro feed (fallback)
  5.4 Zenith tab: legacy display — no API changes, data comes from above layers

Decision rule:
  If Backend live testing shows Public API works reliably → proceed with 5.1 → 5.2 → 5.3.
  If Public API is limited → Phase 4 Tidehunter Pro kicks in first.
  Zenith never changes — it's display-only.

Agent assignments:
  Agent 4 (frontend) — 5.1 + 5.2 + 5.3
  Agent 5 — GSD tracking

What's NOT in scope:
  - Replacing existing /api/chain or /api/data endpoints (they stay for cvserver fallback)
  - Zenith tab changes (display-only, no API changes)
  - Any frontend work before 5.1 is committed and verified

Phase 5 activation:
  Backend live test green → spawn Agent 4 → implement 5.1 → verify →
  implement 5.2 → verify → implement 5.3 → verify → commit.

Acceptance criteria:
  AC5.1 — Solstice tab fetches options chain from /api/public/chain and displays it
  AC5.2 — Triad tab can pull multi-ticker chains from Public API
  AC5.3 — Tidehunter Pro tab shows live flow from Public API (primary) or Tidehunter feed (fallback)
  AC5.4 — Zenith tab unchanged
"""

