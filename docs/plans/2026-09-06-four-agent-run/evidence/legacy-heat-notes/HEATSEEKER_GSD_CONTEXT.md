# GSD Context — Heatseeker Deepening

## What's been done
3 commits on `phase9/g1-reads-witness`:
- `f1ed4bf` widen strike band (day 15%→35%, swing 25%→45%, low-price floor $50→55%)
- `658e6cb` cvserver enrichment for sparse chains
- `4e52e77` switch enrichment to full cvserver chain (not screen API) + ticker position in control bar

## What's left (user directive: do everything)
1. Frontend `windowRows` mode is correct (fit-to-view). The in-frame grid auto-sizes to container height. The EXPAND view shows ALL strikes. No frontend clipping to fix.
2. Backend: VSAT still only gets 20 strikes from Public API (chain depth limit). Need to:
   - Fetch more expiries for sparse tickers (>4) to get more unique strikes
   - Add interpolated strike rows for gaps > $2.50 so the heatmap looks continuous
3. cvserver rate limit (20 calls/hour, no prime) — can only use for Solstice reference, NOT as heatmap data source. Already handled: enrichment path falls back to Public API when cvserver 429s.

## Key files
- Frontend: `frontend/src/components/heatseeker/SkylitDashboard.jsx` (in-frame: `windowRows={fitRows}`, expand: `density="full"`), `SkylitHeatmapGrid.jsx` (renders all strikes when `windowRows=null`)
- Backend: `backend/server.py:_build_heatmap_impl` (band + enrichment), `backend/routes/heatseeker.py:_fetch_chain` (calls `fetch_spot_and_chains_merged` with `expiries=4` default), `backend/services/public_api.py` (Public API chain fetch), `backend/services/cvserver_client.py` (rate-limited)

## Data reality
- VSAT: Public API returns ~20 unique strikes from 4 expiries. Full cvserver chain has 48 (currently rate-limited).
- SPY: 120 strikes, no issue.
- The "hunter" / missing nodes the user mentioned: these are GEX nodes (king, floors, ceilings) that WERE always in the API response — just not visible due to narrow band. After the band fix, they're visible. User can verify in SkylitDashboard by pressing Expand (Esc to close).
