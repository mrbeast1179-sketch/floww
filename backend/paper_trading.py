"""
Paper Trading Automation for Confluence Decoder.

Uses Alpaca paper trading API to automatically place trades based on:
- GEX regime signals
- Alert triggers
- Strategy templates

All trades are placed in PAPER mode only.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Trading configuration
MAX_POSITION_SIZE = 1  # Max contracts per trade
DEFAULT_STRATEGY = "iron_condible"
ENABLED_SIGNALS = {"GAMMA_FLIP", "GAMMA_SQUEEZE", "WALL_BREACH"}


def get_alpaca_client():
    """Get the Alpaca trading client."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        if client.enabled:
            return client
    except Exception as e:
        logger.warning(f"Alpaca client not available: {e}")
    return None


def calculate_position_size(
    signal_type: str,
    account_equity: float,
    risk_pct: float = 0.02,
) -> int:
    """Calculate position size based on account equity and risk."""
    risk_amount = account_equity * risk_pct
    # For options, risk is typically the premium paid
    # Conservative: risk no more than 2% of equity per trade
    max_contracts = max(1, int(risk_amount / 100))  # Assume $100 per contract
    return min(max_contracts, MAX_POSITION_SIZE)


def build_order_from_signal(
    signal: Dict[str, Any],
    ticker: str,
    spot_price: float,
) -> Optional[Dict[str, Any]]:
    """Build an Alpaca order from a trading signal."""
    signal_type = signal.get("type", "")
    
    if signal_type == "GAMMA_FLIP":
        # Negative gamma → expect amplified moves
        # Sell iron condor to collect premium
        return {
            "strategy": "iron_condor",
            "ticker": ticker,
            "spot": spot_price,
            "message": f"Gamma flip detected: {signal.get('message', '')}",
        }
    
    elif signal_type == "GAMMA_SQUEEZE":
        # Gamma squeeze forming → directional play
        direction = signal.get("data", {}).get("direction", "neutral")
        if direction == "bullish":
            return {
                "strategy": "call_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Gamma squeeze (bullish): {signal.get('message', '')}",
            }
        elif direction == "bearish":
            return {
                "strategy": "put_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Gamma squeeze (bearish): {signal.get('message', '')}",
            }
    
    elif signal_type == "WALL_BREACH":
        # Spot broke through wall → momentum play
        direction = signal.get("data", {}).get("direction", "")
        if direction == "BULLISH":
            return {
                "strategy": "call_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Wall breach (bullish): {signal.get('message', '')}",
            }
        elif direction == "BEARISH":
            return {
                "strategy": "put_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Wall breach (bearish): {signal.get('message', '')}",
            }
    
    return None


async def execute_paper_trade(
    order: Dict[str, Any],
    qty: int = 1,
) -> Dict[str, Any]:
    """Execute a paper trade via Alpaca."""
    client = get_alpaca_client()
    if not client:
        return {"status": "error", "message": "Alpaca client not available"}
    
    try:
        strategy = order.get("strategy", "")
        ticker = order.get("ticker", "")
        
        # Get options chain for the ticker
        chain = await client.get_options_chain(ticker)
        if not chain:
            return {"status": "error", "message": f"No options chain for {ticker}"}
        
        # Build the order based on strategy
        if strategy == "iron_condor":
            result = await client.place_iron_condor(ticker, chain, qty)
        elif strategy == "call_spread":
            result = await client.place_call_spread(ticker, chain, qty)
        elif strategy == "put_spread":
            result = await client.place_put_spread(ticker, chain, qty)
        else:
            return {"status": "error", "message": f"Unknown strategy: {strategy}"}
        
        logger.info(f"Paper trade executed: {strategy} {ticker} x{qty}")
        return {
            "status": "executed",
            "strategy": strategy,
            "ticker": ticker,
            "qty": qty,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Paper trade failed: {e}")
        return {"status": "error", "message": str(e)}


async def process_signals_for_ticker(
    ticker: str,
    signals: List[Dict[str, Any]],
    auto_trade: bool = False,
) -> List[Dict[str, Any]]:
    """Process trading signals and optionally execute trades."""
    results = []
    
    for signal in signals:
        signal_type = signal.get("type", "")
        
        if signal_type not in ENABLED_SIGNALS:
            continue
        
        order = build_order_from_signal(signal, ticker, signal.get("spot", 0))
        if not order:
            continue
        
        result = {
            "signal": signal_type,
            "order": order,
            "executed": False,
        }
        
        if auto_trade:
            trade_result = await execute_paper_trade(order)
            result["trade"] = trade_result
            result["executed"] = trade_result.get("status") == "executed"
        
        results.append(result)
    
    return results