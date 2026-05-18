# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file

---

## Status: MongoDB Atlas SSL blocked

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, models
- SPY/TLT v1.0 quarantined (audit findings)
- SHIP-gate bug fixed, model audit rules added
- Agent work merged (gated persistence + multi-ticker features)
- 102 tests pass
- SPY v2.0 training script written
- Paper-trade dry-run script written
- Agent worktrees cleaned up

### Live models (NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81 (INVESTIGATE)
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

---

## Blocked on MongoDB Atlas SSL

- [ ] **Retrain SPY v2.0** — script ready (`scripts/train_spy_v2.py`), needs MongoDB
- [ ] **Paper trade dry-run** — script ready (`scripts/paper_trade_dry_run.py`), needs MongoDB
- [ ] **Expand Databento to IWM/DIA** — needs MongoDB for dedup check

---

## MongoDB SSL Issue
- All 3 shards: errno=54 Connection reset by peer
- TCP connects, SSL handshake fails immediately
- Likely Atlas-side TLS configuration issue
- Check: IP allowlist, Atlas dashboard alerts, try different network
