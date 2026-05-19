"""
backend/services/backtest/__init__.py

Backtest engine for the Confluence Decoder trading system.
"""

from .engine import BacktestEngine, EngineConfig, run_is_oos_split, run_walk_forward_cv, run_monte_carlo_bootstrap
from .signals import Action, Position, Signal, RuleBasedSignal, MLEnrichedSignal
from .report import BacktestResult, TradeRecord

__all__ = [
    "BacktestEngine",
    "EngineConfig",
    "Action",
    "Position",
    "Signal",
    "RuleBasedSignal",
    "MLEnrichedSignal",
    "BacktestResult",
    "TradeRecord",
    "run_is_oos_split",
    "run_walk_forward_cv",
    "run_monte_carlo_bootstrap",
]
