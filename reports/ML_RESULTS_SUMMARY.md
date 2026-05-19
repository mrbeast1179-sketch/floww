# ML Training Results — 2026-05-19

## Bake-off Results (v1.0 features, 8-fold walk-forward CV)

| Ticker | Best Model | Sharpe | Majority Baseline | Persistence Baseline | Verdict |
|--------|-----------|--------|-------------------|---------------------|---------|
| **TLT** | GBM_deep | **1.365** | 0.000 | -0.168 | **SHIP** ✅ |
| **IWM** | GBM_deep | **0.955** | 0.914 | 0.324 | **SHIP** ✅ |
| **IWM** | GBM (enhanced) | **1.397** | 0.914 | 0.324 | **SHIP** ✅ |
| QQQ | GBM_deep | 1.867 | 2.359 | 2.024 | REJECT |
| DIA | GBM_deep | 1.224 | 1.636 | 1.666 | REJECT |

## Enhanced Training Results (engineered features)

| Ticker | Target | Best Model | Sharpe | Verdict |
|--------|--------|-----------|--------|---------|
| **TLT** | directional_move | GBM_deep | **1.143** | **SHIP** ✅ |
| **TLT** | directional_move | GBM | **0.354** | **SHIP** ✅ |
| **IWM** | directional_move | GBM | **1.397** | **SHIP** ✅ |
| **IWM** | directional_move | GBM_deep | **0.988** | **SHIP** ✅ |
| QQQ | directional_move | GBM_deep | 1.867 | REJECT |
| DIA | directional_move | GBM | 1.397 | REJECT |

## Key Insights

1. **TLT is the best ticker for ML trading** — no directional bias (51.1% up), models consistently beat baselines
2. **IWM is second best** — slight upward bias (53%), but models can beat baselines with feature engineering
3. **QQQ and DIA are hard to beat** — strong upward bias (56.2% and 54.7%), majority baseline is very strong
4. **Feature engineering matters** — enhanced features improved IWM from 0.955 to 1.397 Sharpe
5. **Range expansion and gap move targets are too imbalanced** — <3% positive rate, quality gates fail

## Recommended Production Models

1. **TLT direction_v1.0** — GBM_deep, Sharpe=1.365 (bake-off), 47 features
2. **IWM direction_v1.0** — GBM, Sharpe=1.397 (enhanced), 47 features

## Next Steps

1. Save production model artifacts (model.joblib, scaler.joblib, manifest.json)
2. Register models in MongoDB ml_models collection
3. Set up paper trade dry-run for TLT and IWM
4. Investigate why QQQ/DAA are so hard to beat (regime-specific models?)
5. Try non-directional targets (volatility, mean-reversion)
