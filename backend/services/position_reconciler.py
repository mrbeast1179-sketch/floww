"""
backend/services/position_reconciler.py

Position reconciliation loop — compares local position tracker to Schwab's view.

Every 60s during market hours: pull positions from Schwab → compare to local tracker.
Discrepancies → log + auto-reconcile to Schwab's view + emit reconciliation_event.

Reference: Lo (2002) "The Statistics of Sharpe Ratios" — tracking accuracy.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

log = logging.getLogger(__name__)

RECONCILE_INTERVAL_S = 60


class PositionReconciler:
    """Reconcles local positions with Schwab's view."""

    def __init__(self, order_router):
        self._router = order_router
        self._last_reconcile = 0.0
        self._reconcile_count = 0
        self._discrepancy_count = 0

    async def reconcile(self) -> Dict[str, Any]:
        """Run one reconciliation cycle.

        Returns:
            Dict with reconcile results.
        """
        now = time.time()
        self._last_reconcile = now
        self._reconcile_count += 1

        try:
            schwab_positions = await self._router.get_positions_from_schwab()
        except Exception as e:
            log.error(f"Reconcile failed: could not fetch Schwab positions: {e}")
            return {"status": "error", "reason": str(e)}

        local_positions = self._router.position_tracker.snapshot()

        discrepancies = []
        reconciled = {}

        all_tickers = set(list(schwab_positions.keys()) + list(local_positions.keys()))

        for ticker in all_tickers:
            local_qty = local_positions.get(ticker, 0)
            schwab_qty = schwab_positions.get(ticker, 0)

            if local_qty != schwab_qty:
                discrepancy = {
                    "ticker": ticker,
                    "local_qty": local_qty,
                    "schwab_qty": schwab_qty,
                    "delta": schwab_qty - local_qty,
                    "timestamp": now,
                }
                discrepancies.append(discrepancy)
                reconciled[ticker] = schwab_qty
                self._discrepancy_count += 1

                log.warning(
                    f"Position discrepancy: {ticker} local={local_qty} schwab={schwab_qty} "
                    f"(delta={schwab_qty - local_qty})"
                )

                # Auto-reconcile to Schwab's view
                self._router.position_tracker.update(ticker, schwab_qty)

        result = {
            "status": "ok",
            "timestamp": now,
            "tickers_checked": len(all_tickers),
            "discrepancies_found": len(discrepancies),
            "discrepancies": discrepancies,
            "reconciled": reconciled,
        }

        if discrepancies:
            log.warning(f"Reconciliation: {len(discrepancies)} discrepancies found and auto-reconciled")
        else:
            log.debug(f"Reconciliation: all {len(all_tickers)} tickers match")

        return result

    def get_state(self) -> Dict[str, Any]:
        return {
            "last_reconcile": self._last_reconcile,
            "reconcile_count": self._reconcile_count,
            "discrepancy_count": self._discrepancy_count,
            "local_positions": self._router.position_tracker.snapshot(),
        }
