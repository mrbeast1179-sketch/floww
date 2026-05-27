# Hermes Owl Alpha — Agent H27 · Unblock 20 Test Files via `services/__init__.py` (~30 min)

You are Agent H27. You fix a single missing file — `backend/services/__init__.py` — and unblock ~20 test files that currently fail collection with `ModuleNotFoundError: services is not a package`. This is the highest-leverage ticket of Round 9 follow-up: one file change unlocks an entire test directory.

---

## The bug

`backend/services/` has no `__init__.py`. Python treats it as a namespace package, which works for single-file `python -m pytest tests/services/test_X.py` runs (each test file path-hacks `sys.path`), but fails for full collection because pytest's import resolver hits a conflict.

Evidence (capture this in your pre-flight):
```bash
$ cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -5
2106 tests collected, 20 errors in 1.76s

$ .venv/bin/python3 -m pytest --collect-only -q 2>&1 | grep ModuleNotFoundError | head -3
E   ModuleNotFoundError: No module named 'services.gex_history'; 'services' is not a package
E   ModuleNotFoundError: No module named 'services.greek_aggregator'; 'services' is not a package
E   ModuleNotFoundError: No module named 'services.iv_skew_analyzer'; 'services' is not a package
```

---

## Mission

Add `backend/services/__init__.py` and `backend/services/ml/__init__.py` (if also missing) so pytest can collect every test file in `tests/services/`. Confirm the test count surges. Commit with the BEFORE/AFTER counts inline in the commit message as proof.

---

## Hard constraints (same as H26 — re-read every word)

- **Canonical clone**: `/Users/nav/Documents/GitHub/floww`. **Never** `/Users/nav/GitHub/floww`.
- **Forbidden files**: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, model artifacts, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`.
- **Forbidden git ops**: no `--force`, `--no-verify`, `--amend` on others' commits, `--hard`, `clean -fd`.
- **NEVER** mark a test xfail or skip. If your fix breaks a test that was passing, your fix is wrong.
- **Origin-state gate** after every push.
- **15-min pulse** to `kanban/cards/agent_H27_status.md`.

---

## Pre-flight

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`.
- [ ] **PF2.** Confirm the file does NOT exist (don't overwrite an existing one):
  ```
  ls backend/services/__init__.py 2>&1
  ls backend/services/ml/__init__.py 2>&1
  ```
  Expected: both report `No such file or directory`.

- [ ] **PF3.** Capture the BEFORE state — number this clearly so you can paste it in the commit message:
  ```
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -2
  ```
  Expected output similar to: `2106 tests collected, 20 errors in 1.76s`. Save the exact numbers.

- [ ] **PF4.** Capture the LIST of error files:
  ```
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | grep ModuleNotFoundError | sort -u
  ```
  Save this list — you'll paste it (truncated to 5) in your commit message to prove the fix unblocks them.

- [ ] **PF5.** `git status --short` should show only `?? backend/tests/services/ml/test_ml_integration.py` (and your new files once you create them).

- [ ] **PF6.** Write first pulse line.

---

## Task 1: Create `backend/services/__init__.py` (5 min)

- [ ] **T1.1** Use the Write tool (or `cat > file <<EOF`) to create the file with this content (an empty `__init__` is fine, but a small docstring helps documentation):

```python
"""backend/services — service-layer modules.

This package contains all backend service classes that wrap external
dependencies (MongoDB, DuckDB, Alpha Vantage, Schwab, etc.) and provide
domain operations (paper trading, ML inference, GEX history, etc.).

This file exists primarily to make pytest's full-suite collection work.
Without it, pytest treats `services` as a namespace package and bails
with `ModuleNotFoundError: services is not a package`.
"""
```

- [ ] **T1.2** Verify creation:
  ```
  ls -la backend/services/__init__.py
  ```
  Expected: 1 file, non-zero size.

- [ ] **T1.3** Pulse.

---

## Task 2: Create `backend/services/ml/__init__.py` IF needed (5 min)

- [ ] **T2.1** Re-check if `backend/services/ml/__init__.py` already existed (it might have, since `from services.ml import DegenerateModelError` works elsewhere):
  ```
  ls backend/services/ml/__init__.py 2>&1
  ```

- [ ] **T2.2** If it exists, SKIP this task entirely. Note in your pulse: "T2 skipped — ml/__init__.py already present".

- [ ] **T2.3** If it does NOT exist, create it with:
  ```python
  """backend/services/ml — machine-learning service modules.
  
  Exports DegenerateModelError and re-exports the inference engine.
  """
  
  # Re-export the sentinel used by callers
  try:
      from .errors import DegenerateModelError
  except ImportError:
      class DegenerateModelError(RuntimeError):
          """Raised when an ML model has degenerated (e.g., all predictions identical)."""
          pass
  ```

- [ ] **T2.4** Pulse.

---

## Task 3: Re-run collection — confirm the surge (5 min)

- [ ] **T3.1** Run collect:
  ```
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
  ```
  Expected: previous error count drops dramatically. Likely `2300+ tests collected, 0 errors` or similar.

- [ ] **T3.2** If errors REMAIN, capture them — they may be a different root cause:
  ```
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | grep ModuleNotFoundError | sort -u
  ```
  If the remaining errors say `services.X is not a package` for some other subpackage, repeat Task 2 for that subpackage. If the errors are completely different (e.g., missing third-party deps), STOP and HALT — that's out of scope.

- [ ] **T3.3** Run actual tests (not just collect) to confirm none of the newly-collected tests are broken:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/ -q --tb=no 2>&1 | tail -5
  ```
  Expected: large pass count (likely 200+ in `tests/services/`), zero or very few failures. **If failures number > 5, STOP and inspect** — newly-unblocked tests may have been broken for a long time and need triage rather than skipping.

  If you find ≤5 newly-unblocked tests that fail for reasons unrelated to your `__init__.py` creation (e.g., they reference a function that was renamed), document them in your commit message as "pre-existing failures now visible" and proceed. **Do NOT mark them xfail/skip.**

- [ ] **T3.4** Pulse.

---

## Task 4: Write a smoke test to lock the fix (5 min)

This test prevents anyone from accidentally deleting `__init__.py` in the future.

- [ ] **T4.1** Create `backend/tests/test_services_is_package.py`:

```python
"""Regression: backend/services and subpackages must be importable as packages.

If this test ever fails, someone deleted __init__.py — which breaks full
pytest collection and silently hides 20+ test files from CI.
"""
import importlib
import pkgutil
from pathlib import Path

import pytest


def test_services_is_a_package():
    """services must be importable as a regular package, not namespace."""
    import services
    # Namespace packages have no __file__; regular packages do
    assert hasattr(services, "__file__"), \
        "services is a namespace package — __init__.py missing"


def test_services_ml_is_a_package():
    import services.ml
    assert hasattr(services.ml, "__file__"), \
        "services.ml is a namespace package — __init__.py missing"


def test_services_init_file_exists_on_disk():
    """Belt-and-suspenders: the file must physically exist."""
    here = Path(__file__).resolve().parent  # backend/tests/
    init_path = here.parent / "services" / "__init__.py"
    assert init_path.is_file(), f"{init_path} missing"
```

- [ ] **T4.2** Run it:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/test_services_is_package.py -v 2>&1 | tail -8
  ```
  Expected: 3 PASSED.

- [ ] **T4.3** Pulse.

---

## Task 5: Commit + push + close-out (10 min)

- [ ] **T5.1** Commit, with BEFORE/AFTER numbers in the message (paste your real numbers from PF3 + T3.1):

```bash
git add backend/services/__init__.py backend/tests/test_services_is_package.py
# Add services/ml/__init__.py too IF you created it in T2.3
git status --short  # double-check no unrelated files staged

git commit -m "$(cat <<'EOF'
fix(test-infra): add backend/services/__init__.py — unblocks 20 test files

Round-9 follow-up. `backend/services/` had no __init__.py, so pytest
full-collect failed with `ModuleNotFoundError: services is not a package`
for ~20 test files (single-file pytest runs worked via sys.path hacks).

BEFORE this fix:
  $ cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -1
  2106 tests collected, 20 errors in 1.76s

AFTER:
  $ cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -1
  <PASTE YOUR ACTUAL T3.1 LAST LINE HERE>

Unblocked test files (top 5):
<PASTE 5 LINES FROM YOUR PF4 OUTPUT HERE>

Regression test added at backend/tests/test_services_is_package.py so
this can't silently regress.

Verification:
  $ ls backend/services/__init__.py
  backend/services/__init__.py
  $ cd backend && .venv/bin/python3 -m pytest tests/test_services_is_package.py -v
  3 passed
EOF
)"
git push origin main
git fetch origin && git log origin/main --oneline -1 | grep 'test-infra'
```

**If grep fails, STOP.**

- [ ] **T5.2** Final pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H27 :: DONE :: collection went from 20 errors to <N> errors :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H27_status.md
  ```

---

## Halt conditions

1. Pre-flight finds `__init__.py` already exists → STOP, your premise is wrong (the audit may have been stale).
2. Adding `__init__.py` reveals tests that fail (not error-out at collect) in numbers > 5 → STOP and document.
3. Origin gate fails.
4. The remaining collection errors after your fix point at a completely different root cause → STOP and report rather than chasing scope creep.
5. 15 min pulse gap.

---

## What success looks like

- 1 commit on origin (or 2 if you also added `services/ml/__init__.py`)
- pytest collection errors drop from 20 to 0 (or to a small handful of unrelated, documented issues)
- ~150-300 newly-collectable tests visible in the count
- Regression test exists to prevent future deletion
