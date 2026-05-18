# REVIEW_LOG.md

## 2026-05-18 — Full state snapshot

### Data pipeline ✅
- Research CSVs: 45K+ docs (7 collections)
- yfinance: 14,295 OHLCV bars (SPY, QQQ, IWM, DIA, VIX, TLT)
- Databento SPY 2024: 252 days, $108.36, 10 failed
- Databento QQQ 2024H1: 35 days, $15.05
- GEX features: 229 rows (Jan-Nov 2024), computed from Databento chains

### Features
- SPY v1.0: 167 rows × 45 features (academic GEX + underlying)
- SPY v2.0: 229 rows × 23 features (Databento GEX + underlying) — built but not yet trained
- QQQ/IWM/DIA/TLT: 2,799 rows × 32 features each

### Models (all in models/, NOT in quarantine)
- SPY_direction_v1.0: acc=0.90, F1=0.88, Sharpe=31.47
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14
- TLT_direction_v1.0: acc=0.52, F1=0.48, Sharpe=0.0

### Infrastructure
- Quality gates: 7 gates, 33 tests, wired into ml_pipeline.py
- calc_vex/dex/vega_total: 23 tests
- BS greeks d1 fix: 20 canonical tests
- truth_audit.sh + commit-msg hook active

### Agent worktrees (still running)
- agent-a681f0a845b9a734a: ml_pipeline.py changes (319 lines)
- agent-a8e5e9b132407cc03: features.py changes (222 lines)

### Blocked
- MongoDB Atlas: SSL handshake failing (transient network issue)
- XGBoost/LightGBM: Need brew install libomp

### Next steps (when MongoDB recovers)
1. Retrain SPY with v2.0 GEX features
2. Merge agent worktree changes
3. Paper trade dry-run
4. Expand Databento to IWM/DIA
