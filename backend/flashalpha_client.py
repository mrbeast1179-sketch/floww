"""
FlashAlpha API Integration for Confluence Decoder

FlashAlpha has 81 endpoints covering:
- Exposure: GEX, DEX, VEX, CHEX, levels, narrative, zero-dte
- Flow: live flow, blocks, sweeps, outliers, leaderboards, pin risk
- Earnings: VRP, expected move, IV crush, dealer positioning, strategies
- Screener: full options screener with 13 endpoints
- Historical: EOD options, OI, quotes
- Pricing: Greeks, IV, Kelly criterion
- Max Pain, Volatility, Stock quotes

Free tier: stock_summary returns previous-day cached snapshot without a key.
Paid tiers unlock real-time data, flow, and advanced endpoints.

API docs: https://lab.flashalpha.com/swagger
Sign up: https://flashalpha.com
"""

import os
import logging
from typing import Dict, Optional, Any
from datetime import datetime

import aiohttp

logger = logging.getLogger(__name__)

FLASHALPHA_API_KEY = os.environ.get("FLASHALPHA_API_KEY", "")
FLASHALPHA_BASE_URL = "https://lab.flashalpha.com"


class FlashAlphaClient:
    """Client for the FlashAlpha options analytics API."""
    
    def __init__(self):
        self.base_url = FLASHALPHA_BASE_URL
    
    @property
    def enabled(self):
        return bool(os.environ.get("FLASHALPHA_API_KEY", ""))
    
    @property
    def _headers(self):
        key = os.environ.get("FLASHALPHA_API_KEY", "")
        return {"X-Api-Key": key, "Content-Type": "application/json"} if key else {}
    
    async def _get(self, path: str, params: dict = None) -> Optional[dict]:
        if not self.enabled:
            return None
        url = f"{self.base_url}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers, params=params or {},
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:
                        logger.warning("FlashAlpha: Unauthorized. Check API key.")
                        return None
                    elif resp.status == 403:
                        logger.warning(f"FlashAlpha: Tier-restricted endpoint {path}")
                        return None
                    elif resp.status == 429:
                        logger.warning("FlashAlpha: Rate limited")
                        return None
                    else:
                        text = await resp.text()
                        logger.warning(f"FlashAlpha: HTTP {resp.status}: {text[:200]}")
                        return None
        except Exception as e:
            logger.warning(f"FlashAlpha error: {e}")
            return None
    
    # ── Exposure ─────────────────────────────────────────────────
    
    async def get_gex(self, symbol: str) -> Optional[dict]:
        """Get Gamma Exposure (GEX) data."""
        return await self._get(f"/v1/exposure/gex/{symbol}")
    
    async def get_dex(self, symbol: str) -> Optional[dict]:
        """Get Delta Exposure (DEX) data."""
        return await self._get(f"/v1/exposure/dex/{symbol}")
    
    async def get_vex(self, symbol: str) -> Optional[dict]:
        """Get Vanna Exposure (VEX) data."""
        return await self._get(f"/v1/exposure/vex/{symbol}")
    
    async def get_chex(self, symbol: str) -> Optional[dict]:
        """Get Charm Exposure (CHEX) data."""
        return await self._get(f"/v1/exposure/chex/{symbol}")
    
    async def get_exposure_summary(self, symbol: str) -> Optional[dict]:
        """Get exposure summary (GEX + DEX + VEX + CHEX combined)."""
        return await self._get(f"/v1/exposure/summary/{symbol}")
    
    async def get_exposure_levels(self, symbol: str) -> Optional[dict]:
        """Get exposure levels (call wall, put wall, gamma flip, etc.)."""
        return await self._get(f"/v1/exposure/levels/{symbol}")
    
    async def get_exposure_narrative(self, symbol: str) -> Optional[dict]:
        """Get AI-generated narrative summary of exposure."""
        return await self._get(f"/v1/exposure/narrative/{symbol}")
    
    async def get_zero_dte(self, symbol: str) -> Optional[dict]:
        """Get 0DTE (same-day expiration) exposure data."""
        return await self._get(f"/v1/exposure/zero-dte/{symbol}")
    
    async def get_exposure_history(self, symbol: str) -> Optional[dict]:
        """Get historical exposure data."""
        return await self._get(f"/v1/exposure/history/{symbol}")
    
    # ── Flow ─────────────────────────────────────────────────────
    
    async def get_flow_live(self, symbol: str) -> Optional[dict]:
        """Get live options flow."""
        return await self._get(f"/v1/flow/live/{symbol}")
    
    async def get_flow_summary(self, symbol: str) -> Optional[dict]:
        """Get flow summary."""
        return await self._get(f"/v1/flow/summary/{symbol}")
    
    async def get_flow_gex(self, symbol: str) -> Optional[dict]:
        """Get flow GEX data."""
        return await self._get(f"/v1/flow/gex/{symbol}")
    
    async def get_flow_dex(self, symbol: str) -> Optional[dict]:
        """Get flow DEX data."""
        return await self._get(f"/v1/flow/dex/{symbol}")
    
    async def get_flow_levels(self, symbol: str) -> Optional[dict]:
        """Get flow levels."""
        return await self._get(f"/v1/flow/levels/{symbol}")
    
    async def get_flow_oi(self, symbol: str) -> Optional[dict]:
        """Get flow open interest."""
        return await self._get(f"/v1/flow/oi/{symbol}")
    
    async def get_flow_dealer_risk(self, symbol: str) -> Optional[dict]:
        """Get dealer risk flow data."""
        return await self._get(f"/v1/flow/dealer-risk/{symbol}")
    
    async def get_flow_pin_risk(self, symbol: str) -> Optional[dict]:
        """Get pin risk flow data."""
        return await self._get(f"/v1/flow/pin-risk/{symbol}")
    
    async def get_options_flow_recent(self, symbol: str) -> Optional[dict]:
        """Get recent options flow."""
        return await self._get(f"/v1/flow/options/{symbol}/recent")
    
    async def get_options_flow_summary(self, symbol: str) -> Optional[dict]:
        """Get options flow summary."""
        return await self._get(f"/v1/flow/options/{symbol}/summary")
    
    async def get_options_flow_blocks(self, symbol: str) -> Optional[dict]:
        """Get options flow blocks (large trades)."""
        return await self._get(f"/v1/flow/options/{symbol}/blocks")
    
    async def get_options_flow_cumulative(self, symbol: str) -> Optional[dict]:
        """Get cumulative options flow."""
        return await self._get(f"/v1/flow/options/{symbol}/cumulative")
    
    async def get_options_flow_history(self, symbol: str) -> Optional[dict]:
        """Get historical options flow."""
        return await self._get(f"/v1/flow/options/{symbol}/history")
    
    async def get_options_flow_outliers(self) -> Optional[dict]:
        """Get options flow outliers across all tickers."""
        return await self._get("/v1/flow/options/outliers")
    
    async def get_options_flow_leaderboard(self) -> Optional[dict]:
        """Get options flow leaderboard."""
        return await self._get("/v1/flow/options/leaderboard")
    
    async def get_stocks_flow_recent(self, symbol: str) -> Optional[dict]:
        """Get recent stock flow."""
        return await self._get(f"/v1/flow/stocks/{symbol}/recent")
    
    async def get_stocks_flow_summary(self, symbol: str) -> Optional[dict]:
        """Get stock flow summary."""
        return await self._get(f"/v1/flow/stocks/{symbol}/summary")
    
    async def get_stocks_flow_blocks(self, symbol: str) -> Optional[dict]:
        """Get stock flow blocks."""
        return await self._get(f"/v1/flow/stocks/{symbol}/blocks")
    
    async def get_stocks_flow_outliers(self) -> Optional[dict]:
        """Get stock flow outliers across all tickers."""
        return await self._get("/v1/flow/stocks/outliers")
    
    async def get_stocks_flow_leaderboard(self) -> Optional[dict]:
        """Get stock flow leaderboard."""
        return await self._get("/v1/flow/stocks/leaderboard")
    
    # ── Earnings ─────────────────────────────────────────────────
    
    async def get_earnings_vrp(self, symbol: str) -> Optional[dict]:
        """Get Variance Risk Premium (VRP) data."""
        return await self._get(f"/v1/earnings/vrp/{symbol}")
    
    async def get_earnings_expected_move(self, symbol: str) -> Optional[dict]:
        """Get expected move for earnings."""
        return await self._get(f"/v1/earnings/expected-move/{symbol}")
    
    async def get_earnings_history(self, symbol: str) -> Optional[dict]:
        """Get earnings history."""
        return await self._get(f"/v1/earnings/history/{symbol}")
    
    async def get_earnings_iv_crush(self, symbol: str) -> Optional[dict]:
        """Get IV crush data for earnings."""
        return await self._get(f"/v1/earnings/iv-crush/{symbol}")
    
    async def get_earnings_dealer_positioning(self, symbol: str) -> Optional[dict]:
        """Get dealer positioning for earnings."""
        return await self._get(f"/v1/earnings/dealer-positioning/{symbol}")
    
    async def get_earnings_strategies(self, symbol: str) -> Optional[dict]:
        """Get earnings strategies."""
        return await self._get(f"/v1/earnings/strategies/{symbol}")
    
    async def get_earnings_calendar(self) -> Optional[dict]:
        """Get earnings calendar."""
        return await self._get("/v1/earnings/calendar")
    
    async def get_earnings_screener(self) -> Optional[dict]:
        """Get earnings screener."""
        return await self._get("/v1/earnings/screener")
    
    # ── Screener ─────────────────────────────────────────────────
    
    async def get_screener_fields(self) -> Optional[dict]:
        """Get available screener fields."""
        return await self._get("/v1/screener/fields")
    
    async def screener_search(self, criteria: dict) -> Optional[dict]:
        """Search options using screener criteria."""
        if not self.enabled:
            return None
        url = f"{self.base_url}/v1/screener"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self._headers, json=criteria,
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception as e:
            logger.warning(f"FlashAlpha screener error: {e}")
            return None
    
    # ── Other ────────────────────────────────────────────────────
    
    async def get_stock_summary(self, symbol: str) -> Optional[dict]:
        """Get stock summary (free tier works without key for previous day)."""
        return await self._get(f"/v1/stock/{symbol}/summary")
    
    async def get_max_pain(self, symbol: str) -> Optional[dict]:
        """Get max pain data."""
        return await self._get(f"/v1/maxpain/{symbol}")
    
    async def get_volatility(self, symbol: str) -> Optional[dict]:
        """Get volatility data."""
        return await self._get(f"/v1/volatility/{symbol}")
    
    async def get_vrp(self, symbol: str) -> Optional[dict]:
        """Get Variance Risk Premium."""
        return await self._get(f"/v1/vrp/{symbol}")
    
    async def get_vrp_history(self, symbol: str) -> Optional[dict]:
        """Get VRP history."""
        return await self._get(f"/v1/vrp/{symbol}/history")
    
    async def get_symbols(self) -> Optional[dict]:
        """Get available symbols."""
        return await self._get("/v1/symbols")
    
    async def get_tickers(self) -> Optional[dict]:
        """Get available tickers."""
        return await self._get("/v1/tickers")
    
    async def get_account(self) -> Optional[dict]:
        """Get account info."""
        return await self._get("/v1/account")
    
    # ── Convenience: Full Dashboard ───────────────────────────────
    
    async def get_full_dashboard(self, symbol: str) -> Dict[str, Any]:
        """
        Get a full dashboard of data for a ticker.
        Combines multiple endpoints into one response.
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.utcnow().isoformat(),
            "exposure": None,
            "flow": None,
            "earnings": None,
            "max_pain": None,
            "volatility": None,
        }
        
        # Exposure summary (includes GEX, DEX, VEX, CHEX)
        result["exposure"] = await self.get_exposure_summary(symbol)
        
        # Flow summary
        result["flow"] = await self.get_flow_summary(symbol)
        
        # Earnings VRP
        result["earnings"] = await self.get_earnings_vrp(symbol)
        
        # Max pain
        result["max_pain"] = await self.get_max_pain(symbol)
        
        # Volatility
        result["volatility"] = await self.get_volatility(symbol)
        
        return result
