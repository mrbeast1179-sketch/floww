# Agent A10 — Type Hints + Mypy Gate on Utility Modules (target: 2.5 hours)

**You are Agent A10.** Read `_PREAMBLE.md`. Scope: add complete type hints to 4 utility modules (chosen to avoid file-ownership conflicts with A1, A4, A7, A8), add `backend/mypy.ini` config, run mypy on the annotated files and fix any bugs found, document the convention for Round 10.

Your file ownership: `backend/services/option_chain.py`, `backend/services/bs_greeks.py`, `backend/services/spy_helpers.py`, `backend/error_tracking.py`, `backend/mypy.ini` (NEW), new type-check tests, `docs/ROUND9_A10_TYPE_HINTS.md`.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + verify scope files exist | 10 |
| 2 | Install + smoke mypy in venv | 10 |
| 3 | Annotate `option_chain.py` | 30 |
| 4 | Annotate `bs_greeks.py` | 25 |
| 5 | Annotate `spy_helpers.py` | 20 |
| 6 | Annotate `error_tracking.py` | 25 |
| 7 | Create `backend/mypy.ini` strict for these files only | 15 |
| 8 | Run mypy + fix bugs found | 25 |
| 9 | Document convention for Round 10 | 15 |
| 10 | Close-out | 10 |

Total ~185 min.

---

## Why these files

Each is:
- Small enough to annotate fully in 25 min
- A utility (no FastAPI routes, no DB layer) — easy to type
- Touched rarely (low merge-conflict risk)
- Not in another agent's scope this session

---

## Task 1 — Pre-flight (10 min)

- [ ] **1.1** `pwd` canonical.
- [ ] **1.2** Verify scope files exist:
  ```bash
  ls backend/services/option_chain.py backend/services/bs_greeks.py backend/services/spy_helpers.py backend/error_tracking.py 2>&1
  ```
  If any missing, **substitute** with another utility module: `services/auth_utils.py`, `services/data_quality.py`, etc. Note the substitution in your close-out.
- [ ] **1.3** First pulse.

---

## Task 2 — Install + smoke mypy (10 min)

- [ ] **2.1** Check if installed: `backend/.venv/bin/mypy --version 2>&1`.
- [ ] **2.2** If missing: `backend/.venv/bin/pip install mypy`.
- [ ] **2.3** Smoke: `cd backend && .venv/bin/mypy --version`.
- [ ] **2.4** Pulse.

---

## Task 3 — Annotate `option_chain.py` (30 min)

- [ ] **3.1** Open the file with `Read`. Note all function signatures.
- [ ] **3.2** For each function, add hints. Common patterns in this codebase:
  - `ticker: str`
  - `spot: float`
  - `contracts: List[Dict[str, Any]]`
  - `expiry: Optional[str]`
  - Return: `Dict[str, Any]` for chain dicts, `List[Dict[str, Any]]` for lists, `float` for scalars
- [ ] **3.3** Add typing imports at top if missing:
  ```python
  from typing import Any, Dict, List, Optional, Tuple
  ```
- [ ] **3.4** Apply hints with `Edit`. **Do not change runtime behavior** — only annotations + the typing import.
- [ ] **3.5** Smoke import: `cd backend && .venv/bin/python3 -c "import services.option_chain; print('OK')"`.
- [ ] **3.6** Run relevant tests:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/ -k option_chain -v 2>&1 | tail -10
  ```
- [ ] **3.7** Pulse.

---

## Task 4 — Annotate `bs_greeks.py` (25 min)

This is Black-Scholes math — every input is `float`, every output is `float`.

- [ ] **4.1** Open + annotate. Example pattern:
  ```python
  def bs_vanna(S: float, K: float, T: float, sigma: float, r: float = 0.0, q: float = 0.0) -> float:
      ...
  
  def bs_charm(S: float, K: float, T: float, sigma: float, r: float = 0.0, q: float = 0.0, kind: str = "call") -> float:
      ...
  ```
- [ ] **4.2** For helper math functions: same pattern.
- [ ] **4.3** Smoke + tests:
  ```bash
  cd backend && .venv/bin/python3 -c "from services.bs_greeks import bs_vanna, bs_charm; print(bs_vanna(450, 450, 7/365, 0.18))"
  cd backend && .venv/bin/python3 -m pytest tests/services/ -k bs_greeks -v 2>&1 | tail -10
  ```
- [ ] **4.4** Pulse.

---

## Task 5 — Annotate `spy_helpers.py` (20 min)

- [ ] **5.1** Open + annotate. Common helpers: date math, format conversions, SPX/SPY ticker normalization.
- [ ] **5.2** Smoke + tests.
- [ ] **5.3** Pulse.

---

## Task 6 — Annotate `error_tracking.py` (25 min)

This is the error-counting system. Watch for:
- Async functions (annotate as `async def fn(...) -> ...:`)
- The module-level `_error_counts: Dict[str, int]` and `_error_log: List[Dict]` (these were L1 leak audit Low findings — your hints make their type-shape explicit for future fixers)
- Callable params (use `Callable[[...], ...]`)

- [ ] **6.1** Annotate.
- [ ] **6.2** Smoke + tests.
- [ ] **6.3** Pulse.

---

## Task 7 — `backend/mypy.ini` (15 min)

- [ ] **7.1** Create or extend `backend/mypy.ini`:
  ```ini
  [mypy]
  python_version = 3.13
  warn_return_any = True
  warn_unused_configs = True
  no_implicit_optional = True
  check_untyped_defs = False  # too noisy for now; per-file opt-in below
  
  # Strict checking on the modules A10 fully annotated this round
  [mypy-services.option_chain]
  check_untyped_defs = True
  disallow_untyped_defs = True
  
  [mypy-services.bs_greeks]
  check_untyped_defs = True
  disallow_untyped_defs = True
  
  [mypy-services.spy_helpers]
  check_untyped_defs = True
  disallow_untyped_defs = True
  
  [mypy-error_tracking]
  check_untyped_defs = True
  disallow_untyped_defs = True
  
  # Ignore-only for upstream packages that lack stubs
  [mypy-motor.*]
  ignore_missing_imports = True
  
  [mypy-duckdb.*]
  ignore_missing_imports = True
  
  [mypy-databento.*]
  ignore_missing_imports = True
  
  [mypy-yfinance]
  ignore_missing_imports = True
  ```
- [ ] **7.2** Verify file is valid:
  ```bash
  python3 -c "import configparser; c = configparser.ConfigParser(); c.read('backend/mypy.ini'); print(sorted(c.sections()))"
  ```
- [ ] **7.3** Pulse.

---

## Task 8 — Run mypy + fix bugs found (25 min)

- [ ] **8.1** Run mypy on the 4 annotated modules:
  ```bash
  cd backend && .venv/bin/mypy services/option_chain.py services/bs_greeks.py services/spy_helpers.py error_tracking.py 2>&1 | tail -30
  ```
- [ ] **8.2** For each error:
  - If it's a real bug (e.g., function returns `None` in one path but type says `float`), fix the BUG (add the missing return statement, or change the type to `Optional[float]`).
  - If it's a type-system limitation (e.g., complex inheritance), add `# type: ignore[<error-code>]` with a comment explaining why. Use sparingly.
- [ ] **8.3** Re-run mypy until 0 errors on the 4 files.
- [ ] **8.4** Run pytest on the 4 modules' tests to confirm no behavior change:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/ -k "option_chain or bs_greeks or spy_helpers or error_tracking" -v 2>&1 | tail -15
  ```
- [ ] **8.5** Commit annotated files + mypy.ini together:
  ```bash
  git add backend/services/option_chain.py backend/services/bs_greeks.py backend/services/spy_helpers.py backend/error_tracking.py backend/mypy.ini
  git commit -m "$(cat <<'EOF'
  feat(round-9-a10): type hints on 4 utility modules + strict mypy gate
  
  Annotates option_chain.py, bs_greeks.py, spy_helpers.py, error_tracking.py
  with complete signatures. Adds backend/mypy.ini with strict per-module
  opt-in (disallow_untyped_defs) for these 4, lax for everything else
  (Round 10 will expand the strict set).
  
  Bugs fixed during annotation:
  - <list real bugs you found, e.g., "option_chain.get_atm returned None on empty chain but signature said float — added Optional[float]">
  
  Verification:
  \$ cd backend && .venv/bin/mypy services/option_chain.py services/bs_greeks.py services/spy_helpers.py error_tracking.py
  Success: no issues found in 4 source files
  
  \$ cd backend && .venv/bin/python3 -m pytest tests/services/ -k "option_chain or bs_greeks or spy_helpers" 2>&1 | tail -1
  <PASTE ACTUAL PASS COUNT>
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'a10.*type hints'
  ```
- [ ] **8.6** Pulse.

---

## Task 9 — Document convention for Round 10 (15 min)

- [ ] **9.1** Write `docs/ROUND9_A10_TYPE_HINTS.md`:
  ```markdown
  # Type-Hints Convention (Round 9 → Round 10)
  
  ## Status
  
  - Round 9 A10: 4 utility modules fully annotated, mypy strict on those.
  - Round 10: expand strict set by 4 modules per session.
  - Current strict set: option_chain, bs_greeks, spy_helpers, error_tracking.
  
  ## Conventions
  
  ### Imports
  
  Always at top of file, in this order:
  ```python
  from __future__ import annotations  # for forward refs without quotes
  from typing import Any, Dict, List, Optional, Tuple, Callable
  ```
  
  Prefer the lowercase generics if Python ≥3.9: `list[str]`, `dict[str, Any]`, `tuple[int, ...]`. The repo targets Python 3.13.
  
  ### Function signatures
  
  - Every public function: full param + return hints
  - Private helpers (underscore-prefixed): hint if non-trivial
  - Async functions: hint as `async def fn(...) -> ResultType:` (not `Awaitable[ResultType]`)
  - Default None: `Optional[T] = None`
  
  ### Common types in this codebase
  
  - `ticker: str` (always uppercase 3-4 char symbol)
  - `spot: float`
  - `chain_row: Dict[str, Any]` (until we make a TypedDict — R11 candidate)
  - `contracts: List[Dict[str, Any]]`
  - `expiry: Optional[str]` (YYYY-MM-DD)
  - `dte: int` (days to expiry)
  - `result_dict: Dict[str, Any]`
  
  ### When to use `# type: ignore`
  
  Sparingly. With a comment explaining why. Example:
  ```python
  result: float = some_third_party_call()  # type: ignore[no-any-return]  # lib lacks stubs
  ```
  
  ## Module strict-list (current)
  
  | Module | Mypy strict? | Annotated by |
  |--------|--------------|--------------|
  | services.option_chain | yes | A10 (R9) |
  | services.bs_greeks | yes | A10 (R9) |
  | services.spy_helpers | yes | A10 (R9) |
  | error_tracking | yes | A10 (R9) |
  
  ## Round 10 candidates (next 4)
  
  - services.greek_aggregator (~150 lines, pure math)
  - services.iv_skew_analyzer (~200 lines, mostly numpy)
  - services.oi_change_detector (~180 lines, dict comparisons)
  - services.rate_limit_tracker (~120 lines, time math)
  ```
- [ ] **9.2** Commit + push + gate.
- [ ] **9.3** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** `docs/ROUND9_A10_CLOSEOUT.md`.
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. Mypy install fails — STOP, don't proceed with manual type-checking.
2. A scope file doesn't exist — substitute as documented in T1.2; STOP if no good substitute.
3. Adding a type hint causes a test failure — that means the existing code had a bug. Fix the BUG (not the annotation).
4. A `# type: ignore` is required on >5 lines per file — the module has structural problems; document for R10, don't shotgun ignores.
5. Origin gate fails.
6. 15-min pulse gap.
