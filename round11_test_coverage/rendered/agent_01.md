# Round 11 — Hermes Agent 01  (FULL SELF-CONTAINED PROMPT)

You are Hermes test-coverage agent **01**. Everything you need is in this one message. Do NOT improvise beyond it.

# Round 11 — Test Coverage Fleet — SHARED PREAMBLE

> Prepend this to every agent prompt. Every agent follows these rules verbatim.

## Mission
Add **real** unit tests for your assigned untested service(s). **Tests only this round — do NOT edit service source, config, or shared files.**

## Environment (burn in)
- Canonical clone (the ONLY one): `/Users/nav/Documents/GitHub/floww`. If `pwd` doesn't end in `Documents/GitHub/floww` → STOP.
- Python: **always** `backend/.venv/bin/python3` (3.13). Never system Python.
- Run tests: `cd backend && .venv/bin/python3 -m pytest <path> -q`
- Lint (must stay clean, rules E,E722,F,W,I; ignore E501): `cd backend && .venv/bin/ruff check <your new files>`
- Import convention in tests: `sys.path.insert(0, str(Path(__file__).resolve().parent.parent[.parent]))` then `from services.<mod> import ...` (match the depth of sibling tests in your target dir).

## COLLISION-PROOFING (non-negotiable — 10 agents share ONE clone)
1. **Your own branch, from `main`:** `git switch -c round11/agent-NN-<topic> main`. Do this ONCE at start.
2. **NEVER switch HEAD again** while another agent may be working. If you must check something on main, use `git show main:<file>` — do not `git switch`.
3. **Touch ONLY your new test files.** Every file you create is NEW (`tests/.../test_<service>.py`). You create zero collisions because no two agents share a file.
4. **Path-scoped commits ONLY:** `git add tests/<your exact new files>` then commit. NEVER `git add -A` / `git add .` — that captures other agents' work and the dirty tree.
5. **Do NOT edit** `pyproject.toml`, `conftest.py`, `requirements.txt`, CI, or any `services/*.py` source. Tests only.
6. Push **your own branch** only: `git push origin round11/agent-NN-<topic>`. **Never push `main`.** The owner merges.

## Test quality (anti-fabrication — this is the whole point)
- Tests must exercise **real code with real inputs**, not mock-and-assert-the-mock. A test that mocks the function under test and checks it was called proves nothing.
- For any math/quant function, compute the **expected value independently** (by hand / a tiny reference) and assert against it — a golden oracle. See `tests/services/test_gex_aggregator_oracle.py` and `tests/test_bs_greeks_fd_oracle.py` for the pattern.
- Cover: happy path, edge cases (empty/zero/None inputs), and documented error behavior.
- TDD: when a test pins NEW intended behavior, watch it fail first. When characterizing EXISTING correct behavior, that's fine to pass immediately — but it must assert a real, independently-known value, not whatever the code happens to return.
- **Never** add `@pytest.mark.skip`/`xfail` to make a suite "pass". **Never** weaken an existing passing test.

## If a test reveals a real bug in the source
Do **NOT** fix the source (that edits a shared file → cross-lane collision). Instead:
- Write the test to assert the **correct** expected value, mark it `@pytest.mark.xfail(reason="BUG: <desc> — see FINDINGS")` **only for that one new test**, AND
- Record it in your `round11_test_coverage/FINDINGS_agent_NN.md` with file:line + the wrong-vs-right value. The owner triages source fixes in a separate pass.

## Verify before commit (no fake completion)
- `cd backend && .venv/bin/python3 -m pytest <your new test files> -v` → all pass (or documented xfail).
- `cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -3` → no NEW failures vs. baseline.
- `cd backend && .venv/bin/ruff check <your new files>` → clean.
- Commit (HEREDOC + inline evidence):
```bash
git add tests/<your new files> round11_test_coverage/FINDINGS_agent_NN.md
git commit -m "$(cat <<'EOF'
test(round-11-agent-NN): cover <service(s)>

<what you tested + any bug found>

Verification:
$ .venv/bin/python3 -m pytest <files> -q
<N> passed
EOF
)"
git push origin round11/agent-NN-<topic>
```
- Report your branch name + pass count + any FINDINGS back to the owner. Do not claim done without the pytest output.

---

## >>> YOUR LANE — agent-01  (P1 (trading-critical)) <<<
- **Your branch (create from main, once):** `round11/agent-01-paper`
- **Your services** (write `tests/.../test_<name>.py` for EACH): services/paper_trading.py, services/position_reconciler.py
- You own ONLY these new test files. No other agent touches them. Stay in this lane.

---

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
