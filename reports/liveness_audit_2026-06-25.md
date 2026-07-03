# Confluence Decoder — Live-Data Audit & Fix Plan (2026-06-25)

Owner-commissioned audit of every tab + backend data layer: **is the data live?**
Method: 14-agent code trace of `frontend/src` + `backend`, plus two live probes of the
actual data feeds (convexvalue/cvserver + Trading Volatility). Evidence is file:line.
Nothing was runtime-verified — this session has no shell; see §"What only the owner can do".

## Verdict (honest)

**"All tabs have live data" is FALSE today.** Two independent reasons, both fixable only
by the owner — not by frontend edits:

1. **Every provider key in `backend/.env` is empty.** The provider chain
   (cvserver → Databento → FlashAlpha → Finnhub/Polygon/AV → yfinance) short-circuits to
   the **keyless yfinance fallback**. yfinance returns *real* data, but poorer greeks/OI and
   no index fast-path. The 4 architecturally-live tabs are running on the weakest tier.
2. **The convexvalue feed carries no quotes and no trade-level flow.** Probed across
   **1,984,793 contracts**: `open_interest` 100%, `implied_volatility`/`gamma` 86.7%,
   `underlying_price` 96.3% — but `bid`/`ask`/`midpoint`/`quote_last_updated` and
   `trade_price`/`trade_size`/`trade_exchange`/`trade_conditions` are **0% populated**.
   → GEX/OI/IV/greeks views **can be genuinely live**. Real-time quotes, sweeps, tape,
   VPIN, OFI, Kyle-λ **cannot** — they require a tick provider this feed does not include.

## Per-tab status

| Tab | Status | Why |
|---|---|---|
| Heatseeker | LIVE-capable | GEX/OI from cvserver→yfinance→Databento; no synthetic fallback. Needs key for quality. |
| Trinity | LIVE-capable | Same merge chain. `change_pct`+`vix` header chips never emitted by backend (blank). |
| Skylit | LIVE-capable | Same chain. Backend staleness flag not threaded → a stale DuckDB fallback renders as LIVE. |
| Flowseeker Pro | PARTIAL | Chain+GEX live; **microstructure overlays dead** (see Correction below). |
| Journal | PARTIAL | Trade log persists to browser `localStorage` only; no backend route. Sidebar prefill is live. |
| Portfolio | SYNTHETIC | Pure Black-Scholes on user-typed Spot/IV; no provider in path. P&L card never renders (shape bug). |
| turboQuantDC | STUB (by design) | LLM KV-cache status panel — not a market-data tab. |
| SwarmSPX | EXTERNAL | iframe to a separate `:8099` service; no floww backend call. |

## Correction to the auto-audit (verified by hand)

The auto-audit proposed "repoint `FlowseekerProBlademap.jsx:156` `${API}/regime` →
`/api/regime/{t}`". **That is insufficient:**
- `/api/regime/{t}` (`advanced_analytics.calc_market_regime`) returns `{regime: calm|normal|
  stressed|crisis, ...}` — it has **no** `current_state`/`confidence`/`is_warming`, and its
  values don't map to the component's trend/mean classifier. The pill would stay "—".
- The producer that returns the expected shape (`current_state: TRENDING_BULL|RANGING|
  TRENDING_BEAR`, `is_warming`) is `backend/services/hmm_regime.py` — **not exposed by any
  route**. `/api/ml/regime/{t}` is a third concept (vol-percentile) and 404s without a model.
- `vpin` route exists (`/api/microstructure/vpin/{t}`) but returns constructor-default zeros
  (engine never fed). `lambda`/`ofi` have **no route at all**. All three need trade-level data
  the feed lacks → **structurally dead on this source.**

## Fix plan

### A. Owner actions — the real unlock (cannot be done from a no-shell session)
1. **Set `CVSERVER_API_KEY` in `backend/.env`** → flips Heatseeker/Trinity/Skylit/Flowseeker
   chain from yfinance-fallback to full cvserver (32-expiry, real greeks, index fast-path).
   Verify: `GET /api/data/SPY` → `data_source == "cvserver"`.
2. **Run the stack** (see commands below) — liveness can only be *proven* running.
3. **For any flow/tape/VPIN/OFI tab to be live, add a trade-level provider** (Schwab tape,
   Polygon paid options trades, or Databento trades schema). No code can synthesize this.
4. Optional keys: `DATABENTO_API_KEY` (EOD OI overlay for paid tickers),
   `ALPACA_API_KEY/SECRET` (real broker positions for Portfolio), `REACT_APP_SWARM_URL` (SwarmSPX).

### B. Code fixes (correct + low-risk; still verify with stack up)
1. **Trinity header chips** — add `change_pct` (spot vs prior close) + `vix` (^VIX spot) to the
   `build_heatmap` payload (`backend/server.py`). [needs stack to verify]
2. **Skylit staleness** — thread `data.data_fallback`/`stale_age_s` into `SkylitDashboard`/
   `SkylitControlBar` (`frontend/src/App.js` ~883/908) and downgrade the LIVE badge when stale.
3. **Portfolio P&L shape bug** — `calc_portfolio_summary` (`server.py` ~1989) returns `pnl` as a
   scalar; `PortfolioPanel.jsx:404` reads `pnl.total_pnl/...`. Return an object so the card renders.
4. **Honest microstructure** — `routes/microstructure.py` vpin/hawkes/anomaly/liquidity should
   return `status:"no_feed"` instead of zero-valued constants that look like real readings.
5. **Flowseeker overlays** — either gate vpin/ofi/lambda behind an explicit "no live trade data"
   state, or expose `hmm_regime` as `/api/microstructure/regime/{t}` and repoint the pill there
   (the only microstructure overlay that *can* be live, since regime needs no trade data).
6. **Stop shipping dead/misleading code** — unused synthetic `flowseeker/FlowseekerPro.jsx`
   (`generateSyntheticFlowEvents`, header "LIVE · SYNTHETIC DATA"); dead `const API` in
   `TradeJournal.jsx:3`.
7. **Observability honesty** — `/api/data/status` should report cvserver/Databento/FlashAlpha key
   booleans; `DataProviderMonitor.success_rate` (`meta_observability.py` ~413) should return
   `never_called` instead of defaulting to 1.0 (healthy) when no calls recorded.

## What only the owner can do (run the stack)

```bash
# Backend (:8000)
cd /Users/nav/Documents/GitHub/floww/backend && source .venv/bin/activate
# put CVSERVER_API_KEY=... (+ optional DATABENTO_API_KEY) in backend/.env
uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# Frontend (:3000)  — needs REACT_APP_BACKEND_URL=http://localhost:8000 in frontend/.env
cd /Users/nav/Documents/GitHub/floww/frontend && npm start

# Smoke-test which tier actually served:
curl 'http://localhost:8000/api/data/SPY' | grep -o '"data_source":"[^"]*"'   # cvserver | yfinance | databento+yfinance
curl 'http://localhost:8000/api/data/status'   # provider key state
```

Once the stack is up, this session can verify each tab against real responses and apply the
§B fixes with pasted evidence — not before (per the project's anti-fabrication rule).
