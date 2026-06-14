# Round 11 — Agent 10 (causal) — FINDINGS

## Services Covered

### 1. services/causal/ate_estimator.py
- **New test file**: `tests/services/causal/test_ate_estimator_edge.py`
- **Existing test**: `tests/services/causal/test_ate.py` (already covered main paths)
- **New tests**: 16 tests covering:
  - PropensityScoreEstimator: single feature, large sample convergence, predict shape, different-sized prediction
  - IPTW: all-treated/all-control returns 0.0, perfect propensity recovery, propensity clipping
  - Doubly-robust: single treated/control observation fallback, known effect recovery
  - Bootstrap CI: reproducibility, lower <= upper, point within CI, CI width scales with noise
- **Bugs found**: None

### 2. services/backtest/report.py
- **New test file**: `tests/services/backtest/test_report.py`
- **Existing test**: None (this was the primary gap)
- **New tests**: 27 tests covering:
  - TradeRecord defaults and fields
  - BacktestResult with zero trades (all metrics zero)
  - BacktestResult with 5 known trades (3 wins, 2 losses): total_pnl, avg, hit_rate, avg_win, avg_loss, win_loss_ratio, profit_factor, commission, slippage, final_equity, net_return_pct — all verified against hand-computed values
  - Sharpe ratio: known returns, zero std, no bar returns
  - Max drawdown: known curve, empty curve
  - Edge cases: all wins (inf wl_ratio, inf pf), all losses (zero wl, zero pf), single trade, zero initial capital
  - summary_text: format verification, auto-compute
- **Bugs found**: None

### 3. services/backtest/retail_flow_signal.py
- **New test file**: `tests/services/backtest/test_retail_flow_signal_edge.py`
- **Existing test**: `tests/services/test_retail_flow_signal.py` (already covered main signal/regime logic)
- **New tests**: 35 tests covering:
  - _safe_float: None, NaN, inf (passes through — documented behavior), -inf (passes through), valid float/int/string, invalid string, list
  - _sma: short list, exact period, longer list, empty, single element
  - RegimeFilter: price == SMA boundary, custom period, empty prices, two-price behavior
  - RetailFlowSignal: None snapshot values, missing keys, NaN values, negative CPR, exit logic correctness
  - Position: is_open, close long/short, close already closed, update_unrealized long/short/not_open
- **Bugs found**: None (but noted _safe_float does not handle inf/-inf — this is existing behavior, not a new bug)

## Test Count
- Total new tests: 78
- All passing: 78
- Ruff: clean
- No regressions in causal/ backtest directories (103 passed)
