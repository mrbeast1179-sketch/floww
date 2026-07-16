"""
backend/services/consensus_pricing_daily.py

Consensus-Pricing Daily Snapshot tracking — completes deferred of steal-list #6
================================================================================

The PARTIAL chain-consensus ship landed `compute_consensus_per_expiry(chain)`
and `compute_overall_consensus(chain)` that compute per-snapshot OI-weighted
call/put consensus prices, but had no historical accumulation layer. This
service closes that gap:

  1. `init_consensus_daily_table(engine)` — CREATE TABLE IF NOT EXISTS +
     indexes + PRIMARY KEY (snapshot_date, symbol, expiry) where
     expiry=NULL marks the OVERALL row (vs ISO-string for per-expiry rows).
  2. `accumulate_today(engine, ticker, contracts, snapshot_date=None)` —
     UPSERTs today's snapshot idempotently via DuckDB ON CONFLICT. Internally
     calls `compute_consensus_per_expiry` + `compute_overall_consensus` to
     write one row per expiry + one row for the overall blend.
  3. `read_recent_drift(engine, ticker, n_days, expiry=None)` — returns the
     last ``n_days`` of snapshots for ``ticker``. If ``expiry`` is None,
     returns ALL rows (per-expiry + overall); if a specific expiry string is
     supplied, returns ONLY those rows matching that expiry + the overall row.
  4. `compute_consensus_drift(snapshots)` — pure-logic drift analytics
     (1d delta, Nd delta, current-skew, skew-change, convergence-score,
     direction-label) decoupled from any DB I/O.

Schema::

    CREATE TABLE IF NOT EXISTS consensus_daily (
        snapshot_date          DATE,
        symbol                 VARCHAR,
        expiry                 VARCHAR,    -- ISO "YYYY-MM-DD" or NULL = overall
        consensus_price        DOUBLE,
        total_oi               BIGINT,
        call_oi                BIGINT,
        put_oi                 BIGINT,
        avg_call_premium       DOUBLE,
        avg_put_premium        DOUBLE,
        PRIMARY KEY (snapshot_date, symbol, expiry)
    );

Drift-signal semantics:

  drift_consensus_1d        = today_consensus - yesterday_consensus
  drift_consensus_Nd        = today_consensus - oldest_consensus
  drift_skew_today          = abs(today_call_premium - today_put_premium)
  drift_skew_change_1d      = today_skew - yesterday_skew       (skew tilt)
  convergence_score         = clamp(1 - |today - spot| / (0.05 * spot), 0, 1)
  (positive = consensus and spot coinciding — pair with max_pain_drift's
  pin_probability_score for a two-pin magnet read.)
  direction_label = "call_side_pulling_up"   if today_consensus - today_spot > 0.005*spot
                  AND avg_call_premium > avg_put_premium,
                     "put_side_pulling_down"   if today_consensus - today_spot < -0.005*spot
                  AND avg_put_premium > avg_call_premium,
                     "stable"                  otherwise (within ±0.5% of spot).

The threshold of 0.5% of spot matches the convention used by
``max_pain_drift._pin_score`` and ``server.py:782-790``'s implied-move band.

Steal intent: deferred portion of rank #6 — no upstream repo beyond
``czong_option_chain_unusual_activity_detect`` (already integrated).
Part-of-day floww provenance: ``consensus_pricing.compute_*_consensus``.

Audit: ``backend/tests/services/test_consensus_pricing_daily.py``
(±18 cases — empty/single/2-snap same-day OVERWRITE/7-day stable pull-up/
pull-down/balanced/skew-flat-to-tilted/high-convergence/auto-sort/reverse-
chronological/NaN-consensus/missing-field/future-dated/documented-keys +
init-idempotent/accumulate-UPSERT/three-ticker-isolated/read-recent-N/all-
expiries/expiry-filter/empty-table/DB-exception-suppressed).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from services.consensus_pricing import (
    compute_consensus_per_expiry,
    compute_overall_consensus,
)
from services.max_pain_drift import (
    _coerce_to_date,
    _safe_float,
    _to_date,
)

logger = logging.getLogger(__name__)


# Re-export the imported helpers to keep the public surface local-named —
# callers (tests + future services) can import from consensus_pricing_daily
# without depending on max_pain_drift directly.
__all__ = [
    "compute_consensus_drift",
    "accumulate_today",
    "read_recent_drift",
    "init_consensus_daily_table",
    "TABLE_NAME",
    "CREATE_TABLE_SQL",
    "CREATE_INDEX_SQL_LIST",
    "UPSERT_SQL",
]


# ─────────────────────────────────────────────────────────────────────
# Constants — table-name decisions are unprefixed (matches ticks/chains/
# flow_prints/vpin_buckets/max_pain_daily convention; the .md
# "floww.consensus_daily" naming was the spec author's shorthand, not a
# real DuckDB schema qualifier).
# ─────────────────────────────────────────────────────────────────────

TABLE_NAME = "consensus_daily"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS consensus_daily (
    snapshot_date          DATE,
    symbol                 VARCHAR,
    expiry                 VARCHAR,
    consensus_price        DOUBLE,
    total_oi               BIGINT,
    call_oi                BIGINT,
    put_oi                 BIGINT,
    avg_call_premium       DOUBLE,
    avg_put_premium        DOUBLE,
    PRIMARY KEY (snapshot_date, symbol, expiry)
)
"""

CREATE_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_consensus_daily_symbol "
    "ON consensus_daily(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_consensus_daily_date "
    "ON consensus_daily(snapshot_date)",
    "CREATE INDEX IF NOT EXISTS idx_consensus_daily_expiry "
    "ON consensus_daily(symbol, expiry)",
)

UPSERT_SQL = """
INSERT INTO consensus_daily
    (snapshot_date, symbol, expiry, consensus_price,
     total_oi, call_oi, put_oi,
     avg_call_premium, avg_put_premium)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, symbol, expiry) DO UPDATE SET
    consensus_price = excluded.consensus_price,
    total_oi = excluded.total_oi,
    call_oi = excluded.call_oi,
    put_oi = excluded.put_oi,
    avg_call_premium = excluded.avg_call_premium,
    avg_put_premium = excluded.avg_put_premium
"""


# ─────────────────────────────────────────────────────────────────────
# Constants — DuckDB row-fetch sizing.
# ─────────────────────────────────────────────────────────────────────
# Per-snapshot ceiling for ``read_recent_drift``: how many rows a single
# (date, symbol) pair could plausibly hold. Empirically 8 listed expiries
# + 1 OVERALL sentinel row + a comfortable buffer ≅ 32. Keep the constant
# named so future callers can tune it without re-finding a magic number.
_ROWS_PER_DATE_CEILING = 32


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O helpers — operate on the engine objects supplied.
# ─────────────────────────────────────────────────────────────────────


def init_consensus_daily_table(engine) -> None:
    """Create the table + indexes. Idempotent — multiple calls are safe."""
    engine.execute_write(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL_LIST:
        engine.execute_write(stmt)


def _build_row_for_upsert(
    snapshot_date: date,
    ticker: str,
    expiry: str | None,
    row: dict[str, Any],
) -> tuple | None:
    """Build the 9-tuple row for UPSERT. Returns None if consensus_price
    is NaN/missing/None — defensible no-op under the same logic as
    max_pain_drift.accumulate_today's strike-is-None no-op guard."""
    warnings: list[str] = []
    consensus_price = _safe_float(
        "consensus_price", row, row.get("consensus_price"), warnings,
    )
    total_oi_raw = _safe_float(
        "total_oi", row, row.get("total_oi"), warnings,
    )
    call_oi_raw = _safe_float(
        "call_oi", row, row.get("call_oi"), warnings,
    )
    put_oi_raw = _safe_float(
        "put_oi", row, row.get("put_oi"), warnings,
    )
    avg_call_prem = _safe_float(
        "avg_call_premium", row, row.get("avg_call_premium"), warnings,
    )
    avg_put_prem = _safe_float(
        "avg_put_premium", row, row.get("avg_put_premium"), warnings,
    )
    if warnings:
        for w in warnings:
            logger.warning(
                f"_build_row_for_upsert({ticker}, {expiry}): {w}"
            )
    if consensus_price is None:
        # consensus_price is the load-bearing column; if it's missing we
        # can't reason about the row. Defensive no-op matches
        # max_pain_drift.accumulate_today's strike-is-None guard.
        return None
    return (
        snapshot_date,
        ticker.upper(),
        expiry if expiry is not None else "",
        consensus_price,
        int(total_oi_raw) if total_oi_raw is not None else 0,
        int(call_oi_raw) if call_oi_raw is not None else 0,
        int(put_oi_raw) if put_oi_raw is not None else 0,
        avg_call_prem if avg_call_prem is not None else 0.0,
        avg_put_prem if avg_put_prem is not None else 0.0,
    )


def accumulate_today(
    engine,
    ticker: str,
    contracts: list[dict[str, Any]],
    snapshot_date: date | None = None,
) -> None:
    """UPSERT today's consensus snapshot for ``ticker`` into ``consensus_daily``.

    Internally calls ``compute_consensus_per_expiry`` + ``compute_overall_consensus``
    (both already imported from the ``consensus_pricing`` sibling module, so
    the network AND math both happen at the route layer — this is the DB
    write layer only).

    ``snapshot_date`` defaults to today (local date). The UPSERT pattern
    means re-running on the same day OVERWRITES today's rows with the
    freshest numbers — no duplicate rows, no cron-restart litter.

    Writes one row per expiry (expiry = "YYYY-MM-DD") PLUS one row for
    the overall blend (expiry = "" — empty string per DuckDB NULL
    convention; checks at read-time test for ``expiry == ""`` or
    ``expiry IS NULL``).
    """
    if snapshot_date is None:
        snapshot_date = date.today()
    if not contracts:
        # Empty chain — defensive no-op (don't write empty rows).
        return

    per_expiry = compute_consensus_per_expiry(contracts)
    overall = compute_overall_consensus(contracts)
    if not per_expiry and not overall:
        return

    rows_to_write: list[tuple] = []
    for pe in per_expiry:
        built = _build_row_for_upsert(
            snapshot_date, ticker, pe.get("expiry"), pe
        )
        if built is not None:
            rows_to_write.append(built)
    if overall:
        # Empty string marker for "overall" — DuckDB has no enum column
        # for this kind of dimension so a sentinel string is the cleanest.
        built = _build_row_for_upsert(
            snapshot_date, ticker, "", overall
        )
        if built is not None:
            rows_to_write.append(built)

    if not rows_to_write:
        return
    engine.execute_write(UPSERT_SQL, rows_to_write)


def read_recent_drift(
    engine,
    ticker: str,
    n_days: int = 14,
    expiry: str | None = None,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Return the last ``n_days`` of ``consensus_daily`` rows for ``ticker``.

    Forward-chronological (oldest first) so the drift math reads naturally.
    Returns ``[]`` on DB error / empty table / unreachable symbol.

    Args:
        engine: a DuckDBEngine instance from services.duckdb_engine.
        ticker: row-keyed symbol (e.g. "SPY").
        n_days: number of distinct snapshot dates to fetch (rows-per-date
            may be >1 when expiry=None is passed because per-expiry rows
            are returned alongside the overall row).
        expiry: optional filter — if set, only rows with matching expiry
            string come back, plus the overall row (expiry=""). If None,
            all rows for the ticker come back.

    Returns:
        List of dicts, oldest first, normalised so ``snapshot_date`` is a
        plain ``datetime.date`` (not pd.Timestamp — see _coerce_to_date).
    """
    if n_days <= 0:
        return []
    # Date-filter: cut off to "the last n_days" so the LIMIT multiplier
    # bounds row count per date, not total fetch. This matches the time-
    # series semantics the caller asked for: n_days is "n distinct dates
    # back from today", not "n arbitrary rows". ``today`` is injectable so
    # tests with fixed fixture dates stay deterministic across midnight
    # (the 2026-07-16 rollover broke the original real-clock version).
    if today is None:
        today = date.today()
    cutoff = today - timedelta(days=n_days)
    sql = (
        f"SELECT snapshot_date, symbol, expiry, consensus_price, "
        f"total_oi, call_oi, put_oi, avg_call_premium, avg_put_premium "
        f"FROM {TABLE_NAME} "
        f"WHERE symbol = ? "
        f"AND snapshot_date > ? "
        f"ORDER BY snapshot_date DESC, expiry DESC "
        f"LIMIT ?"
    )
    try:
        rows = engine.query(
            sql,
            [ticker.upper(), cutoff, n_days * _ROWS_PER_DATE_CEILING],
        )
        rows = [
            {**r, "snapshot_date": _coerce_to_date(r.get("snapshot_date"))}
            for r in rows
        ]
        if expiry is not None:
            # Per-expiry filter: keep rows whose expiry string matches OR
            # whose expiry is the overall sentinel (empty string). This
            # means a per-expiry query also returns the overall row, so
            # the drift math has a baseline.
            expiry_key = expiry
            rows = [
                r for r in rows
                if (r.get("expiry") or "") == expiry_key
                or (r.get("expiry") or "") == ""
            ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover (defensive)
        logger.warning(
            f"read_recent_drift({ticker}): {type(exc).__name__}: {exc}"
        )
        return []


# ─────────────────────────────────────────────────────────────────────
# Pure-logic drift math — no I/O, fully testable.
# ─────────────────────────────────────────────────────────────────────


def compute_consensus_drift(
    snapshots: list[dict[str, Any]],
    today_spot: float | None = None,
    spot_convergence_threshold_pct: float = 0.005,
) -> dict[str, Any]:
    """Compute drift analytics from a list of dated consensus snapshots.

    Args:
        snapshots: list of {snapshot_date, symbol, expiry, consensus_price,
            avg_call_premium, avg_put_premium, ...} dicts. Must be sorted
            ASC by ``(snapshot_date, expiry)`` but auto-sort is applied
            defensively.
        today_spot: optional override for today's spot. If None, the
            drift math returns convergence_score=None + drift_skew_today
            from the most-recent snapshot's premium columns (no spot is
            stored on consensus_daily rows today — see TODO).
        spot_convergence_threshold_pct: 0.5% of spot by default. Matches
            floww's max_pain_drift convention.

    Returns:
        {
            "today_consensus":   float|None,
            "today_call_premium": float|None,
            "today_put_premium": float|None,
            "today_spot":         float|None,
            "yesterday_consensus": float|None,
            "drift_consensus_1d": float|None,
            "drift_consensus_Nd": float|None,
            "drift_skew_today":    float|None,
            "drift_skew_change_1d": float|None,
            "convergence_score":   float,    # 0..1
            "direction_label":     str,
            "n_days_covered":      int,
            "warnings":            list[str],
        }
    """
    warnings: list[str] = []

    if not isinstance(snapshots, list):
        return {
            "today_consensus": None, "today_call_premium": None,
            "today_put_premium": None, "today_spot": None,
            "yesterday_consensus": None,
            "drift_consensus_1d": None, "drift_consensus_Nd": None,
            "drift_skew_today": None, "drift_skew_change_1d": None,
            "convergence_score": 0.0,
            "direction_label": "insufficient_data",
            "n_days_covered": 0,
            "warnings": ["snapshots must be a list"],
        }

    # Filter + clean.
    cleaned: list[dict[str, Any]] = []
    today = date.today()
    for raw in snapshots:
        if not isinstance(raw, dict):
            warnings.append("non-dict snapshot skipped")
            continue
        snap_date = _to_date(
            raw.get("snapshot_date"), "snapshot_date", warnings,
        )
        if snap_date is None:
            continue
        if snap_date > today:
            warnings.append(f"future-dated snapshot dropped: {snap_date}")
            continue
        consensus_price = _safe_float(
            "consensus_price", raw, raw.get("consensus_price"), warnings,
        )
        if consensus_price is None:
            warnings.append(
                f"consensus_price missing/NaN on {snap_date} — dropped"
            )
            continue
        avg_call_premium = _safe_float(
            "avg_call_premium", raw,
            raw.get("avg_call_premium"), warnings,
        )
        avg_put_premium = _safe_float(
            "avg_put_premium", raw,
            raw.get("avg_put_premium"), warnings,
        )
        total_oi = _safe_float(
            "total_oi", raw, raw.get("total_oi"), warnings,
        )
        call_oi = _safe_float(
            "call_oi", raw, raw.get("call_oi"), warnings,
        )
        put_oi = _safe_float(
            "put_oi", raw, raw.get("put_oi"), warnings,
        )
        cleaned.append({
            "snapshot_date": snap_date,
            "consensus_price": consensus_price,
            "avg_call_premium": avg_call_premium,
            "avg_put_premium": avg_put_premium,
            "total_oi": total_oi,
            "call_oi": call_oi,
            "put_oi": put_oi,
            "expiry": raw.get("expiry"),
        })

    cleaned.sort(
        key=lambda r: (r["snapshot_date"], r.get("expiry") or "")
    )

    n = len(cleaned)
    base_shape: dict[str, Any] = {
        "today_consensus": None, "today_call_premium": None,
        "today_put_premium": None, "today_spot": None,
        "yesterday_consensus": None,
        "drift_consensus_1d": None, "drift_consensus_Nd": None,
        "drift_skew_today": None, "drift_skew_change_1d": None,
        "convergence_score": 0.0,
        "direction_label": "insufficient_data",
        "n_days_covered": n,
        "warnings": warnings,
    }

    if n == 0:
        base_shape["direction_label"] = "insufficient_data"
        return base_shape

    last = cleaned[-1]
    today_consensus = last["consensus_price"]
    today_call_prem = last["avg_call_premium"]
    today_put_prem = last["avg_put_premium"]
    today_spot_val = today_spot  # may be None — convergence will degrade

    if n == 1:
        return {
            **base_shape,
            "today_consensus": round(today_consensus, 4),
            "today_call_premium": (
                round(today_call_prem, 4) if today_call_prem is not None else None
            ),
            "today_put_premium": (
                round(today_put_prem, 4) if today_put_prem is not None else None
            ),
            "today_spot": (
                round(today_spot_val, 4) if today_spot_val is not None else None
            ),
            "yesterday_consensus": None,
            "drift_consensus_1d": None,
            "drift_consensus_Nd": None,
            "drift_skew_today": _skew_abs(
                today_call_prem, today_put_prem
            ),
            "drift_skew_change_1d": None,
            "convergence_score": _convergence_score(
                today_consensus, today_spot_val
            ),
            "direction_label": "insufficient_data",
            "n_days_covered": 1,
        }

    yesterday = cleaned[-2]
    oldest = cleaned[0]

    drift_consensus_1d = round(
        today_consensus - yesterday["consensus_price"], 4
    )
    drift_consensus_Nd = round(
        today_consensus - oldest["consensus_price"], 4
    )

    drift_skew_today = _skew_abs(today_call_prem, today_put_prem)
    yesterday_skew = _skew_abs(
        yesterday.get("avg_call_premium"),
        yesterday.get("avg_put_premium"),
    )
    drift_skew_change_1d: float | None
    if yesterday_skew is None or drift_skew_today is None:
        drift_skew_change_1d = None
    else:
        drift_skew_change_1d = round(
            drift_skew_today - yesterday_skew, 4
        )

    convergence_score = _convergence_score(
        today_consensus, today_spot_val
    )

    # Direction label — combines regression-delta vs spot premium-tilt.
    # Priority order: sufficient_data → stable/call-pulling-up/put-pulling-down.
    # NOTE: convergence_score == 0.0 fires when consensus is FAR from spot
    # (e.g. consensus=120 spot=100 → 1 - 20/5 = -3 → clamped to 0). This is a
    # valid continuous signal, NOT missing data — so we only gate on
    # ``today_spot_val is None``. The 4-arm arbitration below correctly
    # handles low-convergence cases via above_threshold + side-dominance.
    direction_label: str
    if today_spot_val is None:
        direction_label = "insufficient_data"
    else:
        delta_to_spot = today_consensus - today_spot_val
        above_threshold = (
            abs(delta_to_spot)
            > today_spot_val * spot_convergence_threshold_pct
        )
        call_dominant = (
            today_call_prem is not None
            and today_put_prem is not None
            and today_call_prem > today_put_prem
        )
        put_dominant = (
            today_call_prem is not None
            and today_put_prem is not None
            and today_put_prem > today_call_prem
        )
        if not above_threshold:
            direction_label = "stable"
        elif delta_to_spot > 0 and call_dominant:
            direction_label = "call_side_pulling_up"
        elif delta_to_spot < 0 and put_dominant:
            direction_label = "put_side_pulling_down"
        else:
            # Inside the threshold OR no clear side-tilt ⇒ stable.
            direction_label = "balanced"

    return {
        "today_consensus": round(today_consensus, 4),
        "today_call_premium": (
            round(today_call_prem, 4) if today_call_prem is not None else None
        ),
        "today_put_premium": (
            round(today_put_prem, 4) if today_put_prem is not None else None
        ),
        "today_spot": (
            round(today_spot_val, 4) if today_spot_val is not None else None
        ),
        "yesterday_consensus": round(yesterday["consensus_price"], 4),
        "drift_consensus_1d": drift_consensus_1d,
        "drift_consensus_Nd": drift_consensus_Nd,
        "drift_skew_today": drift_skew_today,
        "drift_skew_change_1d": drift_skew_change_1d,
        "convergence_score": convergence_score,
        "direction_label": direction_label,
        "n_days_covered": n,
        "warnings": warnings,
    }


def _skew_abs(
    call_prem: float | None,
    put_prem: float | None,
) -> float | None:
    """Absolute skew — abs(call_premium - put_premium).

    Returns None if either leg is missing. Bounded to [0, ∞).
    """
    if call_prem is None or put_prem is None:
        return None
    return round(abs(call_prem - put_prem), 4)


def _convergence_score(
    consensus: float | None,
    spot: float | None,
) -> float:
    """0..1 score: closer-to-spot consensus scores higher.

    Returns 1.0 when consensus == spot; decays linearly to 0 when
    |consensus - spot| == 5% of spot. Bounded [0, 1]. Returns 0.0
    when either input is missing.
    """
    if consensus is None or spot is None or spot <= 0:
        return 0.0
    dist = abs(consensus - spot)
    return float(max(0.0, min(1.0, 1.0 - dist / (0.05 * spot))))
