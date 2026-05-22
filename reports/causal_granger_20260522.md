# Granger Causality Analysis Report

**Generated:** 2026-05-22 01:18 UTC

**Data:** SPY daily features, 167 observations
**Date range:** 2024-01-02 00:00:00 to 2024-12-30 00:00:00

---

## Summary of Results

| Test | Optimal Lag | F-Statistic | P-Value | Significant (p<0.05) |
|------|------------|-------------|---------|----------------------|
| VPIN CDF → SPY Returns | 4 | 0.5178 | 0.722836 | NO |
| Quote Imbalance → SPY Returns | 8 | 0.9881 | 0.451910 | NO |
| VPIN CDF → SPY Volatility | 5 | 1.0620 | 0.387029 | NO |
| Quote Imbalance → SPY Volatility | 6 | 2.7816 | 0.016214 | YES * |

---

## VPIN CDF → SPY Returns

**Optimal lag:** 4 days
**F-statistic:** 0.5178
**P-value:** 0.722836
**Significance:** No (α = 0.05)

| Lag | F-Statistic | P-Value | Significant |
|-----|-------------|---------|-------------|
| 1 | 0.0677 | 0.795201 |  |
| 2 | 0.1060 | 0.899508 |  |
| 3 | 0.0812 | 0.970073 |  |
| 4 | 0.5178 | 0.722836 |  |
| 5 | 0.5259 | 0.756074 |  |
| 6 | 0.5389 | 0.777180 |  |
| 7 | 0.4675 | 0.855317 |  |
| 8 | 0.4306 | 0.899275 |  |
| 9 | 0.4253 | 0.917545 |  |
| 10 | 0.4869 | 0.893255 |  |

## Quote Imbalance → SPY Returns

**Optimal lag:** 8 days
**F-statistic:** 0.9881
**P-value:** 0.451910
**Significance:** No (α = 0.05)

| Lag | F-Statistic | P-Value | Significant |
|-----|-------------|---------|-------------|
| 1 | 0.1864 | 0.666873 |  |
| 2 | 0.3139 | 0.731312 |  |
| 3 | 0.0223 | 0.995444 |  |
| 4 | 0.1840 | 0.946144 |  |
| 5 | 0.9170 | 0.473932 |  |
| 6 | 0.7558 | 0.606630 |  |
| 7 | 0.5988 | 0.755134 |  |
| 8 | 0.9881 | 0.451910 |  |
| 9 | 0.5817 | 0.808078 |  |
| 10 | 0.6051 | 0.804508 |  |

## VPIN CDF → SPY Volatility

**Optimal lag:** 5 days
**F-statistic:** 1.0620
**P-value:** 0.387029
**Significance:** No (α = 0.05)

| Lag | F-Statistic | P-Value | Significant |
|-----|-------------|---------|-------------|
| 1 | 0.3571 | 0.551504 |  |
| 2 | 0.6133 | 0.543686 |  |
| 3 | 0.9175 | 0.435632 |  |
| 4 | 0.6952 | 0.597185 |  |
| 5 | 1.0620 | 0.387029 |  |
| 6 | 0.8321 | 0.548480 |  |
| 7 | 0.8140 | 0.578276 |  |
| 8 | 0.7667 | 0.632919 |  |
| 9 | 0.5980 | 0.794770 |  |
| 10 | 1.0474 | 0.413843 |  |

## Quote Imbalance → SPY Volatility

**Optimal lag:** 6 days
**F-statistic:** 2.7816
**P-value:** 0.016214
**Significance:** Yes (α = 0.05)

| Lag | F-Statistic | P-Value | Significant |
|-----|-------------|---------|-------------|
| 1 | 3.8663 | 0.052064 |  |
| 2 | 2.3883 | 0.097215 |  |
| 3 | 1.4873 | 0.223124 |  |
| 4 | 2.6395 | 0.038896 | * |
| 5 | 2.5500 | 0.033448 | * |
| 6 | 2.7816 | 0.016214 | * |
| 7 | 2.2153 | 0.041244 | * |
| 8 | 1.9979 | 0.057521 |  |
| 9 | 2.1715 | 0.033438 | * |
| 10 | 2.1426 | 0.031586 | * |

---

## Interpretation

### VPIN CDF → Returns

No significant Granger causality detected (p=0.7228). 
VPIN CDF does not appear to predict SPY returns at daily frequency.

### Quote Imbalance → Returns

No significant Granger causality detected (p=0.4519). 
Quote Imbalance does not appear to predict SPY returns at daily frequency.

### Limitations

- Daily frequency may miss intraday causal dynamics

- VPIN computed from daily bars is an approximation of tick-level VPIN

- Granger causality ≠ true causality (predictive, not structural)

- 167 observations limits statistical power for long lag structures
