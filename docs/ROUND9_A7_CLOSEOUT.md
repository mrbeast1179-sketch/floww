# A7 Close-out — ToxicityGauge UI + Backend Ensemble Validation

## Summary

Investigated and validated the toxicity detection pipeline:
- Backend `ml_ensemble.py` (PlattScaler + ToxicityEnsemble)
- Frontend `ToxicityGauge.jsx`

## Findings

### Backend: Contract Sound ✓

All Platt scaler contract tests pass:
- Output always in [0, 1]
- Monotonic (higher scores → higher probabilities)
- Handles edge cases: constant scores, extreme values, single element
- Unfitted fallback works correctly

**No backend fix needed.**

### Frontend: 3 Fixes Applied

1. **Null safety:** Added `hasData` flag. When `ensemble` is null, shows "No toxicity data — feed VPIN + QI to activate" instead of "No anomalies detected"
2. **Falsy probability bug:** Changed `probs[h.key] || 0` to `probs[h.key] ?? 0` so that probability `0` is displayed correctly (not treated as falsy)
3. **Anomaly flags:** Wrapped in `hasData` guard to prevent showing "No anomalies detected" when there's no data

### Tests

- `backend/tests/services/test_toxicity_ensemble_contract.py` — 9 tests, all passing
- Existing `backend/tests/services/test_ml_ensemble.py` — 12+ tests, unchanged

### Documentation

- `docs/ROUND9_A7_TOXICITY_CONTRACT.md` — Full contract spec for backend + frontend

## Commits

- `fix(a7-frontend): ToxicityGauge null safety + falsy probability fix`
- `test(a7): toxicity ensemble contract tests`
- `docs(a7): toxicity detection contract`

## Round 10 Candidates

See "Round 10 Candidates" section in `ROUND9_A7_TOXICITY_CONTRACT.md`.
