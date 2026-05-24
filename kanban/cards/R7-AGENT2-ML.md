---
card_id: R7-AGENT2-ML
title: "R7: Agent 2 — ML/Anomaly & RL Trading Env"
status: done
assignee: Agent 2
round: 7
sha: 9c32dcd
subject: "feat(rl): Agent 2 — trading environment (Gym-compatible) + tests"
acceptance: "Gym env passes step/reset/spec tests; WalkForwardML backtest RL integration confirmed"
insight: "The RL trading env wraps the existing backtest cleanly — reusing the same data pipeline eliminates train/test leakage"
upstream: [R7-AGENT1-INGEST, R7-AGENT5-MATH]
downstream: [R7-AGENT3-DASH]
---

# R7: Agent 2 — ML/Anomaly & RL Trading Env

## Summary
1D-CNN autoencoder anomaly detector + Gym-compatible RL trading environment. Walk-forward ML backtest with regime-aware thresholds.

## Commits
- `9c32dcd` — feat(rl): Agent 2 — trading environment (Gym-compatible) + tests
- `cf921fd` — feat(ml): ensemble inference + regime-aware thresholds + PatchTST/Autoformer tests

## Acceptance Criteria
- [x] 1D-CNN autoencoder detects anomalies with <30ms p99
- [x] Gym env passes step/reset/spec tests
- [x] Walk-forward backtest integrates RL signals
- [x] Ensemble inference combines multiple models
