# SPY Regime-Enhanced Training Report

**Date:** 2026-05-24T02:19:51.155330+00:00
**Features:** 62 (45 original + 6 regime)

## CV Results (8-fold walk-forward)
          accuracy  precision    recall        f1    sharpe  n_test
model                                                              
GBM_deep  0.770833   0.802715  0.869299  0.806872  8.669429    18.0
Logistic  0.687500   0.737925  0.790938  0.720190  7.613514    18.0
GBM       0.791667   0.826425  0.812354  0.797335  6.191862    18.0

## Winner: GBM_deep
- OOS Sharpe: 8.669
- Baseline majority Sharpe: 0.666
- Baseline persistence Sharpe: 0.722

## Shipped Model
- Model: models/SPY_direction_v2.0-regime.joblib
- In-sample accuracy: 1.000
- In-sample Sharpe: 0.000