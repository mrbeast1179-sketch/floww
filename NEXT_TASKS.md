# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file
> **Morning queue:** See MORNING_QUEUE.md for prioritized WiFi-dependent tasks

---

## Status: Code ready, waiting on WiFi for heavy MongoDB data pulls

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, models
- SPY/TLT/IWM v1.0 quarantined (audit findings)
- SHIP-gate bug fixed, model audit rules added (Rules 1-12)
- Agent work merged (gated persistence + multi-ticker features)
- Truth audit passes (12/12 checks)
- MongoDB Atlas connected (errno=54 resolved)
- 284 tests pass (0 fail) — 76 skipped (need server)
- All scripts written and committed
- MongoDB index created on ml_features (ticker, feature_version, date)

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

## MORNING PRIORITY (need WiFi + MongoDB)

### 1. Cache features to CSV (2 min on WiFi)
```bash
python scripts/cache_features_to_csv.py
```
Output: data/cached_features/{TICKER}_{VERSION}.csv

### 2. Model bake-off on QQQ (5 min, local CSV)
```bash
python scripts/train_v4_bakeoff.py
```
Tests: logistic, gbm, gbm_deep, rf. Goal: beat Sharpe=3.36

### 3. Train production model (local CSV)
```bash
python scripts/train_production.py --ticker QQQ --model gbm_deep --save
```
Saves: model.joblib, scaler.joblib, manifest.json

### 4. Compute GEX for QQQ (35 databento chains)
```bash
python scripts/compute_gex_all_tickers.py
```

### 5. Merge GEX into ml_features
```bash
python scripts/merge_gex_into_features.py --ticker QQQ --base-version v1.0 --new-version v3.0_gex
```

### 6. Re-train QQQ with GEX features
```bash
python scripts/train_production.py --ticker QQQ --feature-version v3.0_gex --model gbm_deep --save
```

### 7. Paper trade dry-run
```bash
python scripts/paper_trade_dry_run.py
```

---

## Scripts ready (all committed)
- `scripts/train_spy_v2.py` — SPY v2.0 with GEX features
- `scripts/train_spy_v3.py` — Multi-ticker with v1.0 features
- `scripts/train_v4_bakeoff.py` — Model bake-off (local CSV)
- `scripts/train_production.py` — Production training + save
- `scripts/cache_features_to_csv.py` — MongoDB → local CSV cache
- `scripts/merge_gex_into_features.py` — GEX → ml_features merge
- `scripts/compute_gex_all_tickers.py` — GEX for all tickers
- `scripts/paper_trade_dry_run.py` — Paper trade simulation
- `scripts/backtest_model.py` — Walk-forward backtest

---

## Data state
- `ml_features`: 11,592 docs (DIA/IWM/QQQ/TLT: 2799 each v1.0, SPY: 396 v2.0_gex)
- `gex_features`: 229 docs (SPY only, 2024)
- `databento_eod_chains`: 287 docs (SPY: 252, QQQ: 35)
- `underlying_bars`: 14,295 docs (2859 per ticker, 2015-2026)

## Blockers
- Large MongoDB queries timeout on phone hotspot
- Morning WiFi needed for: cache_features, GEX computation, paper trade
