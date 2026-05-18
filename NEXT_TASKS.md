# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file
> **Loop:** pick first non-blocked task → run → proof → check off → append ≥3 tasks.

---

## Active: Train remaining tickers + expand data

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, SPY/QQQ models
- Backtest 2024: 93% accuracy
- Quality gates wired into ml_pipeline.py
- 4-ticker features: SPY (167×45), QQQ/IWM/DIA/TLT (2799×32 each)

### Live models (all in models/, NOT in quarantine)
- SPY_direction_v1.0.joblib: acc=0.90, F1=0.88, Sharpe=31.47
- QQQ_direction_v1.0.joblib: acc=0.53, F1=0.57, Sharpe=2.87

---

## On-deck (execute in order)

- [ ] **train_iwm**: Train IWM direction model
  - **Run:** `python scripts/train_spy_model.py --ticker IWM`
  - **Proof:** models/IWM_direction_v1.0.joblib exists

- [ ] **train_dia**: Train DIA direction model
  - **Run:** `python scripts/train_spy_model.py --ticker DIA`
  - **Proof:** models/DIA_direction_v1.0.joblib exists

- [ ] **train_tlt**: Train TLT direction model
  - **Run:** `python scripts/train_spy_model.py --ticker TLT`
  - **Proof:** models/TLT_direction_v1.0.joblib exists

- [ ] **paper_trade**: Paper trade via Alpaca (Claude working on paper_trading.py)
  - Wire model predictions → Alpaca paper orders
  - Position sizing: max 5% of $100K per trade

- [ ] **expand_spy_data**: Pull more GEX data for SPY
  - Databento backfill (debug symbol format: SPY.OPT rejected, need correct format)
  - More yfinance history for underlying bars

---

## Blocked
- XGBoost/LightGBM: Need `brew install libomp` on this Mac
- Databento symbol format: SPY.OPT rejected by API, need to debug correct format
