"""
backend/services/consensus_pricing.py

OI-weighted expected/consensus price per expiration (steal-list #6)
====================================================================

For each expiry in an options chain, computes the OI-premium-weighted
"expected price" the whole chain is positioned around::

    call_expect_price(c)        = strike_c  + premium_c
    put_expect_price(p)         = strike_p  - premium_p
    option_expect_price_expiry  =
        [SUM(call_expect * call_OI) + SUM(put_expect * put_OI)] / SUM(all_OI)

This is a NEW signal that is GENUINELY-DISTINCT from the other three
"consensus-style" numbers floww already computes:

  * GEX "King node"             — *gamma* concentration (dealer-side)
  * Max-pain strike             — total intrinsic-loss-at-expiry minimizer
  * Auction-cleared mid price   — per-row quote, NOT weighted

Tracking this scalar per-expiry + day-over-day shows where positioning
CONSENSUS is drifting (separate from where dealer gamma is concentrated,
separate from where optional pain is highest). The per-expiry OI mix and
average premiums per side are returned alongside the scalar so the row
is self-describing without needing a second roundtrip.

Steal from: ``czong_option_chain_unusual_activity_detect`` —
            ``main-google.py:13-33`` + ``main-yahoo.py:22-53``.
Lands in floww: ``GET /api/chain_consensus/{ticker}?expiries=N`` on
                ``backend/routes/steal_three.py`` (canonical :8000).

Audit:        ``docs/reports/2026-07-11-steal-list-integration-roadmap.md`` #6
              ``backend/tests/services/test_consensus_pricing.py`` (16 cases).

This module is PURE-LOGIC: no yfinance calls, no DB writes, no logging
side-effects (so it's trivially testable and the route layer owns the
external I/O).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

# ----------------------------------------------------------------------------
# Defensive key resolvers (mirror the conventions in services/max_pain.py and
# services/gex_aggregator.py so the same chain payload formats work).
# ----------------------------------------------------------------------------
_OI_KEYS: tuple[str, ...] = (
    "openInterest",
    "open_interest",
    "oi",
    "OI",
)
_EXPIRY_KEYS: tuple[str, ...] = (
    "expiry",
    "expiration",
    "expireDate",
    "exp_date",
)
_TYPE_KEYS: tuple[str, ...] = (
    "type",
    "optionType",
    "kind",
    "side",
    "putCall",
)
_BID_KEYS: tuple[str, ...] = ("bid", "bidPrice")
_ASK_KEYS: tuple[str, ...] = ("ask", "askPrice")
_LAST_KEYS: tuple[str, ...] = ("lastPrice", "last", "price")


def _first_present(d: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    """Return the first non-None value among ``keys`` from dict ``d``."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _is_call(d: dict) -> bool:
    """Best-effort call/put classifier from the yfinance / cvforge dialects.

    Unknown tokens default to PUT so an ambiguous chain doesn't bias the
    ``(strike + premium)`` formula upward into a call-territory consensus
    (calls add premium, so mis-classifying a put as a call inflates the
    numerator). Tests pin per-token behavior — see
    ``test_consensus_pricing.py::test_type_aliases``.
    """
    t = _first_present(d, _TYPE_KEYS, "")
    s = str(t).upper().strip()
    if s in {"C", "CALL", "CALLS", "CE"}:
        return True
    if s in {"P", "PUT", "PUTS", "PE"}:
        return False
    return False


def _is_put(d: dict) -> bool:
    return not _is_call(d)


def _oi(contract: dict) -> float:
    """Open interest for a contract, falling back to 0 on missing/non-numeric.

    OI is non-negative by definition, so any negative raw value is
    clamped to 0 (defensive against bad upstream providers).
    """
    raw = _first_present(contract, _OI_KEYS, 0)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(v, 0.0)


def _strike(contract: dict) -> float | None:
    raw = contract.get("strike")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _expiry_key(contract: dict) -> str:
    """ISO date string key, falling back to a sentinel for unlabeled rows."""
    exp = _first_present(contract, _EXPIRY_KEYS, None)
    if exp is None:
        return "_unknown"
    if isinstance(exp, datetime):
        return exp.strftime("%Y-%m-%d")
    if isinstance(exp, date):
        return exp.strftime("%Y-%m-%d")
    return str(exp)


def _premium(contract: dict) -> float:
    """Resolve the option premium to use in ``(strike ± premium)`` formulas.

    Order (mirrors IV-mid route's existing logic in
    ``backend/routes/steal_three.py``):

      1. ``mid = (bid + ask) / 2``   when both bid AND ask are present
                                     and > 0  (real-time dealer quote)
      2. ``lastPrice``                fallback (stale-quote last sale)
      3. ``0.0``                      both missing — defensible: a contract
                                     with no premium contributes nothing to
                                     the consensus numerator.
    """
    bid = _first_present(contract, _BID_KEYS, 0)
    ask = _first_present(contract, _ASK_KEYS, 0)
    try:
        bid_f = float(bid) if bid is not None else 0.0
    except (TypeError, ValueError):
        bid_f = 0.0
    try:
        ask_f = float(ask) if ask is not None else 0.0
    except (TypeError, ValueError):
        ask_f = 0.0
    if bid_f > 0.0 and ask_f > 0.0:
        return 0.5 * (bid_f + ask_f)
    last = _first_present(contract, _LAST_KEYS, 0)
    try:
        return max(float(last), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _contracts_by_expiry(chain: list[dict]) -> dict[str, list[dict]]:
    """Group contracts by ISO expiry string.

    Contracts missing an ``expiry``/``expiration``/``expireDate`` key are
    grouped under the ``"_unknown"`` sentinel so the caller can still see
    them rather than silently dropping them.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for c in chain:
        grouped[_expiry_key(c)].append(c)
    return grouped


def _row(
    expiry_key: str,
    call_contracts: list[dict],
    put_contracts: list[dict],
) -> dict[str, Any]:
    """Compute the per-expiry consensus row.

    ``call_contracts`` and ``put_contracts`` MUST already be stripped of
    None-strike contracts (otherwise ``strike + premium`` would crash).
    Consensus price is ``None`` (returned numerically as 0.0 for shape
    uniformity) when total_oi == 0 — no fabrication.
    """
    call_oi_total = sum(_oi(c) for c in call_contracts)
    put_oi_total = sum(_oi(c) for c in put_contracts)
    total_oi = call_oi_total + put_oi_total

    if total_oi > 0:
        # Per-leg expected price x OI, summed over both sides.
        call_numerator = sum(
            (_strike(c) + _premium(c)) * _oi(c)
            for c in call_contracts
            if _strike(c) is not None
        )
        put_numerator = sum(
            (_strike(c) - _premium(c)) * _oi(c)
            for c in put_contracts
            if _strike(c) is not None
        )
        consensus_price = (call_numerator + put_numerator) / total_oi
        # Side-aware average premium tells the caller "why" the consensus
        # diverged from the strike-mid: a put-heavy chain with high
        # premiums will pull consensus LOWER, a call-heavy chain with
        # high premiums will pull it HIGHER.
        if call_oi_total > 0:
            avg_call_premium = sum(
                _premium(c) * _oi(c) for c in call_contracts
                if _strike(c) is not None
            ) / call_oi_total
        else:
            avg_call_premium = 0.0
        if put_oi_total > 0:
            avg_put_premium = sum(
                _premium(c) * _oi(c) for c in put_contracts
                if _strike(c) is not None
            ) / put_oi_total
        else:
            avg_put_premium = 0.0
        return {
            "expiry": expiry_key,
            "consensus_price": round(float(consensus_price), 4),
            "total_oi": int(total_oi),
            "call_oi": int(call_oi_total),
            "put_oi": int(put_oi_total),
            "avg_call_premium": round(float(avg_call_premium), 4),
            "avg_put_premium": round(float(avg_put_premium), 4),
        }
    # No OI anywhere — return a sentinel-shaped row (zeroed, no consensus).
    return {
        "expiry": expiry_key,
        "consensus_price": 0.0,
        "total_oi": 0,
        "call_oi": 0,
        "put_oi": 0,
        "avg_call_premium": 0.0,
        "avg_put_premium": 0.0,
    }


def compute_consensus_per_expiry(chain: list[dict]) -> list[dict[str, Any]]:
    """Return one row per expiry in ``chain``, sorted by expiry ascending.

    Each row::

        {"expiry": "YYYY-MM-DD",
         "consensus_price": float,   # OI-weighted (strike ± premium)
         "total_oi": int,             # call_oi + put_oi
         "call_oi": int,
         "put_oi":  int,
         "avg_call_premium": float,   # OI-weighted premium on call side
         "avg_put_premium":  float}   # OI-weighted premium on put side

    Edge cases:
      * ``chain`` empty or all rows lack ``strike`` → ``[]``
      * Expiry has OI but no recognized strike → sentinel row at 0.0
      * Contracts missing premium fields → premium resolves to 0 (defensive)
      * Negative OI upstream → clamped to 0
      * Unknown type tokens (e.g. ``"X"``) → default to PUT (same as max_pain.py)
    """
    if not chain:
        return []

    grouped = _contracts_by_expiry(chain)
    out: list[dict[str, Any]] = []
    for exp_key in sorted(grouped.keys()):
        contracts = grouped[exp_key]

        # Defensive: build side lists AND drop None-strike contracts
        # simultaneously so the ``_strike(c) + _premium(c)`` expression
        # never crashes on None. Also rejects unknown-type contracts so
        # they don't silently bias the consensus via the PUT fallback.
        call_contracts = [
            c for c in contracts
            if _is_call(c) and _strike(c) is not None
        ]
        put_contracts = [
            c for c in contracts
            if _is_put(c) and _strike(c) is not None
        ]
        out.append(_row(exp_key, call_contracts, put_contracts))

    return out


def compute_overall_consensus(chain: list[dict]) -> dict[str, Any]:
    """Compute a single over-all-expiry chain consensus price.

    Treats the entire chain as one big pool — useful as a top-line
    SUMMARY number per ticker, but does *not* respect per-expiry
    positioning dynamics. For per-expiry analysis use
    :func:`compute_consensus_per_expiry`.

    Returns ``{"consensus_price", "total_oi", "call_oi", "put_oi",
    "avg_call_premium", "avg_put_premium"}`` or ``{}`` on empty /
    all-None-strike input.
    """
    if not chain:
        return {}

    call_contracts = [
        c for c in chain
        if _is_call(c) and _strike(c) is not None
    ]
    put_contracts = [
        c for c in chain
        if _is_put(c) and _strike(c) is not None
    ]
    if not call_contracts and not put_contracts:
        return {}

    return _row("overall", call_contracts, put_contracts)
