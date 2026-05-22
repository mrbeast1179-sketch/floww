# Double Machine Learning (DML) Causal Analysis Report

**Generated:** 2026-05-22 01:26 UTC

**Data:** SPY daily features, 115 observations
**Date range:** 2024-01-19 00:00:00 to 2024-12-27 00:00:00

## Methodology

- **Algorithm:** LinearDML (EconML)
- **Treatment:** VPIN CDF (continuous, 0-1)
- **Outcome:** Next-day SPY return (ret_1d)
- **Confounders:** realized_vol_10d, realized_vol_21d, relative_volume, net_gex, put_call_ratio, atr_14, day_of_week, month
- **Nuisance models:** GradientBoostingRegressor (outcome), GradientBoostingRegressor (treatment)
- **Regime split:** realized_vol_21d median

---

## Results

### Overall Average Treatment Effect (ATE)

| Metric | Value |
|--------|-------|
| ATE | 0.024283 |
| 95% CI Lower | 0.016069 |
| 95% CI Upper | 0.032496 |
| Statistically Significant | YES |

**Interpretation:** A high VPIN day is associated with a 2.4283% change 
in next-day SPY returns (causal estimate, controlling for confounders).

### ATE by Market Regime

| Regime | ATE | 95% CI | N | Significant |
|--------|-----|--------|---|-------------|
| Calm (low vol) | 0.002944 | [-0.003673, 0.009561] | 58 | NO |
| Urgent (high vol) | 0.031728 | [0.021691, 0.041765] | 57 | YES |

### Conditional ATE by VPIN Quantile

| VPIN Quantile | ATE | N |
|---------------|-----|---|
| Q4_high | 0.016104 | 29 |
| Q3 | -0.016570 | 28 |
| Q2 | 0.002537 | 29 |
| Q1_low | 0.198618 | 29 |

---

## Discussion

The overall ATE is statistically significant (0.024283), 
suggesting that high VPIN has a causal effect on next-day returns 
after controlling for confounders.

The treatment effect varies by regime, indicating that the VPIN 
signal's causal impact depends on market conditions.

### Limitations

- Binary treatment (high/low VPIN) loses information vs. continuous treatment

- Daily frequency VPIN is an approximation of tick-level VPIN

- DML assumes no unmeasured confounders (strong ignorability)

- 167 observations limits power for subgroup analyses

- GradientBoosting nuisance models may overfit with small samples
