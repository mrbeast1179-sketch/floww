"""
Alpaca Trading API Integration for Confluence Decoder

Free paper trading API — no minimum deposit.
Provides: account info, positions, order placement, market data.

Setup:
1. Sign up at https://alpaca.markets/ (free)
2. Get API key + secret from https://app.alpaca.markets/paper/dashboard/overview
3. Set env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

import aiohttp

logger = logging.getLogger(__name__)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading
ALPACA_DATA_URL = "https://data.alpaca.markets"


class AlpacaClient:
    """Alpaca paper trading client."""
    
    def __init__(self):
        self.enabled = bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)
        self.headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        }
    
    async def _get(self, url: str, params: dict = None) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params or {},
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None
    
    async def _post(self, url: str, data: dict = None) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data or {},
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 201, 207):
                        return await resp.json()
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None
    
    async def _delete(self, url: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=self.headers,
                                          timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 204):
                        return True
                    else:
                        text = await resp.text()
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"Alpaca API error: {e}")
            return None
    
    async def get_account(self) -> Optional[dict]:
        """Get account information."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/account")
        if data:
            return {
                "id": data.get("id", ""),
                "status": data.get("status", ""),
                "buying_power": float(data.get("buying_power", 0)),
                "portfolio_value": float(data.get("portfolio_value", 0)),
                "equity": float(data.get("equity", 0)),
                "cash": float(data.get("cash", 0)),
                "pattern_day_trader": data.get("pattern_day_trader", False),
                "daytrade_count": data.get("daytrade_count", 0),
                "options_trading_level": data.get("options_trading_level", 0),
                "source": "alpaca",
            }
        return None
    
    async def get_positions(self) -> List[dict]:
        """Get all open positions."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/positions")
        if data and isinstance(data, list):
            return [{
                "symbol": p.get("symbol", ""),
                "qty": int(p.get("qty", 0)),
                "side": p.get("side", ""),
                "avg_entry_price": float(p.get("avg_entry_price", 0)),
                "current_price": float(p.get("current_price", 0)),
                "market_value": float(p.get("market_value", 0)),
                "unrealized_pl": float(p.get("unrealized_pl", 0)),
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)) * 100,
                "change_today": float(p.get("change_today", 0)) * 100,
                "source": "alpaca",
            } for p in data]
        return []
    
    async def get_orders(self, status: str = "open", limit: int = 50) -> List[dict]:
        """Get orders."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/orders", {
            "status": status,
            "limit": limit,
        })
        if data and isinstance(data, list):
            return [{
                "id": o.get("id", ""),
                "symbol": o.get("symbol", ""),
                "side": o.get("side", ""),
                "type": o.get("type", ""),
                "qty": o.get("qty", ""),
                "filled_qty": o.get("filled_qty", ""),
                "filled_avg_price": o.get("filled_avg_price", ""),
                "status": o.get("status", ""),
                "created_at": o.get("created_at", ""),
                "source": "alpaca",
            } for o in data]
        return []
    
    async def place_stock_order(self, symbol: str, qty: int, side: str = "buy",
                                 order_type: str = "market", limit_price: float = 0) -> Optional[dict]:
        """Place a stock order."""
        order_data = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": "day",
        }
        if order_type == "limit" and limit_price:
            order_data["limit_price"] = str(limit_price)
        
        data = await self._post(f"{ALPACA_BASE_URL}/v2/orders", order_data)
        if data:
            return {
                "id": data.get("id", ""),
                "status": data.get("status", ""),
                "symbol": data.get("symbol", ""),
                "side": data.get("side", ""),
                "qty": data.get("qty", ""),
                "type": data.get("type", ""),
                "message": f"Order {data.get('status', 'unknown')}",
                "source": "alpaca",
            }
        return None
    
    async def close_position(self, symbol: str) -> Optional[dict]:
        """Close a position."""
        data = await self._delete(f"{ALPACA_BASE_URL}/v2/positions/{symbol.upper()}")
        if data:
            return {"message": f"Position {symbol} closed", "source": "alpaca"}
        return None
    
    async def close_all_positions(self) -> Optional[dict]:
        """Close all positions."""
        data = await self._delete(f"{ALPACA_BASE_URL}/v2/positions")
        if data:
            return {"message": "All positions closed", "source": "alpaca"}
        return None
    
    async def get_options_contracts(self, symbol: str, limit: int = 20) -> List[dict]:
        """Get options contracts."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/options/contracts", {
            "underlying_symbols": symbol.upper(),
            "limit": limit,
        })
        if data and isinstance(data, list):
            return [{
                "symbol": c.get("symbol", ""),
                "underlying": c.get("underlying_symbol", ""),
                "strike": float(c.get("strike_price", 0)),
                "expiry": c.get("expiration_date", ""),
                "type": c.get("contract_type", ""),
                "style": c.get("exercise_style", ""),
            } for c in data]
        return []
    
    async def get_clock(self) -> Optional[dict]:
        """Get market clock."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/clock")
        if data:
            return {
                "is_open": data.get("is_open", False),
                "next_open": data.get("next_open", ""),
                "next_close": data.get("next_close", ""),
                "timestamp": data.get("timestamp", ""),
                "source": "alpaca",
            }
        return None
    
    async def get_bars(self, symbol: str, timeframe: str = "1Day", limit: int = 100) -> List[dict]:
        """Get price bars."""
        data = await self._get(f"{ALPACA_DATA_URL}/v2/stocks/{symbol.upper()}/bars", {
            "timeframe": timeframe,
            "limit": limit,
        })
        if data and data.get("bars"):
            return [{
                "timestamp": b.get("t", ""),
                "open": b.get("o", 0),
                "high": b.get("h", 0),
                "low": b.get("l", 0),
                "close": b.get("c", 0),
                "volume": b.get("v", 0),
                "source": "alpaca",
            } for b in data["bars"]]
        return []
