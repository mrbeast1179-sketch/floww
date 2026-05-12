# Confluence Decoder · Heatseeker GEX Terminal

## Problem Statement
Upgrade the existing Confluence Decoder app, wire in user's Polygon API key (`ZA2f35xffpxPwlBsTiL8IWdmXZW_VFl7`), and make the GEX analytics as close to Skylit's Heatseeker framework as possible. User requested ALL feature scopes: Core node hierarchy, Pattern detection, Trinity Mode, Velocity Mode + Rolling Floors/Ceilings. Keep current visual feel; add more sorts/filters.

## Architecture
- **Backend**: FastAPI, MongoDB, yfinance (chains + spot + bulk movers), Polygon (aggs + tap-count history). Black-Scholes γ → per-strike GEX.
- **Frontend**: React 19, Tailwind, dark Skylit-style terminal aesthetic (JetBrains Mono), 30s refresh.
- **Storage**: Mongo `snapshots` collection (last 50 per ticker) powers Velocity Mode + Rolling Floors/Ceilings.

## User Personas
- Options day-trader / GEX-focused trader who wants Skylit-style structural reads (Pika/Barney/King/Floor/Ceiling/Gatekeeper/Air Pocket) for SPX/SPY/QQQ + top movers.

## Core Requirements (static)
- Polygon API key configured server-side
- Trinity Mode (SPX + SPY + QQQ side-by-side w/ alignment verdict)
- Pattern detection: Rug, Reverse Rug, Pika Cloud, Beach Ball, Whipsaw, Rainbow Road
- Velocity Mode (rate of change in dealer positioning) + Rolling Floors/Ceilings
- Tap probability (80/66/33/10 lifecycle)
- Filters: expiries, side, lifecycle, magnitude threshold
- Top movers panel
- 30s auto-refresh

## What's Implemented (2026-01)
- ✅ GEX engine: Black-Scholes γ, per-strike net GEX, calls=positive, puts=negative
- ✅ Node hierarchy: King, Floors, Ceilings, Gatekeepers (15% threshold), Air Pockets (8% threshold), Polarity zero-crossing
- ✅ All 6 Skylit patterns (Rug / Reverse Rug / Pika Cloud / Beach Ball / Whipsaw / Rainbow Road)
- ✅ Lifecycle tagging: fresh/tested/delivered/decaying via Polygon daily-aggs tap counts
- ✅ Velocity Mode (Mongo snapshot deltas) + Rolling Floor/Ceiling sequences
- ✅ Trinity Mode w/ alignment verdict (full / partial / divergence)
- ✅ Top Movers via yfinance bulk download (60s cache, no rate-limit issues)
- ✅ Filters: expiries (1/2/3/4/6), side (above/below/all), lifecycle, |GEX| magnitude slider
- ✅ Sortable Structural Nodes table
- ✅ Air Pockets dedicated panel
- ✅ Velocity gauge with "warming up" state
- ✅ Spot line marker on every heatmap (single + trinity)
- ✅ NaN/Inf JSON-safe sanitization
- ✅ Ticker normalization (case-insensitive, SPX → ^SPX)
- ✅ Testing: 9/9 backend pytest + full frontend E2E pass

## API Surface
- `GET /api/` — heartbeat
- `GET /api/tickers` — trinity/default/popular lists
- `GET /api/heatmap/{ticker}?expiries=N&taps=bool` — full Heatseeker payload
- `GET /api/trinity?tickers=...` — multi-ticker w/ alignment
- `GET /api/movers?limit=N`
- `GET /api/history/{ticker}?limit=N`
- `GET /api/patterns/glossary`

## Data Sources
- **yfinance**: spot, option chains (OI, IV, strike), bulk movers download
- **Polygon REST** (key in backend/.env): daily aggs (tap counts), reference tickers
- Note: Polygon free tier ⚠️ does NOT support snapshot/options/last-trade. App is fully functional via yfinance fallback; user mentioned $125 Databento credits coming later which can supersede.

## Prioritized Backlog
**P1**
- Databento integration when user activates credits (replace yfinance for real-time OI w/ low latency)
- Intraday tap counts (minute aggs from Polygon) for finer freshness
- Persist tap-probability history per node for true 1st/2nd/3rd tap statistics

**P2**
- Sharing: deep-link a snapshot (strikes + nodes + ts) via URL
- Alert when a Rolling Floor / Ceiling crosses a user-set threshold
- Saved tickers / watchlist personalization

**P3**
- Pin/compare two tickers side-by-side outside Trinity
- Export heatmap PNG for journal/screenshots
- Backtest replay against stored snapshot history

## Next Action Items
- Add Databento provider abstraction when user supplies credits
- Optional virtualization for >150-row heatmaps (SPX with $5 strikes)
