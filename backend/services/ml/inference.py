"""
backend/services/ml/inference.py

Real-time ML inference engine.

Loads pre-trained model artifacts, computes live features from market data,
and serves predictions with confidence scores.

Usage:
    from services.ml.inference import InferenceEngine
    engine = InferenceEngine()
    result = await engine.predict("SPY")
    print(result.prediction, result.confidence)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import yfinance as yf

from services.ml import DegenerateModelError

log = logging.getLogger("ml.inference")

# ── Configuration ─────────────────────────────────────────────────────

MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

# Map ticker -> (model_path, scaler_path, manifest_path)
# Models live in backend/models/
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"

# Map ticker -> model filename (in models/ directory)
# These are the latest trained models from train_spy_model.py
MODEL_REGISTRY: Dict[str, str] = {
    "SPY": str(MODEL_DIR / "SPY_rf_20260524_020801.joblib"),
    "QQQ": str(MODEL_DIR / "QQQ_rf_20260524_022118.joblib"),
    "TLT": str(MODEL_DIR / "TLT_rf_20260524_022154.joblib"),
    "IWM": str(MODEL_DIR / "IWM_rf_20260524_022147.joblib"),
}

# Feature computation constants
FEATURE_WINDOWS = {
    "sma": [5, 10, 21, 50],
    "vol": [5, 10, 21, 60],
    "ret": [1, 3, 5, 10, 21],
}

# Cache TTL
FEATURE_CACHE_TTL_SEC = 300  # 5 minutes


# ── Data classes ───────────────────────────────────────────────────────


@dataclass
class PredictionResult:
    """Single prediction result."""
    ticker: str
    prediction: int  # 1 = bullish, 0 = bearish
    confidence: float  # probability of predicted class
    probabilities: List[float]  # [P(bearish), P(bullish)]
    model_id: str
    features_used: List[str]
    feature_values: Dict[str, float]
    timestamp: str
    data_age_sec: float = 0.0


@dataclass
class ModelInfo:
    """Model metadata."""
    ticker: str
    model_id: str
    model_type: str
    n_features: int
    feature_names: List[str]
    train_accuracy: float
    artifact_path: str
    loaded: bool = False


# ── Feature Engineering ───────────────────────────────────────────────


def compute_live_features(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Compute features from live yfinance data.

    Downloads OHLCV data and computes the full feature set
    matching the v1.0 feature schema.

    Args:
        ticker: Ticker symbol
        period: Data period (default: 1y)

    Returns:
        DataFrame with one row per trading day, columns = features
    """
    log.info(f"Downloading {ticker} data (period={period})")
    try:
        data = yf.download(ticker, period=period, progress=False)
        if data.empty:
            raise DegenerateModelError(f"No data returned for {ticker}")
    except Exception as e:
        raise DegenerateModelError(f"Failed to download {ticker}: {e}")

    # Handle multi-level columns from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    df = data.copy()
    df = df.dropna(subset=["Close"])
    if len(df) < 60:
        raise DegenerateModelError(
            f"Insufficient data for {ticker}: {len(df)} rows (need 60+)"
        )

    features = pd.DataFrame(index=df.index)

    # Price-based features
    close = df["Close"].values
    high = df["High"].values if "High" in df.columns else close
    low = df["Low"].values if "Low" in df.columns else close
    volume = df["Volume"].values if "Volume" in df.columns else np.ones(len(close))
    open_price = df["Open"].values if "Open" in df.columns else close

    # Returns
    for horizon in FEATURE_WINDOWS["ret"]:
        ret = np.zeros(len(close))
        for i in range(horizon, len(close)):
            if close[i - horizon] > 0:
                ret[i] = (close[i] - close[i - horizon]) / close[i - horizon]
        features[f"ret_{horizon}d"] = ret

    # Log returns
    log_ret = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i - 1] > 0 and close[i] > 0:
            log_ret[i] = np.log(close[i] / close[i - 1])
    features["log_ret_1d"] = log_ret

    # Overnight gap
    overnight_gap = np.zeros(len(close))
    for i in range(1, len(close)):
        if close[i - 1] > 0:
            overnight_gap[i] = (open_price[i] - close[i - 1]) / close[i - 1]
    features["overnight_gap"] = overnight_gap

    # Simple Moving Averages
    for window in FEATURE_WINDOWS["sma"]:
        sma = pd.Series(close).rolling(window=window, min_periods=window).mean().values
        features[f"sma_{window}"] = sma
        # Price relative to SMA
        rel = np.zeros(len(close))
        for i in range(len(close)):
            if sma[i] > 0:
                rel[i] = close[i] / sma[i] - 1.0
        features[f"price_vs_sma_{window}"] = rel

    # ATR (Average True Range)
    tr = np.zeros(len(close))
    for i in range(1, len(close)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    atr_14 = pd.Series(tr).rolling(window=14, min_periods=14).mean().values
    features["atr_14"] = atr_14

    # Volume features
    vol_sma_5 = pd.Series(volume).rolling(window=5, min_periods=5).mean().values
    vol_sma_21 = pd.Series(volume).rolling(window=21, min_periods=21).mean().values
    features["volume_sma_5"] = vol_sma_5
    features["volume_sma_21"] = vol_sma_21

    rel_vol = np.zeros(len(close))
    for i in range(len(close)):
        if vol_sma_21[i] > 0:
            rel_vol[i] = volume[i] / vol_sma_21[i]
    features["relative_volume"] = rel_vol

    # Realized volatility
    for window in FEATURE_WINDOWS["vol"]:
        vol = pd.Series(log_ret).rolling(window=window, min_periods=window).std().values * np.sqrt(252)
        features[f"realized_vol_{window}d"] = vol

    # Calendar features
    dates = pd.to_datetime(df.index)
    features["is_month_end"] = dates.is_month_end.astype(float).values if hasattr(dates.is_month_end, 'values') else np.array(dates.is_month_end, dtype=float)
    features["is_month_start"] = dates.is_month_start.astype(float).values if hasattr(dates.is_month_start, 'values') else np.array(dates.is_month_start, dtype=float)

    # RSI (14-day)
    delta = pd.Series(close).diff()
    gain = delta.where(delta > 0, 0).rolling(window=14, min_periods=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=14).mean()
    rs = gain / (loss + 1e-10)
    features["rsi_14"] = (100 - (100 / (1 + rs))).values

    # MACD
    ema_12 = pd.Series(close).ewm(span=12, adjust=False).mean()
    ema_26 = pd.Series(close).ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    features["macd"] = macd.values
    features["macd_signal"] = macd_signal.values
    features["macd_hist"] = (macd - macd_signal).values

    # Bollinger Bands
    sma_20 = pd.Series(close).rolling(window=20, min_periods=20).mean()
    std_20 = pd.Series(close).rolling(window=20, min_periods=20).std()
    bb_upper_arr = (sma_20 + 2 * std_20).values
    bb_lower_arr = (sma_20 - 2 * std_20).values
    features["bb_upper"] = bb_upper_arr
    features["bb_lower"] = bb_lower_arr
    bb_position = np.zeros(len(close))
    for i in range(len(close)):
        band_width = bb_upper_arr[i] - bb_lower_arr[i]
        if band_width > 0:
            bb_position[i] = (close[i] - bb_lower_arr[i]) / band_width
    features["bb_position"] = bb_position

    # Volume ratios
    features["vol_ratio_5_21"] = vol_sma_5 / (vol_sma_21 + 1e-10)
    vol_sma_60 = pd.Series(volume).rolling(window=60, min_periods=60).mean().values
    features["vol_ratio_5_60"] = vol_sma_5 / (vol_sma_60 + 1e-10)

    # SMA crossovers
    sma_5 = pd.Series(close).rolling(window=5, min_periods=5).mean().values
    sma_21 = pd.Series(close).rolling(window=21, min_periods=21).mean().values
    sma_10 = pd.Series(close).rolling(window=10, min_periods=10).mean().values
    sma_50 = pd.Series(close).rolling(window=50, min_periods=50).mean().values

    features["sma_5_21_diff"] = sma_5 - sma_21
    features["sma_5_21_cross"] = np.sign(features["sma_5_21_diff"])
    features["sma_10_50_diff"] = sma_10 - sma_50

    # RSI extremes
    rsi = features["rsi_14"].values if hasattr(features["rsi_14"], 'values') else features["rsi_14"]
    features["rsi_overbought"] = (rsi > 70).astype(float)
    features["rsi_oversold"] = (rsi < 30).astype(float)

    # Momentum / acceleration
    features["ret_momentum"] = pd.Series(close).pct_change(5).values
    features["ret_accel"] = pd.Series(close).pct_change(5).diff().values

    # Vol spike
    features["vol_spike"] = (
        pd.Series(log_ret).rolling(window=5).std().values /
        (pd.Series(log_ret).rolling(window=21).std().values + 1e-10)
    )

    # Gap features
    features["gap_abs"] = np.abs(overnight_gap)
    features["gap_large"] = (np.abs(overnight_gap) > 0.003).astype(float)

    # Clean up
    features = features.replace([np.inf, -np.inf], np.nan)
    features = features.fillna(0.0)

    log.info(f"Computed {len(features.columns)} features for {ticker} ({len(features)} rows)")
    return features


# ── Inference Engine ──────────────────────────────────────────────────


class InferenceEngine:
    """Real-time ML inference engine.

    Loads pre-trained models and serves predictions with live feature computation.

    Usage:
        engine = InferenceEngine()
        result = await engine.predict("IWM")
        print(f"Prediction: {'BULLISH' if result.prediction == 1 else 'BEARISH'} "
              f"(confidence: {result.confidence:.2%})")
    """

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or MODEL_DIR
        self._model_cache: Dict[str, Tuple[Any, Dict]] = {}
        self._feature_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}

    def _load_model(self, ticker: str) -> Tuple[Any, Dict]:
        """Load model and metadata for a ticker."""
        ticker = ticker.upper()

        if ticker in self._model_cache:
            return self._model_cache[ticker]

        if ticker not in MODEL_REGISTRY:
            raise DegenerateModelError(
                f"No model registered for {ticker}. Available: {list(MODEL_REGISTRY.keys())}"
            )

        entry = MODEL_REGISTRY[ticker]

        # Support both string paths and tuple (model_path, scaler_path, manifest_path)
        if isinstance(entry, tuple):
            model_path = entry[0]
            scaler_path = entry[1] if len(entry) > 1 else None
            manifest_path = entry[2] if len(entry) > 2 else None
        else:
            model_path = entry
            scaler_path = None
            manifest_path = None

        if not os.path.exists(model_path):
            raise DegenerateModelError(f"Model artifact not found: {model_path}")

        artifact = joblib.load(model_path)

        # Handle both raw model objects and dict artifacts
        if isinstance(artifact, dict):
            model = artifact["model"]
            metrics = artifact.get("metrics", {})
            manifest = {
                "model_type": artifact.get("model_name", "unknown"),
                "feature_names": artifact.get("feature_names", []),
                "n_features": len(artifact.get("feature_names", [])),
                "train_accuracy": metrics.get("avg_train_accuracy", 0.0),
                "test_accuracy": metrics.get("avg_test_accuracy", 0.0),
                "test_sharpe": metrics.get("avg_test_sharpe", 0.0),
                "model_path": model_path,
            }
        else:
            # Raw model object (saved directly via joblib.dump)
            model = artifact
            # Load manifest from sidecar JSON if available
            if manifest_path and os.path.exists(manifest_path):
                import json as _json
                with open(manifest_path) as _f:
                    _md = _json.load(_f)
                _metrics = _md.get("metrics", {})
                manifest = {
                    "model_type": _md.get("model_type", type(artifact).__name__),
                    "feature_names": _md.get("feature_names", []),
                    "n_features": len(_md.get("feature_names", [])),
                    "train_accuracy": _metrics.get("avg_train_accuracy", 0.0),
                    "test_accuracy": _metrics.get("avg_test_accuracy", 0.0),
                    "test_sharpe": _metrics.get("avg_test_sharpe", 0.0),
                    "model_path": model_path,
                }
            else:
                n_feat = getattr(artifact, "n_features_in_", 0)
                manifest = {
                    "model_type": type(artifact).__name__,
                    "feature_names": [],
                    "n_features": int(n_feat),
                    "train_accuracy": 0.0,
                    "test_accuracy": 0.0,
                    "test_sharpe": 0.0,
                    "model_path": model_path,
                }

        self._model_cache[ticker] = (model, manifest)
        log.info(f"Loaded model for {ticker}: {manifest.get('model_type', 'unknown')}")
        return model, manifest

    async def predict(self, ticker: str) -> PredictionResult:
        """Generate a prediction for a ticker using live data.

        Downloads recent market data, computes features, and runs inference
        using the pre-trained model.

        Args:
            ticker: Ticker symbol (IWM, TLT, QQQ, DIA)

        Returns:
            PredictionResult with prediction, confidence, and metadata
        """
        ticker = ticker.upper()
        model, manifest = self._load_model(ticker)

        # Compute features (in thread pool to avoid blocking)
        import asyncio
        features_df = await asyncio.to_thread(compute_live_features, ticker)

        # Get feature names from manifest
        feature_names = manifest.get("feature_names", [])
        if not feature_names:
            feature_names = list(features_df.columns)

        # Ensure all expected features are present
        available = [f for f in feature_names if f in features_df.columns]
        missing = [f for f in feature_names if f not in features_df.columns]
        if missing:
            log.warning(f"Missing features for {ticker}: {missing}")
            # Add missing features as zeros
            for f in missing:
                features_df[f] = 0.0

        # Get the latest row for prediction
        latest = features_df[feature_names].iloc[-1:]
        X = latest.values.astype(float)

        # Run prediction (no scaler for RF models)
        prediction = int(model.predict(X)[0])
        probabilities = None
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(X)[0].tolist()

        confidence = probabilities[prediction] if probabilities else 0.5

        # Build feature values dict for the latest row
        feature_values = {
            f: float(latest[f].values[0]) for f in feature_names[:10]  # top 10
        }

        now = datetime.now(timezone.utc)
        data_timestamp = str(features_df.index[-1])
        try:
            data_dt = pd.Timestamp(data_timestamp).to_pydatetime()
            if data_dt.tzinfo is None:
                data_dt = data_dt.replace(tzinfo=timezone.utc)
            data_age_sec = (now - data_dt).total_seconds()
        except Exception:
            data_age_sec = 0.0

        return PredictionResult(
            ticker=ticker,
            prediction=prediction,
            confidence=confidence,
            probabilities=probabilities or [0.5, 0.5],
            model_id=manifest.get("model_id", f"{ticker}_direction_v1.0"),
            features_used=available,
            feature_values=feature_values,
            timestamp=now.isoformat(),
            data_age_sec=data_age_sec,
        )

    def get_model_info(self, ticker: str) -> ModelInfo:
        """Get model metadata for a ticker."""
        ticker = ticker.upper()
        _, manifest = self._load_model(ticker)

        return ModelInfo(
            ticker=ticker,
            model_id=manifest.get("model_id", f"{ticker}_direction_v1.0"),
            model_type=manifest.get("model_type", "unknown"),
            n_features=manifest.get("n_features", 0),
            feature_names=manifest.get("feature_names", []),
            train_accuracy=manifest.get("train_accuracy", 0.0),
            artifact_path=manifest.get("model_path", ""),
            loaded=True,
        )

    def list_models(self) -> List[ModelInfo]:
        """List all available models."""
        results = []
        for ticker in MODEL_REGISTRY:
            try:
                results.append(self.get_model_info(ticker))
            except Exception as e:
                log.warning(f"Could not load model for {ticker}: {e}")
        return results


# ── Singleton ─────────────────────────────────────────────────────────

inference_engine = InferenceEngine()
