# FINDINGS — Agent 01, Round 11

## Services Covered
- `services/paper_trading.py` — PaperTradingEngine (12 new tests)
- `services/position_reconciler.py` — stub module (5 new tests)

## Test Count
- 17 new tests total, all passing

## Bugs Found

### 1. `execution_engine.py:459` — ZeroDivisionError when quantity=0
- **File**: `services/execution_engine.py`, line 459
- **Issue**: `cost_bps` calculation divides by `arrival_price * order.quantity`, but the guard only checks `arrival_price > 0`, not `quantity > 0`.
- **Impact**: `submit_order()` with `quantity=0` and a `market` argument crashes.
- **Workaround**: Pass `market=None` for zero-quantity orders.

### 2. `test_paper_trading.py` pre-existing test failure
- **Test**: `TestSubmitOrder::test_submit_rejected_insufficient_cash`
- **Issue**: Position limit check runs before cash check. With low capital, position limit rejects first.
- **Not a regression** — pre-existing issue.
