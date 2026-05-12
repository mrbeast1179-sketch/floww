# Confluence Decoder · Heatseeker GEX Terminal (v3 — Cost-aware Live)

## Problem Statement
A personal Skylit-style trading dashboard, cost-optimized to stretch $125 Databento credit across many trading sessions. User trades SPY + QQQ, watches 09:00-10:30 ET only, prefers Trinity + Swing modes. v1 = baseline. v2 = Databento OI + 2D grid. **v3 (this iteration) = cost-tier gating, live-spot pulse (free), session/budget controls.**

## Architecture
- **Backend**: FastAPI + MongoDB. Two-tier data routing:
  - **Paid tier (Databento)**: only tickers in `PAID_TICKERS` set (default `["SPY"]`). Cached 24h. ~$0.15/ticker/day for OI.
  - **Free tier**: yfinance OI + IV for everything else; Polygon for daily aggs.
- `databento_provider.py`: OPRA.PILLAR statistics (stat_type=9 OI) + Live `trades` stream for Flowseeker. Hard stop_event polling.
- `server.py`: live policy + budget tracking + window enforcement.
- **Frontend**: React 19 dark terminal. Skylit 2D grid, Trinity (default), Flowseeker SSE, Drilldown.

## What's Implemented
### v1 (baseline)
- ✅ Black-Scholes γ GEX, node hierarchy, 6 patterns, tap-prob lifecycle, Velocity Mode, Rolling Floors/Ceilings, Trinity alignment, Top Movers, filters/sort.

### v2 (Databento + Grid)
- ✅ Databento OPRA OI cached in Mongo, 2D Strike × Expiry grid (Skylit-style), Day/Swing toggle, Flowseeker SSE, Contract Drilldown, NaN/Inf sanitization.

### v3 (this iteration — Cost-aware)
- ✅ **Two-tier data routing** — `PAID_TICKERS` set gates Databento; everyone else free. Default ['SPY'] only.
- ✅ **Live policy endpoint** `POST /api/live/policy` to adjust paid tickers + trading window.
- ✅ **Trading window enforcement** — `/api/flow` refuses outside 09:00-10:30 ET unless `enforce_window=false`.
- ✅ **Budget meter** `GET /api/databento/usage` — running cost (OI snapshots × $0.15 + live tape estimate), budget $125, % used, in-window indicator.
- ✅ **Hard stop endpoint** `POST /api/live/tape/stop` — idempotent.
- ✅ **Fast free spot endpoint** `GET /api/spot/{ticker}` — yfinance, 5s cache, used by frontend `useLiveSpot` for live GEX feel without Databento cost.
- ✅ **Trinity is now the default page** (per user preference).
- ✅ **BudgetMeter header widget** — always-visible $$/total + paid tickers + window + on/off-window status + edit-policy panel.
- ✅ **Live spot pulse on Heatseeker** — `● LIVE` indicator + ▲/▼ delta vs heatmap-snapshot spot, free, 5s polling, pauses when tab hidden.
- ✅ **Flowseeker session controls** — duration (1m/2m/5m/10m), override-window checkbox, structured human-readable error messages, session_id + auto_stop_at displayed.
- ✅ Test coverage: **33/33 backend pytest pass** (9 v1 + 8 v2 + 16 v3), full frontend E2E pass.

## Cost Model (v3)
- SPY OI snapshot: ~$0.15/day (cached 24h)
- QQQ + SPXW: $0 (yfinance)
- Spot polling: $0 (yfinance)
- Heatmap recompute on spot tick: $0 (uses cached OI)
- Flowseeker live tape: ~$0.02-0.10 per 2-minute session on SPY (highly variable). User-gated.

**Estimated runway**: SPY OI only = **~830 days** from $125. Adding 2 daily 2-min Flow sessions ≈ 600+ days.

## API Surface (v3 additions)
- `GET /api/spot/{ticker}` — free yfinance spot (5s cache)
- `GET /api/databento/usage` — cost/budget meter + sessions
- `POST /api/live/policy` — update PAID_TICKERS + window
- `POST /api/live/tape/stop` — hard-stop active SSE tape
- `GET /api/flow/{ticker}?enforce_window=true|false` — gated streaming

## Data Sources
- **Databento OPRA.PILLAR**: SPY OI (statistics schema) + SPY live trades (Flowseeker)
- **yfinance**: spot + IV + OI for free-tier tickers (QQQ, SPXW, AAPL, etc.)
- **Polygon REST**: daily aggs for tap-count lifecycle (free tier)

## Prioritized Backlog
**P1**
- Make BudgetMeter "in-window" status more visually prominent (color emphasis when active 9:00-10:30 ET)
- Persist `PAID_TICKERS` in Mongo (currently in-memory; multi-worker safe)
- Auto-pull SPY OI snapshot at 9:00 ET via APScheduler so first request in trading window is instant

**P2**
- Snapshot deep-link sharing (`/snap/:id`)
- Intraday OI delta estimation from Flow trade volume (when tape is active)
- Persist tap-prob history per node for true 1st/2nd/3rd tap stats

**P3**
- Grid virtualization for >200-row swing views
- Export grid as PNG / heatmap image
- Watchlist personalization, alerts on Rolling Floor/Ceiling shifts

## Next Action Items
- Optional: Scheduled OI pre-fetch at 8:55 ET so user gets instant data at open
- Persist PAID_TICKERS + LIVE_WINDOW in Mongo for multi-worker durability

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
