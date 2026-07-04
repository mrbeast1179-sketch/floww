# Test Suite Audit — floww backend
**Date:** 2026-07-03  
**Scope:** `/Users/nav/Documents/GitHub/floww/backend/tests/`  
**Python:** `.venv/bin/python3` | **Framework:** pytest + asyncio_mode=auto  
**Active Round:** Round 10 (P0.1 conftest waiver, P0.2 fetch_spot_and_chains restore, P0.3 A9 cleanup)

---

## 1. Overall Test Run Summary

| Metric | Value |
|---|---|
| Total tests collected | ~1,200+ across all test batches |
| Confirmed failing | **28 tests** (9 categories) |
| Skipped | ~30 |
| xfailed | 3 |
| Passing | ~1,170 |
| Chaos / E2E / perf batches | 67 passed, 5 skipped (all clean) |
| Stateful / integration batches | Clean |

All test batches run:
- `tests/` root
- `tests/routes/`
- `tests/services/` (all subdirs)
- `tests/chaos/`
- `tests/e2e/`
- `tests/integration/`
- `tests/perf/`
- `tests/stateful/`
- `tests/schwab/`
- `tests/server/`

---

## 2. Failing Tests — Full Catalog with Root Cause Analysis

### CATEGORY A — API Key Mismatch (8 tests)

**Root cause:** `.env` sets `API_SECRET_KEY=dev-local-testing-key`, but every test fixture sends `X-API-Key: test-secret-key`. The conftest workaround is ineffective:

```python
# tests/conftest.py (autouse fixture)
os.environ.setdefault("API_SECRET_KEY", "test-secret-key")  # INEFFECTIVE
```

`setdefault()` is a no-op if the key is already in `os.environ`. Because `python-dotenv` / `Settings` loads `.env` before any test runs, `dev-local-testing-key` is already set. Every call to a protected endpoint 401s, including the autouse `POST /api/live/policy` call inside `_reset_event_loop_and_motor` — meaning setup itself fails on every test that uses `aclient`.

**Failing tests:**

| Test | File |
|---|---|
| `test_alerts_crud` | `tests/test_api.py` |
| `test_snapshot_top_movers_roundtrip` | `tests/test_heatseeker_routes.py` |
| `test_llm_analyze_trade_returns_200_or_503` | `tests/routes/test_llm_endpoints.py` |
| `test_llm_generate_briefing_returns_200_or_503` | `tests/routes/test_llm_endpoints.py` |
| `test_record_prediction` | `tests/services/ml/test_outcome_tracking.py` |
| `test_batch_record` | `tests/services/ml/test_outcome_tracking.py` |
| `test_compute_outcomes` | `tests/services/ml/test_outcome_tracking.py` |
| `test_record_all_tickers` | `tests/services/ml/test_outcome_tracking.py` |

**Fix (one-line):** Change `.env`:
```
API_SECRET_KEY=test-secret-key
```
Or force-override the env var in conftest **before** dotenv loads:
```python
# In root conftest.py, BEFORE any import of server/settings:
os.environ["API_SECRET_KEY"] = "test-secret-key"
```

---

### CATEGORY B — Time-Sensitive / Stale Fixture Window (1 test)

**Root cause:** `test_chain_replay.py` creates test data anchored to `2026-06-21 12:00:00` and then reads it back with `minutes=10_000`. Ten thousand minutes = 6.94 days. As of 2026-07-03, that anchor is 12+ days in the past — outside the read window. The test receives 0 snapshots and asserts 6.

```python
# tests/test_chain_replay.py
ANCHOR = datetime(2026, 6, 21, 12, 0, 0)   # 12 days ago
payload = cr.read_payload(minutes=10_000)    # 6.9-day window → misses ANCHOR
assert len(payload["snapshots"]) == 6        # gets 0 → FAIL
```

**Failing test:**

| Test | File |
|---|---|
| `test_read_payload_explicit_minutes_selects_window_kind` | `tests/test_chain_replay.py` |

**Fix:** Either (a) use a `minutes` value that always covers the anchor regardless of when the test runs (`minutes=10_000_000`), or (b) mock `datetime.now()` in `chain_replay.py`'s read implementation so the window is anchored to the fixture's own timestamp.

---

### CATEGORY C — Wrong Response Schema Key (1 test)

**Root cause:** The test asserts `body.get("zones")` but the actual response schema uses the key `"flip_zones"`.

```python
# tests/routes/test_heatseeker_degraded.py
def test_flip_zones_returns_degraded_on_chain_failure():
    assert body.get("zones") == []   # FAILS
    # Actual response: {"ticker": "SPY", "spot": 0, "flip_zones": [], "count": 0, ...}
```

**Failing test:**

| Test | File |
|---|---|
| `test_flip_zones_returns_degraded_on_chain_failure` | `tests/routes/test_heatseeker_degraded.py` |

**Fix:** Change `body.get("zones")` → `body.get("flip_zones")`.

---

### CATEGORY D — Tests Expect 422 But Route Intentionally Omits Validation (5-7 tests)

**Root cause:** `test_analytics_validation.py` was written expecting FastAPI `Query(ge=..., le=...)` constraints on `window_pct`, `min_gap_pct`, and `lookback_mins`. The route (`routes/heatseeker.py`) deliberately strips those constraints — the Query descriptions literally say `"never 422"`:

```python
# routes/heatseeker.py
async def flip_zones_route(
    window_pct: float = Query(
        default=0.05,
        description="Window as fraction of spot; percents (e.g. 5) normalized, never 422"
    ),
    min_gap_pct: float = Query(
        default=0.02,
        description="Minimum gap as fraction of spot; percents normalized, never 422"
    ),
```

The route accepts any float and normalizes it internally — a design decision that conflicts with the test's assumption. Tests that send out-of-range values expecting 422 instead get 200.

**Failing tests:**

| Test | File |
|---|---|
| `TestFlipZonesValidation::test_window_pct_too_large_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestFlipZonesValidation::test_window_pct_too_small_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestFlipZonesValidation::test_min_gap_pct_too_large_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestAirPocketsValidation::test_min_gap_pct_too_small_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestAirPocketsValidation::test_min_gap_pct_too_large_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestNodeLifecycleValidation::test_lookback_too_small_returns_422` | `tests/routes/test_analytics_validation.py` |
| `TestNodeLifecycleValidation::test_lookback_too_large_returns_422` | `tests/routes/test_analytics_validation.py` |

**Fix (two options):**
- Option A (align tests to reality): Delete the `_returns_422` tests and replace with `_returns_200_with_clamped_output` tests that verify the normalization logic.
- Option B (align route to tests): Add `ge=0.001, le=1.0` to `window_pct`, `ge=0.001, le=0.3` to `min_gap_pct`, and appropriate bounds to `lookback_mins`. Remove "never 422" from descriptions.

---

### CATEGORY E — sklearn Version Incompatibility (2 tests)

**Root cause:** Models were serialized (via `joblib.dump`) with scikit-learn 1.8.0. The active venv has sklearn 1.9.0, which renamed the `_loss` internal module. Loading the serialized models raises:

```
ModuleNotFoundError: No module named 'sklearn.tree._classes'
# or
ModuleNotFoundError: No module named '_loss'
```

Additionally, `tests/services/ml/test_ml_integration.py` triggers `InconsistentVersionWarning` for RandomForestClassifier and LogisticRegression — those models load but with version skew risk.

**Failing tests:**

| Test | File |
|---|---|
| `TestMLPipeline::test_model_loads` | `tests/services/ml/test_ml_pipeline.py` |
| `TestMLPipeline::test_model_predicts_valid_output` | `tests/services/ml/test_ml_pipeline.py` |

**Fix:** Retrain and re-serialize all models under the installed sklearn version:
```bash
python scripts/train_models.py  # or equivalent offline training script
```
All `.pkl` / `.joblib` artifacts should be regenerated. Add a CI check that asserts the serialized sklearn version matches the installed version.

---

### CATEGORY F — Kelly Replay Stale Expected-Value Pins (5 tests)

**Root cause:** The test file `test_kelly_replay.py` pins expected values that were calibrated when `half_kelly()` was rounded internally to 4 decimal places (returning `0.1386`). The current implementation returns full float precision (`0.13863636…`), causing `scale_pnl_linear` to produce `693.18…` instead of the pinned `693.00`.

Math trace:
```
kelly_fraction(0.55, 1.65):
  q = 0.45
  f* = (0.55 × 1.65 − 0.45) / 1.65 = 0.4575 / 1.65 = 0.27727272…
half_kelly = 0.5 × 0.27727272… = 0.13863636…

scale_pnl_linear(100.0, 0.13863636…, 0.02):
  = 100.0 × (0.13863636… / 0.02) = 693.1818…

test pins pytest.approx(693.00, abs=1e-2)  → tolerance ±0.01
actual = 693.18 → delta = 0.18  → FAIL
```

A separate test (`test_total_pnl_under_higher_pct_proportionally_larger`) has inverted directional logic — it asserts that scaling from 2% to 4% yields 2× but fails because the ratio is inverted (gets 0.5× instead).

**Failing tests:**

| Test | File |
|---|---|
| `TestKellyReplayCalibration::test_hand_pin_half_kelly_calibration_anchor` | `tests/test_kelly_replay.py` |
| `TestKellyReplayCalibration::test_hand_pin_quarter_kelly_calibration_anchor` | `tests/test_kelly_replay.py` |
| `TestKellyReplayCalibration::test_total_pnl_under_higher_pct_proportionally_larger` | `tests/test_kelly_replay.py` |
| `TestKellyReplayCalibration::test_replay_record_theoretical_half_kelly_anchor` | `tests/test_kelly_replay.py` |
| `TestKellyReplayCalibration::test_replay_record_theoretical_quarter_kelly_anchor` | `tests/test_kelly_replay.py` |

**Fix:** Repin expected values to full-precision output:
```python
# Replace: pytest.approx(693.00, abs=1e-2)
# With:    pytest.approx(693.18, abs=0.1)  # or compute dynamically
expected = scale_pnl_linear(100.0, half_kelly(0.55, 1.65), 0.02)
assert scaled == pytest.approx(expected, rel=1e-6)
```
For `test_total_pnl_under_higher_pct_proportionally_larger`: fix the ratio direction — higher `policy_pct` relative to `baseline_pct` produces a larger scaled PnL, so the assertion should be `pnl_4pct == pytest.approx(2 * pnl_2pct, rel=0.01)`, not the inverse.

---

### CATEGORY G — Live External API Calls Without Mocking (3 tests)

**Root cause:** `test_heatseeker_v2.py` calls the real ConvexValue API (`tap.convexvalue.com`) and real yfinance with ticker `$SPX` in test code with no mock. In CI / rate-limited environments:
- ConvexValue returns 429 Too Many Requests → empty strikes list → assertion fails
- yfinance returns `$SPX: possibly delisted; no price data found` → `spot = None` → downstream assertions fail

Additional issue: the file uses `@pytest.mark.flaky` which emits `PytestUnknownMarkWarning` even though `flaky` is registered in `pytest.ini`. Investigation needed — possible cause is the `pytest.ini` `[tool:pytest]` header (some pytest versions require `[pytest]` not `[tool:pytest]`).

**Failing tests:**

| Test | File |
|---|---|
| `test_fetch_chain_returns_strikes` | `tests/test_heatseeker_v2.py` |
| `test_full_flip_zone_pipeline_live` | `tests/test_heatseeker_v2.py` |
| `test_spot_price_fetch_live` | `tests/test_heatseeker_v2.py` |

**Fix:**
```python
@pytest.fixture(autouse=True)
def mock_cvserver(monkeypatch):
    monkeypatch.setattr(
        "services.cvserver_client.fetch_chain_from_cvserver",
        AsyncMock(return_value={"ticker": "SPX", "spot": 5300.0, "contracts": [...]}),
    )
    monkeypatch.setattr(
        "yfinance.Ticker",
        lambda ticker: MagicMock(fast_info=MagicMock(last_price=5300.0)),
    )
```
For `pytest.ini` warning: change `[tool:pytest]` → `[pytest]` or add `filterwarnings = ignore::pytest.PytestUnknownMarkWarning` as a temporary suppressor while investigating.

---

### CATEGORY H — Logging Config Implementation Bugs (2 tests)

**Root cause (H1 — formatter):** `TestStructuredFormatter::test_format_module_field` asserts `data["module"] == "test_logging_config"` but gets `"f"`. The `StructuredFormatter.format()` method reads a wrong attribute from `LogRecord` — most likely reading a local variable named `f` (the formatter instance or format string) instead of `record.module`. The formatter emits `'f'` literally as the module name in the JSON output.

**Root cause (H2 — middleware):** `TestCorrelationIdMiddleware::test_passes_cid_in_response_header` calls `send.assert_awaited()` on an `AsyncMock`, but the ASGI `send` callable is never invoked in the test code path. The middleware calls `await send(...)` only in certain branches; the test exercises a branch where `send` is not reached, or the test constructs the middleware invocation without triggering the full ASGI `__call__` cycle.

**Failing tests:**

| Test | File |
|---|---|
| `TestStructuredFormatter::test_format_module_field` | `tests/services/test_logging_config.py` |
| `TestCorrelationIdMiddleware::test_passes_cid_in_response_header` | `tests/services/test_logging_config.py` |

**Fix (H1):** In `services/logging_config.py`, confirm `StructuredFormatter.format()` uses `record.module`, not a local variable:
```python
def format(self, record: logging.LogRecord) -> str:
    data = {
        "module": record.module,   # NOT a local `f` variable
        "function": record.funcName,
        ...
    }
```

**Fix (H2):** The test should trigger the full ASGI middleware cycle. Use `starlette.testclient.TestClient` or build the full ASGI scope/receive/send triplet so the middleware actually invokes `send`:
```python
async def test_passes_cid_in_response_header():
    send = AsyncMock()
    scope = {"type": "http", "headers": [], ...}
    receive = AsyncMock(return_value={"type": "http.request", "body": b""})
    await middleware(scope, receive, send)
    send.assert_awaited()
```

---

## 3. Recurring Non-Failing Bug

### `PerformanceMonitor.record` — AttributeError in Every Request

Every test that exercises a live route via `aclient` generates:

```
AttributeError: 'PerformanceMonitor' object has no attribute 'record'
```

This appears in captured stderr on every single API call. The error is caught and swallowed by `server.py` middleware, so it never causes a test failure, but it:
- Pollutes all captured logs
- Masks real performance metrics (monitoring data is silently dropped)
- Will surface as a production outage the moment the swallow is removed

**Fix:** Add the `record` method to `PerformanceMonitor`:
```python
class PerformanceMonitor:
    def record(self, metric_name: str, value: float, tags: dict | None = None) -> None:
        # emit to observability backend or accumulate internally
        ...
```

---

## 4. Services and Routes with No Test Coverage

### Uncovered Services (no dedicated test file)

| Service | Path | Notes |
|---|---|---|
| `cvserver_client` | `services/cvserver_client.py` | Only exercised indirectly via heatseeker tests — no unit tests for retry logic, auth headers, or rate-limit handling |
| `fill_monitor` | `services/fill_monitor.py` | No test file found |
| `graph_updater` | `services/graph_updater.py` | No `test_graph_updater.py`; may be tested indirectly via retail flow graph |
| `institutional_detector` | `services/institutional_detector.py` | No test file found |
| `node_lifecycle` | `services/node_lifecycle.py` | No test file found |
| `slo_tracker` | `services/slo_tracker.py` | No test file found |
| `trinity_alignment` | `services/trinity_alignment.py` | No test file found |
| `turboquant_cache` | `services/turboquant_cache.py` | No test file found |
| `uoa` | `services/uoa.py` | No test file (Unusual Options Activity) |
| `mock_schwab_feed` | `services/mock_schwab_feed.py` | Test support file — no test of the mock itself |

### Uncovered Routes (no direct route-level test)

| Route | Path | Notes |
|---|---|---|
| `alpaca` | `routes/alpaca.py` | Brokerage integration — no tests |
| `alpha_advantage` | `routes/alpha_advantage.py` | Data provider integration — no tests |
| `alphapod_compat` | `routes/alphapod_compat.py` | Compat shim — no tests |
| `flashalpha` | `routes/flashalpha.py` | No tests |
| `ml_dashboard` | `routes/ml_dashboard.py` | Dashboard API — no tests |
| `nexus` | `routes/nexus.py` | No tests |
| `preferences` | `routes/preferences.py` | User prefs API — no tests |
| `social_flow` | `routes/social_flow.py` | No tests |
| `trinity` | `routes/trinity.py` | No tests |
| `data_providers` | `routes/data_providers.py` | No direct test (provider monitoring exists but doesn't cover route) |
| `hawkes` | `routes/hawkes.py` | Route untested (hawkes service has unit tests) |
| `market_data` | `routes/market_data.py` | No route-level test |

---

## 5. Test File Audit Issues

### 5.1 `tests/conftest.py` — Autouse Fixture Design Flaw

```python
@pytest_asyncio.fixture(autouse=True)
async def _reset_event_loop_and_motor(aclient, monkeypatch):
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key")  # dead code
    ...
    await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})  # always 401
```

Every single test in the suite runs through a `_reset_event_loop_and_motor` setup that 401s silently. This means every test's captured stderr contains auth warnings, making log-based debugging noisy. The fixture is doing real I/O (a `POST` to a protected endpoint) that it cannot authorize. The policy-reset intent is correct; the auth mechanism is broken.

### 5.2 `tests/test_kelly_replay.py` — Hardcoded Precision-Sensitive Pins

The test file pins expected PnL values that were calibrated against a now-changed implementation. As written, the tests are fragile: any refactor of `half_kelly()` or `scale_pnl_linear()` will silently break these pins. Pins should be computed at test time rather than hardcoded:

```python
# Fragile (current):
assert scaled == pytest.approx(693.00, abs=1e-2)

# Robust (recommended):
expected = scale_pnl_linear(100.0, half_kelly(ANCHOR_WIN_PROB, ANCHOR_PAYOFF), NAIVE_BASELINE_PCT)
assert scaled == pytest.approx(expected, rel=1e-6)
```

Additionally, `test_total_pnl_under_higher_pct_proportionally_larger` has a conceptual inversion — it checks `pnl_2pct == 2 * pnl_4pct` (4% is the baseline, so 2% would be half), but the variable names suggest the intent is `pnl_4pct == 2 * pnl_2pct`.

### 5.3 `tests/test_heatseeker_v2.py` — Live Network Calls in Unit Test File

Three tests call real external APIs (`tap.convexvalue.com`, `yfinance`). These belong in `tests/service_tests/` (the live integration test directory that pytest.ini excludes from `testpaths`). Moving them there would let the suite run clean in CI without network access.

The `@pytest.mark.flaky` decorator is used but the `PytestUnknownMarkWarning` suggests the marker registration is not taking effect. Check whether `pytest.ini` uses `[pytest]` vs `[tool:pytest]` — some versions of pytest ignore `[tool:pytest]`.

### 5.4 `tests/test_chain_replay.py` — Date-Dependent Fixture with No Freeze

The `ANCHOR = datetime(2026, 6, 21, 12, 0, 0)` constant is hardcoded. Without mocking `datetime.now()` in the production code, any test using a relative time window will drift and fail as the fixture ages. Either the anchor should be `datetime.now() - timedelta(days=X)` (a relative anchor) or the production `read_payload` function needs a `freeze_time` decorator in tests.

### 5.5 `tests/routes/test_analytics_validation.py` — Tests Specification That Doesn't Exist

The test class names and docstrings say "validates out-of-range params return 422". However, the heatseeker route explicitly documents `"never 422"`. These tests are testing intended behavior that was deliberately removed. Either:
- The route needs the constraints added back (fixing the production behavior), or
- The tests need to be rewritten to test the actual normalization behavior

As-is, these tests are specification drift: they describe an API contract the route doesn't implement.

### 5.6 `tests/services/test_logging_config.py` — ASGI Mock Setup Incomplete

`test_passes_cid_in_response_header` creates `send = AsyncMock()` but doesn't construct a valid ASGI scope or call the middleware's `__call__` properly, so `send` is never invoked. The test asserts `send.assert_awaited()` which fails. This is a test fixture bug, not a middleware bug.

### 5.7 `tests/services/ml/test_ml_pipeline.py` — Version-Locked Fixture Path

The test loads model artifacts from a fixed path using `joblib.load`. No version check or conditional skip. Should add:
```python
import sklearn
import pytest
@pytest.mark.skipif(
    tuple(int(x) for x in sklearn.__version__.split(".")[:2]) > (1, 8),
    reason="Models serialized under sklearn 1.8.x; retrain required for 1.9+"
)
```
This converts a hard failure into a documented skip until models are retrained.

---

## 6. Summary Fix Priority

| Priority | Category | Tests Affected | Effort |
|---|---|---|---|
| P0 | API key mismatch (`.env`) | 8 | 1-line `.env` change |
| P0 | `PerformanceMonitor.record` missing | Every request (non-failing) | Add method stub |
| P1 | Kelly replay stale pins | 5 | Repin to computed values |
| P1 | Schema key `zones` → `flip_zones` | 1 | 1-line test fix |
| P1 | Time-sensitive chain replay test | 1 | Mock `datetime.now()` or use relative anchor |
| P2 | sklearn model retrain (1.9 compat) | 2 | Retrain + re-serialize all `.pkl` files |
| P2 | Live API mocking (heatseeker_v2) | 3 | Add `monkeypatch` mocks; move to service_tests |
| P2 | Analytics validation vs route contract | 5-7 | Decide: add Query constraints or rewrite tests |
| P3 | Logging config: formatter + middleware | 2 | Fix attribute read; fix ASGI test invocation |
| P3 | Routes/services with no coverage | 12 routes, 10 services | Write baseline smoke tests |
