---
id: O-PHASE2-ANOMALY
title: Phase 2 — 1D-CNN anomaly detector + HF asset acquisition
assignee: Agent 2
skill: mlops:dspy + mlops:evaluating-llms-harness + gbrain:academic-verify
estimate_hours: 3
dependencies: []
status: done
last_update: 2026-07-09T00:00:00Z
commits: [f77fbc2, 3af1755, b9bcf23, cf921fd, c109a72, 9c32dcd]
blockers: []
---

## Deliverable
Trained AE checkpoint, threshold calibrated to 95th percentile reconstruction error, recall >= 95% on injected toxicity

## Files
- `scripts/acquire_hf_assets.py` (new)
- `scripts/train_anomaly_detector.py` (new)
- `scripts/validate_anomaly_detector.py` (new)
- `backend/tests/services/test_anomaly_training.py` (new)
- `./project_oracle/models/` (new dir)
- `./project_oracle/datasets/` (new dir)

## HuggingFace Targets
- PatchTST, Informer, Autoformer (forecasting)
- 1D-CNN AE, Transformer-AE (anomaly)
- DeepLOB, LiT, Neural Hawkes (LOB)
- FI-2010 dataset

## Acceptance Criteria
- [ ] Trained autoencoder checkpoint saved
- [ ] Threshold calibrated to 95th percentile reconstruction error
- [ ] Recall >= 95% on injected toxicity
- [ ] HF assets acquired and catalogued
- [ ] All commits conventional
