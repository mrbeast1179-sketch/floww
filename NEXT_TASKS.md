# NEXT_TASKS.md

## Phase 4 ML — Round 2 Complete (2026-05-20)

### Shipped ✅
- 1D-CNN AE anomaly detector (trained, validated 100% recall/0% FPR)
- PatchTST VPIN forecaster (CNN fallback, beats persistence by 19%)
- HuggingFace asset acquisition script
- Ensemble inference module (CNN AE + PatchTST residual + statistical)
- Regime-aware thresholds (calm→99th, active→95th, urgent→90th pct)
- 54 ML tests passing (ensemble, regime, anomaly training, PatchTST, Autoformer)
- Backtest harness with synthetic toxic-flow injection

### Remaining
- Autoformer chain dynamics training script (needs HF model download)
- Production training on real MongoDB gex_history data (needs WiFi)
- Ensemble calibration on real FOMC/NFP events
- Wire ensemble into Dash UI toxicity gauge

### Blocked on MongoDB (need WiFi)
- Real VPIN training data from gex_history collection
- Walk-forward backtest on historical data
- FOMC day validation
