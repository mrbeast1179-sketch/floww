# GSD Context — Heatseeker Deepening (user directive: do everything)

## What's done (3 commits on phase9/g1-reads-witness)
- `f1ed4bf` widen strike band (day 15%→35%, swing 25%→45%, low-price 40%→55%)
- `658e6cb` cvserver enrichment for sparse chains
- `4e52e77` switch to full cvserver chain (not screen) + ticker position in control bar

## User directive
"Do everything because CV server is rate limited (20 calls/hour, no prime) so we can use it only for Solstice parity checks. Improve everything else."

## What's left to do

### FRONTEND — already fine (verified)
- `SkylitDashboard.jsx`: in-frame grid auto-sizes via ResizeObserver (`fitRows`, default 21, max 120). Expand view shows ALL strikes (`density="full"`, `windowRows=null`). No clipping bug.
- User's complaint about "heatmap stops" = backend data depth, not frontend clipping.

### BACKEND — real work

**1. Public API chain depth — fetch more expiries for sparse tickers**
- `server.py:_build_heatmap_impl` gets `max_expiries=4` default from the route
- Public API returns only ~20 unique strikes for VSAT from 4 expiries
- Fix: when chain has < 30 unique strikes, re-fetch with more expiries (up to 8-10)
- OR: increase default `max_expiries` for the heatmap route from 4 to 8

**2. Strike interpolation for thin chains**
- VSAT has $5 gaps in far OTM (30, 35, 40, 45...)
- After collecting strikes, detect gaps > $2.50 and insert interpolated rows
- Mark as "estimated" in frontend (different styling)

**3. cvserver — use ONLY for Solstice parity**
- 20 calls/hour rate limit (no prime) — cannot rely on for heatmap data
- Code already falls back to Public API when cvserver 429s
- Keep cvserver enrichment path but make it non-blocking (already done in 4e52e77)

## Key files
- `backend/server.py:943-1106` — `_build_heatmap_impl` (band + enrichment + GEX computation)
- `backend/server.py:906-940` — `build_heatmap` (cache + OOM protection)
- `backend/routes/heatseeker.py:78-100` — `_fetch_chain` (calls `fetch_spot_and_chains_merged`)
- `backend/services/public_api_adapter.py:277-322` — `fetch_chain_from_public_api`
- `frontend/src/components/heatseeker/SkylitDashboard.jsx` — in-frame + expand views
- `frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx` — renders all strikes when `windowRows=null`
