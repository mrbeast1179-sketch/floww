"""
backend/services/paper_broker.py

Enhanced paper broker with shadow trading, fill simulation, slippage model,
and position tracking. Inspired by swarmSPX's paper.py.

Features:
- Order submission with deterministic IDs
- Realistic fill simulation with configurable slippage model
  - Fixed slippage per contract
  - Market impact proportional to size
  - Optional random component for Monte Carlo
- Position tracking (quantity, avg_cost, unrealized/realized PnL)
- Daily PnL tracking for kill switch integration
- Trade history with full fill details
- Close positions with market data

No external dependencies beyond stdlib + numpy.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Fill:
    """Represents a single fill event."""
    fill_id: str
    order_id: str
    ticker: str
    side: str  # "buy" or "sell"
    quantity: int
    fill_price: float
    slippage: float
    market_impact: float
    commission: float
    timestamp: str
    raw_price: float  # price before slippage/impact

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "fill_price": round(self.fill_price, 4),
            "slippage": round(self.slippage, 6),
            "market_impact": round(self.market_impact, 6),
            "commission": round(self.commission, 2),
            "timestamp": self.timestamp,
            "raw_price": round(self.raw_price, 4),
        }


@dataclass
class Position:
    """Tracks a single ticker's position."""
    ticker: str
    quantity: int  # positive = long, negative = short
    avg_cost: float
    realized_pnl: float = 0.0
    trades: int = 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def notional(self) -> float:
        return abs(self.quantity) * self.avg_cost

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL given current market price."""
        if self.quantity == 0:
            return 0.0
        return (current_price - self.avg_cost) * self.quantity

    def to_dict(self, current_price: Optional[float] = None) -> Dict[str, Any]:
        d = {
            "ticker": self.ticker,
            "quantity": self.quantity,
            "avg_cost": round(self.avg_cost, 4),
            "realized_pnl": round(self.realized_pnl, 2),
            "trades": self.trades,
        }
        if current_price is not None:
            d["current_price"] = round(current_price, 4)
            d["unrealized_pnl"] = round(self.unrealized_pnl(current_price), 2)
            d["notional"] = round(abs(self.quantity) * current_price, 2)
        return d


@dataclass
class Order:
    """Represents a submitted order."""
    order_id: str
    ticker: str
    side: str
    quantity: int
    order_type: str  # "market", "limit"
    limit_price: float
    status: str = "pending"  # pending, filled, partial, rejected
    filled_quantity: int = 0
    fills: List[Fill] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── Slippage model ────────────────────────────────────────────────────────────

class SlippageModel:
    """Configurable slippage model for fill simulation.

    Components:
    1. Fixed slippage per contract (e.g., $0.01 per contract)
    2. Market impact proportional to size (e.g., 0.1% per contract)
    3. Optional random component for Monte Carlo simulation
    """

    def __init__(
        self,
        slippage_per_contract: float = 0.01,
        market_impact_pct: float = 0.001,
        random_slippage: bool = False,
        random_seed: Optional[int] = None,
    ):
        self.slippage_per_contract = slippage_per_contract
        self.market_impact_pct = market_impact_pct
        self.random_slippage = random_slippage
        if random_seed is not None:
            self._rng = np.random.default_rng(random_seed)
        else:
            self._rng = np.random.default_rng()

    def compute_slippage(
        self, price: float, quantity: int, side: str
    ) -> tuple[float, float, float]:
        """Compute total slippage for a fill.

        Returns:
            (total_slippage, fixed_component, impact_component)
        """
        # Fixed component: per-contract cost
        fixed = self.slippage_per_contract * quantity

        # Market impact: proportional to size and price
        impact = price * self.market_impact_pct * quantity

        # Random component (optional)
        random_component = 0.0
        if self.random_slippage:
            # Normal distribution, std = 0.5 bps of price
            random_component = abs(self._rng.normal(0, price * 0.0005)) * quantity

        total = fixed + impact + random_component

        # Slippage always against the trader
        # For buys: fill price goes up; for sells: fill price goes down
        sign = 1.0 if side == "buy" else -1.0
        return sign * total, fixed, impact

    def get_fill_price(self, price: float, quantity: int, side: str) -> tuple[float, float, float, float]:
        """Get the simulated fill price.

        Returns:
            (fill_price, total_slippage, fixed_component, impact_component)
        """
        total_slippage, fixed, impact = self.compute_slippage(price, quantity, side)
        fill_price = max(price + total_slippage, 0.0001)
        return fill_price, total_slippage, fixed, impact


# ── Paper Broker ──────────────────────────────────────────────────────────────

class PaperBroker:
    """Enhanced paper broker with shadow trading and fill simulation.

    Simulates order submission, fill execution with slippage, position
    tracking, and PnL calculation. Designed for backtesting and
    shadow-trading before going live.

    Configurable:
    - initial_capital: Starting cash (default $100,000)
    - slippage_per_contract: Fixed slippage per contract (default $0.01)
    - market_impact_pct: Impact as fraction of price (default 0.1%)
    - commission_per_contract: Commission per contract (default $0.65)
    - random_slippage: Enable random slippage component (default False)
    - random_seed: Seed for random slippage RNG
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        slippage_per_contract: float = 0.01,
        market_impact_pct: float = 0.001,
        commission_per_contract: float = 0.65,
        random_slippage: bool = False,
        random_seed: Optional[int] = None,
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.commission_per_contract = commission_per_contract

        # Slippage model
        self.slippage_model = SlippageModel(
            slippage_per_contract=slippage_per_contract,
            market_impact_pct=market_impact_pct,
            random_slippage=random_slippage,
            random_seed=random_seed,
        )

        # State
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.trade_history: List[Fill] = []
        self._order_counter = 0

        # Daily PnL tracking for kill switch
        self._daily_pnl: Dict[str, float] = {}  # date.isoformat() -> pnl
        self._max_daily_loss_pct: float = 0.05  # 5% daily loss limit

        logger.info(
            "PaperBroker initialized: capital=$%.2f, slippage=$%.4f/contract, "
            "impact=%.4f%%, commission=$%.2f/contract",
            initial_capital, slippage_per_contract,
            market_impact_pct * 100, commission_per_contract,
        )

    # ── Order submission ─────────────────────────────────────────────────

    def submit_order(
        self,
        ticker: str,
        side: str,
        quantity: int,
        order_type: str = "market",
        limit_price: float = 0.0,
    ) -> str:
        """Submit a paper order.

        Args:
            ticker: Symbol to trade (e.g., "SPY")
            side: "buy" or "sell"
            quantity: Number of contracts/shares
            order_type: "market" or "limit"
            limit_price: Limit price (only used for limit orders)

        Returns:
            order_id: Unique order identifier

        Raises:
            ValueError: If side is invalid or quantity <= 0
        """
        if side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {side!r}. Must be 'buy' or 'sell'.")
        if quantity <= 0:
            raise ValueError(f"Quantity must be > 0, got {quantity}")

        self._order_counter += 1
        order_id = f"PAPER-{self._order_counter:06d}-{uuid.uuid4().hex[:8]}"

        order = Order(
            order_id=order_id,
            ticker=ticker.upper(),
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )

        self.orders[order_id] = order
        logger.info(
            "Order submitted: %s %s %s x%d (type=%s)",
            order_id, side, ticker, quantity, order_type,
        )
        return order_id

    # ── Fill simulation ──────────────────────────────────────────────────

    def get_fill_price(
        self,
        order: Order,
        market_data: Dict[str, Any],
    ) -> float:
        """Simulate a fill price with slippage model.

        Args:
            order: The order to fill
            market_data: Dict with at least:
                - "bid": float
                - "ask": float
                - "last": float (optional, used as fallback)
                - "mid": float (optional, computed if missing)

        Returns:
            Simulated fill price (float)
        """
        ticker = order.ticker
        side = order.side
        quantity = order.quantity

        # Determine base price from market data
        bid = float(market_data.get("bid", 0))
        ask = float(market_data.get("ask", 0))
        last = float(market_data.get("last", 0))

        if side == "buy":
            base_price = ask if ask > 0 else last
        else:
            base_price = bid if bid > 0 else last

        if base_price <= 0:
            raise ValueError(
                f"Invalid market data for {ticker}: bid={bid}, ask={ask}, last={last}"
            )

        # Apply slippage model
        fill_price, total_slippage, fixed, impact = self.slippage_model.get_fill_price(
            base_price, quantity, side
        )

        logger.debug(
            "Fill price for %s: base=%.4f, fill=%.4f, slippage=%.4f "
            "(fixed=%.4f, impact=%.4f)",
            order.order_id, base_price, fill_price, total_slippage, fixed, impact,
        )

        return fill_price

    def fill_order(
        self,
        order_id: str,
        market_data: Dict[str, Any],
        fill_quantity: Optional[int] = None,
    ) -> Fill:
        """Execute a fill for an order.

        Args:
            order_id: The order to fill
            market_data: Market data dict (bid, ask, last)
            fill_quantity: Optional partial fill quantity (default: full order)

        Returns:
            Fill object with fill details
        """
        order = self.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status == "filled":
            raise ValueError(f"Order {order_id} already filled")

        qty = fill_quantity or order.quantity
        if qty <= 0:
            raise ValueError(f"Fill quantity must be > 0, got {qty}")
        if qty > order.quantity - order.filled_quantity:
            raise ValueError(
                f"Partial fill {qty} exceeds remaining {order.quantity - order.filled_quantity}"
            )

        fill_price = self.get_fill_price(
            Order(
                order_id=order.order_id,
                ticker=order.ticker,
                side=order.side,
                quantity=qty,
                order_type=order.order_type,
                limit_price=order.limit_price,
            ),
            market_data,
        )

        # Compute slippage components for the fill record
        base_price = fill_price
        total_slippage, fixed, impact = self.slippage_model.compute_slippage(
            self._get_base_price(order, market_data), qty, order.side
        )

        commission = self.commission_per_contract * qty

        fill = Fill(
            fill_id=f"FILL-{uuid.uuid4().hex[:12]}",
            order_id=order_id,
            ticker=order.ticker,
            side=order.side,
            quantity=qty,
            fill_price=fill_price,
            slippage=total_slippage,
            market_impact=impact,
            commission=commission,
            timestamp=datetime.now(timezone.utc).isoformat(),
            raw_price=base_price,
        )

        # Update order
        order.filled_quantity += qty
        order.fills.append(fill)
        if order.filled_quantity >= order.quantity:
            order.status = "filled"
        else:
            order.status = "partial"

        # Update positions
        self._update_positions(fill)

        # Update cash
        if order.side == "buy":
            self.cash -= fill_price * qty + commission
        else:
            self.cash += fill_price * qty - commission

        # Record
        self.trade_history.append(fill)

        # Update daily PnL
        today = date.today().isoformat()
        if order.side == "buy":
            self._daily_pnl[today] = self._daily_pnl.get(today, 0.0) - commission
        else:
            self._daily_pnl[today] = self._daily_pnl.get(today, 0.0) - commission

        logger.info(
            "Fill: %s %s %s x%d @ %.4f (slippage=%.4f, commission=%.2f)",
            fill.fill_id, order.side, order.ticker, qty, fill_price,
            total_slippage, commission,
        )

        return fill

    def _get_base_price(self, order: Order, market_data: Dict[str, Any]) -> float:
        """Get the base price from market data for slippage computation."""
        bid = float(market_data.get("bid", 0))
        ask = float(market_data.get("ask", 0))
        last = float(market_data.get("last", 0))

        if order.side == "buy":
            return ask if ask > 0 else last
        else:
            return bid if bid > 0 else last

    # ── Position tracking ────────────────────────────────────────────────

    def _update_positions(self, fill: Fill) -> None:
        """Update positions after a fill."""
        ticker = fill.ticker
        side = fill.side
        qty = fill.quantity
        price = fill.fill_price

        if ticker not in self.positions:
            self.positions[ticker] = Position(
                ticker=ticker, quantity=0, avg_cost=0.0
            )

        pos = self.positions[ticker]
        old_qty = pos.quantity

        # Determine signed quantity
        signed_qty = qty if side == "buy" else -qty
        new_qty = old_qty + signed_qty

        if old_qty == 0:
            # Opening new position
            pos.avg_cost = price
            pos.quantity = new_qty
        elif (old_qty > 0 and signed_qty > 0) or (old_qty < 0 and signed_qty < 0):
            # Adding to existing position: weighted average cost
            total_cost = pos.avg_cost * abs(old_qty) + price * qty
            pos.avg_cost = total_cost / (abs(old_qty) + qty)
            pos.quantity = new_qty
        else:
            # Reducing or flipping position
            if abs(signed_qty) <= abs(old_qty):
                # Partial or full close
                close_qty = min(abs(signed_qty), abs(old_qty))
                realized = (price - pos.avg_cost) * close_qty
                if old_qty < 0:
                    realized = -realized  # Short position
                pos.realized_pnl += realized
                pos.quantity = new_qty
                if pos.quantity == 0:
                    pos.avg_cost = 0.0
            else:
                # Flip: close old, open new in opposite direction
                close_qty = abs(old_qty)
                realized = (price - pos.avg_cost) * close_qty
                if old_qty < 0:
                    realized = -realized
                pos.realized_pnl += realized
                pos.quantity = new_qty
                pos.avg_cost = price

        pos.trades += 1
        logger.debug(
            "Position updated: %s qty=%d avg_cost=%.4f realized_pnl=%.2f",
            ticker, pos.quantity, pos.avg_cost, pos.realized_pnl,
        )

    def get_position(self, ticker: str) -> Dict[str, Any]:
        """Get current position for a ticker.

        Args:
            ticker: Symbol to look up

        Returns:
            Position dict or flat position dict if no position exists
        """
        ticker = ticker.upper()
        if ticker in self.positions and self.positions[ticker].quantity != 0:
            return self.positions[ticker].to_dict()
        return {"ticker": ticker, "quantity": 0, "avg_cost": 0.0, "realized_pnl": 0.0}

    def get_all_positions(self) -> List[Dict[str, Any]]:
        """Get all open (non-flat) positions.

        Returns:
            List of position dicts
        """
        return [
            pos.to_dict()
            for pos in self.positions.values()
            if pos.quantity != 0
        ]

    # ── PnL calculation ──────────────────────────────────────────────────

    def get_pnl(self, market_data: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Get comprehensive PnL summary.

        Args:
            market_data: Optional dict of ticker -> {"last": price, ...}
                         for unrealized PnL calculation

        Returns:
            Dict with realized_pnl, unrealized_pnl, total_pnl, daily_pnl
        """
        realized = 0.0
        unrealized = 0.0

        for ticker, pos in self.positions.items():
            realized += pos.realized_pnl
            if market_data and ticker in market_data:
                price = float(market_data[ticker].get("last", 0))
                if price > 0:
                    unrealized += pos.unrealized_pnl(price)

        total = realized + unrealized

        # Daily PnL
        today = date.today().isoformat()
        daily = self._daily_pnl.get(today, 0.0)

        return {
            "realized_pnl": round(realized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(total, 2),
            "daily_pnl": round(daily, 2),
            "cash": round(self.cash, 2),
            "initial_capital": self.initial_capital,
            "return_pct": round((total / self.initial_capital) * 100, 4),
        }

    # ── Close position ───────────────────────────────────────────────────

    def close_position(
        self, ticker: str, market_data: Dict[str, Any]
    ) -> Fill:
        """Close an entire position for a ticker.

        Args:
            ticker: Symbol to close
            market_data: Market data dict (bid, ask, last)

        Returns:
            Fill object for the closing trade

        Raises:
            ValueError: If no open position for ticker
        """
        ticker = ticker.upper()
        pos = self.positions.get(ticker)

        if not pos or pos.quantity == 0:
            raise ValueError(f"No open position for {ticker}")

        # Determine closing side and quantity
        close_side = "sell" if pos.quantity > 0 else "buy"
        close_qty = abs(pos.quantity)

        # Submit and fill closing order
        order_id = self.submit_order(
            ticker=ticker,
            side=close_side,
            quantity=close_qty,
        )

        fill = self.fill_order(order_id, market_data)
        logger.info(
            "Position closed: %s %d contracts @ %.4f",
            ticker, close_qty, fill.fill_price,
        )

        return fill

    # ── Trade history ────────────────────────────────────────────────────

    def get_trade_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get trade history (all fills).

        Args:
            limit: Optional max number of fills to return (most recent)

        Returns:
            List of fill dicts
        """
        history = [f.to_dict() for f in self.trade_history]
        if limit:
            return history[-limit:]
        return history

    # ── Daily PnL / Kill switch ──────────────────────────────────────────

    def get_daily_pnl(self, day: Optional[str] = None) -> float:
        """Get PnL for a specific day (ISO date string) or today."""
        if day is None:
            day = date.today().isoformat()
        return self._daily_pnl.get(day, 0.0)

    def is_daily_loss_limit_breached(self) -> bool:
        """Check if daily loss limit has been breached (kill switch)."""
        today = date.today().isoformat()
        daily = self._daily_pnl.get(today, 0.0)
        limit = -self.initial_capital * self._max_daily_loss_pct
        breached = daily <= limit
        if breached:
            logger.warning(
                "Daily loss limit breached: daily_pnl=%.2f, limit=%.2f",
                daily, limit,
            )
        return breached

    def set_max_daily_loss_pct(self, pct: float) -> None:
        """Set the maximum daily loss percentage (for kill switch)."""
        if not 0 < pct < 1:
            raise ValueError(f"max_daily_loss_pct must be between 0 and 1, got {pct}")
        self._max_daily_loss_pct = pct

    # ── State ─────────────────────────────────────────────────────────────

    def get_state(self) -> Dict[str, Any]:
        """Get full broker state summary."""
        pnl = self.get_pnl()
        return {
            "cash": round(self.cash, 2),
            "initial_capital": self.initial_capital,
            "open_positions": len(self.get_all_positions()),
            "total_orders": len(self.orders),
            "total_fills": len(self.trade_history),
            "realized_pnl": pnl["realized_pnl"],
            "unrealized_pnl": pnl["unrealized_pnl"],
            "total_pnl": pnl["total_pnl"],
            "daily_pnl": pnl["daily_pnl"],
            "daily_loss_limit_breached": self.is_daily_loss_limit_breached(),
        }

    def reset(self) -> None:
        """Reset the broker to initial state."""
        self.cash = self.initial_capital
        self.positions.clear()
        self.orders.clear()
        self.trade_history.clear()
        self._order_counter = 0
        self._daily_pnl.clear()
        logger.info("PaperBroker reset to initial state")
