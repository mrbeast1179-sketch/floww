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

__all__ = [
    "market_data_router",
    "analytics_router",
    "portfolio_router",
    "paper_trading_router",
    "briefing_router",
    "admin_router",
]
