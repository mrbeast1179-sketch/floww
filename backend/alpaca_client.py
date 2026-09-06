"""
Alpaca Trading API Integration for Confluence Decoder

Free paper trading API — no minimum deposit.
Provides: account info, positions, order placement, market data.

Setup:
1. Sign up at https://alpaca.markets/ (free)
2. Get API key + secret from https://app.alpaca.markets/paper/dashboard/overview
3. Set env vars: ALPACA_API_KEY, ALPACA_SECRET_KEY
"""

import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading
ALPACA_DATA_URL = "https://data.alpaca.markets"


class AlpacaClient:
    """Alpaca paper trading client."""

    def __init__(self):
        self._load_keys()
        # Last HTTP outcome (status + short detail). _get/_post/_delete
        # still return None on failure (backward compat) — callers read
        # last_failure() for the honest reason (403 = no options approval,
        # 401 = bad keys, None = keys missing/unreachable).
        self._last_status: int | None = None
        self._last_error: str = ""

    def _load_keys(self):
        """Load keys from environment at call time (not import time)."""
        self._api_key = os.environ.get("ALPACA_API_KEY", "")
        self._secret_key = os.environ.get("ALPACA_SECRET_KEY", "")

    @property
    def enabled(self):
        self._load_keys()
        return bool(self._api_key and self._secret_key)

    @property
    def headers(self):
        self._load_keys()
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._secret_key,
        }

    def last_failure(self) -> dict:
        """Honest last-error detail (never raises)."""
        return {"http_status": getattr(self, "_last_status", None),
                "detail": getattr(self, "_last_error", "")}

    async def _get(self, url: str, params: dict = None) -> Any | None:
        if not self.enabled:
            self._last_status = None
            self._last_error = "alpaca keys not configured"
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params or {},
                                       timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        self._last_status = 200
                        self._last_error = ""
                        return await resp.json()
                    else:
                        text = await resp.text()
                        self._last_status = resp.status
                        self._last_error = text[:200]
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            self._last_status = None
            self._last_error = str(e)[:200]
            logger.warning(f"Alpaca API error: {e}")
            return None

    async def _post(self, url: str, data: dict = None) -> Any | None:
        if not self.enabled:
            self._last_status = None
            self._last_error = "alpaca keys not configured"
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, json=data or {},
                                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status in (200, 201):
                        self._last_status = resp.status
                        self._last_error = ""
                        return await resp.json()
                    elif resp.status == 207:
                        # Partial success — some orders filled, some failed
                        result = await resp.json()
                        self._last_status = 207
                        self._last_error = "partial success"
                        logger.warning(f"Alpaca partial success (207): {result}")
                        return result
                    else:
                        text = await resp.text()
                        self._last_status = resp.status
                        self._last_error = text[:200]
                        logger.warning(f"Alpaca API error {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            self._last_status = None
            self._last_error = str(e)[:200]
            logger.warning(f"Alpaca API error: {e}")
            return None

    async def _delete(self, url: str) -> Any | None:
        if not self.enabled:
            return None
        try:
            async with aiohttp.ClientSession() as session, session.delete(url, headers=self.headers,
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

    async def get_order(self, order_id: str) -> dict | None:
        """Fetch one paper order by venue ID (fill reconciliation read)."""
        if not order_id:
            return None
        data = await self._get(f"{ALPACA_BASE_URL}/v2/orders/{order_id}")
        return data if isinstance(data, dict) else None

    async def place_stock_order(self, symbol: str, qty: int, side: str = "buy",
                                 order_type: str = "market", limit_price: float = 0) -> dict | None:
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

    async def close_position(self, symbol: str) -> dict | None:
        """Close a position."""
        data = await self._delete(f"{ALPACA_BASE_URL}/v2/positions/{symbol.upper()}")
        if data:
            return {"message": f"Position {symbol} closed", "source": "alpaca"}
        return None

    async def get_positions(self) -> list[dict] | None:
        """List open paper positions (each with symbol + qty strings)."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/positions")
        return data if isinstance(data, list) else None

    async def get_account(self) -> dict | None:
        """Paper account (equity, buying power, day P&L fields)."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/account")
        return data if isinstance(data, dict) else None

    async def get_orders(self, status: str = "open", limit: int = 50) -> list[dict] | None:
        """Orders by status (open/closed/all)."""
        try:
            lim = max(1, min(int(limit), 500))
        except (TypeError, ValueError):
            lim = 50
        data = await self._get(f"{ALPACA_BASE_URL}/v2/orders",
                               params={"status": status, "limit": lim, "direction": "desc"})
        return data if isinstance(data, list) else None

    async def get_clock(self) -> dict | None:
        """Market clock (is_open, next open/close)."""
        data = await self._get(f"{ALPACA_BASE_URL}/v2/clock")
        return data if isinstance(data, dict) else None

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open paper order. True when the venue confirms."""
        if not order_id:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                        f"{ALPACA_BASE_URL}/v2/orders/{order_id}",
                        headers=self.headers,
                        timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status in (200, 204)
        except Exception as e:
            logger.warning("Alpaca cancel error: %s", e)
            return False

    async def get_bars(self, ticker: str, timeframe: str = "1Day", limit: int = 100) -> list[dict] | None:
        """Stock bars from Alpaca data (paper keys work for data)."""
        try:
            lim = max(1, min(int(limit), 10000))
        except (TypeError, ValueError):
            lim = 100
        data = await self._get(f"{ALPACA_DATA_URL}/v2/stocks/{ticker.upper()}/bars",
                               params={"timeframe": timeframe, "limit": lim,
                                       "adjustment": "raw", "feed": "iex"})
        if isinstance(data, dict) and isinstance(data.get("bars"), list):
            return data["bars"]
        return None

    @staticmethod
    def normalize_option_symbol(symbol: str) -> str:
        """Normalize an option OCC symbol for Alpaca (no spaces, uppercase).

        Alpaca expects OCC symbology, e.g. SPY260918C00760000. Public OSI
        symbols already match; this strips whitespace/dashes defensively.
        Returns "" when the symbol does not look like an OCC contract.
        """
        import re

        s = re.sub(r"[\s\-]", "", str(symbol or "").upper())
        if not re.fullmatch(r"[A-Z]{1,6}\d{6}[CP]\d{8}", s):
            return ""
        return s

    async def place_option_order(self, symbol: str, qty: int, side: str = "buy",
                                 order_type: str = "limit", limit_price: float = 0,
                                 time_in_force: str = "day") -> dict | None:
        """Place an option order on Alpaca PAPER. None on failure.

        Requires options approval on the paper account — otherwise Alpaca
        rejects with 403 and the error surfaces honestly (never silent).
        """
        osi = self.normalize_option_symbol(symbol)
        if not osi:
            logger.warning("Alpaca option order refused: bad OCC symbol %r", symbol)
            return None
        try:
            qty_i = int(qty)
        except (TypeError, ValueError):
            return None
        if qty_i <= 0:
            return None
        otype = str(order_type or "limit").lower()
        if otype not in ("limit", "market", "stop", "stop_limit"):
            return None
        order_data: dict[str, Any] = {
            "symbol": osi,
            "qty": str(qty_i),
            "side": side.lower(),
            "type": otype,
            "time_in_force": time_in_force,
        }
        if otype in ("limit", "stop_limit"):
            try:
                order_data["limit_price"] = str(float(limit_price))
            except (TypeError, ValueError):
                return None
        if otype in ("stop", "stop_limit"):
            try:
                order_data["stop_price"] = str(float(limit_price))
            except (TypeError, ValueError):
                return None
        data = await self._post(f"{ALPACA_BASE_URL}/v2/orders", order_data)
        if data:
            return {
                "id": data.get("id", ""),
                "status": data.get("status", ""),
                "symbol": data.get("symbol", osi),
                "side": data.get("side", side),
                "qty": data.get("qty", str(qty_i)),
                "type": data.get("type", otype),
                "message": f"Order {data.get('status', 'unknown')}",
                "source": "alpaca",
            }
        return None

    async def place_bracket_order(self, symbol: str, qty: int, side: str = "buy",
                                  take_profit_price: float | None = None,
                                  stop_loss_price: float | None = None,
                                  time_in_force: str = "gtc") -> dict | None:
        """Bracket stock order on PAPER: market entry + TP limit + stop legs.

        Alpaca prices bracket legs absolutely, so callers pass ABSOLUTE
        prices (the bot derives them from the live quote ± pct). Omit a leg
        with None. GTC by default so the TP/SL survive past today. None on
        failure (e.g. account without options/short permission → 403,
        surfaced by the caller's error path, never silent).
        """
        try:
            qty_i = int(qty)
        except (TypeError, ValueError):
            return None
        if qty_i <= 0 or side.lower() not in ("buy", "sell"):
            return None
        order_data: dict[str, Any] = {
            "symbol": symbol.upper(),
            "qty": str(qty_i),
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
        }
        if take_profit_price is not None:
            try:
                order_data["take_profit"] = {"limit_price": str(float(take_profit_price))}
            except (TypeError, ValueError):
                return None
        if stop_loss_price is not None:
            try:
                order_data["stop_loss"] = {"stop_price": str(float(stop_loss_price))}
            except (TypeError, ValueError):
                return None
        if "take_profit" not in order_data and "stop_loss" not in order_data:
            return None  # a bracket with no legs is just a market order
        order_data["time_in_force"] = time_in_force
        data = await self._post(f"{ALPACA_BASE_URL}/v2/orders", order_data)
        if data:
            return {
                "id": data.get("id", ""),
                "status": data.get("status", ""),
                "symbol": data.get("symbol", symbol.upper()),
                "legs": data.get("legs", []),
                "message": f"Bracket {data.get('status', 'unknown')}",
                "source": "alpaca",
            }
        return None
