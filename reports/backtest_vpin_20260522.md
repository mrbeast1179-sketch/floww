# VPIN_HFT Strategy Backtest Report

**Generated:** 2026-05-22 02:12 UTC
**Period:** 90 trading days (synthetic data)
**Initial Capital:** $100,000.00

## Performance Metrics

| Metric | Value |
|--------|-------|
| Sharpe Ratio | 2.8441 |
| Max Drawdown | -0.13% |
| Win Rate | 0.00% |
| Profit Factor | inf |
| Total Trades | 0 |
| Strategy Return | 9.63% |
| Buy & Hold Return | 4.88% |
| Final Equity | $109,634.77 |

## Assessment

**PASS:** Sharpe ratio 2.8441 > 1.0 threshold.

## Notes

- This backtest uses **synthetic data** generated via GBM.
- Real performance depends on actual VPIN CDF computation from tick data.
- Correlation z-scores use simulated multi-asset/multi-exchange data.
- Death count mechanism limits holding periods to 10 bars.
- Commission: $0.005/share, Position size: 5% of capital per trade.