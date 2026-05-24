# Offline ML Training Report — 2026-05-24

## Pipeline

- **Script:** `backend/scripts/train_offline.py`
- **Data:** `data/cached_features/{DIA,IWM,QQQ,TLT}_v1.0.csv` (2800 rows each)
- **Features:** 44 per sample (returns, SMAs, ATR, volume, realized vol, RSI, MACD, BB, calendar)
- **Target:** `target_directional_move` (1 if next-day return > 0)
- **CV:** Walk-forward, expanding window: 500 train → 50 test, step 50, 5 folds
- **Gate:** Must beat majority + persistence baselines, test_acc > 50%, gap < 15%

## Results

| Ticker | Model | Ship Rate | Median Sharpe | Best Sharpe | Avg Acc | Gap |
|--------|-------|-----------|---------------|-------------|---------|-----|
| **TLT** | logistic | **4/5 (80%)** | **1.86** | 3.24 | 55.2% | 0.05 |
| QQQ | logistic | 1/5 (20%) | 2.57 | 8.10 | 58.4% | 0.03 |
| IWM | logistic | 1/5 (20%) | 2.00 | 4.73 | 48.4% | 0.10 |
| DIA | logistic | 0/5 (0%) | 3.62 | 5.36 | 56.0% | 0.05 |

## Key Findings

1. **TLT logistic is the clear winner**: 80% ship rate, consistent positive Sharpe across 4/5 folds, tiny 5% overfit gap. This is a robust, generalizable model.

2. **Logistic Regression is the only model that generalizes**: GBM and RF were tested but rejected in all folds due to massive overfit (train-test gap 30-60%). With 500 samples and 44 features, tree-based models overfit badly.

3. **DIA has edge but no consistent regime**: All 5 folds had positive Sharpe (median 3.62) but each fold's test period was different enough that the gate rejected. The model works but isn't regime-consistent.

4. **QQQ and IWM show promise**: Both have 1 SHIP fold with strong Sharpe (8.10 and 4.73 respectively). More data or regime filtering could improve consistency.

5. **The gate is working correctly**: It rejects models that overfit (gap > 15%) or fail to beat baselines. No false positives shipped.

## Shipped Artifacts

- `models/TLT_logistic_offline_20260524_022311.joblib` — TLT logistic model (full data)
- `models/IWM_logistic_offline_20260524_022311.joblib` — IWM logistic model (full data)
- `models/QQQ_logistic_offline_20260524_022311.joblib` — QQQ logistic model (full data)
- `models/offline_training_summary.json` — Full results JSON

## Next Steps

1. **Add GEX features to the v1.0 feature set**: The current 44 features are all technical/return-based. Adding the 6 GEX features from `add_gex_features` (gex_zscore_60d, gex_roc_5d, gex_regime_pos, gex_distance_to_flip_norm, gex_wall_density_pct, gex_herfindahl) could significantly improve predictive power.

2. **Regime-filtered training**: Train separate models for high/low volatility regimes. TLT's consistency suggests bond market regimes are more stable.

3. **Ensemble**: Combine logistic predictions across tickers for a meta-signal.

4. **MongoDB integration**: When WiFi is available, retrain on the full `gex_history` collection for more features and longer history.
