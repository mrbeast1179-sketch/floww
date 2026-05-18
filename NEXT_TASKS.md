# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file
> **Loop:** pick first non-blocked task → run → proof → check off → append ≥3 tasks.

---

## Active: Backtest + paper trade

### Done ✅
- Phase 0: Audit, delete synthetic, quarantine (12 models), guards, CI, hooks
- Phase 1: Data pipeline (45K+ docs, 14K OHLCV bars)
- Phase 2: ML quality gates (7 gates, 33 tests) + calc_vex/dex/vega_total (23 tests)
- Phase 3: BS greeks d1 bug fix + 20 canonical tests
- Phase 4: Feature engineering v1.0 (45 features, 167 rows SPY)
- Phase 5: Model training — SHIP ✅ (acc=0.90, F1=0.88, Sharpe=31.47)

### Live model
- models/SPY_direction_v1.0.joblib (NOT in quarantine)
- models/SPY_scaler_v1.0.joblib
- 44 features, trained on 167 samples (2024 SPY GEX data)

---

## On-deck (execute in order)

- [ ] **phase5-2**: Backtest 2024 outcomes
  - **Run:** create `scripts/backtest_2024.py`. Walk-forward backtest on 2024 data. Monthly precision/recall/F1 + equity curve.
  - **Proof:** `reports/backtest_2024.md` with monthly breakdown

- [ ] **phase6-1**: Wire quality gates into ml_pipeline.py
  - **Run:** add run_all_gates() call before model.save() in ml_pipeline.py. DegenerateModelError on failure.
  - **Proof:** training a degenerate model raises DegenerateModelError

- [ ] **phase7-1**: Paper trade via Alpaca
  - **Run:** load SPY model, predict daily, submit paper orders via Alpaca. Position sizing: max 5% of $100K.
  - **Proof:** paper_trading.py runs daily via cron, logs orders to MongoDB

- [ ] **phase4-2**: QQQ feature engineering
  - **Run:** compute_features for QQQ ticker
  - **Proof:** ml_features has QQQ rows, QQQ model trains

---

## Blocked
- phase1-4 (real Databento backfill): Needs Nav approval ($125 credit)
- XGBoost/LightGBM: Need `brew install libomp` on this Mac
