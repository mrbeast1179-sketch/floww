VERDICT: INVESTIGATE

# SPY Direction Model v1.0 — 2024 Backtest
_Generated: 2026-05-18T03:27:53.562796+00:00_

## Methodology

Loaded the shipped SPY artifact (`models/SPY_direction_v1.0.joblib` + `models/SPY_scaler_v1.0.joblib`) with a `_quarantine` guard, pulled SPY `ml_features` rows for `2024-01-01 <= date < 2025-01-01` from MongoDB (`confluence_decoder.ml_features`), and joined next-day outcomes from `gex_llm_patterns_outcomes` (167 labeled 2024 rows in this database). Where outcomes are absent for a date, we fall back to the `target_directional_move` / `target_return_pct` fields already on the `ml_features` row. The walk-forward structure splits 2024 into four calendar quarters; the **same shipped model** is evaluated on each quarter — we do not retrain. Metrics: precision, recall, F1 (positive class = next-day up move), accuracy, hit rate (signed prediction = signed return), and profit factor (sum of winning trade P&L over absolute losing P&L, with P&L = +`return_pct` when predicting up and −`return_pct` when predicting down).

> CAVEAT: the shipped artifact was trained on 167 rows (per `SPY_meta_v1.0.json`); the 2024 evaluation set has 167 rows that overlap with that training window. Headline metrics are therefore IN-SAMPLE on the deployed pickle. Treat the quarterly breakdown as a sanity check on the deployed artifact, not as out-of-sample evidence.

## Monthly Breakdown

| Month | Precision | Recall | F1 | Accuracy | Hit Rate | Profit Factor | n_predictions |
|-------|-----------|--------|----|----------|----------|---------------|---------------|
| 2024-01 | 1.000 | 1.000 | 1.000 | 1.000 | 0.529 | 1.400 | 17 |
| 2024-02 | 1.000 | 1.000 | 1.000 | 1.000 | 0.533 | 2.811 | 15 |
| 2024-03 | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 2.133 | 16 |
| 2024-04 | 1.000 | 1.000 | 1.000 | 1.000 | 0.375 | 0.593 | 16 |
| 2024-05 | 1.000 | 1.000 | 1.000 | 1.000 | 0.429 | 2.278 | 14 |
| 2024-06 | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0.000 | 1 |
| 2024-07 | 1.000 | 1.000 | 1.000 | 1.000 | 0.455 | 1.568 | 11 |
| 2024-08 | 1.000 | 1.000 | 1.000 | 1.000 | 0.353 | 0.853 | 17 |
| 2024-09 | 1.000 | 1.000 | 1.000 | 1.000 | 0.667 | 2.000 | 15 |
| 2024-10 | 1.000 | 1.000 | 1.000 | 1.000 | 0.471 | 0.718 | 17 |
| 2024-11 | 1.000 | 1.000 | 1.000 | 1.000 | 0.538 | 3.866 | 13 |
| 2024-12 | 1.000 | 1.000 | 1.000 | 1.000 | 0.533 | 0.652 | 15 |

## Quarterly Walk-Forward

| Quarter | Precision | Recall | F1 | Accuracy | Hit Rate | Profit Factor | n_predictions |
|---------|-----------|--------|----|----------|----------|---------------|---------------|
| Q1 | 1.000 | 1.000 | 1.000 | 1.000 | 0.604 | 2.006 | 48 |
| Q2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.387 | 1.000 | 31 |
| Q3 | 1.000 | 1.000 | 1.000 | 1.000 | 0.488 | 1.184 | 43 |
| Q4 | 1.000 | 1.000 | 1.000 | 1.000 | 0.511 | 1.065 | 45 |

## Overall (2024)

- n_predictions: 167
- precision: 1.000
- recall: 1.000
- F1: 1.000
- accuracy: 1.000
- hit rate: 0.509
- profit factor: 1.272

## Label Sources

- `outcomes_collection`: 167

## Verdict Logic

- SHIP when n >= 60, accuracy >= 0.55, profit_factor >= 1.5
- INVESTIGATE when accuracy >= 0.5 and profit_factor >= 1.0
- REJECT otherwise

Note: a SHIP verdict here is necessary but not sufficient for deployment confidence — see the in-sample caveat above. Out-of-sample validation requires fresh post-2024 labeled rows.
