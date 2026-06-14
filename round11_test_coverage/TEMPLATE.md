# Round 11 — Per-Agent Task (append after PREAMBLE + your lane row)

You are a Round 11 test-coverage agent. Follow the PREAMBLE exactly. Your lane (above) lists your service(s) and branch. Work ONLY in your lane.

## Steps
1. `cd /Users/nav/Documents/GitHub/floww` ; confirm `pwd`. `git fetch origin && git switch -c <your-branch> main`.
2. For EACH service in your lane:
   a. Read the source. Identify the **public API** (top-level functions / class methods not prefixed `_`).
   b. Read 1–2 nearby existing tests to copy the import + fixture conventions exactly.
   c. Create `tests/.../test_<service>.py`. Write tests covering: happy path with realistic inputs, each documented edge case (empty/None/zero/negative), and documented error/guard behavior.
   d. For any numeric/quant output, assert an **independently-computed** expected value (golden), not a copy of the code's output.
   e. Run them: `cd backend && .venv/bin/python3 -m pytest <file> -v`. Fix YOUR tests until green (or xfail a real bug per PREAMBLE).
3. Full-suite no-regression check + ruff on your files (see PREAMBLE).
4. Write `round11_test_coverage/FINDINGS_agent_NN.md`: services covered, test count, any bugs (file:line, wrong vs right).
5. Commit path-scoped + push your branch (see PREAMBLE). Report branch + pass count + FINDINGS.

## Worked example — agent-01, `services/paper_trading.py`
```python
# tests/services/test_paper_trading.py
from __future__ import annotations
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # -> backend/
from services.paper_trading import PaperTradingEngine  # adjust to the REAL public symbol you find

class TestPaperTradingExecute:
    def setup_method(self):
        self.engine = PaperTradingEngine(starting_cash=100_000.0)  # adjust to real ctor

    def test_buy_reduces_cash_by_premium_times_multiplier(self):
        # 1 contract @ $4.50, x100 multiplier => $450 debited
        self.engine.execute(symbol="SPX", option_type="call", strike=6700,
                            qty=1, entry_price=4.50, is_long=True)
        assert self.engine.cash == pytest.approx(100_000.0 - 450.0)

    def test_execute_with_zero_qty_is_rejected_or_noop(self):
        before = self.engine.cash
        with pytest.raises((ValueError, AssertionError)):
            self.engine.execute(symbol="SPX", option_type="call", strike=6700,
                                qty=0, entry_price=4.50, is_long=True)
        assert self.engine.cash == before
```
This is illustrative — read the ACTUAL signatures in `paper_trading.py` and adjust names/args. The point: real engine, real arithmetic, an independently-derived expected number ($450), and an edge case. No mocking the engine itself.

## Guardrails recap
Tests only. Your branch only. Path-scoped commits. No source/config edits. No skip/xfail except a documented real bug. Verify with real pytest output before claiming done.
