"""
backend/tests/services/test_consensus_pricing.py

Tests for backend/services/consensus_pricing.py — pure-math, no network/DB.

Coverage profile (16 cases + parametrize):

  1.  empty chain                                → []
  2.  single-expiry known-answer (HAND-VERIFIED) → 99.0303
  3.  multi-expiry segregation                  → rows don't bleed
  4.  strict expiry sorting                      → ascending output
  5.  all-calls asymmetry                        → put stats zero, call side drives
  6.  all-puts asymmetry                         → call stats zero, put side drives
  7.  explicit OI=0 contracts                    → 0.0 consensus (no ZeroDivisionError)
  8.  missing ``openInterest`` key               → OI=0 fallback (no KeyError)
  9.  premium resolver — bid-ask mid WINS over lastPrice
  10. premium resolver — bid-ask missing → falls back to lastPrice
  11. premium resolver — both missing → 0.0
  12. tied expect-prices                         → both calls/puts sum properly
  13. ``strike`` is None                         → contract dropped (no crash)
  14. unknown-expiry normal (has strike)         → "_unknown" row with consensus
  15. unknown-expiry sentinel (no strike)        → "_unknown" row at strike 0
  16. overall top-line blend                     → multi-expiry aggregation
  +  parametric type-alias regressions

Hand-verified math for case #2 (the reference case):
────────────────────────────────────────────────────
chain:
  C1: strike=100, OI=1000, bid=1.9, ask=2.1     → mid = (1.9+2.1)/2 = 2.0
  C2: strike=105, OI= 500, lastPrice=1.0       → no bid/ask → premium = 1.0
  P1: strike= 95, OI= 800, bid=1.0, ask=2.0     → mid = (1.0+2.0)/2 = 1.5
  P2: strike=100, OI=1000, lastPrice=3.0       → no bid/ask → premium = 3.0

call_expect = 100 + 2.0 = 102.0      ; weighted = 102*1000 = 102000
call_expect = 105 + 1.0 = 106.0      ; weighted = 106* 500 =  53000
put_expect  =  95 - 1.5 =  93.5      ; weighted = 93.5* 800 = 74800
put_expect  = 100 - 3.0 =  97.0      ; weighted = 97 * 1000 = 97000

sum_oi  = 1500 + 1800 = 3300
numerator = 102000 + 53000 + 74800 + 97000 = 326800.0
consensus_price = 326800.0 / 3300 = 99.030303…

avg_call_premium = ((2.0*1000) + (1.0*500)) / 1500 = 2500/1500 = 1.6666…  → 1.6667
avg_put_premium  = ((1.5* 800) + (3.0*1000)) / 1800 = 4200/1800 = 2.3333…  → 2.3333
"""

from __future__ import annotations

import pytest

from services.consensus_pricing import (
    compute_consensus_per_expiry,
    compute_overall_consensus,
)

# ----------------------------------------------------------------------------
# Helpers — small hand-verifiable contract builders.
# ----------------------------------------------------------------------------

def _call_mid(
    strike: float, oi: int,
    bid: float = 0.0, ask: float = 0.0, last: float = 0.0,
    expiry: str = "2026-08-15",
) -> dict:
    return {
        "strike": float(strike), "type": "CALL",
        "openInterest": oi, "expiry": expiry,
        "bid": bid, "ask": ask, "lastPrice": last,
    }


def _put_mid(
    strike: float, oi: int,
    bid: float = 0.0, ask: float = 0.0, last: float = 0.0,
    expiry: str = "2026-08-15",
) -> dict:
    return {
        "strike": float(strike), "type": "PUT",
        "openInterest": oi, "expiry": expiry,
        "bid": bid, "ask": ask, "lastPrice": last,
    }


# ----------------------------------------------------------------------------
# 1. Empty chain
# ----------------------------------------------------------------------------
def test_empty_chain_returns_empty_list():
    assert compute_consensus_per_expiry([]) == []
    assert compute_overall_consensus([]) == {}


# ----------------------------------------------------------------------------
# 2. Hand-verified single-expiry known-answer.
# Full math walked strike-by-strike in the module docstring above.
# ----------------------------------------------------------------------------
def test_single_expiry_known_answer_99_0303():
    chain = [
        _call_mid(100, 1000, bid=1.9, ask=2.1),
        _call_mid(105,  500, last=1.0),
        _put_mid( 95,  800, bid=1.0, ask=2.0),
        _put_mid(100, 1000, last=3.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    assert len(rows) == 1
    row = rows[0]
    assert row["expiry"] == "2026-08-15"
    assert row["consensus_price"] == 99.0303
    assert row["total_oi"] == 3300
    assert row["call_oi"] == 1500
    assert row["put_oi"] == 1800
    assert row["avg_call_premium"] == round(2500.0 / 1500.0, 4)  # 1.6667
    assert row["avg_put_premium"] == round(4200.0 / 1800.0, 4)   # 2.3333


# ----------------------------------------------------------------------------
# 3. Multi-expiry segregation.
# ----------------------------------------------------------------------------
def test_multi_expiry_does_not_bleed():
    chain = [
        # Expiry A: heavy OI at 100 ⇒ consensus should land RIGHT AT 100 if
        # premium = 0 across the board.
        _call_mid(100, 1000, last=0.0),
        _put_mid( 100, 1000, last=0.0),
        # Expiry B: heavy OI at 110
        _call_mid(110, 1000, last=0.0),
        _put_mid( 110, 1000, last=0.0),
    ]
    for c in chain[2:]:
        c["expiry"] = "2026-09-19"
    rows = compute_consensus_per_expiry(chain)
    assert [r["expiry"] for r in rows] == ["2026-08-15", "2026-09-19"]
    assert rows[0]["consensus_price"] == 100.0
    assert rows[1]["consensus_price"] == 110.0


# ----------------------------------------------------------------------------
# 4. Mixed-order input → ascending output.
# ----------------------------------------------------------------------------
def test_expiry_rows_sorted_ascending():
    chain = [
        _call_mid(100, 100, last=0.0, expiry="2026-12-31"),
        _call_mid(100, 100, last=0.0, expiry="2026-07-20"),
        _call_mid(100, 100, last=0.0, expiry="2026-08-15"),
    ]
    rows = compute_consensus_per_expiry(chain)
    assert [r["expiry"] for r in rows] == ["2026-07-20", "2026-08-15", "2026-12-31"]


# ----------------------------------------------------------------------------
# 5. All-calls asymmetry.
#   Pure call side ⇒ put_oi=0, avg_put_premium=0.0, consensus = strike+premium.
# ----------------------------------------------------------------------------
def test_all_calls_asymmetry_puts_drive_zero():
    chain = [
        _call_mid(100, 100, last=2.0),   # consensus = 100 + 2 = 102
        _call_mid(105, 100, last=1.0),   # consensus = 105 + 1 = 106
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # numerator = 102*100 + 106*100 = 20800 ; total_oi = 200
    assert row["consensus_price"] == 104.0
    assert row["call_oi"] == 200
    assert row["put_oi"] == 0
    assert row["avg_call_premium"] == 1.5
    assert row["avg_put_premium"] == 0.0


# ----------------------------------------------------------------------------
# 6. All-puts asymmetry.
#   Pure put side ⇒ call_oi=0, avg_call_premium=0.0, consensus = strike-premium.
# ----------------------------------------------------------------------------
def test_all_puts_asymmetry_calls_drive_zero():
    chain = [
        _put_mid(100, 100, last=3.0),    # expect = 100 - 3 = 97
        _put_mid(105, 100, last=5.0),    # expect = 105 - 5 = 100
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # numerator = 97*100 + 100*100 = 19700 ; total_oi = 200
    assert row["consensus_price"] == 98.5
    assert row["call_oi"] == 0
    assert row["put_oi"] == 200
    assert row["avg_call_premium"] == 0.0
    assert row["avg_put_premium"] == 4.0


# ----------------------------------------------------------------------------
# 7. Explicit OI=0 — defensive against ZeroDivisionError.
# ----------------------------------------------------------------------------
def test_zero_oi_returns_zero_consensus_not_crash():
    chain = [
        _call_mid(100, 0, last=2.0),
        _put_mid( 100, 0, last=3.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    assert row["consensus_price"] == 0.0
    assert row["total_oi"] == 0
    assert row["call_oi"] == 0
    assert row["put_oi"] == 0


# ----------------------------------------------------------------------------
# 8. Missing ``openInterest`` key → fallback to 0.
# ----------------------------------------------------------------------------
def test_missing_oi_key_falls_back_to_zero():
    chain = [
        {"strike": 100, "type": "CALL", "expiry": "2026-08-15", "lastPrice": 2.0},
        {"strike":  95, "type": "PUT",  "expiry": "2026-08-15", "lastPrice": 1.5},
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    assert row["total_oi"] == 0
    assert row["consensus_price"] == 0.0


# ----------------------------------------------------------------------------
# 9. Premium resolver — bid/ask mid WINS over lastPrice.
# ----------------------------------------------------------------------------
def test_premium_resolver_uses_mid_over_last():
    chain = [
        # lastPrice=99 (junk) but mid=(1+2)/2=1.5 ⇒ premium should be 1.5.
        _call_mid(100, 1000, bid=1.0, ask=2.0, last=99.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # consensus = (100+1.5) * 1000 / 1000 = 101.5
    assert row["consensus_price"] == 101.5
    assert row["avg_call_premium"] == 1.5


# ----------------------------------------------------------------------------
# 10. Premium resolver — bid/ask missing/zero → falls back to lastPrice.
# ----------------------------------------------------------------------------
def test_premium_resolver_falls_back_to_last():
    chain = [
        _call_mid(100, 1000, bid=0.0, ask=0.0, last=2.5),
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    assert row["consensus_price"] == 102.5
    assert row["avg_call_premium"] == 2.5


# ----------------------------------------------------------------------------
# 11. Premium resolver — both bid/ask AND lastPrice missing → 0.0.
# ----------------------------------------------------------------------------
def test_premium_resolver_missing_yields_zero():
    chain = [
        {"strike": 100.0, "type": "CALL", "openInterest": 1000, "expiry": "2026-08-15"},
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # call_expect = 100 + 0 = 100  (per-premium=0, math walk)
    assert row["consensus_price"] == 100.0
    assert row["avg_call_premium"] == 0.0


# ----------------------------------------------------------------------------
# 12. Tied expect-prices — both sides should sum normally with no special
# tiebreak (this is a CONSENSUS, not a max-pain-style min).
# ----------------------------------------------------------------------------
def test_tied_expect_prices():
    # call C=100 premium=2  → expect = 102; weighted = 102*1000 = 102000
    # put  P=104 premium=2  → expect = 102; weighted = 102*1000 = 102000
    chain = [
        _call_mid(100, 1000, last=2.0),
        _put_mid( 104, 1000, last=2.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # numerator = 204000 ; total_oi = 2000 → consensus_price = 102.0
    assert row["consensus_price"] == 102.0
    assert row["avg_call_premium"] == 2.0
    assert row["avg_put_premium"] == 2.0


# ----------------------------------------------------------------------------
# 13. ``strike`` is None (present-but-null) → contract dropped, no crash.
# ----------------------------------------------------------------------------
def test_none_strike_contract_dropped():
    chain = [
        {"strike": None, "type": "CALL", "openInterest": 9999, "expiry": "2026-08-15"},
        _call_mid(100, 100, last=2.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    row = rows[0]
    # Only the real contract contributes; the None-strike CALL must NOT leak
    # into OI sum (preventing TypeError on (None + premium)).
    assert row["call_oi"] == 100
    assert row["total_oi"] == 100
    assert row["consensus_price"] == 102.0


# ----------------------------------------------------------------------------
# 14. Normal unknown-expiry path (has strike but no expiry key).
# ----------------------------------------------------------------------------
def test_unknown_group_with_strikes_processes_normally():
    chain = [
        {"strike": 50.0, "type": "CALL", "openInterest": 100, "lastPrice": 1.5},
        _call_mid(100, 100, last=2.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    unknown_row = next(r for r in rows if r["expiry"] == "_unknown")
    # consensus = (50+1.5)*100/100 = 51.5
    assert unknown_row["consensus_price"] == 51.5
    assert unknown_row["call_oi"] == 100


# ----------------------------------------------------------------------------
# 15. Sentinel unknown-expiry path (no strike AND no expiry) — strike=0.0
# row preserving shape.
# ----------------------------------------------------------------------------
def test_unknown_sentinel_no_strike_no_expiry():
    chain = [
        {"type": "CALL", "openInterest": 50},  # no strike, no expiry
        _call_mid(100, 100, last=2.0),
    ]
    rows = compute_consensus_per_expiry(chain)
    expiries = [r["expiry"] for r in rows]
    assert expiries == ["2026-08-15", "_unknown"]
    unknown_row = next(r for r in rows if r["expiry"] == "_unknown")
    assert unknown_row["consensus_price"] == 0.0
    assert unknown_row["call_oi"] == 0


# ----------------------------------------------------------------------------
# 16. Overall top-line blend across multiple expiries.
# ----------------------------------------------------------------------------
def test_overall_top_line_total_blend():
    chain = [
        # Expiry A: 100 OI 1500, avg expect ~100 (premiums 0)
        _call_mid(100, 1000, last=0.0),
        _put_mid( 100,  500, last=0.0),
        # Expiry B: 110 OI 2000
        _call_mid(110, 2000, last=0.0),
    ]
    # NOTE: compute_overall_consensus is expiry-agnostic (treats the entire chain as
    #       one flat pool). chain[3:] is intentionally empty here so the test
    #       verifies the overall blend on a single mixed-contract chain.
    for c in chain[3:]:
        c["expiry"] = "2026-09-19"
    overall = compute_overall_consensus(chain)
    # numerator = 100*1500 + 110*2000 = 150000 + 220000 = 370000
    # total_oi = 3500
    # consensus = 370000/3500 = 105.7142…
    assert overall["consensus_price"] == round(370000.0 / 3500.0, 4)
    assert overall["total_oi"] == 3500
    assert overall["call_oi"] == 3000
    assert overall["put_oi"] == 500


# ----------------------------------------------------------------------------
# Type-alias sanity (cheap regression for downstream dialect drift).
# ----------------------------------------------------------------------------
@pytest.mark.parametrize("alias", ["CALL", "C", "call", "CALLS", "CE"])
def test_type_alias_call(alias):
    contract = {"strike": 100, "type": alias, "openInterest": 100, "expiry": "2026-08-15", "lastPrice": 1.0}
    out = compute_overall_consensus([contract])
    assert out["consensus_price"] == 101.0
    assert out["avg_call_premium"] == 1.0


@pytest.mark.parametrize("alias", ["PUT", "P", "put", "PUTS", "PE"])
def test_type_alias_put(alias):
    contract = {"strike": 100, "type": alias, "openInterest": 100, "expiry": "2026-08-15", "lastPrice": 1.0}
    out = compute_overall_consensus([contract])
    assert out["consensus_price"] == 99.0
    assert out["avg_put_premium"] == 1.0
