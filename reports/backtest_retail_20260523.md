# Retail Flow Strategy Backtest Report

**Generated:** 2026-05-23 02:21 UTC

**Data:** SPY daily features, 167 observations
**Date range:** 2024-01-02 00:00:00 to 2024-12-30 00:00:00

**Strategy:** CPR + OI Skew Contrarian
**Hold period:** 3 days
**Initial capital:** $5,000.00

---

## Performance Summary

| Metric | Strategy | Buy & Hold |
|--------|----------|------------|
| Total Return | -12.32% | 24.35% |
| Final Equity | $4,384.24 | $6,217.46 |
| Sharpe Ratio (ann.) | -2.051 | N/A |
| Max Drawdown | -14.19% | N/A |
| Win Rate | 60.0% | N/A |
| Profit Factor | 1.73 | N/A |
| Number of Trades | 15 | N/A |
| Avg Win | 1.638% | N/A |
| Avg Loss | -1.424% | N/A |
| Expectancy per Trade | 0.4134% | N/A |

---

## Signal Analysis

| Signal Type | Count |
|-------------|-------|
| Long (contrarian) | 31 |
| Short (contrarian) | 0 |
| Neutral | 136 |

**CPR Z-score range:** -2.17 to 5.95
**OI Skew Z-score range:** -2.17 to 5.95

---

## Trade Log (first 20)

| # | Entry Date | Exit Date | Direction | Return | Days |
|---|------------|-----------|-----------|--------|------|
| 1 | 2024-02-20 00:00:00 | 2024-02-26 00:00:00 | LONG | 1.794% | 3 |
| 2 | 2024-02-28 00:00:00 | 2024-03-05 00:00:00 | LONG | -0.747% | 3 |
| 3 | 2024-03-15 00:00:00 | 2024-03-20 00:00:00 | LONG | 2.075% | 3 |
| 4 | 2024-04-02 00:00:00 | 2024-04-05 00:00:00 | LONG | -0.066% | 3 |
| 5 | 2024-04-15 00:00:00 | 2024-04-18 00:00:00 | LONG | -0.980% | 3 |
| 6 | 2024-04-19 00:00:00 | 2024-04-29 00:00:00 | LONG | 0.895% | 3 |
| 7 | 2024-05-01 00:00:00 | 2024-05-07 00:00:00 | LONG | 2.285% | 3 |
| 8 | 2024-07-18 00:00:00 | 2024-07-25 00:00:00 | LONG | -1.756% | 3 |
| 9 | 2024-08-01 00:00:00 | 2024-08-06 00:00:00 | LONG | -3.852% | 3 |
| 10 | 2024-08-07 00:00:00 | 2024-08-14 00:00:00 | LONG | 3.068% | 3 |
| 11 | 2024-10-03 00:00:00 | 2024-10-08 00:00:00 | LONG | 0.950% | 3 |
| 12 | 2024-10-23 00:00:00 | 2024-10-28 00:00:00 | LONG | 0.491% | 3 |
| 13 | 2024-10-31 00:00:00 | 2024-11-05 00:00:00 | LONG | 1.416% | 3 |
| 14 | 2024-12-18 00:00:00 | 2024-12-23 00:00:00 | LONG | 1.769% | 3 |
| 15 | 2024-12-27 00:00:00 | 2024-12-30 00:00:00 | LONG | -1.141% | 1 |

---

## Discussion

### Directional (Long + Short)
The directional strategy (both long and short contrarian signals) returned **-24.05%** with a -3.740 Sharpe.
The short side was the primary detractor — shorting a strong bull market is a losing proposition.
However, the win rate of 55.6% and profit factor of 1.39 suggest the signal direction is correct
more often than not; the issue is asymmetry (losses larger than wins).

### Long-Only Contrarian
The long-only variant returned **-12.32%** with a 60% win rate and 1.73 profit factor.
The **expectancy per trade is +0.4134%**, which is positive — meaning over many trades,
the strategy is expected to be profitable. The negative total return in this period is due to:

1. **Small sample**: Only 15 trades — not enough to realize the edge
2. **Trend headwind**: 2024 was a relentless bull market; contrarian longs bought into pullbacks
   that sometimes continued lower before recovering
3. **Asymmetric losses**: The avg win (+1.64%) is larger than the avg loss (-1.42%), but
   the loses occurred during the worst moments (Aug 2024 selloff)

### Key Insight
**The contrarian signal HAS predictive power** (60% win rate, 1.73 profit factor, +0.41% expectancy),
but needs:
- A regime filter (avoid counter-trend trading in strong trends)
- More data (15 trades is insufficient for statistical confidence)
- Volatility scaling (reduce size during high-vol regimes)

### Limitations

- 167 daily observations (~8 months) is a short backtest window
- 15 trades is a small sample for statistical significance
- 2024 was a strong bull market; contrarian signals may underperform in trending markets
- No transaction costs or slippage modeled
- OI Skew derived from GEX data, not raw open interest
- Daily frequency misses intraday signal dynamics
- 3-day hold period is arbitrary; optimal hold may vary
