"""API routes for Alpaca paper trading."""

import logging
import re

from fastapi import APIRouter, Depends

from auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpaca", tags=["alpaca"])


@router.get("/account")
async def get_account(_: bool = Depends(require_api_key)):
    """Get Alpaca account info."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        account = await client.get_account()
        if account:
            return account
        return {"error": "Alpaca not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars."}
    except Exception as e:
        return {"error": str(e)}


@router.get("/positions")
async def get_positions(_: bool = Depends(require_api_key)):
    """Get all open positions."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        positions = await client.get_positions()
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        return {"error": str(e), "positions": []}


@router.get("/orders")
async def get_orders(status: str = "open", limit: int = 50, _: bool = Depends(require_api_key)):
    """Get orders."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        orders = await client.get_orders(status=status, limit=limit)
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        return {"error": str(e), "orders": []}


@router.get("/clock")
async def get_clock():
    """Get market clock."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        clock = await client.get_clock()
        if clock:
            return clock
        return {"error": "Alpaca not configured"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/bars/{ticker}")
async def get_bars(ticker: str, timeframe: str = "1Day", limit: int = 100):
    """Get price bars for a ticker."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        bars = await client.get_bars(ticker, timeframe=timeframe, limit=limit)
        return {"ticker": ticker.upper(), "bars": bars, "count": len(bars)}
    except Exception as e:
        return {"error": str(e), "bars": []}


@router.post("/order")
async def place_order(
    symbol: str,
    qty: int,
    side: str = "buy",
    order_type: str = "market",
    limit_price: float = 0,
):
    """Place a stock order (Alpaca paper). Successful fills are journaled
    as equity seeds (fail-open) so click-to-trade lands in position memory."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.place_stock_order(symbol, qty, side, order_type, limit_price)
        if result:
            _journal_equity_fill(symbol, qty, side, order_type, limit_price, result)
            return result
        return {"error": "Order failed. Check Alpaca credentials and parameters."}
    except Exception as e:
        return {"error": str(e)}


def _journal_equity_fill(symbol: str, qty: int, side: str,
                         order_type: str, limit_price: float, result: dict) -> None:
    """Journal a UI/API equity fill (fail-open, never breaks the trade)."""
    try:
        from datetime import UTC, datetime

        from services.journal_store import get_engine, init_journal_tables, save_seeds

        engine = get_engine()
        init_journal_tables(engine)
        save_seeds(engine, [{
            "ticker": symbol.upper(),
            "type": "equity",
            "action": side.lower(),
            # No strike on equity legs, but strike is PK-NOT-NULL: store 0.0
            # labeled as ref-px convention (see discord_ops approve path).
            "strike": 0.0,
            "expiry": "",
            "quantity": str(qty),
            "entry_price": None,
            "exit_price": "",
            "entry_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "exit_date": "",
            "notes": (f"API/UI {side} {qty} {symbol.upper()} "
                      f"{order_type} (Alpaca paper id={(result or {}).get('id', '')})"[:500]),
            "gex_regime": "",
            "setup": "manual equity",
            "tags": "alpaca,equity,ui-click",
            "source": "api-alpaca",
        }])
    except Exception as e:
        logger.warning("alpaca order journaling failed (non-fatal): %s", e)


@router.post("/order/option")
async def place_option_order(
    symbol: str,
    qty: int = 1,
    side: str = "buy",
    order_type: str = "limit",
    limit_price: float = 0,
):
    """Place an OPTION order on Alpaca PAPER (OCC symbol, e.g. SPY260904C00760000).

    Requires options approval on the paper account — Alpaca 403s otherwise
    and the error surfaces honestly. Successful fills journal as option
    seeds (fail-open) so click-to-trade lands in position memory.
    """
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.place_option_order(symbol, qty, side, order_type, limit_price)
        if result:
            _journal_option_fill(symbol, qty, side, result)
            return result
        return {"error": "Option order failed. Check Alpaca options approval, credentials, and symbol."}
    except Exception as e:
        return {"error": str(e)}


def _parse_occ(symbol: str) -> dict | None:
    """OCC symbol → {type, strike, expiry}. None when unparseable."""
    m = re.fullmatch(r"[A-Z]{1,6}(\d{6})([CP])(\d{8})", str(symbol or "").upper())
    if not m:
        return None
    try:
        exp = f"20{m.group(1)[:2]}-{m.group(1)[2:4]}-{m.group(1)[4:6]}"
        return {"type": "call" if m.group(2) == "C" else "put",
                "strike": int(m.group(3)) / 1000.0, "expiry": exp}
    except (TypeError, ValueError):
        return None


def _journal_option_fill(symbol: str, qty: int, side: str, result: dict) -> None:
    """Journal an option fill (fail-open, never breaks the trade)."""
    try:
        from datetime import UTC, datetime

        from services.journal_store import get_engine, init_journal_tables, save_seeds

        occ = _parse_occ(symbol) or {}
        engine = get_engine()
        init_journal_tables(engine)
        save_seeds(engine, [{
            "ticker": re.sub(r"\d{6}[CP]\d{8}$", "", str(symbol).upper()),
            "type": occ.get("type", "call"),
            "action": "buy" if side.lower() == "buy" else "sell",
            "strike": occ.get("strike"),
            "expiry": occ.get("expiry", ""),
            "quantity": str(qty),
            "entry_price": None,
            "exit_price": "",
            "entry_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "exit_date": "",
            "notes": (f"Click-to-trade {side} {qty} {symbol} "
                      f"(Alpaca paper id={(result or {}).get('id', '')})"[:500]),
            "gex_regime": "",
            "setup": "click-to-trade",
            "tags": "alpaca,option,ui-click",
            "source": "api-alpaca-option",
        }])
    except Exception as e:
        logger.warning("alpaca option journaling failed (non-fatal): %s", e)


@router.delete("/position/{symbol}")
async def close_position(symbol: str):
    """Close a position.

    On a confirmed venue close, open journal cards for the symbol get
    their exits stamped (fail-open) so !journal/!pnl review the full
    loop. The exit price is the latest venue bar close — never invented.
    """
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.close_position(symbol)
        if result:
            closed = await _journal_closeout(symbol, client)
            if closed:
                result["journal_closed"] = closed
            return result
        return {"error": "Failed to close position"}
    except Exception as e:
        return {"error": str(e)}


async def _journal_closeout(symbol: str, client) -> int:
    """Stamp exits on open journal cards for a closed symbol.

    Returns count closed, 0 when no reference price or nothing open.
    Fail-open: never raises into the close path.
    """
    try:
        from datetime import UTC, datetime

        from services.journal_store import close_open_by_symbol, get_engine, init_journal_tables

        bars = await client.get_bars(symbol, timeframe="1Day", limit=1)
        px = None
        if bars:
            try:
                px = float(bars[-1].get("c"))
            except (TypeError, ValueError, AttributeError):
                px = None
        if not px:
            logger.warning("alpaca close journaling skipped for %s: no reference price", symbol)
            return 0
        engine = get_engine()
        init_journal_tables(engine)
        return int(close_open_by_symbol(
            engine, symbol, exit_price=px,
            exit_date=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")))
    except Exception as e:
        logger.warning("alpaca close journaling failed (non-fatal): %s", e)
        return 0


@router.get("/status")
async def get_status():
    """Get Alpaca connection status."""
    try:
        from alpaca_client import ALPACA_API_KEY, ALPACA_SECRET_KEY
        return {
            "configured": bool(ALPACA_API_KEY and ALPACA_SECRET_KEY),
            "api_key_set": bool(ALPACA_API_KEY),
            "secret_key_set": bool(ALPACA_SECRET_KEY),
            "base_url": "https://paper-api.alpaca.markets",
            "mode": "paper trading",
        }
    except Exception as e:
        return {"error": str(e)}
