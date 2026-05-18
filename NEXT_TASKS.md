# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file

---

## Status: MongoDB Atlas SSL blocked

### All background processes completed ✅
- SPY Databento 2024: 252 days, $108.36
- QQQ Databento 2024H1: 35 days, $15.05
- GEX features: 229 rows (Jan-Nov 2024)

### Done ✅
- 5 ticker models trained (SPY/QQQ/IWM/DIA/TLT)
- SPY v1.0 and TLT v1.0 quarantined (audit findings)
- SHIP-gate bug fixed
- Model audit rules in truth_audit.sh
- calc_vex/dex/vega_total (23 tests)
- BS greeks d1 fix (20 tests)
- ML quality gates (33 tests)

### Agent worktrees (pending merge)
- agent-a681f0a845b9a734a: ml_pipeline.py gated persistence (319 lines)
- agent-a8e5e9b132407cc03: features.py multi-ticker support (222 lines)

### Live models (NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81 (INVESTIGATE)
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

---

## On-deck (when MongoDB recovers)

- [ ] **Merge agent worktrees** — review and merge ml_pipeline.py + features.py changes
- [ ] **Retrain SPY v2.0** with GEX features (229 rows × 23 features)
- [ ] **Paper trade dry-run** via Alpaca
- [ ] **Expand Databento** to IWM/DIA

---

## Blocked
- MongoDB Atlas: SSL handshake failing (server-side RST, all 3 shards)
