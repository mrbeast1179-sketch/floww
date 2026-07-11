"""Regression tests for the 2026-07-11 full-repo audit fixes.

Two confirmed semantic bugs found by the audit:
  1. portfolio.Position.current_greeks marked expiring (0-DTE) options at 0
     instead of intrinsic value → ITM positions reported as ~100% loss.
  2. server.create_alert used str(len(_alert_rules)+1) for ids, which collided
     after a delete → wrong-target deletes and double-counted triggers.
"""
from __future__ import annotations

from datetime import date

import pytest

from portfolio import Position


class TestExpiringIntrinsicValue:
    def test_itm_call_marks_to_intrinsic_at_expiry(self):
        # Expiry = today → dte=0 → T=0 → current_greeks hits the expiry branch.
        pos = Position(
            symbol="SPY", option_type="call", strike=100.0,
            expiry=date.today().strftime("%Y-%m-%d"),
            quantity=10, entry_price=5.0, entry_iv=0.2, underlying_price=118.0,
        )
        g = pos.current_greeks(spot=120.0, iv=0.2)
        assert g["price"] == pytest.approx(20.0)      # intrinsic = 120 - 100, NOT 0
        assert g["delta"] == pytest.approx(1.0)       # ITM call → terminal delta 1

    def test_otm_put_marks_to_zero_at_expiry(self):
        pos = Position(
            symbol="SPY", option_type="put", strike=100.0,
            expiry=date.today().strftime("%Y-%m-%d"),
            quantity=1, entry_price=3.0, entry_iv=0.2, underlying_price=120.0,
        )
        g = pos.current_greeks(spot=120.0, iv=0.2)
        assert g["price"] == pytest.approx(0.0)       # OTM put expires worthless
        assert g["delta"] == pytest.approx(0.0)

    def test_itm_put_marks_to_intrinsic_at_expiry(self):
        pos = Position(
            symbol="SPY", option_type="put", strike=100.0,
            expiry=date.today().strftime("%Y-%m-%d"),
            quantity=1, entry_price=3.0, entry_iv=0.2, underlying_price=90.0,
        )
        g = pos.current_greeks(spot=90.0, iv=0.2)
        assert g["price"] == pytest.approx(10.0)      # 100 - 90
        assert g["delta"] == pytest.approx(-1.0)


@pytest.mark.asyncio
class TestAlertIdCollision:
    async def test_ids_stay_unique_after_delete_then_create(self, aclient):
        base = {"ticker": "SPY", "alert_type": "gex_cross", "threshold": 1.0}
        r1 = await aclient.post("/api/alerts", json=base)
        r2 = await aclient.post("/api/alerts", json=base)
        r3 = await aclient.post("/api/alerts", json=base)
        id2 = r2.json()["rule"]["id"]

        # Delete the middle rule, then create a new one.
        d = await aclient.delete(f"/api/alerts/{id2}")
        assert d.status_code == 200, d.text
        r4 = await aclient.post("/api/alerts", json=base)

        ids = [r1.json()["rule"]["id"], r3.json()["rule"]["id"], r4.json()["rule"]["id"]]
        # Pre-fix, r4 reused r3's id (len+1 rewound after the delete).
        assert len(set(ids)) == 3, f"colliding alert ids: {ids}"
