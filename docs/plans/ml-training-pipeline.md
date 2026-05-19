# ML Training Pipeline — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-time.
> **Constraint:** Large MongoDB queries fail on phone hotspot. Batch operations must use small batches (≤100 docs) with retries.

**Goal:** Build a production-grade ML training pipeline that trains, evaluates, and registers models for SPY/QQQ options direction prediction.

**Architecture:** 
- Data cached from MongoDB to local CSV (batch size 100, retry on timeout)
- Feature engineering combines v1.0 features + GEX features
- Walk-forward CV with 8 folds, 3 baselines (majority, persistence, logistic)
- Model registry in MongoDB with shadow/active/retired states
- SHIP gate: must beat all 3 baselines on Sharpe

**Tech Stack:** Python 3.11, scikit-learn, pandas, numpy, pymongo, joblib

---

## Phase 1: Data Infrastructure (MORNING - needs WiFi)

### Task 1.1: Cache ml_features to CSV
- Script: `scripts/cache_features_to_csv.py`
- Batch size: 100 docs, _id-based pagination
- Retry: 3 attempts with exponential backoff on timeout
- Output: `data/cached_features/{TICKER}_{VERSION}.csv`
- Tickers: QQQ, DIA, IWM, TLT (v1.0), SPY (v2.0_gex)

### Task 1.2: Verify MongoDB index
- Check index on (ticker, feature_version, date) exists
- If not, create it (background)

## Phase 2: Model Bake-off (can run locally with cached data)

### Task 2.1: Run bake-off on QQQ
- Script: `scripts/train_v4_bakeoff.py`
- Models: logistic, gbm, gbm_deep, rf
- Target: beat Sharpe=3.36

### Task 2.2: Run bake-off on DIA
- Same pipeline, target: beat persistence baseline

### Task 2.3: Run bake-off on SPY (v2.0_gex features)
- Only 396 samples but has GEX data
- Target: beat majority baseline

## Phase 3: Production Model Training

### Task 3.1: Train production QQQ model
- Script: `scripts/train_production.py`
- Best model from bake-off
- Save: model.joblib, scaler.joblib, manifest.json
- Register in MongoDB ml_models collection

### Task 3.2: Generate model report
- SHIP/REJECT verdict
- Per-fold metrics
- Baseline comparison
- Feature importance (if tree model)

## Phase 4: GEX Feature Expansion (MORNING - needs WiFi)

### Task 4.1: Compute GEX for QQQ
- 35 databento chains available
- Script: `scripts/compute_gex_all_tickers.py`

### Task 4.2: Merge GEX into ml_features
- Script: `scripts/merge_gex_into_features.py`
- Creates v3.0_gex feature version

### Task 4.3: Re-train QQQ with GEX features
- Compare vs v1.0-only model

## Phase 5: Paper Trading

### Task 5.1: Run paper trade dry-run
- Script: `scripts/paper_trade_dry_run.py`
- Load active model, simulate trades
- Report: P&L, hit rate, max-DD

## Phase 6: Backtesting

### Task 6.1: Walk-forward backtest
- Script: `scripts/backtest_model.py`
- Full backtest with slippage/commission
- Report: Sharpe, max-DD, hit rate, profit factor
