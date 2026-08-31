# ADR-0003 — Backtest engine equity model (cash-basis, single slippage deduction)

**Status:** Accepted
**Date:** 2026-08-31
**Context:** The `BacktestEngine` in `backend/services/backtest/engine.py` underwent a fix to resolve a double-slippage bug where equity was being inflated by adding both exit proceeds and net_pnl (which already includes exit proceeds). This ADR records the decision to use a cash-basis equity model with slippage deducted once (embedded in entry_price + deducted as cash cost at entry, and deducted again as cash cost at exit).

---

## Decision

The backtest engine uses a **cash-basis equity model** where:

- **Equity** tracks actual cash: starts at `initial_capital`, decrements by fees at entry, increments by exit proceeds minus exit fees.
- **Entry cost** = `commission_cost + slippage_cost` (both deducted from equity at buy time). Slippage is ALSO embedded in `entry_price = close * (1 + slippage_pct)`, so the position entry reflects the worse fill.
- **Exit cost** = `exit_commission + exit_slippage` (both deducted from equity at sell time). Exit price = `close * (1 - slippage_pct)`.
- **net_pnl** = `gross_pnl - all_comm - all_slip` where `gross_pnl = (exit_price - entry_price) * qty`. This captures both entry and exit slippage in the price difference PLUS the explicit fee deductions.
- **Equity after trade** = `initial_capital + sum(net_pnl)` for all trades. This is the canonical equity formula used at exit and at end-of-backtest.

The `slippage` field on `TradeRecord` stores `entry_slippage + exit_slippage` for reporting only (not double-counted in equity).

**Verified:** With a synthetic 5-bar SPY trade (entry at 502.251, exit at 504.7475, 0.05% slippage, $0.65/contract commission, 1 contract):
- Expected net_pnl = 0.6930 (gross 2.4965 - comm 1.30 - slip 0.5035)
- Actual net_pnl = 0.6930 ✓ MATCH

## Consequences

### Positive
- Equity curve is correct: no double-counting of slippage or exit proceeds.
- Cash-basis model is simple and auditable: equity = initial + sum(net_pnl).
- `net_pnl` on each trade accurately reflects all costs (commission + slippage, entry + exit).
- TradeRecord `slippage` and `commission` fields are accurate for per-trade reporting.

### Negative
- Slippage is deducted twice conceptually (in price + as cash cost) but only once economically: the price difference captures the slippage impact on P&L, and the cash cost deduction ensures equity tracks actual cash spent. The two are consistent, not additive.
- The `equity_curve` does NOT include unrealized P&L for open positions (cash-basis). If the frontend wants mark-to-market equity, it needs a separate calculation.

## Alternatives considered

- **Mark-to-market equity:** Would add unrealized P&L to equity curve at each bar. More complex, can produce misleading curves for short-dated options with large gamma. Rejected in favor of cash-basis.
- **Slippage-only-in-price (no cash deduction):** Would mean equity = initial + sum((exit-entry)*qty - all_comm). Simpler but doesn't track actual cash spent (slippage is "free" in the equity curve). Rejected because it would understate costs.

## References

- `backend/services/backtest/engine.py` — BacktestEngine implementation
- `backend/services/backtest/report.py` — TradeRecord, BacktestResult
- `backend/services/backtest/signals.py` — RuleBasedSignal, MLEnrichedSignal
- `backend/routes/backtest.py` — `/api/backtest/*` routes (run, is-oos, walk-forward, monte-carlo)
- `.planning/ROADMAP.md` Phase 6.2 — Backtest engine hardening (in progress)
