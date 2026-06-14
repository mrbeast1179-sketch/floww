"""
backend/services/execution_doctrine.py

Execution doctrine enforcer: applies Project Oracle trading rules
before any order reaches the router.

Rules:
1. Tap Probability decay — node state determines R:R requirement
2. Deflection zones only — entry must be near a node
3. Never trade midpoint — reject if between two nodes
4. 3:1 R:R minimum (2:1 for fresh nodes)

References:
- Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading."
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NODE_STATE_FRESH = "fresh"
NODE_STATE_TESTED = "tested"
NODE_STATE_DELIVERED = "delivered"
NODE_STATE_DECAYING = "decaying"

MAX_DEFLECTION_DISTANCE_PCT = 0.001  # 0.1%
MIDPOINT_NODE_SEPARATION_PCT = 0.005  # 0.5%
MIN_RR_FRESH = 2.0
MIN_RR_TESTED = 3.0


class ExecutionDoctrine:
    """Enforces Project Oracle execution doctrine."""

    def apply(
        self,
        intent: dict[str, Any],
        market_state: dict[str, Any],
    ) -> tuple[bool, str]:
        """Apply all doctrine rules.

        Args:
            intent: TradeIntent dict with ticker, side, qty, limit_price, stop_loss, take_profit
            market_state: dict with spot, nodes (list of {strike, state})

        Returns:
            (allow: bool, reason: str)
        """
        spot = market_state.get("spot", 0.0)
        nodes = market_state.get("nodes", [])
        entry = intent.get("limit_price", 0.0)
        stop_loss = intent.get("stop_loss", 0.0)
        take_profit = intent.get("take_profit", 0.0)

        if spot <= 0 or entry <= 0:
            return False, "invalid spot or entry price"

        # Rule 1: Tap Probability decay
        nearest_node = self._find_nearest_node(entry, nodes)
        if nearest_node:
            node_state = nearest_node.get("state", NODE_STATE_FRESH)
            if node_state == NODE_STATE_DELIVERED:
                return False, "delivered node — wait for fresh"
            if node_state == NODE_STATE_DECAYING:
                return False, "decaying node — never trade"

            # R:R check based on node state
            rr = self._compute_rr(entry, stop_loss, take_profit, intent.get("side", "buy"))
            if node_state == NODE_STATE_FRESH:
                if rr < MIN_RR_FRESH:
                    return False, f"R:R {rr:.2f} < {MIN_RR_FRESH} (fresh node)"
            elif node_state == NODE_STATE_TESTED and rr < MIN_RR_TESTED:
                return False, f"R:R {rr:.2f} < {MIN_RR_TESTED} (tested node)"

        # Rule 2: Deflection zones only
        if nearest_node:
            distance_pct = abs(entry - nearest_node.get("strike", 0)) / spot
            if distance_pct > MAX_DEFLECTION_DISTANCE_PCT:
                return False, f"distance {distance_pct:.4f} > {MAX_DEFLECTION_DISTANCE_PCT} (not near node)"

        # Rule 3: Never trade midpoint
        if self._is_midpoint(entry, nodes, spot):
            return False, "midpoint trade — no-man's land"

        return True, "approved"

    def _find_nearest_node(self, entry: float, nodes: list[dict]) -> dict | None:
        """Find the nearest node to the entry price."""
        if not nodes:
            return None
        nearest = None
        min_dist = float("inf")
        for node in nodes:
            strike = node.get("strike", 0)
            dist = abs(entry - strike)
            if dist < min_dist:
                min_dist = dist
                nearest = node
        return nearest

    def _compute_rr(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        side: str,
    ) -> float:
        """Compute risk:reward ratio."""
        if side == "buy":
            risk = entry - stop_loss
            reward = take_profit - entry
        else:
            risk = stop_loss - entry
            reward = entry - take_profit

        if risk <= 0:
            return 0.0
        return reward / risk

    def _is_midpoint(self, entry: float, nodes: list[dict], spot: float) -> bool:
        """Check if entry is in a midpoint zone between two nodes."""
        if len(nodes) < 2:
            return False

        strikes = sorted([n.get("strike", 0) for n in nodes])
        for i in range(len(strikes) - 1):
            lower = strikes[i]
            upper = strikes[i + 1]
            separation = (upper - lower) / spot

            if separation > MIDPOINT_NODE_SEPARATION_PCT:
                midpoint = (lower + upper) / 2
                if abs(entry - midpoint) / spot < separation / 4:
                    return True

        return False
