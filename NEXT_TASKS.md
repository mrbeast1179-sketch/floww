# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file

---

## Status: MongoDB Atlas SSL blocked — all other work complete

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, models
- SPY/TLT v1.0 quarantined (audit findings)
- SHIP-gate bug fixed, model audit rules added
- Agent work merged (gated persistence + multi-ticker features)
- 102 tests pass
- 50+ commits on main

### Live models (NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81 (INVESTIGATE)
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

---

## Blocked on MongoDB Atlas SSL

All remaining tasks require MongoDB:

- [ ] **Retrain SPY v2.0** with GEX features (229 rows × 23 features)
- [ ] **Paper trade dry-run** via Alpaca
- [ ] **Expand Databento** to IWM/DIA
- [ ] **Verify feature quality** (variance checks on v2.0 features)

---

## MongoDB SSL Issue
- All 3 shards: errno=54 Connection reset by peer
- TCP connects, SSL handshake fails immediately
- Likely Atlas-side TLS configuration issue
- Check: IP allowlist, Atlas dashboard alerts, try different network
