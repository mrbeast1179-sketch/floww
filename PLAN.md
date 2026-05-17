# CONFLUENCE DECODER — BUILD PLAN
## Status: Phase 3/5 Complete, Phase 4 (Schwab) waiting on user

### ✅ COMPLETED FEATURES

**Core Analytics:**
- GEX heatmap (2D grid + bar view) with strike×expiry visualization
- Options chain table with full Greeks (Δ, Γ, V, Va, Ch), sortable/filterable
- Multi-timeframe GEX (0DTE, 1DTE, weekly, monthly, all)
- Implied PDF (Breeden-Litzenberger)
- Market regime detection (calm/normal/stressed/crisis)
- Hedge impulse curve (gamma + vanna combined)
- Pressure cloud (stability/acceleration zones)
- Charm integral (time-decay pressure)
- Gamma flip level tracking (call wall, put wall, max pain, 0DTE magnet)
- Dealer hedging flow estimates at ±1% moves

**Daily Trading:**
- Morning Briefing component (regime, key levels, strategy, risk)
- Daily Checklist API (GEX-based strategy recommendations)
- Position Sizing Calculator (account-based with GEX regime multiplier)
- Trade Entry Templates (iron condor, straddle, call/put spread, single leg)
- Trade Journal with P&L tracking, win rate, GEX regime at entry

**Alerts & Flow:**
- GEX alerts (gex_cross, gex_spike, oi_spike, iv_spike)
- Unusual options activity detection
- Flow ticker (SSE live trade tape)
- Pattern detection (Whipsaw, Rug, Pika Cloud, etc.)

**Infrastructure:**
- Rate limiting (60 req/min per IP, configurable)
- CORS configuration
- File logging (backend/logs/app.log)
- Health check endpoint (/health, /api/health)
- Docker setup (Dockerfile.backend, Dockerfile.frontend, docker-compose.yml)
- GitHub Actions CI/CD pipeline
- 24 integration tests passing
- Mobile-responsive layout
- Keyboard shortcuts modal (press ?)
- Settings panel (refresh rate, default ticker)
- WebSocket live GEX streaming
- Cache pre-warming for all 12 tickers

### 🔜 NEXT PRIORITIES

**Phase 4 — Schwab Integration (waiting on user's API access):**
- OAuth flow UI
- Position sync
- Sweep detection UI

**Phase 5 — Deployment:**
- HTTPS support
- Production monitoring
- Deploy to Azure ($100 credit available)

**Algorithm Improvements (from research):**
- Vanna exposure tracking (vol changes affect dealer hedging)
- Charm exposure (time decay effects)
- 0DTE-specific analytics (same-day pin targets)
- Expiration roll tracking (OI reset effects on GEX)

### 📊 CURRENT MARKET READING (SPY)
- Regime: NEGATIVE gamma (dealers short gamma, moves amplified)
- Gamma flip: ~740.8 (SPY below flip = negative gamma)
- Call wall: 744 (0.65% above spot)
- Put wall: 732 (0.97% below spot)
- Max pain: 728 (1.37% below spot)
- Strategy: Long vol, momentum trades, avoid mean-reversion
- Position sizing: Max 1% account risk per trade (0.5% if deep negative gamma)

### 💰 TRADING RULES FOR $5K ACCOUNT
- Max 1-2% risk per trade ($50-$100)
- Reduce size in negative gamma (volatile)
- Place stops beyond GEX walls, not at them
- Track every trade in Journal
- Review morning briefing before entering positions
- Use position sizing calculator for every trade