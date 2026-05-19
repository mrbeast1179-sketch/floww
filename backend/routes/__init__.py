"""
backend/routes/__init__.py

Route module exports.
"""
from .market_data import router as market_data_router
from .analytics import router as analytics_router
from .portfolio import router as portfolio_router
from .paper_trading import router as paper_trading_router
from .briefing import router as briefing_router
from .admin import router as admin_router
from .ml_training import router as ml_training_router
from .llm import router as llm_router
from .schwab import router as schwab_router
from .live_trading import router as live_trading_router
from .memory import router as memory_router

__all__ = [
    "market_data_router",
    "analytics_router",
    "portfolio_router",
    "paper_trading_router",
    "briefing_router",
    "admin_router",
    "ml_training_router",
    "llm_router",
    "schwab_router",
    "live_trading_router",
    "memory_router",
]
