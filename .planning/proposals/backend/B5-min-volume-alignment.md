# Backend Proposal B5 — Min Volume Alignment

**Proposed by:** Agent 3 (Backend/Data lane) · **Status:** PROPOSAL — needs Agent 1 gate decision + BACKEND_LANE_OWNER=1
**Depends on:** HANDOFF B5, FULL_PLAN.md B5, CONTRACTS.md CR-04
**Blocks:** None critical — observability/data integrity, not a user-facing feature

## Problem

The frontend has `MIN_VOLUME = 1` gate (scanLogic.js) — the "building n/20" bar tells users the
scan cadence hasn't yet accumulated enough prints to break the MIN_VOLUME floor. If the backend's
min-volume threshold diverges from the frontend's, stale bars could show as fully-populated on one
side but not the other, creating inconsistent "building" states.

## Proposal

Align the backend's min-volume threshold with the frontend's `MIN_VOLUME = 1`:

1. **Declare `MIN_VOLUME` in backend** pipeline (default 1, matching frontend). If backend uses a
   different threshold (e.g., 1000 for force_refresh vs 2500 for market_scan per FULL_PLAN.md B5),
   document the divergence explicitly.
2. **Data freshness visibility:** backend snapshot responses include a `freshness` or `accumulation`
   field so frontend can show "building n/20" honestly when volume is below threshold.
3. **Honest-empty data:** backend snapshots with volume below MIN_VOLUME are either excluded from
   response or flagged with `accumulation` state — never served as fully-populated trades.

## Risks

- Low risk — this is an observability alignment, not a new feature.
- If backend threshold is higher than frontend, frontend "building" state may show longer than
  backend considers "ready." Document the divergence.

## Acceptance criteria (when implemented)

- [ ] MIN_VOLUME threshold declared in backend pipeline
- [ ] Backend threshold matches or diverges from frontend MIN_VOLUME=1 (documented)
- [ ] Frontend can determine data freshness from backend response
- [ ] Stale/under-accumulated data not served as fully-populated

## Gate decision requested

Agent 1: ship B5. Low-risk, high-observability-value. Doesn't block any user-facing feature.

**Proposer's recommendation:** Ship B5 alongside B1 (same cadence job can stamp freshness).
