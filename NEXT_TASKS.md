# NEXT_TASKS.md — Hermes work queue

> **Read order:** 1. CLAUDE_REVIEW_PROMPT.md → 2. REVIEW_LOG.md → 3. This file

---

## Status: All CLI work complete — blocked on MongoDB Atlas SSL

### Done ✅
- Phase 0-5: Audit, data, quality gates, math, features, models
- SPY/TLT v1.0 quarantined (audit findings)
- SHIP-gate bug fixed, model audit rules added (Rules 1-12)
- Agent work merged (gated persistence + multi-ticker features)
- 139 tests pass (0 fail)
- All scripts written and committed
- Agent worktrees cleaned up

### Live models (NOT in quarantine)
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- IWM_direction_v1.0: acc=0.55, F1=0.48, Sharpe=5.81 (INVESTIGATE)
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

### Scripts written
- `scripts/train_spy_v2.py` — SPY v2.0 training with GEX features
- `scripts/paper_trade_dry_run.py` — daily paper-trade dry-run
- `scripts/backtest_model.py` — walk-forward backtest
- `scripts/compute_gex_features.py` — GEX/VEX/DEX from Databento chains
- `scripts/build_spy_gex_features.py` — combined GEX + underlying features

### Tests written (139 total)
- `test_train_spy_v2.py` — 15 tests (walk-forward, baselines, Sharpe, features, quality gates)
- `test_paper_trade_dry_run.py` — 7 tests (model loading, features, dry-run)
- `test_pipeline_integration.py` — 10 tests (end-to-end, separable data, degenerate data)
- `test_backtest_model.py` — 5 tests (feature building, backtest, model loading)
- Plus existing: 33 quality gates, 29 analytics, 20 BS greeks, 25 other

---

## Blocked on MongoDB Atlas SSL

- [ ] **Retrain SPY v2.0** — script ready, needs MongoDB
- [ ] **Paper trade dry-run** — script ready, needs MongoDB
- [ ] **Backtest** — script ready, needs MongoDB
- [ ] **Expand Databento to IWM/DIA** — needs MongoDB for dedup check

---

## MongoDB SSL Issue
- All 3 shards: errno=54 Connection reset by peer
- TCP connects, SSL handshake fails immediately
- Server-side RST — Atlas TLS configuration issue
- Check: IP allowlist, Atlas dashboard alerts, try different network
