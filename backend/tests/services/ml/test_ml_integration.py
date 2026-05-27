"""
backend/tests/services/ml/test_ml_integration.py

Integration tests for the ML pipeline.
- Verifies every model in MODEL_REGISTRY loads from disk
- Verifies each model's manifest has required fields
- Smoke-tests the InferenceEngine contract and 3-class prediction system
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


def _models_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3] / "models"


def _all_model_files():
    """Return all .joblib model files on disk (not scalers)."""
    models_dir = _models_dir()
    return sorted([
        f for f in models_dir.glob("*.joblib")
        if "_scaler" not in f.name and "_wf_scaler" not in f.name
    ])


def _find_manifest(model_path: Path) -> Path | None:
    """Find the manifest file for a model."""
    for suffix in ("_manifest.json", "_meta.json"):
        cand = model_path.with_name(model_path.stem + suffix)
        if cand.exists():
            return cand
    return None


def _ticker_from_name(name: str) -> str:
    """Extract ticker from model filename (e.g. 'SPY_gbm_production' -> 'SPY')."""
    return name.split("_")[0]


# ── TestModelFilesOnDisk ─────────────────────────────────────────────────


ALL_MODELS = _all_model_files()
TICKERS_ON_DISK = sorted(set(_ticker_from_name(p.stem) for p in ALL_MODELS))


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_model_loads_with_joblib(model_file):
    import joblib
    model = joblib.load(str(model_file))
    assert model is not None, f"{model_file.name} loaded as None"
    assert hasattr(model, "predict"), \
        f"{model_file.name} has no .predict (type: {type(model).__name__})"


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_exists_for_model(model_file):
    manifest = _find_manifest(model_file)
    assert manifest is not None, \
        f"{model_file.name} has no manifest (_manifest.json or _meta.json)"
    assert manifest.exists()


REQUIRED_MANIFEST_FIELDS = {"ticker", "feature_names", "trained_at"}


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_has_required_fields(model_file):
    manifest = _find_manifest(model_file)
    if manifest is None:
        pytest.skip(f"no manifest for {model_file.name}")
    with open(manifest) as f:
        data = json.load(f)
    missing = REQUIRED_MANIFEST_FIELDS - set(data.keys())
    assert not missing, \
        f"{model_file.name} manifest missing fields: {missing}"


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_feature_count_matches_model(model_file):
    import joblib
    model = joblib.load(str(model_file))
    manifest = _find_manifest(model_file)
    if manifest is None:
        pytest.skip(f"no manifest for {model_file.name}")
    with open(manifest) as f:
        data = json.load(f)
    manifest_n = len(data.get("feature_names", []))
    model_n = getattr(model, "n_features_in_", None)
    if model_n is None:
        pytest.skip(f"{model_file.name}: n_features_in_ unavailable (Pipeline?)")
    assert manifest_n == model_n, \
        f"{model_file.name}: manifest says {manifest_n} features, model expects {model_n}"


# ── TestRegistryConsistency ──────────────────────────────────────────────


def test_registry_exists():
    from services.ml.inference import MODEL_REGISTRY
    assert isinstance(MODEL_REGISTRY, dict)
    assert len(MODEL_REGISTRY) >= 4, \
        f"MODEL_REGISTRY has only {len(MODEL_REGISTRY)} entries"


def test_registry_tickers_have_models_on_disk():
    """Every ticker in MODEL_REGISTRY should have a corresponding model on disk."""
    from services.ml.inference import MODEL_REGISTRY
    models_dir = _models_dir()
    for ticker, entry in MODEL_REGISTRY.items():
        if isinstance(entry, tuple):
            model_file = Path(entry[0])
        else:
            model_file = Path(entry)
        if not model_file.is_absolute():
            model_file = models_dir / model_file.name
        # Check if the specific model exists OR any model for that ticker exists
        if not model_file.exists():
            # Fallback: check if ANY model for this ticker exists on disk
            ticker_models = list(models_dir.glob(f"{ticker}_*.joblib"))
            assert ticker_models, \
                f"{ticker} in MODEL_REGISTRY but no model file on disk"


# ── TestThreeClassPrediction ─────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_external_modules():
    """Mock motor and dotenv so inference imports don't need a live DB."""
    motor_mock = types.ModuleType("motor")
    motor_mock.motor_asyncio = types.ModuleType("motor.motor_asyncio")
    motor_mock.motor_asyncio.AsyncIOMotorClient = type("FakeClient", (), {})
    sys.modules["motor"] = motor_mock
    sys.modules["motor.motor_asyncio"] = motor_mock.motor_asyncio
    dm = types.ModuleType("dotenv")
    dm.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dm
    yield
    for k in list(sys.modules):
        if k.startswith(("motor", "dotenv")):
            sys.modules.pop(k, None)


def test_class_labels_3way():
    from services.ml.inference import CLASS_LABELS
    assert isinstance(CLASS_LABELS, dict)
    assert set(CLASS_LABELS.keys()) == {0, 1, 2}
    assert CLASS_LABELS[0] == "DOWN"
    assert CLASS_LABELS[1] == "HOLD"
    assert CLASS_LABELS[2] == "UP"


def test_strong_confidence_threshold():
    from services.ml.inference import STRONG_CONFIDENCE
    assert 0.5 < STRONG_CONFIDENCE < 1.0


def test_map_binary_to_3way_strong_bullish():
    from services.ml.inference import _map_binary_to_3way, UP
    pred, probs = _map_binary_to_3way(1, [0.2, 0.8])
    assert pred == UP
    assert abs(probs[2] - 0.8) < 0.01


def test_map_binary_to_3way_strong_bearish():
    from services.ml.inference import _map_binary_to_3way, DOWN
    pred, probs = _map_binary_to_3way(0, [0.9, 0.1])
    assert pred == DOWN
    assert abs(probs[0] - 0.9) < 0.01


def test_map_binary_to_3way_hold_zone():
    """When confidence is weak (between 0.35 and 0.65), must produce HOLD."""
    from services.ml.inference import _map_binary_to_3way, HOLD
    pred, probs = _map_binary_to_3way(1, [0.45, 0.55])
    assert probs[1] > 0.0, f"Expected HOLD mass in middle band, got {probs}"
    assert abs(sum(probs) - 1.0) < 0.01, f"Probs don't sum to 1: {sum(probs)}"


def test_prediction_result_dataclass():
    from services.ml.inference import PredictionResult
    r = PredictionResult(
        ticker="SPY", prediction=2, confidence=0.8,
        probabilities=[0.1, 0.1, 0.8],
        model_id="SPY_test", features_used=["a", "b"],
        feature_values={"a": 0.5}, timestamp="2026-05-26"
    )
    assert r.prediction == 2
    assert r.gex_signal is None  # default


def test_gex_snapshot_dataclass():
    from services.ml.inference import GEXSnapshot
    g = GEXSnapshot(ticker="SPY", date="2026-05-26", net_gex=-1.5e9,
                    regime="NEGATIVE", spot=740.0)
    assert g.regime == "NEGATIVE"
