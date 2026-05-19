# MORNING QUEUE — Priority Order
> Generated: 2026-05-18 21:00 (night session)
> Constraint: Phone hotspot = slow MongoDB. Heavy data ops wait for morning WiFi.
> Strategy: Tonight = code/tests/docs. Morning = data pull + training.

## BLOCKER: MongoDB large queries timeout on hotspot
- Small queries (count, ping, <10 docs) work fine
- Large queries (find all 2799 docs, aggregation) timeout
- Index created on (ticker, feature_version, date) - background, should be ready by morning
- Solution: Morning session runs `scripts/cache_features_to_csv.py` first, then all training runs locally

---

## TIER 1: MORNING FIRST LIGHT (need WiFi + MongoDB)

### 1. Cache all ml_features to local CSV
- Script: `scripts/cache_features_to_csv.py` (already written)
- Fetches all 11,592 docs in batches, saves to `data/cached_features/`
- Expected time on WiFi: ~2 minutes
- Output: `QQQ_v1.0.csv`, `DIA_v1.0.csv`, `IWM_v1.0.csv`, `TLT_v1.0.csv`, `SPY_v2.0_gex.csv`

### 2. Model bake-off on QQQ (best ticker so far)
- Script: `scripts/train_v4_bakeoff.py` (already written)
- Uses cached CSV, no MongoDB needed
- Tests: logistic, gbm, gbm_deep, rf
- Expected: 5-10 minutes locally
- Goal: Beat QQQ v3.0 Sharpe=3.36

### 3. Train production QQQ model with best hyperparams
- Script: `scripts/train_production.py` (needs writing)
- Full training on best model from bake-off
- Save model artifact + scaler + manifest to `models/`
- Register in MongoDB `ml_models` collection

### 4. Expand GEX features to QQQ
- Only 35 QQQ databento chains exist (vs 252 SPY)
- Compute GEX for those 35 days
- Merge into QQQ v1.0 features → new v3.0_gex feature set
- Re-train QQQ with GEX features

### 5. Databento backfill for DIA/IWM/TLT
- Check Databento credits remaining
- Backfill 2022-2024 for DIA, IWM, TLT
- Compute GEX for all
- Merge into ml_features for all tickers

---

## TIER 2: TONIGHT (no heavy MongoDB, code-only)

### 6. Write `scripts/train_production.py`
- Full training pipeline with model saving
- Saves: model.joblib, scaler.joblib, manifest.json
- Registers model in MongoDB ml_models collection
- Generates SHIP/REJECT report

### 7. Write `scripts/cache_features_to_csv.py` properly
- Already written but needs testing
- Use _id-based pagination (not skip/limit)
- Save to data/cached_features/

### 8. Add MongoDB index on ml_features
- Already created in background
- Verify it exists in morning before running cache script

### 9. Write `scripts/merge_gex_into_features.py`
- For each ticker, merge gex_features into ml_features
- Creates new feature version (e.g., v3.0_gex)
- Only works after GEX is computed for that ticker

### 10. Paper trade dry-run
- Script: `scripts/paper_trade_dry_run.py` (already written)
- Needs MongoDB for latest data
- Run in morning after data cache

---

## TIER 3: AFTER TIER 1+2 COMPLETE

### 11. Walk-forward backtest on QQQ production model
- Script: `scripts/backtest_model.py` (already written)
- Full backtest with slippage/commission
- Report: Sharpe, max-DD, hit rate, profit factor

### 12. Train DIA/IWM/TLT with expanded GEX features
- After Databento backfill + GEX computation
- Same pipeline as QQQ

### 13. Model registry + promotion
- MongoDB ml_models collection
- Shadow → Active promotion gate
- Drift monitoring

### 14. server.py decomposition
- Phase 7 from CLAUDE_REVIEW_PROMPT.md
- 74 handlers → route modules
- server.py ≤ 200 lines

---

## CURRENT STATE SUMMARY

### Models trained so far:
| Ticker | Version | Samples | Features | Sharpe | Verdict |
|--------|---------|---------|----------|--------|---------|
| SPY | v2.0_gex | 208 | 22 (GEX) | 2.35 | REJECT |
| QQQ | v3.0 | 2799 | 32 (v1.0) | 3.36 | SHIP |
| DIA | v3.0 | 2799 | 32 (v1.0) | 1.90 | REJECT |

### Best model: QQQ v3.0 (GBM, 8-fold walk-forward, Sharpe=3.36)
### Next goal: Beat 3.36 with better hyperparams + GEX features

### Data available:
- ml_features: 11,592 docs (5 tickers × 2799, SPY also has 396 v2.0_gex)
- gex_features: 229 docs (SPY only, 2024)
- databento_eod_chains: 287 docs (SPY: 252, QQQ: 35)
- underlying_bars: 14,295 docs (2859 per ticker, 2015-2026)

### Scripts ready:
- cache_features_to_csv.py (needs WiFi)
- train_v4_bakeoff.py (needs cached data)
- train_spy_v3.py (works, proved QQQ SHIP)
- paper_trade_dry_run.py (needs MongoDB)
- backtest_model.py (needs MongoDB)
- compute_gex_all_tickers.py (needs WiFi for large chains)

### Tests: 284 pass, 76 need server, 0 fail
