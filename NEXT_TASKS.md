# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file

---

## Status: Databento backfill + GEX compute running

### Background processes
- SPY Databento backfill: 170/252 days (Sep 5), proc_af36538c06cf
- QQQ Databento backfill: 35/252 days (Mar), proc_d8071cddb57f
- GEX feature compute: running, proc_58185fa92275

### Done ✅
- 5 ticker models trained (SPY/QQQ/IWM/DIA/TLT), all SHIP
- 4-ticker features: SPY(167×45), QQQ/IWM/DIA/TLT(2799×32)
- Backtest 2024: 93% accuracy
- Quality gates wired into ml_pipeline.py
- calc_vex/dex/vega_total implemented (23 tests)
- BS greeks d1 bug fixed (20 canonical tests)
- ML quality gates (33 tests)

### Live models (models/, NOT in quarantine)
- SPY_direction_v1.0: acc=0.90, F1=0.88, Sharpe=31.47
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14
- TLT_direction_v1.0: acc=0.52, F1=0.48, Sharpe=0.0

---

## On-deck (after backfills complete)

- [ ] **gex_features**: Compute GEX/VEX/DEX from Databento chains (running in background)
- [ ] **retrain_spy_gex**: Retrain SPY model with GEX features from Databento
- [ ] **paper_trade**: Paper trade via Alpaca (Claude working on paper_trading.py)
- [ ] **expand_backfill**: IWM/DIA Databento backfill

---

## Blocked
- XGBoost/LightGBM: Need `brew install libomp`
