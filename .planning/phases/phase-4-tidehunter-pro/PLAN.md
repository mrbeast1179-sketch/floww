# Phase 4 — Tidehunter Pro Integration

.planning/phases/phase-4-tidehunter-pro/PLAN.md

Phase 4 — Tidehunter Pro Integration

**Status:** [GATED] (contingency — do not build until live Public API limits are confirmed)
**Parent:** ROADMAP.md §Phase 4
**Source:** `.planning/PHASE3_PUBLIC_API_PLAN.md` §6 (Tidehunter Pro fallback design)

Goal:
  Paid-tier fallback for heatmap when Public API is limited.
  Only built if Phase 3 live testing shows real Public API limits.

Don't start until:
  - Phase 3 is live-tested with real PUBLIC_API_KEY
  - Public API rate limits or data gaps are confirmed in production logs

Tickets:
  4.1 Tidehunter Pro API assessment — endpoints, data shape, rate limits, cost
  4.2 Fallback routing — Solstice heatmap detects Public API limit → Tidehunter Pro
  4.3 Threshold policy — when Tidehunter kicks in vs. just waiting for Public API recovery

Decision rule:
  If Public API stays healthy for 2+ weeks in production → skip Phase 4 entirely.
  If limits appear → build 4.1 → 4.2 → 4.3 in order.

Agent assignments:
  Agent 4 (frontend) — 4.2 fallback routing in Solstice
  Agent 1 (you) — 4.1 API assessment + 4.3 threshold policy
  Agent 5 — GSD tracking

What's NOT in scope:
  - Replacing Public API as primary (it stays primary)
  - Building a Tidehunter Pro UI tab (Phase 5.3 covers that if needed)
  - Any frontend work before 4.1 assessment is done
