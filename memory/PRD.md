# Confluence Decoder · Heatseeker GEX Terminal (v2 — Databento + 2D Grid)

## Problem Statement
A personal Skylit-style trading dashboard. v1 wired Polygon + yfinance for GEX. v2 (this iteration) plugs in **Databento** ($125 credits) for real OPRA Open Interest, refactors the heatmap to a **2D Strike × Expiry grid** matching Skylit's Heatseeker layout, adds **Swing Mode** for multi-expiry views, **Flowseeker** (live OPRA trade tape), and **Contract Drilldown**. Trinity Mode (SPXW + SPY + QQQ) for cross-index confluence.

## Architecture
- **Backend**: FastAPI + MongoDB.
  - `databento_provider.py`: OPRA.PILLAR statistics (stat_type=9 OI) via tight pre-market window (10:00-13:30 UTC, ~$0.15/ticker/day); 24h Mongo cache. Live trades for Flowseeker via Databento Live API (`db.Live`).
  - `server.py`: merges Databento OI + yfinance IV → Black-Scholes γ → per-strike + per-(strike,expiry) GEX. Polygon for daily-aggs tap counts.
- **Frontend**: React 19, dark JetBrains-Mono terminal. Skylit-style 2D grid (teal Pika / purple Barney / yellow-green King) + bar view + Trinity + Flowseeker SSE + Drilldown modal.

## What's Implemented
### v1 (baseline)
- ✅ Black-Scholes γ GEX, node hierarchy (King/Floors/Ceilings/Gatekeepers/Air Pockets), polarity, 6 Skylit patterns (Rug, Reverse Rug, Pika Cloud, Beach Ball, Whipsaw, Rainbow Road), tap-prob lifecycle (80/66/33/10), Velocity Mode, Rolling Floors/Ceilings, Trinity alignment, Top Movers, filters/sort.

### v2 (this iteration)
- ✅ Databento OPRA OI fetcher with Mongo cache (24h per ticker per date); ~$0.45/day burn for Trinity → ~280 days from $125
- ✅ Real-OI driven GEX (data source now `databento+yfinance` for SPY/QQQ/SPXW; falls back to pure yfinance otherwise)
- ✅ 2D Strike × Expiry **grid heatmap** (Skylit-style): cells colored teal (positive)/purple (negative)/yellow-green (King), spot row auto-scrolled into view, KING/FLR/CEIL/GATE/AIR tags per row, empty rows hidden
- ✅ Bar heatmap kept as alternate view (toggle in filter panel)
- ✅ **Day / Swing** mode toggle: Day = ±15% band & ≤4 expiries; Swing = ±25% band & up to 12 expiries
- ✅ **Flowseeker** SSE endpoint `/api/flow/{ticker}` streams live OPRA trades via Databento Live; auto-stops after 120s; classifies sweep (≥250) / block (≥500) / unusual; filter UI for unusual/sweep/block/calls/puts
- ✅ **Contract Drilldown** modal: click any grid cell → `/api/contract/{ticker}` returns rows with δ, γ, GEX, OI source. Empty state handled.
- ✅ **Databento usage** endpoint `/api/databento/usage` shows cached days + counts
- ✅ Fixed: integer strike keys ("739" not "739.0") for clean JS lookup; true arithmetic IV mean for DBN-only contracts; SSE emits error when DBN key missing; drilldown empty-state UX

## Cost Model
- OI fetch per ticker per day = ~$0.15 (statistics narrow window 10:00-13:30 UTC)
- 3-ticker Trinity (SPY+QQQ+SPXW) = ~$0.45/day
- Flowseeker live trades = ~$3/hour per ticker (gated, max 120s per session)
- $125 budget → ~280 days of daily Trinity OI before depleted

## Test Status
- v1: 9/9 pytest pass
- v2: 8/8 new pytest pass + 9/9 prior = **17/17 backend**, full frontend E2E pass

## API Surface
- `GET /api/heatmap/{ticker}?expiries=N&mode=day|swing` — full Heatseeker payload (incl. `grid`)
- `GET /api/trinity?tickers=...&mode=day|swing`
- `GET /api/movers?limit=N`
- `GET /api/contract/{ticker}?expiry=...&strike=...` — drilldown
- `GET /api/flow/{ticker}?max_seconds=N` — SSE live trades (Databento Live)
- `GET /api/databento/usage` — cache stats
- `GET /api/history/{ticker}` · `GET /api/patterns/glossary` · `GET /api/tickers`

## Data Sources
- **Databento OPRA.PILLAR** (statistics schema): real EOD OI per contract — primary driver of GEX magnitude
- **yfinance**: spot + implied volatility (Databento has no IV)
- **Polygon REST**: daily aggs for tap-count lifecycle

## Prioritized Backlog
**P1**
- Persist tap-prob history per node for true 1st/2nd/3rd tap statistics (Polygon minute aggs)
- Snapshot deep-link sharing (`/snap/:id`) — frozen Heatseeker map → Discord/X share
- After-hours Flowseeker UX hint when no trades stream

**P2**
- Virtualization for >200-row grids in swing mode (SPX wide range)
- Empty-cell click disabled in grid (currently opens "no contracts" modal)
- Live re-pull of OI mid-session via Databento Live `statistics` stream (cost-tier dependent)

**P3**
- Export grid as PNG / heatmap image
- Backtest replay against `snapshots` history
- Watchlist personalization, alerts on Rolling Floor/Ceiling shifts

## Next Action Items
- Wire Databento Live `statistics` stream for live OI deltas (cost check first)
- Add intraday tap counts (Polygon minute aggs)
- Snapshot sharing endpoint + viral landing
