# Server.py Decomposition Plan (Phase 7)

> Target: server.py ≤ 200 lines (currently 3536 lines)
> Strategy: Extract route handlers into backend/routes/<domain>.py modules

## Route Inventory (from server.py)

### Already Extracted ✅
- backend/routes/alerts.py — Alert routes
- backend/routes/alpaca.py — Alpaca trading routes
- backend/routes/data_providers.py — Data provider routes
- backend/routes/flashalpha.py — FlashAlpha routes
- backend/routes/gemini.py — Gemini routes
- backend/routes/heatseeker.py — Heatseeker routes
- backend/routes/ml_api.py — ML API routes
- backend/routes/social_flow.py — Social flow routes

### Still in server.py (to extract):

#### Group 1: Market Data (tickers, heatmap, trinity, gex-timeframes, chain, uoa)
- GET /tickers
- GET /heatmap/{ticker}
- GET /trinity
- GET /gex-timeframes/{ticker}
- GET /chain/{ticker}
- GET /uoa/{ticker}
- GET /spot/{ticker}

#### Group 2: Analytics (implied-pdf, regime, hedge-impulse, pressure-cloud, charm-integral, advanced, gamma-flip, daily-checklist, movers, history, patterns/glossary, contract, flow)
- GET /implied-pdf/{ticker}
- GET /regime/{ticker}
- GET /hedge-impulse/{ticker}
- GET /pressure-cloud/{ticker}
- GET /charm-integral/{ticker}
- GET /advanced/{ticker}
- GET /gamma-flip/{ticker}
- GET /daily-checklist/{ticker}
- GET /movers
- GET /history/{ticker}
- GET /patterns/glossary
- GET /contract/{ticker}
- GET /flow/{ticker}
- GET /api/analytics/surface/{ticker}
- GET /api/analytics/regime-stats/{ticker}
- GET /api/analytics/compare
- GET /api/analytics/correlation

#### Group 3: Portfolio (portfolio, position-size)
- GET/POST/DELETE /portfolio/{name}/...
- POST /position-size

#### Group 4: Paper Trading (paper-trading)
- POST /api/paper-trading/execute
- POST /api/paper-trading/signals
- GET /api/paper-trading/status

#### Group 5: Briefing (briefing)
- GET /api/briefing/{ticker}
- GET /api/briefing/{ticker}/html
- POST /api/briefing/{ticker}/send

#### Group 6: ML Training (ml)
- POST /api/ml/train/{ticker}
- GET /api/ml/predict/{ticker}
- GET /api/ml/features/{ticker}
- GET /api/ml/data/{ticker}
- POST /api/ml/collect/{ticker}
- POST /api/ml/collect-all
- POST /api/ml/train-price/{ticker}
- GET /api/ml/predict-price/{ticker}
- POST /api/ml/train-advanced/{ticker}
- GET /api/ml/model-info/{ticker}

#### Group 7: LLM (llm)
- POST /api/llm/analyze-trade
- POST /api/llm/generate-briefing
- GET /api/llm/providers

#### Group 8: Schwab (schwab)
- GET /schwab/auth-url
- POST /schwab/auth
- GET /schwab/accounts
- GET /schwab/positions/{account_hash}
- GET /schwab/sweeps/{account_hash}
- POST /schwab/import-to-portfolio/{name}/{account_hash}

#### Group 9: Live Trading (live)
- GET/POST /live/policy
- POST /live/tape/stop

#### Group 10: Memory (memory)
- POST /memory/trade
- POST /memory/gex
- GET /memory/recall/{ticker}
- GET /memory/summary/{ticker}

#### Group 11: Admin/Errors (errors, performance, databento)
- GET /api/errors/summary
- GET /api/performance/stats
- POST /api/errors/clear
- GET /databento/usage

## Extraction Order
1. market_data.py (most routes, clean domain)
2. analytics.py (many routes, clean domain)
3. portfolio.py
4. paper_trading.py
5. briefing.py
6. ml_training.py
7. llm.py
8. schwab.py
9. live_trading.py
10. memory.py
11. admin.py

## Final server.py structure:
- Imports
- App creation + middleware
- Router includes (one per domain)
- Lifespan events
- Health check
