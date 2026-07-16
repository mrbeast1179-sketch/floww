"""
backend/services/max_pain.py

Max Pain per expiration (steal-list rank #9 — partial)
======================================================

For each candidate expiry in an options chain, computes the strike ``K``
that minimizes the total intrinsic-loss-to-option-holders-at-K
(equivalently, maximizes total payout to option writers at expiry).
This is the OI-weighted "pin magnet" — distinct from the GEX "King node"
which is *gamma*-based; the two often disagree and the disagreement is a
signal. Daily drift of max-pain into expiry will be a follow-up once the
scalar computation lands.

Steal from: asad70/Options-Max-Pain-Calculator ``OptionsMaxPainCalc.py`` +
            ZubZubZuberi/MaxPainHistory (drift-tracking portion deferred).

Lands in floww: ``GET /api/max_pain/{ticker}`` on
                 ``backend/routes/steal_three.py`` (canonical :8000).
Audit:         ``docs/reports/2026-07-11-steal-list-integration-roadmap.md`` #9.
                 ``backend/tests/services/test_max_pain.py`` (10 + 2 cases).

This module is PURE-LOGIC: no yfinance calls, no DB writes, no logging
side-effects (so it's trivially testable and the route layer owns the
external I/O). Drift tracking into DuckDB is intentionally deferred
(see .md #9 PARTIAL block) — that work would pull in the
``execute_write`` audit pattern + a schema model, which belong in their
own change rather than mixed into this one.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any

# ----------------------------------------------------------------------------
# Defensive key resolvers (mirror the conventions in services/gex_dual.py and
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


def _first_present(d: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    """Return the first non-None value among ``keys`` from dict ``d``."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _is_call(d: dict) -> bool:
    """Best-effort call/put classifier from the yfinance / cvforge dialects.

    Unknown tokens default to PUT so an ambiguous chain doesn't silently
    bias the loss curve upward toward strike-K (call-biased). Tests pin
    per-token behavior — see test_max_pain.py::test_type_aliases.
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


def _candidate_strikes(contracts: list[dict]) -> list[float]:
    """Distinct, ascending candidate strikes for max-pain evaluation.

    Skips contracts whose strike is missing or non-numeric — those rows
    cannot contribute to the candidate set.
    """
    seen: set[float] = set()
    out: list[float] = []
    for c in contracts:
        k = _strike(c)
        if k is None:
            continue
        if k not in seen:
            seen.add(k)
            out.append(k)
    return sorted(out)


def _total_loss_at_strike(calls: list[dict], puts: list[dict], K: float) -> float:
    """Total intrinsic loss to option holders if spot closes at ``K`` at expiry.

    Per contract:
      * Call with strike ``C``: intrinsic = ``max(K - C, 0)`` (loss to holder
        when ``K > C``: writer pays (K-C) per contract).
      * Put  with strike ``C``: intrinsic = ``max(C - K, 0)`` (loss to holder
        when ``C > K``: writer pays (C-K) per contract).

    Total = SUM over all contracts of (intrinsic × OI). Smaller total = the
    strike where the *least* money flows at expiry = the "max pain" pin point
    (= the strike where option *writers* are most exposed — opposite side).

    Defensive: ``c["strike"] is not None`` filter ensures the comparison
    never raises on a contract whose strike is missing/None — callers may
    or may not pre-filter, so the safety lives at the iteration site.
    """
    call_loss = sum(
        (K - c["strike"]) * _oi(c)
        for c in calls
        if c["strike"] is not None and c["strike"] < K
    )
    put_loss = sum(
        (c["strike"] - K) * _oi(c)
        for c in puts
        if c["strike"] is not None and c["strike"] > K
    )
    return call_loss + put_loss


def compute_max_pain_per_expiry(chain: list[dict]) -> list[dict[str, Any]]:
    """Return one row per expiry in ``chain``, sorted by expiry ascending.

    Each row::

        {"expiry": "YYYY-MM-DD", "max_pain_strike": float,
         "total_loss_at_strike": float (.2dp),
         "calls_at_strike": int  (sum of call OI at the winning strike),
         "puts_at_strike":  int}

    Edge cases:
      * ``chain`` empty or all rows lack ``strike``/``expiry`` → ``[]``
      * Expiry with contracts but no ``strike`` → sentinel row at strike 0.0
      * Ties at minimum loss → deterministic tie-break to LOWER strike
      * Contracts missing ``openInterest`` → OI 0 (no KeyError)
      * Negative OI upstream → clamped to 0
    """
    if not chain:
        return []

    grouped = _contracts_by_expiry(chain)
    out: list[dict[str, Any]] = []
    for exp_key in sorted(grouped.keys()):
        contracts = grouped[exp_key]
        # Defensive: filter None-strike contracts out of calls/puts in addition
        # to the candidate set, so the loss-iteration
        # `(K - c["strike"]) * _oi(c)` never crashes on `K > None`.
        calls = [c for c in contracts if _is_call(c) and _strike(c) is not None]
        puts = [c for c in contracts if _is_put(c) and _strike(c) is not None]
        candidates = _candidate_strikes(contracts)

        if not candidates:
            # Preserve the expiry in the output so callers see "we saw X but
            # had no strike info" rather than silently skipping.
            out.append({
                "expiry": exp_key,
                "max_pain_strike": 0.0,
                "total_loss_at_strike": 0.0,
                "calls_at_strike": 0,
                "puts_at_strike": 0,
            })
            continue

        # Find K minimizing loss; tie-break to lower K (deterministic, ascending).
        best_K = candidates[0]
        best_loss = _total_loss_at_strike(calls, puts, best_K)
        for K in candidates[1:]:
            loss = _total_loss_at_strike(calls, puts, K)
            if loss < best_loss or (loss == best_loss and best_K > K):
                best_K, best_loss = K, loss

        out.append({
            "expiry": exp_key,
            "max_pain_strike": round(float(best_K), 4),
            "total_loss_at_strike": round(float(best_loss), 2),
            "calls_at_strike": int(sum(_oi(c) for c in calls if _strike(c) == best_K)),
            "puts_at_strike":  int(sum(_oi(c) for c in puts  if _strike(c) == best_K)),
        })

    return out


def compute_overall_max_pain(chain: list[dict]) -> dict[str, Any]:
    """Compute a single over-all-expiry max-pain strike for dashboard use.

    Treats the entire chain as one big pool — useful as a top-line PIN
    number per ticker (matches how Flowseeker's sidebar renders `max_pain`),
    but does *not* respect per-expiry pinning dynamics. For per-expiry
    analysis use :func:`compute_max_pain_per_expiry`.

    Returns ``{"max_pain_strike", "total_loss_at_strike", "calls_at_strike",
    "puts_at_strike"}`` or ``{}`` on empty/missing-strike input.
    """
    if not chain:
        return {}

    calls = [c for c in chain if _is_call(c)]
    puts = [c for c in chain if _is_put(c)]
    candidates = _candidate_strikes(chain)
    if not candidates:
        return {}

    best_K = candidates[0]
    best_loss = _total_loss_at_strike(calls, puts, best_K)
    for K in candidates[1:]:
        loss = _total_loss_at_strike(calls, puts, K)
        if loss < best_loss or (loss == best_loss and best_K > K):
            best_K, best_loss = K, loss

    return {
        "max_pain_strike": round(float(best_K), 4),
        "total_loss_at_strike": round(float(best_loss), 2),
        "calls_at_strike": int(sum(_oi(c) for c in calls if _strike(c) == best_K)),
        "puts_at_strike":  int(sum(_oi(c) for c in puts  if _strike(c) == best_K)),
    }
