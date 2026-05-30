"""
backend/services/position_reconciler.py

Position reconciliation loop — compares local position tracker to Schwab's view.

Every 60s during market hours: pull positions from Schwab → compare to local tracker.
Discrepancies → log + auto-reconcile to Schwab's view + emit reconciliation_event.

Reference: Lo (2002) "The Statistics of Sharpe Ratios" — tracking accuracy.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

RECONCILE_INTERVAL_S = 60


