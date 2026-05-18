# REVIEW_LOG.md

## 2026-05-18T05:00:00Z — Multi-ticker features + QQQ model
- QQQ/IWM/DIA/TLT features: 2,799 rows × 32 features each
- QQQ model: acc=0.53, F1=0.57, Sharpe=2.87
- IWM model: acc=0.55, F1=0.48, Sharpe=5.81
- DIA model: acc=0.53, F1=0.55, Sharpe=2.14
- TLT model: acc=0.52, F1=0.48, Sharpe=0.0

## 2026-05-18T06:00:00Z — Databento backfill working
- Fixed OSI regex (needed \s* between underlying and date)
- Removed limit=300000 param (caused timeouts)
- Backfill running: 12+ days stored, ~6K contracts/day, ~20M OI/day
- Background process: proc_423039fff708

### All models (in models/, NOT in quarantine)
- SPY_direction_v1.0: acc=0.90, F1=0.88, Sharpe=31.47
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14
- TLT_direction_v1.0: acc=0.52, F1=0.48, Sharpe=0.0

### Commits
- 7f6559b: IWM/DIA/TLT models
- 1f7ae46: QQQ model + 4-ticker features
- da32638: Fix OSI regex + Databento backfill

### What's next
- Wait for Databento backfill to complete
- Compute GEX features from Databento chain data
- Retrain SPY model with GEX features
- Paper trade via Alpaca
