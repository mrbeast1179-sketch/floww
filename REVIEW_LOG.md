# REVIEW_LOG.md

## 2026-05-18 — Final state

### All CLI work complete ✅

**Tests: 276 pass, 0 fail**

**Merged branches (13):**
- feat/ml-gate-module, feat/rolling-oos-evaluator
- fix/audit-pipefail-guards, fix/ci-test-failure-detection, fix/training-baseline-gate
- safety/audit-detect-suspect-models, safety/quarantine-iwm-v1, safety/quarantine-spy-tlt-v1
- feat/research-discovery-framework, feat/research-extract-code-links, feat/code-link-extractor
- docs/adr-live-trading-promotion, docs/adr-model-promotion-policy

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
