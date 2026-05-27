# Agent A2 — Test Infrastructure Overhaul (target: 2.5 hours)

**You are Agent A2.** Read `_PREAMBLE.md` first. Scope: create `services/__init__.py` to unblock ~20 test files, rewrite `test_ml_integration.py` against real `MODEL_REGISTRY`, add `pytest.ini` for consistent test runs, audit for similar package-init gaps elsewhere.

Your file ownership: `backend/services/__init__.py` (NEW), `backend/services/ml/__init__.py` (NEW if missing), `backend/tests/services/ml/test_ml_integration.py` (REWRITE), `backend/tests/test_services_is_package.py` (NEW), `backend/pytest.ini` (NEW).

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + capture BEFORE state | 10 |
| 2 | Create `services/__init__.py` | 10 |
| 3 | Create `services/ml/__init__.py` if missing | 10 |
| 4 | Verify collection surges, write regression test | 15 |
| 5 | Inspect real `MODEL_REGISTRY` + on-disk models | 15 |
| 6 | Rewrite `test_ml_integration.py` against truth | 30 |
| 7 | Add `pytest.ini` for consistent config | 15 |
| 8 | Audit for other missing `__init__.py` (read-only) | 20 |
| 9 | Run full pytest sweep + capture AFTER deltas | 10 |
| 10 | Close-out doc | 10 |

Total ~145 min.

---

## Task 1 — Pre-flight (10 min)

- [ ] **1.1** `pwd` → `…/Documents/GitHub/floww`.
- [ ] **1.2** Confirm files missing (don't overwrite existing):
  ```bash
  ls backend/services/__init__.py 2>&1
  ls backend/services/ml/__init__.py 2>&1
  ls backend/pytest.ini 2>&1
  ```
  All should report `No such file or directory`. (If `services/ml/__init__.py` EXISTS, mark Task 3 as no-op.)
- [ ] **1.3** Capture BEFORE pytest collect (this number drives your commit messages):
  ```bash
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
  ```
  Save the exact `N tests collected, M errors` line.
- [ ] **1.4** Capture LIST of error files (truncate to 10 for commit message):
  ```bash
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | grep ModuleNotFoundError | sort -u | head -10
  ```
- [ ] **1.5** Confirm working tree state:
  ```bash
  git status --short
  ```
  Should show `?? backend/tests/services/ml/test_ml_integration.py` and nothing else.
- [ ] **1.6** First pulse.

---

## Task 2 — Create `backend/services/__init__.py` (10 min)

- [ ] **2.1** Write with the Write tool:
  ```python
  """backend/services — service-layer modules.
  
  Contains async-aware classes wrapping external dependencies
  (MongoDB, DuckDB, Alpha Vantage, Schwab, etc.) and domain
  operations (paper trading, ML inference, GEX history).
  
  This file exists primarily to make pytest's full-suite collection
  succeed. Without it, pytest treats `services` as a namespace
  package and bails with `ModuleNotFoundError: services is not a
  package` on ~20 test files (each works individually because they
  path-hack sys.path).
  """
  ```
- [ ] **2.2** `ls -la backend/services/__init__.py` → file present, non-zero size.
- [ ] **2.3** Pulse.

---

## Task 3 — Create `backend/services/ml/__init__.py` if missing (10 min)

- [ ] **3.1** If pre-flight 1.2 showed it EXISTS, skip this task — note in pulse `T3 skipped — already present`.
- [ ] **3.2** If MISSING, write:
  ```python
  """backend/services/ml — machine-learning service modules.
  
  Exports the DegenerateModelError sentinel and lazily re-exports
  the inference engine.
  """
  
  try:
      from .errors import DegenerateModelError
  except ImportError:
      class DegenerateModelError(RuntimeError):
          """Raised when an ML model has degenerated (e.g., all preds identical)."""
          pass
  ```
- [ ] **3.3** Verify: `cd backend && .venv/bin/python3 -c "from services.ml import DegenerateModelError; print('OK')"` → `OK`.

---

## Task 4 — Confirm collection surge + regression test (15 min)

- [ ] **4.1** Re-run collect:
  ```bash
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
  ```
  Expected: error count drops from 20 to 0 (or ≤2 unrelated).
- [ ] **4.2** Run a sample of newly-unblocked tests:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/test_gex_history.py tests/services/test_greek_aggregator.py -v 2>&1 | tail -10
  ```
  Expected: tests pass (or fail with REAL bugs you didn't introduce).
- [ ] **4.3** Write regression test `backend/tests/test_services_is_package.py`:
  ```python
  """Regression: backend/services must be importable as a regular package.
  
  If this fails, someone deleted __init__.py — which breaks full pytest
  collection and silently hides 20+ test files from CI.
  """
  from pathlib import Path
  
  
  def test_services_is_a_package():
      import services
      assert hasattr(services, "__file__"), \
          "services is a namespace package — __init__.py missing"
  
  
  def test_services_ml_is_a_package():
      import services.ml
      assert hasattr(services.ml, "__file__"), \
          "services.ml is a namespace package — __init__.py missing"
  
  
  def test_services_init_file_on_disk():
      here = Path(__file__).resolve().parent  # backend/tests/
      init_path = here.parent / "services" / "__init__.py"
      assert init_path.is_file(), f"{init_path} missing"
  ```
- [ ] **4.4** Run: `cd backend && .venv/bin/python3 -m pytest tests/test_services_is_package.py -v` → 3 PASSED.
- [ ] **4.5** Commit Task 2-4 together:
  ```bash
  git add backend/services/__init__.py backend/tests/test_services_is_package.py
  # Add backend/services/ml/__init__.py too if you created it
  git commit -m "$(cat <<'EOF'
  fix(test-infra): add backend/services/__init__.py — unblocks ~20 test files
  
  Round-9 follow-up. `backend/services/` had no __init__.py, so pytest
  full-collect failed with `ModuleNotFoundError: services is not a package`
  for ~20 test files. Single-file pytest runs worked via sys.path hacks.
  
  BEFORE:
  \$ cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -1
  <YOUR T1.3 LINE>
  
  AFTER:
  \$ cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -1
  <YOUR T4.1 LINE>
  
  Unblocked test files (sample):
  <YOUR T1.4 OUTPUT — top 5 lines>
  
  Regression test at backend/tests/test_services_is_package.py.
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'test-infra'
  ```
- [ ] **4.6** Pulse.

---

## Task 5 — Read inference.py truths (15 min)

`backend/services/ml/inference.py` is READ-ONLY for you (forbidden to modify). Read it to learn the real contract your tests need to match.

- [ ] **5.1** Grep for the registry + classes:
  ```bash
  grep -nE 'MODEL_REGISTRY|class .*Engine|^CLASS_LABELS|^UP|^DOWN|^HOLD' backend/services/ml/inference.py | head -20
  ```
- [ ] **5.2** Use `Read` to inspect ~50 lines around `MODEL_REGISTRY` definition. Capture the keys + values.
- [ ] **5.3** List real models on disk:
  ```bash
  ls backend/models/ | sort
  ```
  Note pattern: `<TICKER>_gbm_production.joblib`, `<TICKER>_gbm_production_manifest.json`, `<TICKER>_gbm_production_scaler.joblib`, plus older `<TICKER>_rf_<ts>.joblib`.
- [ ] **5.4** Verify MODEL_REGISTRY values match disk:
  ```bash
  cd backend && .venv/bin/python3 -c "
  from services.ml.inference import MODEL_REGISTRY
  from pathlib import Path
  for ticker, path in MODEL_REGISTRY.items():
      p = Path(path)
      if not p.is_absolute():
          p = Path('models') / p.name
      print(f'{ticker}: {p} → exists={p.exists()}')
  "
  ```
  Document mismatches. If any model is MISSING from disk, that's a separate bug — note in your closeout, don't paper over.
- [ ] **5.5** Pulse.

---

## Task 6 — Rewrite test_ml_integration.py against truth (30 min)

- [ ] **6.1** Verify no `retry_on_failure` exists anywhere:
  ```bash
  grep -rn 'def retry_on_failure\|def _retry\|def retry\b' backend/services/ml/ backend/services/ 2>&1 | head -5
  ```
  If 0 → drop `TestRetryDecorator` entirely from the rewrite. If a real retry helper exists with a different name → write the test against THAT.

- [ ] **6.2** Replace ENTIRE content of `backend/tests/services/ml/test_ml_integration.py` with:

```python
"""
backend/tests/services/ml/test_ml_integration.py

Integration tests for the ML pipeline.
- Verifies every model in MODEL_REGISTRY loads from disk
- Verifies each model's manifest JSON has the required fields
- Smoke-tests the InferenceEngine contract
"""
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import joblib
import pytest


# ── Module-mocking fixtures (run before importing inference) ─────────────


@pytest.fixture(autouse=True)
def mock_motor():
    motor_mock = types.ModuleType("motor")
    motor_mock.motor_asyncio = types.ModuleType("motor.motor_asyncio")
    motor_mock.motor_asyncio.AsyncIOMotorClient = MagicMock
    sys.modules["motor"] = motor_mock
    sys.modules["motor.motor_asyncio"] = motor_mock.motor_asyncio
    yield
    for k in list(sys.modules):
        if k.startswith("motor"):
            del sys.modules[k]


@pytest.fixture(autouse=True)
def mock_dotenv():
    dm = types.ModuleType("dotenv")
    dm.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dm
    yield
    if "dotenv" in sys.modules:
        del sys.modules["dotenv"]


# ── Helpers ──────────────────────────────────────────────────────────────


def _models_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3] / "models"


def _registry():
    from services.ml.inference import MODEL_REGISTRY
    return MODEL_REGISTRY


def _resolve(model_path) -> Path:
    p = Path(model_path)
    if not p.is_absolute():
        p = _models_dir() / p.name
    return p


# ── TestModelLoading ─────────────────────────────────────────────────────


TICKERS = ["SPY", "QQQ", "DIA", "IWM", "TLT"]


@pytest.mark.parametrize("ticker", TICKERS)
def test_model_file_exists(ticker):
    registry = _registry()
    assert ticker in registry, f"{ticker} not in MODEL_REGISTRY"
    path = _resolve(registry[ticker])
    assert path.exists(), f"{ticker} model missing: {path}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_model_loads_with_joblib(ticker):
    path = _resolve(_registry()[ticker])
    model = joblib.load(path)
    assert hasattr(model, "predict"), \
        f"{ticker} model has no .predict (got {type(model).__name__})"


# ── TestManifestIntegrity ────────────────────────────────────────────────


REQUIRED_FIELDS = {"ticker", "feature_names", "trained_at"}


def _manifest_path(ticker: str) -> Path:
    model_path = _resolve(_registry()[ticker])
    for suffix in ("_manifest.json", "_meta.json"):
        cand = model_path.with_name(model_path.stem + suffix)
        if cand.exists():
            return cand
    return model_path.with_name(model_path.stem + "_manifest.json")


@pytest.mark.parametrize("ticker", TICKERS)
def test_manifest_file_exists(ticker):
    mp = _manifest_path(ticker)
    assert mp.exists(), f"{ticker} manifest missing: {mp}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_manifest_has_required_fields(ticker):
    with open(_manifest_path(ticker)) as f:
        data = json.load(f)
    missing = REQUIRED_FIELDS - set(data.keys())
    assert not missing, f"{ticker} manifest missing fields: {missing}"


@pytest.mark.parametrize("ticker", TICKERS)
def test_manifest_feature_count_matches_model(ticker):
    model = joblib.load(_resolve(_registry()[ticker]))
    with open(_manifest_path(ticker)) as f:
        data = json.load(f)
    manifest_n = len(data["feature_names"])
    model_n = getattr(model, "n_features_in_", None)
    if model_n is None:
        pytest.skip(f"{ticker} model is a Pipeline; n_features_in_ unavailable")
    assert manifest_n == model_n, \
        f"{ticker}: manifest {manifest_n} vs model {model_n}"


# ── TestInferenceContract ────────────────────────────────────────────────


def test_class_labels_3way():
    from services.ml.inference import CLASS_LABELS
    assert isinstance(CLASS_LABELS, dict)
    assert set(CLASS_LABELS.keys()) <= {0, 1, 2}, \
        f"unexpected CLASS_LABELS keys: {CLASS_LABELS.keys()}"


def test_inference_engine_importable():
    from services.ml.inference import InferenceEngine
    assert InferenceEngine is not None
```

- [ ] **6.3** Run: `cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v 2>&1 | tail -20`. Expected: most pass, possibly some skipped on Pipeline models. **No failures.**
- [ ] **6.4** If a test fails for a real reason (missing model on disk), document in close-out but DO NOT skip/xfail. HALT and ping architect.
- [ ] **6.5** Commit:
  ```bash
  git add backend/tests/services/ml/test_ml_integration.py
  git commit -m "$(cat <<'EOF'
  fix(round-9-a2): rewrite ML integration tests against real MODEL_REGISTRY
  
  Previous (uncommitted) version hardcoded paths like DIA_logistic_wf.joblib
  that don't exist (real is DIA_gbm_production.joblib) and referenced an
  undefined retry_on_failure decorator. 7 of 9 tests failed.
  
  This rewrite:
  - Reads model paths from MODEL_REGISTRY (single source of truth)
  - Parameterizes 5 tickers so all are covered uniformly
  - Handles _manifest.json and _meta.json conventions
  - Skips n_features_in_ gracefully on Pipeline models
  - Replaced TestRetryDecorator (non-existent fn) with TestInferenceContract
    smoke-test (CLASS_LABELS + InferenceEngine import)
  - Mocks motor + dotenv so tests run without a live DB
  
  Verification:
  \$ cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v 2>&1 | tail -1
  <PASTE YOUR ACTUAL T6.3 LAST LINE HERE>
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'a2'
  ```
- [ ] **6.6** Pulse.

---

## Task 7 — Add `pytest.ini` for consistent config (15 min)

Goal: stop CI/local pytest from drifting on collection settings.

- [ ] **7.1** Check existing config:
  ```bash
  ls backend/pytest.ini backend/setup.cfg backend/pyproject.toml 2>&1
  grep -A20 '\[tool.pytest.ini_options\]\|^\[pytest\]' backend/pyproject.toml backend/setup.cfg 2>/dev/null
  ```
- [ ] **7.2** If no pytest config exists, create `backend/pytest.ini`:
  ```ini
  [pytest]
  # Test discovery
  testpaths = tests
  python_files = test_*.py
  python_classes = Test*
  python_functions = test_*
  
  # Async test runner (default mode for tests using pytest-asyncio)
  asyncio_mode = auto
  
  # Markers (suppress "unknown marker" warnings)
  markers =
      slow: tests that take >1s
      integration: tests requiring a live MongoDB or external API
      regression: tests pinned to a specific bug (don't delete without ticket)
  
  # Hide noisy warnings from upstream packages
  filterwarnings =
      ignore::DeprecationWarning:starlette.*
      ignore::PendingDeprecationWarning
  
  # Default options
  addopts = --tb=short --strict-markers --strict-config
  ```
- [ ] **7.3** Verify: `cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3` → should still pass, possibly with new strict-marker errors (if any test uses an undeclared marker, fix the marker declaration in pytest.ini).
- [ ] **7.4** Commit:
  ```bash
  git add backend/pytest.ini
  git commit -m "feat(test-infra): add pytest.ini — strict markers, asyncio auto-mode"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **7.5** Pulse.

---

## Task 8 — Audit for other missing `__init__.py` (READ-ONLY survey, 20 min)

- [ ] **8.1** Find every backend directory that contains `.py` files but no `__init__.py`:
  ```bash
  find backend -type d -name '__pycache__' -prune -o -type d -print \
    | grep -v '\.venv\|node_modules' \
    | while read d; do
        if ls "$d"/*.py 2>/dev/null | grep -q . ; then
          if [ ! -f "$d/__init__.py" ]; then
            echo "MISSING: $d/__init__.py"
          fi
        fi
      done
  ```
- [ ] **8.2** For each MISSING result, decide:
  - Is it a top-level (like `backend/services` was)? → likely needs `__init__.py`
  - Is it `backend/tests/...`? → may not need one (pytest handles tests differently); check the analogous-level test dir
  - Is it `backend/.venv/...`? → skip
- [ ] **8.3** Write findings to your closeout doc (don't auto-create — let architect decide which to actually fix in Round 10).
- [ ] **8.4** Pulse.

---

## Task 9 — Full pytest sweep + capture deltas (10 min)

- [ ] **9.1** Final pytest run with summary:
  ```bash
  cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5
  ```
  Capture the pass/fail/skip/error counts.
- [ ] **9.2** Compare to BEFORE (your T1.3 number): the diff should show +many tests now collected + (ideally) +many tests now passing.
- [ ] **9.3** If new failures appeared (tests that USED to be hidden by the collection error and now run + fail), document each in close-out. Do NOT skip/xfail.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** Write `docs/ROUND9_A2_CLOSEOUT.md`:
  ```markdown
  # Agent A2 Close-out — Test Infrastructure Overhaul
  
  ## Commits
  | Task | SHA | Subject |
  | 2-4 | <sha> | services/__init__.py + regression test |
  | 6 | <sha> | rewrite test_ml_integration.py |
  | 7 | <sha> | pytest.ini |
  
  ## Pytest delta
  - BEFORE: <T1.3>
  - AFTER:  <T9.1>
  - Net: +<delta> tests now collected
  
  ## Newly-visible failures (not caused by A2, but now surfaced)
  - <list any from T9.3>
  
  ## Missing __init__.py audit (T8)
  | Directory | Has .py files | Should add |
  | <dir> | yes | yes/no/architect decides |
  
  ## Round 10 candidates
  - <any new test failures that need triage>
  ```
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse: `A2 :: DONE :: 3 commits :: +<N> tests collectable`.

---

## Halt conditions

1. Pre-flight finds `services/__init__.py` already exists.
2. Adding `__init__.py` makes tests FAIL (not error) in numbers > 5.
3. MODEL_REGISTRY claims a model that doesn't exist on disk.
4. Rewrite can't get ≥80% passing without skip/xfail.
5. Origin gate fails.
6. 15-min pulse gap.
