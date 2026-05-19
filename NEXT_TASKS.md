# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file
> **Morning queue:** See MORNING_QUEUE.md for prioritized WiFi-dependent tasks

---

## Status: MongoDB blocked (SSL errno=54 on hotspot). WiFi needed for data tasks.

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, models
- SPY/TLT/IWM v1.0 quarantined (audit findings)
- SHIP-gate bug fixed, model audit rules added (Rules 1-12)
- Truth audit passes (11/12 checks)
- 479 tests pass — 64 fail (all server routing issues, not regressions)
- server.py decomposition: 3536 → 2028 lines (de81322)
- TestClient migration: test_portfolio.py, test_heatseeker_v2.py, test_v3_costsave.py (1619270)
- Heatseeker Wave 3 backend: rolling floors/ceilings, node classification, stacked nodes, tug-of-war (48af492)
- Research pipeline: 79 papers, 2 new repos cloned (8b88db8)
- git-lfs installed for LFS-enabled repos

### ML Training Results
| Ticker | Version | Samples | Features | Sharpe | Verdict |
|--------|---------|---------|----------|--------|---------|
| SPY | v2.0_gex | 208 | 22 (GEX) | 2.35 | REJECT |
| QQQ | v3.0 | 2799 | 32 (v1.0) | 3.36 | SHIP |
| DIA | v3.0 | 2799 | 32 (v1.0) | 1.90 | REJECT |

### Live models (NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

---

## BLOCKED: Need WiFi + MongoDB

### 1. Cache features to CSV (2 min on WiFi)
```bash
python scripts/cache_features_to_csv.py
```

### 2. Model bake-off on QQQ (5 min, local CSV)
```bash
python scripts/train_v4_bakeoff.py
```

### 3. Train production model (local CSV)
```bash
python scripts/train_production.py --ticker QQQ --model gbm_deep --save
```

### 4. GEX history backfill
```bash
python scripts/backfill_gex_history.py --tickers SPY,QQQ,DIA,IWM,TLT --start 2022-01-01 --dry-run
```

---

## CAN DO NOW (no MongoDB)

### Fix Route Module Wiring
The 19 route modules in `backend/routes/` have issues:
- Multiple modules have overlapping paths (6+ have `/status`)
- Some reference missing services (`services.uoa`)
- Response shapes differ from test expectations
- Need to fix paths, imports, and response shapes before mounting

Files to fix:
- `backend/routes/market_data.py` — fix `calc_gex_timeframes` → `build_gex_history`
- `backend/routes/analytics.py` — deduplicate `/api/analytics/` prefixed routes
- `backend/routes/alerts.py`, `alpaca.py`, etc. — deduplicate `/status` paths
- Mount all modules in `server.py` with correct prefixes

### Port RLOP Techniques
From `data/github-repos/cloned/owen8877_RLOP/playground/options_pricing_baselines_v7.py`:
- Robust IV bisection with bracket expansion → `vol_analytics.py`
- Heston CF + Simpson's rule → `vol_analytics.py`
- American → European conversion → data pipeline

### Frontend Test Infrastructure
- Add vitest to `frontend/`
- Tests for 10 Heatseeker components in `frontend/src/components/heatseeker/`

---

## Data state
- `ml_features`: 11,592 docs (DIA/IWM/QQQ/TLT: 2799 each v1.0, SPY: 396 v2.0_gex)
- `gex_features`: 229 docs (SPY only, 2024)
- `databento_eod_chains`: 287 docs (SPY: 252, QQQ: 35)
- `underlying_bars`: 14,295 docs (2859 per ticker, 2015-2026)

## Blockers
- MongoDB Atlas SSL failing (errno=54) on phone hotspot — need WiFi
- Route modules need import/shape fixes before mounting
