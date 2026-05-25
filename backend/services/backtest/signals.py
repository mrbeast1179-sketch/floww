"""
backend/services/backtest/signals.py

Signal interface for the backtest engine.

Two signal types:
  - RuleBasedSignal: decision rules on snapshot/bar features
  - MLEnrichedSignal: ML model predictions gated by a quality threshold

The engine calls Signal.evaluate(snapshot, bars, position) -> Action for each bar.
No lookahead: snapshot and bars only contain data available at/before current bar.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np

log = logging.getLogger("backtest.signals")


class Action(Enum):
    """Trading action for one option contract."""
    BUY_CALL = "BUY_CALL"
    BUY_PUT = "BUY_PUT"
    SELL_CALL = "SELL_CALL"
    SELL_PUT = "SELL_PUT"
    HOLD = "HOLD"


@dataclass
class Position:
    """Tracks a single open option position."""
    side: Optional[str] = None          # "CALL" or "PUT"
    direction: Optional[str] = None     # "LONG" or "SHORT"
    entry_price: float = 0.0
    quantity: int = 0
    entry_bar_idx: int = 0
    unrealized_pnl: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.quantity > 0 and self.side is not None

    def close(self, exit_price: float) -> float:
        """Close position and return realized P&L."""
        if not self.is_open:
            return 0.0
        if self.direction == "LONG":
            pnl = (exit_price - self.entry_price) * self.quantity
        else:
            pnl = (self.entry_price - exit_price) * self.quantity
        self.quantity = 0
        self.side = None
        self.direction = None
        self.unrealized_pnl = 0.0
        return pnl

    def update_unrealized(self, current_price: float) -> float:
        """Update unrealized P&L given current market price."""
        if not self.is_open:
            self.unrealized_pnl = 0.0
            return 0.0
        if self.direction == "LONG":
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity
        return self.unrealized_pnl


class Signal(ABC):
    """Abstract base for all signal generators.

    Subclasses must implement evaluate(), which receives only data available
    at the current bar (no lookahead). The engine guarantees snapshot_history
    and bar_history are truncated to the current bar index.
    """

    @abstractmethod
    def evaluate(
        self,
        snapshot_history: List[Dict[str, Any]],
        bar_history: List[Dict[str, Any]],
        position: Position,
    ) -> Action:
        """Return the action to take at the current bar.

        Args:
            snapshot_history: GEX snapshots up to and including current bar.
            bar_history: OHLCV bars up to and including current bar.
            position: Current open position (may be empty).

        Returns:
            Action to execute.
        """
        ...


class RuleBasedSignal(Signal):
    """Rule-based signal using GEX and price features.

    Configurable thresholds for:
      - net_gex_zscore_60d: extreme GEX regimes
      - price_vs_sma_21: trend filter
      - relative_volume: volume confirmation

    Default rules (long call on bullish confluence, long put on bearish):
      - BUY_CALL:  gex_zscore < -1.0 AND price > SMA21 AND rel_vol > 1.2
      - BUY_PUT:   gex_zscore >  1.0 AND price < SMA21 AND rel_vol > 1.2
      - SELL_CALL: close long call if gex_zscore > 0.5
      - SELL_PUT:  close long put  if gex_zscore < -0.5
      - HOLD:      otherwise
    """

    def __init__(
        self,
        gex_zscore_buy_call_thresh: float = -1.0,
        gex_zscore_buy_put_thresh: float = 1.0,
        gex_zscore_exit_call_thresh: float = 0.5,
        gex_zscore_exit_put_thresh: float = -0.5,
        rel_vol_thresh: float = 1.2,
    ):
        self.gex_zscore_buy_call_thresh = gex_zscore_buy_call_thresh
        self.gex_zscore_buy_put_thresh = gex_zscore_buy_put_thresh
        self.gex_zscore_exit_call_thresh = gex_zscore_exit_call_thresh
        self.gex_zscore_exit_put_thresh = gex_zscore_exit_put_thresh
        self.rel_vol_thresh = rel_vol_thresh

    def evaluate(
        self,
        snapshot_history: List[Dict[str, Any]],
        bar_history: List[Dict[str, Any]],
        position: Position,
    ) -> Action:
        if not snapshot_history or not bar_history:
            return Action.HOLD

        snap = snapshot_history[-1]
        bar = bar_history[-1]

        gex_zscore = _safe_float(snap.get("net_gex_zscore_60d"))
        price_vs_sma = _safe_float(bar.get("price_vs_sma_21"))
        rel_vol = _safe_float(bar.get("relative_volume"))

        # Exit logic: close existing positions on regime shift
        if position.is_open and position.side == "CALL" and position.direction == "LONG":
            if gex_zscore > self.gex_zscore_exit_call_thresh:
                return Action.SELL_CALL

        if position.is_open and position.side == "PUT" and position.direction == "LONG":
            if gex_zscore < self.gex_zscore_exit_put_thresh:
                return Action.SELL_PUT

        # Entry logic: only if flat
        if not position.is_open:
            if (
                gex_zscore < self.gex_zscore_buy_call_thresh
                and price_vs_sma > 0.0
                and rel_vol > self.rel_vol_thresh
            ):
                return Action.BUY_CALL

            if (
                gex_zscore > self.gex_zscore_buy_put_thresh
                and price_vs_sma < 0.0
                and rel_vol > self.rel_vol_thresh
            ):
                return Action.BUY_PUT

        return Action.HOLD


class MLEnrichedSignal(Signal):
    """ML-model-enriched signal that wraps a trained classifier.

    The model predicts 1 (bullish) or 0 (bearish) from a feature vector
    derived from the current bar/snapshot. A probability threshold gates
    trade entry to avoid low-confidence predictions.

    Args:
        model: Trained classifier with .predict() and .predict_proba() methods.
        scaler: Fitted feature scaler (e.g. StandardScaler).
        feature_names: Ordered list of feature column names.
        proba_threshold: Minimum predicted probability to act (default 0.55).
        scaler_required: Whether to apply scaler.transform before predict.
    """

    def __init__(
        self,
        model: Any,
        scaler: Any,
        feature_names: List[str],
        proba_threshold: float = 0.55,
        scaler_required: bool = True,
    ):
        self.model = model
        self.scaler = scaler
        self.feature_names = feature_names
        self.proba_threshold = proba_threshold
        self.scaler_required = scaler_required

    def evaluate(
        self,
        snapshot_history: List[Dict[str, Any]],
        bar_history: List[Dict[str, Any]],
        position: Position,
    ) -> Action:
        if not snapshot_history or not bar_history:
            return Action.HOLD

        snap = snapshot_history[-1]
        bar = bar_history[-1]

        # Build feature vector from current snapshot + bar
        features: List[float] = []
        for name in self.feature_names:
            val = snap.get(name)
            if val is None:
                val = bar.get(name)
            features.append(_safe_float(val))

        X = np.array(features, dtype=float).reshape(1, -1)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        if self.scaler_required:
            X = self.scaler.transform(X)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        proba = self.model.predict_proba(X)[0]
        pred = int(np.argmax(proba))
        confidence = float(proba[pred])

        if confidence < self.proba_threshold:
            return Action.HOLD

        # Exit existing positions on opposite signal
        if position.is_open and position.side == "CALL" and position.direction == "LONG":
            if pred == 0:
                return Action.SELL_CALL

        if position.is_open and position.side == "PUT" and position.direction == "LONG":
            if pred == 1:
                return Action.SELL_PUT

        # Entry logic
        if not position.is_open:
            if pred == 1:
                return Action.BUY_CALL
            else:
                return Action.BUY_PUT

        return Action.HOLD


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default
