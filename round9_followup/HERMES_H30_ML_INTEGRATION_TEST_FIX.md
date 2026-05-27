# Hermes Owl Alpha — Agent H30 · Rewrite `test_ml_integration.py` Against Real Model Paths (~45 min)

You are Agent H30. You fix the broken integration test file `backend/tests/services/ml/test_ml_integration.py` that's been sitting uncommitted in the working tree across multiple sessions. It currently fails 7 of 9 tests because:

1. It hardcodes model paths like `DIA_logistic_wf.joblib` — actual models on disk are `DIA_gbm_production.joblib` (and `*_rf_<timestamp>.joblib`).
2. It references `retry_on_failure` decorator — not defined anywhere in the codebase.

Your job: rewrite the tests to validate the REAL contracts of `services.ml.inference`, commit it, get all tests passing without `xfail`/`skip`.

---

## Hard constraints

- **Canonical clone**: `/Users/nav/Documents/GitHub/floww`. **Not** the stale one.
- **Forbidden files**: `backend/services/ml/inference.py` is **READ-ONLY** for you. You cannot modify it; you can (and should) read it to learn the real contract. Same for `backend/services/dash_ui.py` and `backend/tests/conftest.py`.
- **You CAN modify**: `backend/tests/services/ml/test_ml_integration.py` (the broken file), and you may create supporting fixture files in `backend/tests/services/ml/` if needed.
- **No `--force`, `--no-verify`, `--amend` of others' commits.**
- **NEVER** mark a test xfail/skip. If a test you write can't pass, the test is wrong — rewrite or delete it.
- **No new pip dependencies.** If your test needs something that's not installed, HALT.
- **Origin gate after commit.**
- **15-min pulse** to `kanban/cards/agent_H30_status.md`.

---

## Pre-flight

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`.

- [ ] **PF2.** Confirm the broken file is still untracked (not already deleted or fixed by another agent):
  ```
  git status --short backend/tests/services/ml/test_ml_integration.py
  ```
  Expected: `?? backend/tests/services/ml/test_ml_integration.py`.

- [ ] **PF3.** Capture the current failure state:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py --tb=line 2>&1 | tail -15
  ```
  Save this output — you'll cite the 7 failure counts in the commit message.

- [ ] **PF4.** Discover what models actually exist on disk:
  ```
  ls backend/models/ | grep -E '\.joblib$|_manifest\.json$' | head -20
  ```
  Save the list. You'll see patterns like `SPY_gbm_production.joblib`, `SPY_gbm_production_manifest.json`, `SPY_rf_<timestamp>.joblib`, `SPY_rf_<timestamp>_meta.json`, etc.

- [ ] **PF5.** Read the inference engine to learn the REAL contract:
  ```
  grep -nE 'MODEL_REGISTRY|class .*Engine|async def predict|class CLASS_LABELS' backend/services/ml/inference.py | head -20
  ```
  Then `Read` the file (it's frozen — read-only) and note:
  - The exact `MODEL_REGISTRY` dict keys + values
  - The `predict()` method signature + return type
  - What `CLASS_LABELS` maps (likely `{0: "DOWN", 1: "HOLD", 2: "UP"}`)
  - Any module-level constants like `UP`, `DOWN`, `HOLD`

- [ ] **PF6.** Read the current broken test file to know what to fix:
  ```
  Read tool on backend/tests/services/ml/test_ml_integration.py (full file)
  ```

- [ ] **PF7.** Pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H30 :: started :: <N> models on disk, <M> failing tests :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H30_status.md
  ```

---

## Task 1: Catalog what the tests SHOULD verify (10 min)

The broken file is shooting for legitimate integration coverage. Even though the implementation is broken, the INTENT is sound. Your job is to keep the intent and fix the contract.

From your PF6 read, the broken file has these test classes:

- `TestModelLoading` — verifies all 5 tickers' model files exist and load via joblib
- `TestManifestIntegrity` — verifies manifest JSON shape matches model
- `TestRetryDecorator` — verifies the (non-existent) `retry_on_failure` decorator

The 1st and 2nd classes have real value. The 3rd is dead — `retry_on_failure` isn't a function in this codebase, so just **delete that test class entirely**. (You may briefly look in `backend/services/ml/` for a decorator named anything like `_retry`, `retry`, `with_retry` — if a similar real decorator exists, write the test against IT. Otherwise drop the class.)

- [ ] **T1.1** Confirm by grep that no `retry_on_failure` or analog exists:
  ```
  grep -rn 'def retry_on_failure\|def _retry\|def retry\b' backend/services/ml/ backend/services/ 2>&1 | head -10
  ```
  If 0 results → drop the `TestRetryDecorator` class entirely.
  If a real retry decorator exists → write the test against THAT.

- [ ] **T1.2** Capture the actual MODEL_REGISTRY shape:
  ```
  cd backend && .venv/bin/python3 -c "
  from services.ml.inference import MODEL_REGISTRY
  for k, v in MODEL_REGISTRY.items():
      print(f'{k}: {v}')
  "
  ```
  This is the source of truth for your tests. Don't hardcode file names — read from `MODEL_REGISTRY`.

---

## Task 2: Rewrite the test file (15 min)

Replace the entire content of `backend/tests/services/ml/test_ml_integration.py` with the new version below. Tweak it to match what PF4/PF5/T1.2 told you about reality.

```python
"""
backend/tests/services/ml/test_ml_integration.py

Integration tests for the ML pipeline.
- Verifies every model in MODEL_REGISTRY loads from disk
- Verifies each model's manifest JSON has the required fields
- Verifies feature count agreement between manifest and model
"""
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import joblib
import pytest


# ── Module-mocking fixtures (run before importing services.ml.inference) ─


@pytest.fixture(autouse=True)
def mock_motor():
    """Mock motor (MongoDB async driver) so import doesn't need a live DB."""
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
    dotenv_mock = types.ModuleType("dotenv")
    dotenv_mock.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dotenv_mock
    yield
    if "dotenv" in sys.modules:
        del sys.modules["dotenv"]


# ── Helpers ──────────────────────────────────────────────────────────────


def _models_dir() -> Path:
    """Path to backend/models/ regardless of cwd."""
    here = Path(__file__).resolve()  # backend/tests/services/ml/test_ml_integration.py
    return here.parents[3] / "models"  # backend/models/


def _registry():
    """Import MODEL_REGISTRY lazily (after motor/dotenv mocks are installed)."""
    from services.ml.inference import MODEL_REGISTRY
    return MODEL_REGISTRY


# ── TestModelLoading ─────────────────────────────────────────────────────


class TestModelLoading:
    """Every model in MODEL_REGISTRY must exist on disk and load via joblib."""

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "DIA", "IWM", "TLT"])
    def test_model_file_exists(self, ticker):
        registry = _registry()
        assert ticker in registry, f"{ticker} not in MODEL_REGISTRY"
        model_path_str = registry[ticker]
        # MODEL_REGISTRY values may be Path objects or strings; normalize
        model_path = Path(model_path_str)
        if not model_path.is_absolute():
            model_path = _models_dir() / model_path.name
        assert model_path.exists(), \
            f"{ticker} model file missing: {model_path}"

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "DIA", "IWM", "TLT"])
    def test_model_loads_with_joblib(self, ticker):
        registry = _registry()
        model_path_str = registry[ticker]
        model_path = Path(model_path_str)
        if not model_path.is_absolute():
            model_path = _models_dir() / model_path.name
        model = joblib.load(model_path)
        # Sklearn models all expose .predict — minimal contract check
        assert hasattr(model, "predict"), \
            f"{ticker} model has no .predict method (got {type(model).__name__})"


# ── TestManifestIntegrity ────────────────────────────────────────────────


class TestManifestIntegrity:
    """Each model has an accompanying manifest JSON with required fields."""

    REQUIRED_FIELDS = {"ticker", "feature_names", "trained_at"}

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "DIA", "IWM", "TLT"])
    def test_manifest_file_exists(self, ticker):
        manifest = self._manifest_path(ticker)
        assert manifest.exists(), f"{ticker} manifest missing: {manifest}"

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "DIA", "IWM", "TLT"])
    def test_manifest_has_required_fields(self, ticker):
        manifest = self._manifest_path(ticker)
        with open(manifest) as f:
            data = json.load(f)
        missing = self.REQUIRED_FIELDS - set(data.keys())
        assert not missing, f"{ticker} manifest missing fields: {missing}"

    @pytest.mark.parametrize("ticker", ["SPY", "QQQ", "DIA", "IWM", "TLT"])
    def test_manifest_feature_count_matches_model(self, ticker):
        registry = _registry()
        model_path = Path(registry[ticker])
        if not model_path.is_absolute():
            model_path = _models_dir() / model_path.name
        model = joblib.load(model_path)
        manifest = self._manifest_path(ticker)
        with open(manifest) as f:
            data = json.load(f)
        manifest_n = len(data["feature_names"])
        # sklearn 1.x exposes n_features_in_; pipelines may not
        model_n = getattr(model, "n_features_in_", None)
        if model_n is None:
            pytest.skip(f"{ticker} model has no n_features_in_ (likely a Pipeline) — manifest-only check")
        assert manifest_n == model_n, \
            f"{ticker}: manifest says {manifest_n} features, model expects {model_n}"

    def _manifest_path(self, ticker: str) -> Path:
        """Find the manifest JSON next to the model file."""
        registry = _registry()
        model_path = Path(registry[ticker])
        if not model_path.is_absolute():
            model_path = _models_dir() / model_path.name
        # Convention: <model>.joblib has manifest <model>_manifest.json (or <model>_meta.json)
        candidates = [
            model_path.with_name(model_path.stem + "_manifest.json"),
            model_path.with_name(model_path.stem + "_meta.json"),
        ]
        for c in candidates:
            if c.exists():
                return c
        # If neither convention matches, return the _manifest one and let the test report it
        return candidates[0]


# ── TestInferenceContract ────────────────────────────────────────────────


class TestInferenceContract:
    """Smoke-test the InferenceEngine returns the expected contract shape."""

    def test_class_labels_present(self):
        from services.ml.inference import CLASS_LABELS
        # 3-class system landed in Round-10 H17 (commit 44c706b)
        assert isinstance(CLASS_LABELS, dict)
        assert set(CLASS_LABELS.keys()) <= {0, 1, 2}, \
            f"unexpected CLASS_LABELS keys: {CLASS_LABELS.keys()}"

    def test_engine_class_importable(self):
        from services.ml.inference import InferenceEngine
        assert InferenceEngine is not None
```

- [ ] **T2.1** Note: the test above is INTENT-PRESERVING but ADAPTED to reality.

- [ ] **T2.2** **IMPORTANT** — if your PF4/PF5 discovered the model paths are DIFFERENT from what `MODEL_REGISTRY` claims (e.g., registry says `DIA_gbm_production.joblib` but only `DIA_rf_<ts>.joblib` exists on disk), don't paper over — this is a separate bug. Write the test against the registry's claim, and let it fail. Then HALT and flag in the commit message + status pulse — that's a Round 10 ticket, not yours to fix.

---

## Task 3: Run and iterate (10 min)

- [ ] **T3.1** Run the new tests:
  ```
  cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v 2>&1 | tail -30
  ```

- [ ] **T3.2** Expected outcomes:
  - All 5 `test_model_file_exists` pass (or fail loudly with the specific missing-file path — that's a real bug, document it)
  - All 5 `test_model_loads_with_joblib` pass
  - 5 manifest tests likely pass; manifest_feature_count may skip on Pipeline models
  - 2 inference contract tests pass

- [ ] **T3.3** If a test fails for a REAL reason (model genuinely missing from disk), do NOT skip/xfail it. Either:
  - The model needs to be regenerated → HALT, ping architect, model regeneration is a separate ticket
  - The MODEL_REGISTRY is wrong → READ `inference.py` again to see if there's a getter function you should call instead of the dict; adjust your test
  - The test itself is wrong → fix the test

---

## Task 4: Commit (5 min)

```bash
git add backend/tests/services/ml/test_ml_integration.py
git status --short
git commit -m "$(cat <<'EOF'
fix(round-9-h30): rewrite ML integration tests against real MODEL_REGISTRY

The previous version of this file (uncommitted across multiple sessions)
hardcoded model paths like DIA_logistic_wf.joblib that don't exist
(real names are DIA_gbm_production.joblib) and referenced an undefined
`retry_on_failure` decorator. All 7 of 9 tests were failing.

This rewrite:
- Reads model paths from MODEL_REGISTRY rather than hardcoding
- Parameterizes over 5 tickers (SPY/QQQ/DIA/IWM/TLT) so all are covered
- Handles both `_manifest.json` and `_meta.json` conventions
- Skips n_features_in_ assertion gracefully on Pipeline models
- Replaces the TestRetryDecorator class (testing a non-existent function)
  with a TestInferenceContract class that smoke-tests CLASS_LABELS +
  InferenceEngine importability
- Mocks motor + dotenv so the tests run without a live MongoDB

Verification:
  $ cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v
  <PASTE YOUR ACTUAL PASS COUNT HERE>
EOF
)"
git push origin main
git fetch origin && git log origin/main --oneline -1 | grep 'h30'
```

**If grep fails, STOP.**

- [ ] **T4.1** Pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H30 :: DONE :: tests rewritten, <N>/<M> passing :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H30_status.md
  ```

---

## Halt conditions

1. Pre-flight finds the broken file already gone (another agent ate it).
2. `inference.py` reading turns up unexpected — e.g., `MODEL_REGISTRY` isn't a dict anymore, it's a function. Then your tests need different shape. HALT and re-scope.
3. A model file the registry claims exists actually doesn't on disk → that's a real bug, not yours to fix; HALT.
4. You can't get the new tests to ≥80% pass without skipping any → HALT, the model layout has drifted further than expected.
5. Origin gate fails.
6. 15-min pulse gap.

---

## What success looks like

- 1 commit on origin: the rewritten test file
- All (or near-all, with at most 1-2 documented `pytest.skip` for genuine Pipeline limitations) tests pass
- `git status --short` no longer shows `?? backend/tests/services/ml/test_ml_integration.py` (it's committed)
- The test file references `MODEL_REGISTRY` as source of truth, not hardcoded names — future agents who add a 6th ticker can `git diff` and see exactly what needs to change (just the parametrize list)
