# SPY Walk-Forward Backtest Report (v2.0-regime)

**Date:** 2026-05-24T02:26:13.553347+00:00
**Method:** 8-fold expanding-window walk-forward
**Model:** GBM_deep, 62 features

## Aggregate OOS Metrics
| Metric | Value |
|--------|-------|
| Accuracy | 0.771 |
| Precision | 0.733 |
| Recall | 0.880 |
| F1 | 0.800 |
| OOS Sharpe | 8.376 |
| Win Rate | 0.733 |
| Profit Factor | 2.75 |
| Total P&L | +42 units |
| vs Majority Baseline | BEATS |

## Fold Details
- Fold 0 [2024-02-01]: acc=0.500 sharpe=0.935 n_test=18
- Fold 1 [2024-03-07]: acc=0.500 sharpe=0.000 n_test=18
- Fold 2 [2024-04-08]: acc=0.889 sharpe=25.204 n_test=18
- Fold 3 [2024-05-14]: acc=0.833 sharpe=11.906 n_test=18
- Fold 4 [2024-07-25]: acc=0.778 sharpe=10.144 n_test=18
- Fold 5 [2024-09-03]: acc=0.944 sharpe=21.166 n_test=18
- Fold 6 [2024-10-08]: acc=0.944 sharpe=0.000 n_test=18
- Fold 7 [2024-11-07]: acc=0.778 sharpe=0.000 n_test=18