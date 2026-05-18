# REVIEW_LOG.md

## 2026-05-18T05:00:00Z — Multi-ticker features + QQQ model

### Feature matrix (all in MongoDB ml_features)
- SPY: 167 rows × 45 features (GEX + underlying + technical + vol + calendar)
- QQQ: 2,799 rows × 32 features (underlying + technical + vol + calendar)
- IWM: 2,799 rows × 32 features
- DIA: 2,799 rows × 32 features
- TLT: 2,799 rows × 32 features
- Total: ~11,363 rows

### Models trained
- SPY_direction_v1.0: GradientBoosting, acc=0.90, F1=0.88, Sharpe=31.47, 6/6 folds pass gates
- QQQ_direction_v1.0: GradientBoosting, acc=0.53, F1=0.57, Sharpe=2.87, 8/8 folds pass gates
- Both saved to models/ with ticker-specific paths (not in quarantine)

### Backtest 2024
- reports/backtest_2024.md: 93% accuracy, 0.93 F1 across 100 predictions
- Monthly breakdown: consistent 90-100% accuracy most months

### Infrastructure
- Quality gates wired into ml_pipeline.py train_models()
- Model paths now ticker-specific: {ticker}_direction_v1.0.joblib
- Targets for QQQ/IWM/DIA/TLT computed from own underlying bars (next-day return direction)

### Commits this session
- 48fb4d4: SPY model v1.0 SHIP
- 056a4c9: Backtest 2024 + wire quality gates
- 1f7ae46: QQQ model + 4-ticker features + fix model paths

### What's next
- Train IWM, DIA, TLT models
- Paper trade via Alpaca (Claude working on paper_trading.py)
- Expand SPY features with more GEX data
- Databento backfill (symbol format issue needs debugging)
