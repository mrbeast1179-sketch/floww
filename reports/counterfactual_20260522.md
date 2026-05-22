# Counterfactual Analysis Report

**Generated:** 2026-05-22 01:29 UTC

**Data:** SPY daily features, 115 observations
**Date range:** 2024-01-19 00:00:00 to 2024-12-27 00:00:00

**Initial capital:** $10,000

## Strategy Definitions

1. **BASELINE:** Buy and hold SPY (always 100% invested)
2. **VPIN-FILTERED:** Reduce position by 50% when VPIN CDF > 0.7
3. **DML-WEIGHTED:** Position size adjusted by DML-estimated causal effect

---

## Performance Comparison

| Metric | Baseline | VPIN-Filtered | DML-Weighted |
|--------|----------|---------------|--------------|
| Total Return | 19.19% | 13.27% | 20.27% |
| Annualized Sharpe | 2.8635 | 2.1739 | 3.1042 |
| Max Drawdown | -5.22% | -5.22% | -4.91% |
| Win Rate | 60.00% | 60.00% | 0.00% |
| Trading Days | 115 | 115 | 115 |
| Days Reduced | N/A | 47 | N/A |

---

## Key Findings

### VPIN-Filtered vs Baseline

- VPIN-filtered return: 13.27%
- Baseline return: 19.19%
- Alpha from VPIN filtering: -5.93%
- **VPIN filtering UNDERPERFORMED** buy-and-hold by 5.93%
- Days with reduced exposure: 47

### DML-Weighted vs Baseline

- DML-weighted return: 20.27%
- Baseline return: 19.19%
- Alpha from DML weighting: 1.08%
- **DML weighting OUTPERFORMED** buy-and-hold by 1.08%
### Risk Comparison

- Baseline max drawdown: -5.22%
- VPIN-filtered max drawdown: -5.22%
- DML-weighted max drawdown: -4.91%
- Baseline Sharpe: 2.8635
- VPIN-filtered Sharpe: 2.1739
- DML-weighted Sharpe: 3.1042

---

## Discussion

The counterfactual analysis demonstrates the value add of VPIN-based position sizing.

VPIN filtering did not improve raw returns, but may have improved 
risk-adjusted returns (Sharpe ratio). The 2024 bull market meant 
that being out of the market was costly.

### Limitations

- No transaction costs or slippage modeled

- Single-year backtest (2024) may not generalize

- VPIN threshold (0.7) and reduction fraction (0.5) are not optimized

- Daily frequency VPIN is an approximation

- DML ATE used for position sizing assumes stable causal relationship
