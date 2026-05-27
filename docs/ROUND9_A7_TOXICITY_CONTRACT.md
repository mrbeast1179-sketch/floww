# Toxicity Detection Contract

## Backend

**Module:** `backend/services/ml_ensemble.py`

### PlattScaler

**Class:** `PlattScaler`

| Method | Signature | Returns |
|--------|-----------|---------|
| `fit` | `(scores: np.ndarray, labels: np.ndarray) → None` | Fits Platt scaling parameters (A, B) via MLE |
| `predict_proba` | `(scores: np.ndarray) → np.ndarray` | Calibrated probabilities in [0, 1] |

**Contract:**
- Output is always in [0, 1] (sigmoid function)
- Monotonic: higher input scores → higher output probabilities
- Handles edge cases: constant scores, extreme values, single element
- Unfitted fallback: sigmoid with default params (mean/std normalization)

### ToxicityEnsemble

**Class:** `ToxicityEnsemble`

| Method | Signature | Returns |
|--------|-----------|---------|
| `update` | `(vpin: float, qi: float) → Dict[str, Any]` | Ensemble output with probabilities per horizon |
| `calibrate` | `(horizon: int, scores: np.ndarray, labels: np.ndarray) → None` | Calibrates a specific horizon |
| `get_state` | `() → Dict[str, Any]` | Current ensemble state |

**Input features:**
- `vpin`: float — Volume-Synchronized Probability of Informed Trading, [0, 1]
- `qi`: float — Quote Imbalance, signed

**Output shape:**
```python
{
    "ensemble_probabilities": {
        "p_toxic_1min": float,   # [0, 1]
        "p_toxic_5min": float,   # [0, 1]
        "p_toxic_15min": float,  # [0, 1]
        "p_toxic_60min": float,  # [0, 1]
    },
    "component_scores": {
        "cnn_ae": float,           # CNN autoencoder reconstruction error
        "statistical": float,      # Statistical anomaly score
        "forecast_residual": float, # PatchTST forecast residual
    },
    "cnn_anomaly": bool,
    "statistical_anomaly": bool,
    "status": "active" | "inactive",
}
```

**Thresholds (recommended for UI):**
- [0.0, 0.4) — low toxicity (green)
- [0.4, 0.7) — elevated (yellow)
- [0.7, 1.0] — high toxicity (red)

**Sub-models:**
1. 1D-CNN Autoencoder (reconstruction error)
2. Statistical detector (z-score based)
3. PatchTST forecaster (forecast vs realized residual)

**Aggregation:** Simple average of normalized scores, then Platt-calibrated per horizon.

## Frontend

**Component:** `frontend/src/components/ToxicityGauge.jsx`

### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `ensemble` | `object \| null` | No | Output from `ToxicityEnsemble.update()` |
| `onRefresh` | `() → void` | No | Refresh callback |

### Behavior

- **Null safety:** When `ensemble` is null or has no probability data, renders "No toxicity data" empty state
- **Falsy probability handling:** Uses `?? 0` (not `|| 0`) so that probability `0` is displayed correctly
- **Color thresholds:** Matches backend thresholds (green < 0.4, yellow 0.4-0.7, red ≥ 0.7)
- **NaN protection:** `probColor()` returns gray `#64748b` for null/undefined/NaN
- **Deterministic:** Same input always produces same output (no random state)

### Visual Layout

1. Status badge (LIVE/INACTIVE indicator)
2. HIGH TOXICITY / ELEVATED tags (conditional)
3. 4 horizon gauge arcs (1m, 5m, 15m, 60m)
4. Component scores (CNN-AE, Statistical, Forecast)
5. Anomaly flags (CNN ANOMALY, STATISTICAL ANOMALY)

## Round 10 Candidates

1. **Per-horizon scoring:** Currently all horizons get the same combined score before calibration. Each horizon should compute its own score based on horizon-specific features.
2. **Calibration data persistence:** `_calibration_data` is stored in memory only. Should persist to MongoDB for restart resilience.
3. **Ensemble weights:** Simple average (1/3 each) — could be learned from historical performance.
4. **Frontend animation:** Gauge arcs could animate smoothly between values instead of jumping.
5. **WebSocket push:** Currently requires polling. WebSocket push would reduce latency.
