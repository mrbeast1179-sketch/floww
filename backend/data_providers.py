"""
Free Data Source Integrations for Confluence Decoder

Aggregates data from multiple free APIs:
- Finnhub (60 calls/min free): real-time quotes, earnings, news
- Alpha Vantage (5 calls/min, 500/day free): technical indicators, forex
- Polygon.io (5 calls/min free): real-time options data
- Yahoo Finance via yfinance (unlimited): options chains, historical

Falls back gracefully when rate limits hit.
"""

import os
import json
import time
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

# API Keys from environment
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY", "")


class RateLimiter:
    """Simple rate limiter for API calls."""
    def __init__(self, calls_per_minute: int):
        self.interval = 60.0 / calls_per_minute
        self.last_call = 0
    
    async def wait(self):
        now = time.time()
        elapsed = now - self.last_call
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self.last_call = time.time()


class FreeDataProvider:
    """Base class for free data providers."""
    
    def __init__(self, name: str, rate_limit: int = 60):
        self.name = name
        self.rate_limiter = RateLimiter(rate_limit)
        self.enabled = False
    
    async def _get(self, url: str, params: dict = None) -> Optional[dict]:
        await self.rate_limiter.wait()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        logger.warning(f"{self.name}: Rate limited")
                        return None
                    else:
                        logger.warning(f"{self.name}: HTTP {resp.status}")
                        return None
        except Exception as e:
            logger.warning(f"{self.name}: {e}")
            return None


class FinnhubProvider(FreeDataProvider):
    """Finnhub free tier: 60 calls/min."""
    
    def __init__(self):
        super().__init__("Finnhub", rate_limit=60)
        self.enabled = bool(FINNHUB_API_KEY)
        self.base = "https://finnhub.io/api/v1"
    
    async def get_quote(self, ticker: str) -> Optional[dict]:
        """Get real-time quote."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/quote", {
            "symbol": ticker,
            "token": FINNHUB_API_KEY,
        })
        if data and data.get("c", 0) > 0:
            return {
                "price": data["c"],
                "open": data.get("o", 0),
                "high": data.get("h", 0),
                "low": data.get("l", 0),
                "prev_close": data.get("pc", 0),
                "change": data["c"] - data.get("pc", 0),
                "change_pct": round((data["c"] - data.get("pc", 0)) / data.get("pc", 0) * 100, 2) if data.get("pc", 0) > 0 else 0,
                "source": "finnhub",
            }
        return None
    
    async def get_news(self, ticker: Optional[str] = None, count: int = 10) -> List[dict]:
        """Get market news or company news."""
        if not self.enabled:
            return []
        
        if ticker:
            data = await self._get(f"{self.base}/company-news", {
                "symbol": ticker,
                "from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
                "to": datetime.now().strftime("%Y-%m-%d"),
                "token": FINNHUB_API_KEY,
            })
        else:
            data = await self._get(f"{self.base}/news", {
                "category": "general",
                "token": FINNHUB_API_KEY,
            })
        
        if data and isinstance(data, list):
            return [{
                "headline": item.get("headline", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "timestamp": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else "",
                "summary": item.get("summary", "")[:200],
                "ticker": ticker or "",
            } for item in data[:count]]
        return []
    
    async def get_earnings(self, ticker: str) -> List[dict]:
        """Get earnings calendar."""
        if not self.enabled:
            return []
        data = await self._get(f"{self.base}/calendar/earnings", {
            "symbol": ticker,
            "token": FINNHUB_API_KEY,
        })
        if data and isinstance(data, list):
            return [{
                "date": item.get("date", ""),
                "eps_estimate": item.get("epsEstimate"),
                "revenue_estimate": item.get("revenueEstimate"),
                "hour": item.get("hour", ""),
            } for item in data[:4]]
        return []

    async def get_recommendation(self, ticker: str) -> Optional[dict]:
        """Get analyst recommendations."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/stock/recommendation", {
            "symbol": ticker,
            "token": FINNHUB_API_KEY,
        })
        if data and isinstance(data, list) and len(data) > 0:
            latest = data[0]
            return {
                "strong_buy": latest.get("strongBuy", 0),
                "buy": latest.get("buy", 0),
                "hold": latest.get("hold", 0),
                "sell": latest.get("sell", 0),
                "strong_sell": latest.get("strongSell", 0),
                "period": latest.get("period", ""),
                "source": "finnhub",
            }
        return None
    
    async def get_options_flow(self, ticker: str) -> Optional[dict]:
        """Get options flow data (if available on free tier)."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/stock/option-chain", {
            "symbol": ticker,
            "token": FINNHUB_API_KEY,
        })
        if data and data.get("data"):
            return {
                "expirations": [d.get("expirationDate") for d in data["data"][:4]],
                "source": "finnhub",
            }
        return None


class AlphaVantageProvider(FreeDataProvider):
    """Alpha Vantage free tier: 5 calls/min, 500/day."""
    
    def __init__(self):
        super().__init__("AlphaVantage", rate_limit=5)
        self.enabled = bool(ALPHA_VANTAGE_KEY)
        self.base = "https://www.alphavantage.co/query"
    
    async def get_technical_indicator(self, ticker: str, indicator: str = "RSI", period: int = 14) -> Optional[dict]:
        """Get technical indicator (RSI, MACD, SMA, EMA, etc.)."""
        if not self.enabled:
            return None
        
        function_map = {
            "RSI": "RSI",
            "MACD": "MACD",
            "SMA": "SMA",
            "EMA": "EMA",
            "BBANDS": "BBANDS",
            "STOCH": "STOCH",
            "ADX": "ADX",
            "ATR": "ATR",
        }
        
        function = function_map.get(indicator, indicator)
        params = {
            "function": function,
            "symbol": ticker,
            "interval": "daily",
            "time_period": period,
            "series_type": "close",
            "apikey": ALPHA_VANTAGE_KEY,
        }
        
        data = await self._get(self.base, params)
        if data and "Error Message" not in data:
            # Get latest value
            tech_key = f"Technical Analysis: {function}"
            if tech_key in data:
                latest_date = sorted(data[tech_key].keys())[-1]
                values = data[tech_key][latest_date]
                return {
                    "indicator": indicator,
                    "date": latest_date,
                    "values": values,
                    "source": "alphavantage",
                }
        return None
    
    async def get_forex_rate(self, from_cur: str = "USD", to_cur: str = "EUR") -> Optional[float]:
        """Get forex rate."""
        if not self.enabled:
            return None
        data = await self._get(self.base, {
            "function": "CURRENCY_EXCHANGE_RATE",
            "from_currency": from_cur,
            "to_currency": to_cur,
            "apikey": ALPHA_VANTAGE_KEY,
        })
        if data and "Realtime Currency Exchange Rate" in data:
            rate = data["Realtime Currency Exchange Rate"].get("5. Exchange Rate")
            return float(rate) if rate else None
        return None


class PolygonProvider(FreeDataProvider):
    """Polygon.io free tier: 5 calls/min."""
    
    def __init__(self):
        super().__init__("Polygon", rate_limit=5)
        self.enabled = bool(POLYGON_API_KEY)
        self.base = "https://api.polygon.io"
    
    async def get_ticker_details(self, ticker: str) -> Optional[dict]:
        """Get ticker details."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/v3/reference/tickers/{ticker}", {
            "apiKey": POLYGON_API_KEY,
        })
        if data and data.get("results"):
            r = data["results"]
            return {
                "name": r.get("name", ""),
                "market": r.get("market", ""),
                "locale": r.get("locale", ""),
                "active": r.get("active", True),
                "source": "polygon",
            }
        return None
    
    async def get_options_contracts(self, ticker: str, limit: int = 20) -> List[dict]:
        """Get options contracts for a ticker."""
        if not self.enabled:
            return []
        data = await self._get(f"{self.base}/v3/reference/options/contracts", {
            "underlying_ticker": ticker,
            "limit": limit,
            "apiKey": POLYGON_API_KEY,
        })
        if data and data.get("results"):
            return [{
                "ticker": c.get("ticker", ""),
                "strike": c.get("strike_price", 0),
                "expiry": c.get("expiration_date", ""),
                "type": c.get("contract_type", ""),
                "exercise": c.get("exercise_style", ""),
            } for c in data["results"]]
        return []
    
    async def get_last_trade(self, ticker: str) -> Optional[dict]:
        """Get last trade."""
        if not self.enabled:
            return None
        data = await self._get(f"{self.base}/v2/last/trade/{ticker}", {
            "apiKey": POLYGON_API_KEY,
        })
        if data and data.get("results"):
            r = data["results"]
            return {
                "price": r.get("p", 0),
                "size": r.get("s", 0),
                "timestamp": r.get("t", 0),
                "source": "polygon",
            }
        return None


class DataAggregator:
    """
    Aggregates data from all free providers with fallback.
    Priority: Finnhub -> Polygon -> Alpha Vantage -> yfinance
    """
    
    def __init__(self):
        self.finnhub = FinnhubProvider()
        self.polygon = PolygonProvider()
        self.alphavantage = AlphaVantageProvider()
    
    async def get_spot_price(self, ticker: str) -> Optional[dict]:
        """Get spot price from best available source."""
        # Try Finnhub first (fastest, highest rate limit)
        quote = await self.finnhub.get_quote(ticker)
        if quote:
            return quote
        
        # Try Polygon
        trade = await self.polygon.get_last_trade(ticker)
        if trade:
            return {
                "price": trade["price"],
                "source": "polygon",
            }
        
        # Fallback to yfinance
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.fast_info
            return {
                "price": info.last_price,
                "prev_close": info.previous_close,
                "source": "yfinance",
            }
        except:
            return None
    
    async def get_full_quote(self, ticker: str) -> dict:
        """Get comprehensive quote data from all sources."""
        result = {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "spot": None,
            "news": [],
            "earnings": [],
            "recommendation": None,
            "technicals": {},
            "options_contracts": [],
        }
        
        # Spot price
        result["spot"] = await self.get_spot_price(ticker)
        
        # News (Finnhub)
        result["news"] = await self.finnhub.get_news(ticker, count=5)
        
        # Earnings
        result["earnings"] = await self.finnhub.get_earnings(ticker)
        
        # Analyst recommendation
        result["recommendation"] = await self.finnhub.get_recommendation(ticker)
        
        # Technical indicators (Alpha Vantage - rate limited)
        rsi = await self.alphavantage.get_technical_indicator(ticker, "RSI")
        if rsi:
            result["technicals"]["rsi"] = rsi
        
        # Options contracts (Polygon)
        result["options_contracts"] = await self.polygon.get_options_contracts(ticker, limit=10)
        
        return result
    
    def get_status(self) -> dict:
        """Get status of all data providers."""
        return {
            "finnhub": {"enabled": self.finnhub.enabled, "rate_limit": "60/min"},
            "polygon": {"enabled": self.polygon.enabled, "rate_limit": "5/min"},
            "alphavantage": {"enabled": self.alphavantage.enabled, "rate_limit": "5/min, 500/day"},
            "yfinance": {"enabled": True, "rate_limit": "unlimited (unofficial)"},
        }
