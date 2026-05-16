# CONFLUENCE DECODER — COMPLETE BUILD PLAN
## Morning Session Todo List (Priority Order)

### PHASE 1: CRITICAL FIXES & MISSING CORE FEATURES
These are things that are broken or major gaps vs skylit.

#### 1.1 — Fix scalp mode backend support
- [ ] Verify scalp mode actually works in build_heatmap (check if `scalp` param is used)
- [ ] Add volume-weighted GEX calculation for scalp mode
- [ ] Test scalp mode returns 0DTE-only data with ±2% band

#### 1.2 — Implied PDF (from floe library)
- [ ] Implement Breeden-Litzenberger implied probability distribution
- [ ] Add endpoint: GET /api/implied-pdf/{ticker}
- [ ] Frontend: probability distribution chart in VolAnalyticsPanel
- [ ] Show: most likely price, median, expected move, tail skew

#### 1.3 — Pressure Cloud / Hedge Impulse (from floe)
- [ ] Implement dealer hedge volume estimation (ES/MES/NQ/MNQ contracts)
- [ ] Add endpoint: GET /api/hedge-impulse/{ticker}
- [ ] Frontend: pressure zone panel showing support/resistance from hedge flows
- [ ] Show: expected dealer buying/selling zones, contract estimates

#### 1.4 — Market Regime Detection (from floe)
- [ ] Implement regime detection from IV surface (low vol, high vol, trending, mean-reverting)
- [ ] Add regime params to heatmap response: atmIV, impliedSpotVolCorr, impliedVolOfVol, expectedDailySpotMove, expectedDailyVolMove
- [ ] Frontend: regime badge in ticker summary

### PHASE 2: FEATURE PARITY WITH SKYLIT
Features skylit has that we're missing.

#### 2.1 — Options Chain Table View
- [ ] Add chain view toggle (grid/bars/chain) in Heatseeker
- [ ] Show full option chain: bid/ask/IV/OI/Greeks per strike
- [ ] Color code by moneyness and OI weight

#### 2.2 — Multi-Timeframe GEX
- [ ] Add timeframe selector: 0DTE / 1DTE / Weekly / Monthly / All
- [ ] Pre-compute GEX for each timeframe bucket
- [ ] Show timeframe comparison view

#### 2.3 — GEX Alerts / Watchlist
- [ ] Backend: alert config (price near flip, GEX crossing threshold, etc.)
- [ ] Frontend: alert panel with configurable triggers
- [ ] Store alerts in Mongo, check on each snapshot

#### 2.4 — Dark Pool / Unusual Options Activity
- [ ] Add UOA detection from transaction size patterns
- [ ] Flag trades >100 contracts as unusual, >250 as sweeps, >500 as blocks
- [ ] Frontend: UOA feed in FlowTicker (already partially done, enhance)

### PHASE 3: POLISH & INSTITUTIONAL FEATURES

#### 3.1 — Backend Error Handling
- [ ] Add global exception handler for all endpoints
- [ ] Add request validation middleware
- [ ] Add rate limiting for expensive endpoints (heatmap, flow)
- [ ] Add health check endpoint with dependency status (Mongo, Databento, yfinance)

#### 3.2 — Frontend Polish
- [ ] Add keyboard shortcuts (1/2/3 for tabs, / for search, etc.)
- [ ] Add ticker search/autocomplete
- [ ] Add export to CSV for portfolio and chain data
- [ ] Add settings panel (refresh rate, theme, default ticker)
- [ ] Improve mobile responsiveness

#### 3.3 — Performance
- [ ] Add Redis caching layer for heatmap responses
- [ ] Implement WebSocket for live spot updates (replace polling)
- [ ] Add request debouncing for filter changes
- [ ] Optimize large option chain rendering (virtual scrolling)

#### 3.4 — Testing
- [ ] Add integration tests for all new endpoints
- [ ] Add frontend component tests
- [ ] Add load testing for concurrent users
- [ ] Add CI/CD pipeline (GitHub Actions)

### PHASE 4: SCHWAB INTEGRATION (When account ready)

#### 4.1 — OAuth Flow UI
- [ ] Add Schwab connect button in Portfolio tab
- [ ] Handle OAuth callback
- [ ] Show connection status

#### 4.2 — Position Sync
- [ ] Auto-import positions on connect
- [ ] Periodic sync (every 5 min during market hours)
- [ ] Map Schwab option symbols to our format

#### 4.3 — Sweep Detection UI
- [ ] Show sweep feed from Schwab transactions
- [ ] Filter by size, symbol, direction
- [ ] Alert on large sweeps

### PHASE 5: DEPLOYMENT PREP

#### 5.1 — Docker
- [ ] Dockerfile for backend
- [ ] Dockerfile for frontend
- [ ] docker-compose.yml with Mongo
- [ ] Environment variable templates

#### 5.2 — Production Config
- [ ] Add proper CORS config
- [ ] Add HTTPS support
- [ ] Add logging configuration
- [ ] Add monitoring/health endpoints

---
## IMMEDIATE NEXT STEPS (First 2 hours tomorrow):

1. Fix scalp mode backend
2. Implement implied PDF endpoint + frontend chart
3. Add pressure cloud / hedge impulse
4. Add market regime detection
5. Test everything end-to-end
