# REVIEW_LOG.md

## 2026-05-18 — Final state

### All CLI work complete ✅

**Tests: 223 pass, 0 fail**

**Merged branches:**
- feat/ml-gate-module (gate.py + tests)
- feat/rolling-oos-evaluator (rolling_oos.py + 22 tests)
- fix/audit-pipefail-guards (truth_audit.sh fix)
- fix/ci-test-failure-detection (CI workflow fix)
- fix/training-baseline-gate (SHIP-gate bug fixes)
- safety/audit-detect-suspect-models (model audit rules)
- safety/quarantine-iwm-v1 (IWM quarantined, Sharpe 5.81)
- safety/quarantine-spy-tlt-v1 (SPY/TLT quarantined)
- feat/research-discovery-framework (arxiv discovery)
- feat/research-extract-code-links (code link extraction)
- feat/code-link-extractor (code link extraction from papers)

**Live models (NOT in quarantine):**
- QQQ_direction_v1.0: acc=0.53, F1=0.57, Sharpe=2.87
- DIA_direction_v1.0: acc=0.53, F1=0.55, Sharpe=2.14

**Quarantined models:**
- SPY v1.0 (overfit, Sharpe 31.5)
- TLT v1.0 (Sharpe 0.0, no edge)
- IWM v1.0 (Sharpe 5.81 > 5)
- 12 synthetic data models

**Blocked on MongoDB Atlas SSL:**
- All 3 shards: errno=54 Connection reset by peer
- Blocks: SPY v2.0 retraining, paper-trade, backtest, IWM/DIA backfill
