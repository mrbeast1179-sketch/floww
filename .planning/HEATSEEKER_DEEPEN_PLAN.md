# HEATSEEKER_DEEPEN_PLAN.md — Plan for heatmap strike-depth improvements

**Branch:** phase9/g1-reads-witness (already pushed: 3 heatmap commits)
**Goal:** Make the heatmap show more strikes for sparse tickers (VSAT, etc.) and fill gaps in thin chains.
**Constraint:** cvserver is rate-limited at 20 calls/hour (no prime) — use ONLY for Solstice reference parity checks, NOT as a heatmap data source.

## Context (from investigation)

### Frontend — NO BUG
- `SkylitDashboard.jsx` in-frame grid: `windowRows={fitRows}` where `fitRows` is auto-measured from container height via ResizeObserver (default 21, max 120). This is intentional — the in-frame view shows what fits.
- Expanded overlay (`density="full"`): renders ALL strikes — no windowing. Press Expand in the control bar to see full grid.
- `SkylitHeatmapGrid.jsx`: when `windowRows=null` (expand mode), renders every strike the API sends.
- **Conclusion:** Frontend is not clipping. The user's complaint is about backend data depth.

### Backend — REAL ISSUE
- Heatmap route: `GET /api/heatmap/{ticker}` → `server.py:build_heatmap()` defaults `max_expiries=4`
- `_build_heatmap_impl` gets `max_strikes=200` default, but the chain fetch only gets 4 expiries from Public API
- Public API: `public_api_adapter.py:fetch_chain_from_public_api(ticker, max_expiries=4)` — fetches 4 expiries
- For VSAT: 4 expiries = ~20 unique strikes from Public API. More expiries = more strikes.
- The band filter (already widened to ±35% day / ±45% swing) then narrows to near-ATM.
- cvserver has 48 strikes for VSAT but is rate-limited (429, 600s pause) — can't rely on it.

### Data reality
- VSAT: Public API = ~20 strikes from 4 expiries. More expiries would yield more.
- SPY: 120 strikes, no issue.
- The "hunter" / missing nodes: these are GEX nodes that WERE always in the API response — just not visible due to narrow band. After the band fix + Expand view, they're visible.

## Sub-tasks

### 1. Public API chain depth — fetch more expiries for sparse tickers
**File:** `backend/server.py:_build_heatmap_impl` and/or `backend/routes/heatmap.py` (route)
**Change:** When the chain from Public API has < 30 unique strikes, re-fetch with more expiries (up to 8-10). Or: always fetch more expiries for the heatmap route (since it's meant to show the full chain).
**Risk:** More Public API calls = more rate-limit exposure. Bounded to max 8 expiries.
**Priority:** HIGH — this is the main lever for VSAT-like tickers.

### 2. Strike interpolation for thin chains
**File:** `backend/server.py:_build_heatmap_impl` (post-chain-collection, before band filter)
**Change:** After collecting strikes, detect gaps > $2.50 and insert interpolated strike rows. Mark them as "estimated" (different tooltip / styling in frontend).
**UI:** Interpolated rows get dashed border or lighter color in `SkylitHeatmapGrid`.
**Priority:** MEDIUM — polish for thin chains once we have more strikes from sub-task 1.

### 3. Frontend — no action needed (verified)
The in-frame view is intentionally windowed. Expand view shows all. No bug to fix.
**Priority:** NONE — documented for the user.

### 4. cvserver rate-limit backoff — SKIP
cvserver is rate-limited at 20 calls/hour. We cannot fix this without paying for prime.
The code already falls back gracefully to Public API when cvserver returns 429.
**Priority:** SKIP — no action possible.

## Execution order
1. Sub-task 1 (chain depth) — main fix for VSAT
2. Sub-task 2 (interpolation) — polish
3. Verify with curl against live backend
4. Commit + push
