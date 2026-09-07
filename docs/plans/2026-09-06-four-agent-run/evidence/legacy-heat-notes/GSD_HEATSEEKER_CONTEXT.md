# GSD Context — Heatseeker Deepening

## What's been done (3 commits on phase9/g1-reads-witness)
- `f1ed4bf` widen strike band (day 15%→35%, swing 25%→45%, low-price 40%→55%)
- `658e6cb` cvserver enrichment for sparse chains
- `4e52e77` switch to full cvserver chain + ticker position in control bar

## What's left (user directive: do everything, cvserver = Solstice only)
1. Frontend: `windowRows` mode is correct — auto-fits to container height. Expand view shows ALL strikes. No clipping to fix.
2. Backend: Heatmap route (`/api/heatmap/{ticker}`) in `server.py` calls `fetch_spot_and_chains_merged(ticker, max_expiries)` — need to find where `max_expiries` is set and increase for sparse tickers.
3. `max_strikes=120` in `_build_heatmap_impl` is the cap — increasing it won't help if Public API only returns 20 unique strikes.
4. cvserver: 20 calls/hour rate limit — only use for Solstice parity checks, NOT as heatmap data source.

## Key files to read
- `backend/server.py` lines ~1080-1140 (heatmap route + `_build_heatmap_impl`)
- `backend/server.py` lines ~540-575 (`fetch_spot_and_chains_merged`)
- `backend/services/public_api.py` (Public API chain fetch — how many expiries? what's the limit?)
