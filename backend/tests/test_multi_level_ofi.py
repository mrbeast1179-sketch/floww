"""
backend/tests/test_multi_level_ofi.py

Regression tests for the Multi-Level OFI service used by Flowseeker Pro.

These tests lock the formula serialization of:
  * MultiLevelOFI.compute()        — LOB-based, Xu/Gould/Howison (2019) style.
  * StructuralOFI.compute()        — chain-based proxy used by Flowseeker
                                     until a real LOB feed lands.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_multi_level_ofi.py -v

Dependencies: pytest only (stdlib math + collections in the module itself).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

# Allow running this file directly (without `pytest` install) by ensuring
# the backend package root is importable.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.multi_level_ofi import MultiLevelOFI, StructuralOFI


# ─────────────────────────────────────────────────────────────────────
# MultiLevelOFI (LOB-based)
# ─────────────────────────────────────────────────────────────────────

def _lob_snapshot(base_price: float, base_bid_size: int, base_ask_size: int):
    """Build a 5-level LOB snapshot {level: {'bid': (px, sz), 'ask': (px, sz)}}."""
    snap = {}
    for lvl in range(5):
        bid_px = base_price + 0.05 * lvl
        ask_px = bid_px + 0.10
        bid_sz = max(1, base_bid_size + 10 * lvl)
        ask_sz = max(1, base_ask_size - 5 * lvl)
        snap[lvl] = {
            "bid": (bid_px, bid_sz),
            "ask": (ask_px, ask_sz),
        }
    return snap


def test_multilevelofi_warming_after_one_snapshot():
    m = MultiLevelOFI(levels=5)
    m.push_snapshot(_lob_snapshot(100.0, 100, 100))
    out = m.compute()
    assert out["snaps_used"] == 1
    assert out["of_per_level"] == []
    assert out["of_aggregated"] == 0.0
    assert out["imbalance_label"] == "neutral"


def test_multilevelofi_buy_pressure_detected_when_bids_grow():
    m = MultiLevelOFI(levels=5)
    m.push_snapshot(_lob_snapshot(100.0, 100, 100))
    # Bid sizes double, ask prices fall + sizes shrink (buy pressure signal).
    snap = {}
    for lvl in range(5):
        snap[lvl] = {
            "bid": (100.05 * lvl + 100.10, 200 + 10 * lvl),   # bid price up, size up
            "ask": (100.05 * lvl + 100.05, 60 - 5 * lvl),     # ask price down, size down
        }
    m.push_snapshot(snap)
    out = m.compute()
    assert out["snaps_used"] == 2
    assert out["levels_used"] == 5
    assert math.isfinite(out["of_aggregated"])
    assert out["of_aggregated"] > 0, f"expected buy-pressure aggregate, got {out['of_aggregated']}"
    assert out["imbalance_label"] == "buy_pressure"


def test_multilevelofi_sell_pressure_detected_when_asks_swallow_liquidity():
    """Sell pressure — bulletproof single-side scenario.

    Strategy: hold the bid side FLAT (prices and sizes unchanged) so of_bid == 0
    for every level. Then ONLY ask prices fall (cap < pap → of_ask -= cas).
    That guarantees a negative aggregate without any sign-flip ambiguity
    introduced by the bid branch.

        prev = _lob_snapshot(100.0, 200, 100)   # asks start at base+0.10+0.05*lvl
        cur  = same bid prices + sizes; asks step down ~0.20 per level

    Expected:
        of_bid  per level = cbs - pbs = 0  (sizes unchanged)
        of_ask  per level = -cas           (ask prices fell)
        aggregate = -sum(cas) → negative → sell_pressure
    """
    m = MultiLevelOFI(levels=5)
    # _lob_snapshot(100.0, 200, 100) → bid_sz=[200,210,220,230,240], ask_sz=[100,95,90,85,80]
    prev = _lob_snapshot(100.0, 200, 100)
    m.push_snapshot(prev)
    snap = {}
    for lvl in range(5):
        # Bid px + sz UNCHANGED from prev → of_bid == 0
        prev_level = prev[lvl]
        # Ask px only: drop by 0.20 from prev each level so cap < pap
        old_ask_px, old_ask_sz = prev_level["ask"]
        snap[lvl] = {
            "bid": prev_level["bid"],                  # unchanged
            "ask": (old_ask_px - 0.20, old_ask_sz),     # ask px DOWN, size unchanged
        }
    m.push_snapshot(snap)
    out = m.compute()
    # Sanity: bid-side contribution is identically zero (prices + sizes unchanged)
    # → every per_level value must equal of_ask (= -cas, strictly negative).
    assert all(v < 0 for v in out["of_per_level"]), (
        f"every per_level should be negative; got {out['of_per_level']}"
    )
    assert out["of_aggregated"] < 0, (
        f"expected sell-pressure aggregate, got {out['of_aggregated']}"
    )
    assert out["imbalance_label"] == "sell_pressure"


def test_multilevelofi_history_buffer_clamps_to_maxlen():
    m = MultiLevelOFI(levels=5, history=3)
    for _ in range(10):
        m.push_snapshot(_lob_snapshot(100.0, 100, 100))
    # deque maxlen enforces FIFO; len() must not exceed history.
    assert len(m._snaps) <= 3


# ─────────────────────────────────────────────────────────────────────
# StructuralOFI (chain-based proxy)
# ─────────────────────────────────────────────────────────────────────

def _strike_row(strike: float, call_oi: float, put_oi: float,
                call_vol: float, put_vol: float):
    """Build a CVForge-shape strike row [strike, call_v, put_v]."""
    return [
        strike,
        [None] * 4 + [call_oi, 0.30] + [0] * 3 + [3.10, 3.20, 3.15, call_vol] + [580] + [None] * 4,
        [None] * 4 + [put_oi,  0.34] + [0] * 3 + [4.20, 4.30, 4.25, put_vol]  + [580] + [None] * 4,
    ]


def _chain(rows):
    return [{"expiration": "2026-07-25", "strikes": rows}]


def test_structuralofi_warming_after_one_snapshot():
    sof = StructuralOFI(levels=4)
    sof.push_chain(_chain([_strike_row(575, 500, 800, 50, 80)]))
    out = sof.compute()
    assert out["snaps_used"] == 1
    assert out["of_per_level"] == []
    assert out["of_aggregated"] == 0.0


def test_structuralofi_call_oi_growth_yields_positive_ofi():
    sof = StructuralOFI(levels=4)
    chain_a = _chain([
        _strike_row(575, 500, 800, 50, 80),
        _strike_row(580, 1200, 900, 1500, 800),
        _strike_row(585, 2000, 1100, 2500, 1000),
        _strike_row(590, 600, 700, 700, 650),
    ])
    # Snapshot B: call OI grows at every strike (institutional buying),
    # put OI drops at every strike.
    chain_b = _chain([
        _strike_row(575, 800, 600, 80, 100),
        _strike_row(580, 1700, 700, 2000, 600),
        _strike_row(585, 2600, 900, 3000, 800),
        _strike_row(590, 900, 500, 900, 400),
    ])
    sof.push_chain(chain_a)
    sof.push_chain(chain_b)
    out = sof.compute()
    assert out["snaps_used"] == 2
    assert out["levels_used"] == 4
    assert math.isfinite(out["of_aggregated"])
    # Call OI growth (positive) and put OI decline (positive after inversion)
    # should sum to a positive OFI.
    assert out["of_aggregated"] > 0, f"expected positive aggregate, got {out['of_aggregated']}"
    assert out["imbalance_label"] == "buy_pressure"
    # Per-level output length must match levels_used.
    assert len(out["of_per_level"]) == out["levels_used"]


def test_structuralofi_put_oi_growth_inverts_to_negative():
    sof = StructuralOFI(levels=4)
    chain_a = _chain([
        _strike_row(575, 800, 500, 100, 50),
        _strike_row(580, 1500, 800, 1800, 1500),
    ])
    # Snapshot B: put OI grows at every strike, call OI shrinks.
    chain_b = _chain([
        _strike_row(575, 600, 800, 80, 100),
        _strike_row(580, 1200, 1500, 1500, 2200),
    ])
    sof.push_chain(chain_a)
    sof.push_chain(chain_b)
    out = sof.compute()
    assert out["of_aggregated"] < 0, f"expected negative aggregate, got {out['of_aggregated']}"
    assert out["imbalance_label"] == "sell_pressure"


# ─────────────────────────────────────────────────────────────────────
# End-to-end smoke: snapshot -> compute -> snapshot -> compute (warming flips off)
# ─────────────────────────────────────────────────────────────────────

def test_warming_state_resolves_after_second_fetch():
    sof = StructuralOFI(levels=4)
    chain = _chain([
        _strike_row(580, 1200, 900, 1500, 800),
        _strike_row(585, 2000, 1100, 2500, 1000),
    ])
    # First push + compute = warming.
    sof.push_chain(chain)
    warming = sof.compute()
    assert warming["snaps_used"] == 1
    # Second push + compute = resolved.
    sof.push_chain(chain)
    resolved = sof.compute()
    assert resolved["snaps_used"] == 2
    assert resolved["levels_used"] >= 1


if __name__ == "__main__":
    # Allow running as a plain script if pytest isn't installed.
    test_cases = [v for k, v in globals().items() if k.startswith("test_")]
    failures = 0
    for tc in test_cases:
        try:
            tc()
            print(f"PASS {tc.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {tc.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {tc.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(test_cases) - failures}/{len(test_cases)} passed")
    sys.exit(0 if failures == 0 else 1)
