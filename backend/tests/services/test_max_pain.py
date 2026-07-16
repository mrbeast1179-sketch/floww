"""
backend/tests/services/test_max_pain.py

Tests for backend/services/max_pain.py — pure-math, no network or DB.

Coverage profile (16 cases):

  1.  empty chain                                       → returns []
  2.  single-expiry 5-strike known answer              → max pain K=100, loss=3000
  3.  multi-expiry segregation                          → rows don't bleed across expiries
  4.  strict expiry sorting                             → mixed input → ascending output
  5.  tiebreak → lower strike (degenerate single-candidate) → K=100 deterministic
  6.  tiebreak → lower strike (multi-candidate tie)     → K=95, loss=10 (three-way tie)
  7.  zero-OI chain                                      → lowest candidate, no crash
  8.  missing ``openInterest`` key                      → OI=0 fallback (no KeyError)
  9.  all-calls asymmetry                                → max pain at LOWEST candidate
  10. all-puts asymmetry                                 → max pain at HIGHEST candidate
  11. fractional strikes ($0.50 / $12.50)               → no coerce / no rounding loss
  12. unknown-expiry sentinel: no-strike contract       → "_unknown" row with strike=0
  13. unknown-expiry normal: contract has strike        → "_unknown" row with normal max_pain
  14. ``strike`` is None                                 → row dropped from candidates, no crash
  15. overall top-line number on hand-verified chain    → K=100 loss=3000
  16. overall returns ``{}`` on empty chain
  +  parametric type-alias regressions for ``CALL``/``PUT`` spellings.

NOTE: My prior round of test math in cases 2/6/15 used estimated total-loss
values (4000, 0, 4000) that did not match hand-recounts. The docstrings below
walk the formula strike-by-strike so a future reviewer can re-verify the
expected values without rerunning the implementation.
"""

from __future__ import annotations

import pytest

from services.max_pain import (
    compute_max_pain_per_expiry,
    compute_overall_max_pain,
)

# ----------------------------------------------------------------------------
# Helpers — small hand-verifiable chain builders.
# ----------------------------------------------------------------------------

def _call(strike: float, oi: int, expiry: str = "2026-08-15") -> dict:
    return {"strike": float(strike), "type": "CALL", "openInterest": oi, "expiry": expiry}


def _put(strike: float, oi: int, expiry: str = "2026-08-15") -> dict:
    return {"strike": float(strike), "type": "PUT", "openInterest": oi, "expiry": expiry}


# ----------------------------------------------------------------------------
# 1. Empty chain
# ----------------------------------------------------------------------------
def test_empty_chain_returns_empty_list():
    assert compute_max_pain_per_expiry([]) == []


# ----------------------------------------------------------------------------
# 2. Single-expiry known answer — HAND-VERIFIED 4th time.
#
# chain  = [(call C=100,OI=1000)+(call C=105,OI=500)+(call C=110,OI=200)
#        + (put S=95,OI=800)+(put S=100,OI=1000)+(put S=105,OI=600)]
# candidates = [95, 100, 105, 110]
#
# K=95 (only puts to the right):
#   call_loss = 0                         (no call strikes < 95)
#   put_loss  = (100-95)*800 + (105-95)*600 = 4000 + 6000 = 10000
#   TOTAL     = 10000
# K=100:
#   call_loss = 0                         (no call strikes < 100; call C=100 NOT < K)
#   put_loss  = (105-100)*600 = 3000      (put S=95: 95>100 false; S=100: false; S=105: true)
#   TOTAL     = 3000  ← minimum
# K=105:
#   call_loss = (105-100)*1000 = 5000     (call C=100 strikes < K)
#   put_loss  = 0                         (no put strikes > K=105; put S=105: 105>105 false)
#   TOTAL     = 5000
# K=110:
#   call_loss = (110-100)*1000 + (110-105)*500 = 10000 + 2500 = 12500
#   put_loss  = 0
#   TOTAL     = 12500
# ⇒ max_pain = K=100 (loss 3000.0). calls_at_strike=1000 (call C=100 only),
#    puts_at_strike=1000 (put S=100 only).
# ----------------------------------------------------------------------------
def test_single_expiry_known_max_pain_pin():
    chain = [
        _call(100, 1000), _call(105, 500), _call(110, 200),
        _put(95, 800),   _put(100, 1000), _put(105, 600),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert len(rows) == 1
    row = rows[0]
    assert row["expiry"] == "2026-08-15"
    assert row["max_pain_strike"] == 100.0
    assert row["total_loss_at_strike"] == 3000.0
    assert row["calls_at_strike"] == 1000  # sum of call OI at strike 100
    assert row["puts_at_strike"] == 1000   # sum of put OI at strike 100


# ----------------------------------------------------------------------------
# 3. Multi-expiry segregation — row count == unique expiry count, values
# don't bleed across the boundary.
# ----------------------------------------------------------------------------
def test_multi_expiry_does_not_bleed():
    chain = [
        # Expiry A: clearly pin at 100 (heavy 100 OI)
        _call(95, 100, "2026-07-20"), _call(100, 5000, "2026-07-20"),
        _call(105, 100, "2026-07-20"),
        _put(95, 100, "2026-07-20"),  _put(100, 5000, "2026-07-20"),
        _put(105, 100, "2026-07-20"),
        # Expiry B: clearly pin at 110 (heavy 110 OI)
        _call(105, 100, "2026-08-15"), _call(110, 5000, "2026-08-15"),
        _call(115, 100, "2026-08-15"),
        _put(105, 100, "2026-08-15"),  _put(110, 5000, "2026-08-15"),
        _put(115, 100, "2026-08-15"),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert [r["expiry"] for r in rows] == ["2026-07-20", "2026-08-15"]
    assert rows[0]["max_pain_strike"] == 100.0
    assert rows[1]["max_pain_strike"] == 110.0


# ----------------------------------------------------------------------------
# 4. Mixed-order input → ascending output.
# ----------------------------------------------------------------------------
def test_expiry_rows_sorted_ascending():
    chain = [
        _call(100, 1000, "2026-08-15"),
        _call(100, 1000, "2026-07-20"),  # earlier than the row above
        _call(100, 1000, "2026-12-31"),  # LEAP, last
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert [r["expiry"] for r in rows] == ["2026-07-20", "2026-08-15", "2026-12-31"]


# ----------------------------------------------------------------------------
# 5. Degenerate tie-break: one candidate strike, value is trivially pinned.
# ----------------------------------------------------------------------------
def test_single_candidate_trivially_pins():
    chain = [
        _call(100, 0),   # zero OI but still in candidate set
        _put(100, 0),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert rows[0]["max_pain_strike"] == 100.0
    assert rows[0]["total_loss_at_strike"] == 0.0


# ----------------------------------------------------------------------------
# 6. Multi-candidate tie-break → LOWER strike wins deterministically.
#
# chain = [(call C=95,OI=1) + (put S=105,OI=1)]
#   candidates = [95, 105]
#   K=95:  call_loss = 0;  put_loss = (105-95)*1 = 10  → total = 10
#   K=105: call_loss = (105-95)*1 = 10;  put_loss = 0 → total = 10
# Three-way tie (loss=10) at K=95 and K=105 → tiebreak picks LOWER → K=95.
# (K=100 also has loss=10 if it were a candidate, but it's not in this chain.)
# ----------------------------------------------------------------------------
def test_tie_break_lower_strike_with_multi_candidate_chain():
    chain = [_call(95, 1), _put(105, 1)]
    rows = compute_max_pain_per_expiry(chain)
    assert rows[0]["max_pain_strike"] == 95.0   # lower strike wins ties
    assert rows[0]["total_loss_at_strike"] == 10.0


# ----------------------------------------------------------------------------
# 7. Zero-OI chain (every contract has 0). Should not crash.
# All losses are 0; tiebreak picks lowest candidate (95).
# ----------------------------------------------------------------------------
def test_zero_oi_chain_does_not_crash():
    chain = [
        _call(95, 0), _call(100, 0), _call(105, 0),
        _put(95, 0),  _put(100, 0),  _put(105, 0),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert len(rows) == 1
    assert rows[0]["max_pain_strike"] == 95.0
    assert rows[0]["total_loss_at_strike"] == 0.0
    assert rows[0]["calls_at_strike"] == 0
    assert rows[0]["puts_at_strike"] == 0


# ----------------------------------------------------------------------------
# 8. Missing ``openInterest`` key → OI=0 fallback. No KeyError.
# ----------------------------------------------------------------------------
def test_missing_oi_key_falls_back_to_zero():
    chain = [
        {"strike": 100.0, "type": "CALL", "expiry": "2026-08-15"},          # no openInterest
        {"strike": 100.0, "type": "PUT",  "expiry": "2026-08-15"},          # no openInterest
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert len(rows) == 1
    assert rows[0]["max_pain_strike"] == 100.0
    assert rows[0]["total_loss_at_strike"] == 0.0
    assert rows[0]["calls_at_strike"] == 0
    assert rows[0]["puts_at_strike"] == 0


# ----------------------------------------------------------------------------
# 9. All-calls asymmetry → max pain at LOWEST candidate.
# put_loss is always 0; call_loss grows monotonically as K rises past
# each call strike. So lowest K wins.
# ----------------------------------------------------------------------------
def test_all_calls_asymmetry_pins_at_lowest_candidate():
    chain = [
        _call(95, 100), _call(100, 100), _call(105, 100), _call(110, 100),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert rows[0]["max_pain_strike"] == 95.0
    assert rows[0]["calls_at_strike"] == 100
    assert rows[0]["puts_at_strike"] == 0


# ----------------------------------------------------------------------------
# 10. All-puts asymmetry → max pain at HIGHEST candidate.
# Higher K ⇔ fewer strikes > K ⇔ lower put_loss.
# ----------------------------------------------------------------------------
def test_all_puts_asymmetry_pins_at_highest_candidate():
    chain = [
        _put(95, 100), _put(100, 100), _put(105, 100), _put(110, 100),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert rows[0]["max_pain_strike"] == 110.0
    assert rows[0]["calls_at_strike"] == 0
    assert rows[0]["puts_at_strike"] == 100


# ----------------------------------------------------------------------------
# 11. Fractional strikes ($0.50 step) preserved without rounding loss.
# ------------------------------------------------------------------------
def test_fractional_strike_preserved():
    chain = [
        _call(12.25, 100), _call(12.50, 100), _call(12.75, 100),
        _put(12.25, 100),  _put(12.50, 100),  _put(12.75, 100),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert rows[0]["max_pain_strike"] == 12.5
    assert isinstance(rows[0]["max_pain_strike"], float)


# ------------------------------------------------------------------------
# 12. Sentinel path: a contract with NO ``expiry`` AND NO ``strike`` lands
# in the "_unknown" bucket with empty candidates → sentinel row at strike 0.0.
# ------------------------------------------------------------------------
def test_unknown_sentinel_for_no_strike_no_expiry_contract():
    chain = [
        {"type": "CALL", "openInterest": 50},         # no expiry, no strike
        _call(100, 100, "2026-08-15"),
    ]
    rows = compute_max_pain_per_expiry(chain)
    expiries = [r["expiry"] for r in rows]
    assert expiries == ["2026-08-15", "_unknown"]
    unknown_row = next(r for r in rows if r["expiry"] == "_unknown")
    assert unknown_row["max_pain_strike"] == 0.0      # sentinel — no strikes
    assert unknown_row["calls_at_strike"] == 0
    assert unknown_row["puts_at_strike"] == 0
    assert unknown_row["total_loss_at_strike"] == 0.0


# ------------------------------------------------------------------------
# 13. Normal path: a contract with NO ``expiry`` but WITH a strike still
# gets a normal max_pain computed for its "_unknown" group.
# ------------------------------------------------------------------------
def test_unknown_group_with_strikes_processes_normally():
    chain = [
        {"strike": 100.0, "type": "CALL", "openInterest": 50},  # no expiry
        _call(100, 100, "2026-08-15"),
    ]
    rows = compute_max_pain_per_expiry(chain)
    unknown_row = next(r for r in rows if r["expiry"] == "_unknown")
    assert unknown_row["max_pain_strike"] == 100.0
    assert unknown_row["calls_at_strike"] == 50


# ------------------------------------------------------------------------
# 14. ``strike`` is None (not missing, present-but-null). The contract
# should be entirely skipped — no KeyError, no TypeError, no row entry
# with ``max_pain_strike=None``.
# ------------------------------------------------------------------------
def test_none_strike_contract_dropped_silently():
    chain = [
        {"strike": None, "type": "CALL", "openInterest": 100, "expiry": "2026-08-15"},
        _call(100, 100, "2026-08-15"),
    ]
    rows = compute_max_pain_per_expiry(chain)
    assert len(rows) == 1, "single-expiry row expected (None-strike dropped)"
    row = rows[0]
    assert row["expiry"] == "2026-08-15"
    assert row["max_pain_strike"] == 100.0
    assert row["calls_at_strike"] == 100
    assert row["puts_at_strike"] == 0


# ------------------------------------------------------------------------
# 15. ``compute_overall_max_pain`` on the hand-verified chain (same data
# as case 2) — top-line number is K=100, loss=3000.
# ------------------------------------------------------------------------
def test_overall_max_pain_hand_verified_chain():
    chain = [
        _call(100, 1000), _call(105, 500), _call(110, 200),
        _put(95, 800),   _put(100, 1000), _put(105, 600),
    ]
    out = compute_overall_max_pain(chain)
    assert out["max_pain_strike"] == 100.0
    assert out["total_loss_at_strike"] == 3000.0
    assert out["calls_at_strike"] == 1000
    assert out["puts_at_strike"] == 1000


# ------------------------------------------------------------------------
# 16. ``compute_overall_max_pain`` empty / no-strike inputs → empty dict.
# ------------------------------------------------------------------------
def test_overall_max_pain_empty_returns_empty_dict():
    assert compute_overall_max_pain([]) == {}
    assert compute_overall_max_pain([{"strike": None}]) == {}


# ------------------------------------------------------------------------
# Type-alias sanity (cheap regression for downstream dialect drift).
# ------------------------------------------------------------------------
@pytest.mark.parametrize("alias", ["CALL", "C", "call", "CALLS", "CE"])
def test_type_alias_call(alias):
    contract = {"strike": 100, "type": alias, "openInterest": 100, "expiry": "2026-08-15"}
    assert compute_overall_max_pain([contract])["max_pain_strike"] == 100.0


@pytest.mark.parametrize("alias", ["PUT", "P", "put", "PUTS", "PE"])
def test_type_alias_put(alias):
    contract = {"strike": 100, "type": alias, "openInterest": 100, "expiry": "2026-08-15"}
    assert compute_overall_max_pain([contract])["max_pain_strike"] == 100.0

# ---------------------------------------------------------------------------
# 17. ``compute_overall_max_pain`` defends against None-strike contracts —
# the central filter inside ``_total_loss_at_strike`` (post round-2
# hardening) keeps both per-expiry AND overall paths safe even if a caller
# forgets to pre-filter the chain. Critical regression guard — also locks
# the OI-at-strike path so a future refactor cannot leak OI from None-strike
# contracts through the call/put-at-strike counters.
# ---------------------------------------------------------------------------
def test_overall_max_pain_handles_none_strike_contracts():
    chain = [
        _call(95, 1),
        {"strike": None, "type": "PUT", "openInterest": 50},
        {"strike": None, "type": "CALL", "openInterest": 9999},
    ]
    # If the central filter regresses, this raises TypeError (`K > None`).
    out = compute_overall_max_pain(chain)
    assert out["max_pain_strike"] == 95.0
    assert out["calls_at_strike"] == 1    # only the real _call(95,1); None OI=9999 must NOT leak
    assert out["puts_at_strike"] == 0
    assert out["total_loss_at_strike"] == 0.0

