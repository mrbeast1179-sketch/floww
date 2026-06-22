"""
backend/tests/services/test_ml_api_silent_error_observability.py

Pinned regression tests for Phase 6 Task 10 Decision Queue #1:
routes/ml_api.py silent-failure observability remediation.

The audit doc (docs/superpowers/research/2026-06-20-decoder-endpoint-silent-failure-audit.md),
row #2 + §Hot-spot deep-dive #1) graded 5 `except Exception: pass` blocks
in ml_api.py as REPRODUCIBLE-HOT-SPOT.  Recon shows ALL 5 are inside
async def interactive request handlers (not background loops) -- the
per-line context judgement the audit flagged.

Fix shape: same as `routes/admin.py` Decision Queue #4 (commit 72b00c8).
NOT HTTPException(500) (which would defeat the partial-data design intent
in ml_briefing where each section is OPTIONAL).  Instead, preserve HTTP
200 + partial data BUT eliminate silent-swallow by:
  - logging the exception via `logger.error(...)`
  - injecting a `<section>_error` key into the response dict so monitoring
    agents can detect degraded section state via response shape

This is an "observability-gap" fix, not a 5xx-escalation fix.

TDD discipline:
- These tests FAIL on the pre-fix code (silent except: pass; no
  `<section>_error` key in body; no logger.error emitted).
- These tests PASS after the fix.

SITES (per audit):
- L378: get_ensemble / statistical detector score (key: statistical_error)
- L513: ml_briefing / GEX fallback (inner) inside DegenerateModelError handler
        (key: prediction_fallback_error)
- L525: ml_briefing / model info section (key: model_error)
- L534: ml_briefing / drift/regime section (key: drift_error)
- L546: ml_briefing / rolling accuracy section (key: rolling_accuracy_error)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

# Ensure backend/ is on sys.path so `import routes.ml_api` resolves.
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes.ml_api import get_ensemble, ml_briefing  # noqa: E402

# -------------------------------------------------------------------------
# Stubs / helpers
# -------------------------------------------------------------------------

class _StubAnomalyDetectorRaises:
    """Stand-in for FlowAnomalyDetector() that ALWAYS raises on .score()."""


    def __init__(self, *args, **kwargs) -> None:
        pass


    def score(self, *args, **kwargs) -> dict:
        raise RuntimeError("anomaly-detector score failed: numerical instability")


def _install_get_ensemble_basics(monkeypatch, *, features_df_factory):
    """Install minimal stubs so `get_ensemble` reaches L378 (statistical
    detector block) and the stat_score try fires.

    Requires the route's earlier branches (load_active_artifact +
    compute_latest_features) to succeed so execution reaches L378.

    NOTE on stubs accepting `self`: the route calls `_load_active_artifact`
    and `_compute_latest_features` as class methods on a registry instance
    (`registry._load_active_artifact(ticker)`), so the stubs must accept
    `(self, ...)` to receive the bound registry instance even though
    the stubs ignore it.  Without `self`, Python raises
    `TypeError: takes 1 positional argument but 2 were given`.
    """
    # Stub the registry + features factories.  Both accept `self` because
    # they replace class methods that Python will bind via the registry
    # instance at call time.
    class _Model:
        def predict_proba(self, X):
            import numpy as np
            return np.array([[0.5, 0.5]])

    async def _load_active_artifact_stub(self, ticker):  # noqa: ARG002
        # NB: the route reads `model_doc["model_id"]` and `model_doc["feature_version"]`
        # at multiple points, so the stub must include both keys (the route does NOT
        # use model_doc.get for these reads).
        return (
            _Model(),
            None,
            {
                "model_id": "stub_model_v1",
                "feature_version": "v1.0",
                "metrics_summary": {},
            },
        )

    async def _compute_latest_features_stub(self, ticker, feature_version):  # noqa: ARG002
        return features_df_factory()

    monkeypatch.setattr(
        "services.ml.registry.ModelRegistry._load_active_artifact",
        _load_active_artifact_stub,
    )
    monkeypatch.setattr(
        "services.ml.registry.ModelRegistry._compute_latest_features",
        _compute_latest_features_stub,
    )


def _make_single_row_features_df():
    """Build a minimal DataFrame so get_ensemble reaches L378."""
    import pandas as pd
    df = pd.DataFrame({
        "feature_a": [1.0], "feature_b": [2.0], "feature_c": [3.0],
        "feature_d": [4.0], "feature_e": [5.0], "feature_f": [6.0],
        "feature_g": [7.0], "feature_h": [8.0], "feature_i": [9.0],
        "feature_j": [10.0],
    })
    return df


# -------------------------------------------------------------------------
# Test 1 — get_ensemble L378: statistical detector score raises
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ensemble_statistical_detector_failure_includes_error_key(
    monkeypatch, caplog
):
    """L378 silent except:pass is inside get_ensemble.  When the
    FlowAnomalyDetector().score() call raises, the response should
    STILL be HTTP 200 (graceful partial-data preservation — the ML
    score is unaffected) BUT inject a `statistical_error` key so
    monitoring agents can detect the degraded stat detector.

    Pre-fix: silent swallow; post-fix: log + `statistical_error` key.
    """
    _install_get_ensemble_basics(monkeypatch, features_df_factory=_make_single_row_features_df)
    # Make `from services.anomaly_detector import FlowAnomalyDetector`
    # return a stub class whose .score() raises.
    monkeypatch.setattr(
        "services.anomaly_detector.FlowAnomalyDetector",
        _StubAnomalyDetectorRaises,
    )

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await get_ensemble("SPY", horizon_minutes=15)

    # Graceful degradation preserved.
    assert isinstance(result, dict)
    assert result["ticker"] == "SPY"
    # ml_score + ensemble still present (ML component is unaffected).
    assert "ml_score" in result
    assert "ensemble_score" in result

    # Observability hook: statistical_error key present + non-empty.
    assert "statistical_error" in result, (
        "get_ensemble response is missing 'statistical_error' key after "
        f"stat-detector exception -- silent-swallow regression.  Result: {result!r}"
    )
    assert isinstance(result["statistical_error"], str) and result["statistical_error"].strip(), (
        f"get_ensemble 'statistical_error' must be non-empty.  Got: {result.get('statistical_error')!r}"
    )

    # Logger.error MUST have been called.
    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records, (
        "get_ensemble should have logged an ERROR when stat detector raises. "
        f"Got: {[r.message for r in caplog.records]}"
    )


# -------------------------------------------------------------------------
# Tests 2-5 — ml_briefing L513/L525/L534/L546: section-level partial-data
# preserves + error keys injected per section
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ml_briefing_gex_fallback_failure_includes_error_key(
    monkeypatch, caplog
):
    """L513 silent except:pass is inside the GEX FALLBACK branch of
    ml_briefing's section 1 (prediction).  The fallback only fires
    when predict() raises DegenerateModelError.  When the GEX fetch
    ALSO raises inside the fallback, the response should still be
    HTTP 200 + present a degenerate prediction_error (already there
    from the outer catch) + inject a `prediction_fallback_error` key
    so monitoring agents can detect the secondary fallback failure.
    """
    import routes.ml_api
    import server
    # Stub server.db to a MagicMock so the briefing's `from server import db`
    # resolves without crashing the route's import chain.
    class _DbDict(dict):
        def __missing__(self, key):
            raise KeyError(key)
    monkeypatch.setattr(server, "db", _DbDict(), raising=False)

    # Stub inference_engine.predict to raise DegenerateModelError.
    from services.ml import DegenerateModelError
    async def _predict_raise(ticker):  # noqa: ARG001
        raise DegenerateModelError(f"no active model for {ticker}")
    monkeypatch.setattr(routes.ml_api.inference_engine, "predict", _predict_raise)

    # Stub the GEX fetch path: make fetch_spot_and_chains_merged raise.
    import services.heatseeker as heatseeker_mod
    async def _fetch_raises(*args, **kwargs):
        raise RuntimeError("GEX fetch failed: upstream unavailable")
    monkeypatch.setattr(heatseeker_mod, "fetch_spot_and_chains_merged", None, raising=False)
    monkeypatch.setattr(server, "fetch_spot_and_chains_merged", _fetch_raises, raising=False)
    # Stub heatseeker._gex_per_strike -- shouldn't be reached if fetch raises.
    monkeypatch.setattr(heatseeker_mod, "_gex_per_strike", lambda spot, contracts: {}, raising=False)

    # Stub inference_engine.get_model_info to ALSO raise so the model_error
    # section becomes a testable failure too.
    def _info_raise(ticker):  # noqa: ARG001
        raise RuntimeError("model info failed: artifact not loaded")
    monkeypatch.setattr(routes.ml_api.inference_engine, "get_model_info", _info_raise)

    # Stub registry.compute_drift to raise.
    async def _drift_raise(ticker):  # noqa: ARG001
        raise RuntimeError("drift computation failed: no samples")
    import services.ml.registry as reg_mod
    async def _get_registry_stub():
        class _R:
            pass
        return _R()
    monkeypatch.setattr(reg_mod, "ModelRegistry", lambda db: type("R", (), {
        "compute_drift": staticmethod(_drift_raise),
    })())
    monkeypatch.setattr(routes.ml_api, "_get_registry", _get_registry_stub)

    # Stub compute_rolling_accuracy to raise.
    services_ml_outcomes_mod = sys.modules.get("services.ml.outcomes")
    if services_ml_outcomes_mod is None:
        import services.ml.outcomes as _o
        services_ml_outcomes_mod = _o
    async def _rolling_raise(*args, **kwargs):
        raise RuntimeError("rolling accuracy failed: db handle missing")
    monkeypatch.setattr(services_ml_outcomes_mod, "compute_rolling_accuracy", _rolling_raise)

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await ml_briefing("SPY")

    # Graceful degradation: HTTP 200 + prediction_error present (already there).
    assert isinstance(result, dict)
    assert "prediction_error" in result

    # Observability hook: prediction_fallback_error key present + non-empty.
    assert "prediction_fallback_error" in result, (
        "ml_briefing response is missing 'prediction_fallback_error' key after "
        f"GEX fallback failure -- silent-swallow regression.  Result: {result!r}"
    )
    assert isinstance(result["prediction_fallback_error"], str) and result["prediction_fallback_error"].strip(), (
        f"ml_briefing 'prediction_fallback_error' must be non-empty.  Got: {result.get('prediction_fallback_error')!r}"
    )

    # Logger.error MUST have fired.
    fallback_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert fallback_records, (
        "ml_briefing should have logged an ERROR when the GEX fallback raises. "
        f"Got: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_ml_briefing_model_info_failure_includes_error_key(
    monkeypatch, caplog
):
    """L525 silent except:pass is section 2 (model info) of ml_briefing.
    When inference_engine.get_model_info raises, the response should
    still be HTTP 200 BUT inject a `model_error` key so consumers can
    detect the missing model info."""
    import server
    class _DbDict(dict):
        def __missing__(self, key):
            raise KeyError(key)
    monkeypatch.setattr(server, "db", _DbDict(), raising=False)

    import routes.ml_api as ml
    async def _predict_ok(ticker):
        class _R:
            prediction = 1
            probabilities = [0.33, 0.34, 0.33]
            feature_values = {"a": 1.0}
            data_age_sec = 30.0
        return _R()
    monkeypatch.setattr(ml.inference_engine, "predict", _predict_ok)
    def _info_raise(ticker):  # noqa: ARG001
        raise RuntimeError("model info failed: artifact not loaded")
    monkeypatch.setattr(ml.inference_engine, "get_model_info", _info_raise)

    # Stub drift + rolling to succeed (or be irrelevant) so this test isolates L525.
    async def _drift_ok(ticker):  # noqa: ARG001
        return {"status": "stable", "n_recent_samples": 50}
    import services.ml.registry as reg_mod
    async def _get_registry_stub():
        class _R:
            compute_drift = staticmethod(_drift_ok)
        return _R()
    monkeypatch.setattr(reg_mod, "ModelRegistry", lambda db: type("R", (), {
        "compute_drift": staticmethod(_drift_ok),
    })())
    monkeypatch.setattr(ml, "_get_registry", _get_registry_stub)

    import services.ml.outcomes as outcomes_mod
    async def _rolling_ok(*args, **kwargs):
        return {"accuracy": 0.6, "n_with_outcomes": 100}
    monkeypatch.setattr(outcomes_mod, "compute_rolling_accuracy", _rolling_ok)

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await ml_briefing("SPY")

    assert isinstance(result, dict)
    assert "model_error" in result, (
        "ml_briefing response is missing 'model_error' key after model-info "
        f"exception.  Result: {result!r}"
    )
    assert isinstance(result["model_error"], str) and result["model_error"].strip()

    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records


@pytest.mark.asyncio
async def test_ml_briefing_drift_failure_includes_error_key(
    monkeypatch, caplog
):
    """L534 silent except:pass is section 3 (drift/regime) of ml_briefing."""
    import server
    class _DbDict(dict):
        def __missing__(self, key):
            raise KeyError(key)
    monkeypatch.setattr(server, "db", _DbDict(), raising=False)

    import routes.ml_api as ml
    async def _predict_ok(ticker):
        class _R:
            prediction = 1
            probabilities = [0.33, 0.34, 0.33]
            feature_values = {"a": 1.0}
            data_age_sec = 30.0
        return _R()
    monkeypatch.setattr(ml.inference_engine, "predict", _predict_ok)
    def _info_ok(ticker):  # noqa: ARG001
        class _I:
            model_id = "spy_v1"
            model_type = "lgbm"
            n_features = 12
            train_accuracy = 0.62
        return _I()
    monkeypatch.setattr(ml.inference_engine, "get_model_info", _info_ok)

    async def _drift_raise(ticker):  # noqa: ARG001
        raise RuntimeError("drift computation failed: no samples")
    import services.ml.registry as reg_mod
    monkeypatch.setattr(reg_mod, "ModelRegistry", lambda db: type("R", (), {
        "compute_drift": staticmethod(_drift_raise),
    })())
    async def _get_registry_stub():
        return type("R", (), {"compute_drift": staticmethod(_drift_raise)})()
    monkeypatch.setattr(ml, "_get_registry", _get_registry_stub)

    import services.ml.outcomes as outcomes_mod
    async def _rolling_ok(*args, **kwargs):
        return {"accuracy": 0.6, "n_with_outcomes": 100}
    monkeypatch.setattr(outcomes_mod, "compute_rolling_accuracy", _rolling_ok)

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await ml_briefing("SPY")

    assert isinstance(result, dict)
    assert "drift_error" in result, (
        "ml_briefing response is missing 'drift_error' key after drift exception. "
        f"Result: {result!r}"
    )
    assert isinstance(result["drift_error"], str) and result["drift_error"].strip()

    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records


@pytest.mark.asyncio
async def test_ml_briefing_rolling_accuracy_failure_includes_error_key(
    monkeypatch, caplog
):
    """L546 silent except:pass is section 4 (rolling accuracy) of ml_briefing."""
    import server
    class _DbDict(dict):
        def __missing__(self, key):
            raise KeyError(key)
    monkeypatch.setattr(server, "db", _DbDict(), raising=False)

    import routes.ml_api as ml
    async def _predict_ok(ticker):
        class _R:
            prediction = 1
            probabilities = [0.33, 0.34, 0.33]
            feature_values = {"a": 1.0}
            data_age_sec = 30.0
        return _R()
    monkeypatch.setattr(ml.inference_engine, "predict", _predict_ok)
    def _info_ok(ticker):  # noqa: ARG001
        class _I:
            model_id = "spy_v1"
            model_type = "lgbm"
            n_features = 12
            train_accuracy = 0.62
        return _I()
    monkeypatch.setattr(ml.inference_engine, "get_model_info", _info_ok)

    async def _drift_ok(ticker):  # noqa: ARG001
        return {"status": "stable", "n_recent_samples": 50}
    import services.ml.registry as reg_mod
    monkeypatch.setattr(reg_mod, "ModelRegistry", lambda db: type("R", (), {
        "compute_drift": staticmethod(_drift_ok),
    })())
    async def _get_registry_stub():
        return type("R", (), {"compute_drift": staticmethod(_drift_ok)})()
    monkeypatch.setattr(ml, "_get_registry", _get_registry_stub)

    import services.ml.outcomes as outcomes_mod
    async def _rolling_raise(*args, **kwargs):
        raise RuntimeError("rolling accuracy failed: db handle missing")
    monkeypatch.setattr(outcomes_mod, "compute_rolling_accuracy", _rolling_raise)

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await ml_briefing("SPY")

    assert isinstance(result, dict)
    assert "rolling_accuracy_error" in result, (
        "ml_briefing response is missing 'rolling_accuracy_error' key after "
        f"rolling-accuracy exception.  Result: {result!r}"
    )
    assert isinstance(result["rolling_accuracy_error"], str) and result["rolling_accuracy_error"].strip()

    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records


# -------------------------------------------------------------------------
# Test 6 — happy-path control: when no section fails, no error keys present
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ml_briefing_no_failure_has_no_error_keys(
    monkeypatch, caplog
):
    """Happy-path control: when ALL sections succeed, NO `<section>_error`
    keys are present (the observability hook is opt-in by exception only).
    """
    import server
    class _DbDict(dict):
        def __missing__(self, key):
            raise KeyError(key)
    monkeypatch.setattr(server, "db", _DbDict(), raising=False)

    import routes.ml_api as ml
    async def _predict_ok(ticker):
        class _R:
            prediction = 1
            probabilities = [0.33, 0.34, 0.33]
            feature_values = {"a": 1.0}
            data_age_sec = 30.0
        return _R()
    monkeypatch.setattr(ml.inference_engine, "predict", _predict_ok)
    def _info_ok(ticker):  # noqa: ARG001
        class _I:
            model_id = "spy_v1"
            model_type = "lgbm"
            n_features = 12
            train_accuracy = 0.62
        return _I()
    monkeypatch.setattr(ml.inference_engine, "get_model_info", _info_ok)

    async def _drift_ok(ticker):  # noqa: ARG001
        return {"status": "stable", "n_recent_samples": 50}
    import services.ml.registry as reg_mod
    monkeypatch.setattr(reg_mod, "ModelRegistry", lambda db: type("R", (), {
        "compute_drift": staticmethod(_drift_ok),
    })())
    async def _get_registry_stub():
        return type("R", (), {"compute_drift": staticmethod(_drift_ok)})()
    monkeypatch.setattr(ml, "_get_registry", _get_registry_stub)

    import services.ml.outcomes as outcomes_mod
    async def _rolling_ok(*args, **kwargs):
        return {"accuracy": 0.6, "n_with_outcomes": 100}
    monkeypatch.setattr(outcomes_mod, "compute_rolling_accuracy", _rolling_ok)

    with caplog.at_level(logging.ERROR, logger="routes.ml_api"):
        result = await ml_briefing("SPY")

    # Sections provide normal output.
    assert "model_id" in result
    assert "drift_status" in result
    assert "rolling_7d_accuracy" in result

    # No error keys on happy path.
    for key in (
        "statistical_error", "prediction_fallback_error",
        "model_error", "drift_error", "rolling_accuracy_error",
    ):
        assert key not in result, (
            f"ml_briefing must NOT include '{key}' on the happy path.  "
            f"Result: {result!r}"
        )

    # No ERROR-level log records.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_records, (
        f"ml_briefing should NOT log ERROR on happy path.  Got: "
        f"{[r.message for r in error_records]}"
    )
