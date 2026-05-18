# REVIEW_LOG.md

## 2026-05-18 — End of session state

### Critical fixes applied this session
- **Quarantined SPY v1.0**: 167 samples/45 features = overfit. Moved to _quarantine/
- **Quarantined TLT v1.0**: Sharpe=0.0, no edge. Moved to _quarantine/
- **Fixed SHIP-gate bug**: beats_baselines now defaults False when baselines missing
- **Added model audit rules**: truth_audit.sh now flags Sharpe>5 and empty baselines
- **Merged agent work**: gated persistence (_save_with_gates) into ml_pipeline.py

### Data pipeline ✅
- Research CSVs: 45K+ docs (7 collections)
- yfinance: 14,295 OHLCV bars
- Databento SPY 2024: 252 days, $108.36
- Databento QQQ 2024H1: 35 days, $15.05
- GEX features: 229 rows (Jan-Nov 2024)

### Features
- SPY v1.0: 167 rows × 45 features (QUARANTINED)
- SPY v2.0: 229 rows × 23 features (Databento GEX + underlying) — NOT YET TRAINED
- QQQ/IWM/DIA/TLT: 2,799 rows × 32 features each

### Live models (models/, NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87 — KEEP, needs OOS
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81 — INVESTIGATE
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14 — KEEP, needs OOS

### Blocked
- MongoDB Atlas: SSL handshake failing (transient)
- Next: Retrain SPY v2.0 with GEX features when MongoDB recovers

### Commits (30+ total)
- 9b878a3: Merge audit branch
- 79193e8: Fix SHIP-gate bug
- b94ee3c: Quarantine SPY/TLT + audit rules
- 009db0c: SPY v2.0 GEX features
- da32638: Fix OSI regex
- 7f6559b: Train IWM/DIA/TLT
- 1f7ae46: QQQ model + 4-ticker features
- 6303218: calc_vex/dex/vega_total
- 96f07e5: ML quality gates
- be44fbe: yfinance + BS greeks fix
