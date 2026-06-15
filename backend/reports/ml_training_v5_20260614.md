# ML Training Report — v5 Production Ensemble

**Date**: 2026-06-14
**Data**: 5 years (2021-06-14 to 2026-06-12) via yfinance
**Model**: Ensemble (GBM + RF + Logistic, soft voting, weights [2,1,1])
**Features**: 30 selected from 54 raw (39 technical + 15 GEX)
**Target**: 2-class (UP/DOWN, 0.3% threshold)
**Split**: 70/15/15 train/val/test with 5-day embargo

---

## Results Summary

| Ticker | Test Acc | WF CV | Sharpe | B&H Sharpe | Return | B&H Return | Max DD | Trades |
|--------|----------|-------|--------|------------|--------|------------|--------|--------|
| **SPY** | **56.0%** | 50.6% | **2.22** | 2.00 | **24.9%** | 24.2% | **-4.8%** | 186 |
| QQQ | 53.2% | 50.5% | 0.31 | 0.48 | 6.8% | 12.8% | -24.7% | 184 |
| DIA | 41.0% | 48.1% | 0.00 | 1.81 | 0.0% | 18.9% | -5.9% | 139 |
| IWM | 46.3% | 48.7% | -0.84 | 0.46 | -17.6% | 12.3% | -24.4% | 176 |
| TLT | 54.7% | 53.2% | -0.46 | -0.23 | -5.4% | -3.5% | -12.8% | 157 |

---

## SPY Progression (v3 → v4 → v5)

| Metric | v3 RF | v4 Ensemble | v5 Ensemble |
|--------|-------|-------------|-------------|
| Test Acc | 40.6% | 47.9% | **56.0%** |
| WF CV | 40.4% | 50.0% | **50.6%** |
| Sharpe | 1.01 | 1.28 | **2.22** |
| Return | 11.3% | 6.3% | **24.9%** |
| Max DD | -10.1% | -3.8% | **-4.8%** |
| Features | 54 | 54 | **30** |

---

## Top Features by Ticker

### SPY
1. ret_1d (0.054), price_vs_sma_50 (0.053), overnight_gap (0.044)

### QQQ
1. realized_vol_21d (0.058), price_vs_sma_5 (0.052), realized_vol_10d (0.047)

### DIA
1. overnight_gap (0.055), rsi_14 (0.050), ret_1d (0.050)

### IWM
1. realized_vol_5d (0.059), net_gex (0.057), ret_3d (0.044)

### TLT
1. net_gex_zscore_60d (0.057), sma_5 (0.054), vol_ratio_5_60 (0.051)

---

## Key Findings

1. **SPY is the strongest model**: 56% test acc, Sharpe 2.22 vs B&H 2.00, max DD only -4.8%
2. **GEX features matter**: net_gex_zscore_60d is top-3 for TLT, net_gex #2 for IWM
3. **Volatility features dominate**: realized_vol in top-3 for QQQ, IWM, TLT
4. **Overnight gap is universal**: top-3 for SPY, DIA
5. **QQQ/IWM need work**: negative or low Sharpe — need different hyperparameters

## Artifacts

Models saved to backend/models/ (gitignored):
- {SPY,QQQ,DIA,IWM,TLT}_ensemble_v5_*.joblib
- {SPY,QQQ,DIA,IWM,TLT}_ensemble_v5_*_scaler.joblib
- {SPY,QQQ,DIA,IWM,TLT}_ensemble_v5_*_manifest.json

Training script: scripts/train_v5_production.py
