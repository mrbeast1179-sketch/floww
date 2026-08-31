"""
.planning/phases/phase-4-tidehunter-pro/REQUIREMENTS.md

Phase 4 — Tidehunter Pro Integration

Requirements (traced to ROADMAP.md §Phase 4 + PHASE3_PUBLIC_API_PLAN.md §6):

R4.1 — API Assessment
  - [ ] Identify Tidehunter Pro API endpoints for options chain + heatmap data
  - [ ] Document data shape (compare to PublicBroker.get_option_chain_parsed output)
  - [ ] Document rate limits (requests/minute, daily cap)
  - [ ] Document cost (per-call, per-month, tiers)
  - [ ] Document auth model (API key, OAuth, etc.)
  - [ ] Output: `.planning/phases/phase-4-tidehunter-pro/TIDEHUNTER_PRO_API.md`

R4.2 — Fallback Routing
  - [ ] Solstice heatmap endpoint detects Public API failure/limit
  - [ ] Automatic fallback to Tidehunter Pro when threshold crossed
  - [ ] No user action required — transparent failover
  - [ ] Logs which source was used per request
  - [ ] Output: server.py patch + routes/tidehunter.py (if new router needed)

R4.3 — Threshold Policy
  - [ ] Define "Public API limited" — e.g. 3 consecutive 502s or 429s within 5min
  - [ ] Define cooldown — e.g. retry Public API every 30min after fallback
  - [ ] Define permanent disable — e.g. after 3 days of limits, flag for manual review
  - [ ] Document in AGENT_CONTRACT.md data source decision tree
  - [ ] Output: updated AGENT_CONTRACT.md + DATA_SOURCES.md

Acceptance criteria:
  AC4.1 — Tidehunter Pro API assessment document exists with endpoints, shape, limits, cost
  AC4.2 — Solstice heatmap returns data from Tidehunter Pro when Public API is limited
  AC4.3 — Threshold policy documented and implemented (auto-failover + cooldown + review flag)

Out of scope:
  - Replacing Public API as primary source
  - Building Tidehunter Pro UI tab (Phase 5.3 if needed)
  - Any work before 4.1 assessment is complete

Gating condition:
  Phase 4 work STARTS only when Phase 3 live testing confirms Public API limits.
  If Public API stays healthy for 2+ weeks → Phase 4 may be skipped entirely.
"""
