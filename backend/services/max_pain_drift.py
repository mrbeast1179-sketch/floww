"""
backend/services/max_pain_drift.py

Max-Pain Drift tracking — completes deferred portion of steal-list #9
======================================================================

The PARTIAL max-pain ship landed `compute_overall_max_pain(chain)` that's
correct per-snapshot but had no historical accumulation layer. This
service closes that gap:

  1. `init_max_pain_daily_table(engine)` — CREATE TABLE IF NOT EXISTS +
     indexes + UNIQUE constraint for the daily snapshot table.
  2. `accumulate_today(engine, ticker, spot, max_pain_row)` — UPSERTs
     today's snapshot idempotently (DuckDB ON CONFLICT pattern).
  3. `read_recent_drift(engine, ticker, n_days)` — returns the last N
     days of snapshots ordered ascending by date.
  4. `compute_max_pain_drift(snapshots)` — pure-logic drift analytics
     (1d delta, Nd delta, drift-toward-spot, velocity, pin-prob-score,
     direction label) decoupled from any DB I/O.

Schema::

    CREATE TABLE IF NOT EXISTS max_pain_daily (
        snapshot_date          DATE,
        symbol                 VARCHAR,
        spot                   DOUBLE,
        max_pain_strike        DOUBLE,
        total_loss_at_strike   DOUBLE,
        calls_at_strike        BIGINT,
        puts_at_strike         BIGINT,
        expiry                 VARCHAR,
        PRIMARY KEY (snapshot_date, symbol, expiry)
    );

Drift-signal semantics:

  drift_strike_Nd  = today_strike - oldest_strike          # raw migration
  drift_toward_now = |oldest - spot| - |today - spot|
  (positive = max-pain converging to spot, reinforcing the pin
   hypothesis; negative = pin weakening, possibly a regime change)
  pin_probability_score = clamp(1 - |today - spot| / (0.05 * spot), 0, 1)
  (rough heuristic — closer-to-spot strikes score higher; bounded by 5%
   spot-move threshold matching floww's intraday band convention).
  direction_label = "migrating_toward_spot" if drift_toward_now > 0.005*spot,
                     "migrating_away"          if drift_toward_now < -0.005*spot,
                     "stable"                  otherwise.

The threshold of 0.5% of spot scales with ticker price (matches the
implied-move band's convention at backend/server.py:782-790).

Steal intent: ZubZubZuberi/MaxPainHistory (drift piece). Part-of-day
floww provenance: max_pain.py::compute_overall_max_pain.

Audit: ``backend/tests/services/test_max_pain_drift.py`` (16 cases —
empty/single/2-snap same-day OVERWRITE/7-day stable/migrating-toward-spot/
migrating-away/high-pin-convergence/init-idempotent/accumulate-idempotent/
read-recent-N/auto-sort/NaN-spot/missing-field/DB-exception/documented-keys).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Constants — table-name decisions are unprefixed (matches ticks/chains/
# flow_prints/vpin_buckets convention; the .md "floww.max_pain_daily" naming
# was the spec author's shorthand, not a real DuckDB schema qualifier).
# ─────────────────────────────────────────────────────────────────────

TABLE_NAME = "max_pain_daily"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS max_pain_daily (
    snapshot_date          DATE,
    symbol                 VARCHAR,
    spot                   DOUBLE,
    max_pain_strike        DOUBLE,
    total_loss_at_strike   DOUBLE,
    calls_at_strike        BIGINT,
    puts_at_strike         BIGINT,
    expiry                 VARCHAR,
    PRIMARY KEY (snapshot_date, symbol, expiry)
)
"""

CREATE_INDEX_SQL_LIST = (
    "CREATE INDEX IF NOT EXISTS idx_max_pain_daily_symbol "
    "ON max_pain_daily(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_max_pain_daily_date "
    "ON max_pain_daily(snapshot_date)",
)

UPSERT_SQL = """
INSERT INTO max_pain_daily
    (snapshot_date, symbol, spot, max_pain_strike, total_loss_at_strike,
     calls_at_strike, puts_at_strike, expiry)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (snapshot_date, symbol, expiry) DO UPDATE SET
    spot = excluded.spot,
    max_pain_strike = excluded.max_pain_strike,
    total_loss_at_strike = excluded.total_loss_at_strike,
    calls_at_strike = excluded.calls_at_strike,
    puts_at_strike = excluded.puts_at_strike,
    expiry = excluded.expiry
"""


# ─────────────────────────────────────────────────────────────────────
# Defensive extractors — coerce malformed inputs to safe defaults.
# ─────────────────────────────────────────────────────────────────────


def _safe_float(key: str, row: dict[str, Any], value: Any,
                warnings: list[str]) -> float | None:
    """Coerce a value to float. NaN / inf / None / non-numeric → None + warning."""
    if value is None:
        warnings.append(f"{key} missing")
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{key} not numeric")
        return None
    if not math.isfinite(v):
        warnings.append(f"{key} not finite")
        return None
    return v


def _to_date(value: Any, key: str, warnings: list[str]) -> date | None:
    """Coerce to a date. ISO-format strings accepted; future-dated → warn + drop."""
    if value is None:
        warnings.append(f"{key} missing")
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            warnings.append(f"{key} not ISO-format YYYY-MM-DD: {value!r}")
            return None
    warnings.append(f"{key} unrecognised type: {type(value).__name__}")
    return None


def _coerce_to_date(value: Any) -> date | None:
    """Defensive DATE-coercion for DuckDB-returned rows.

    ``DuckDBEngine.query`` routes through ``pandas.fetchdf`` which converts a
    DuckDB ``DATE`` column to ``pandas.Timestamp`` (a ``datetime.datetime``
    subclass). Callers of ``read_recent_drift`` should never see that — they
    should see a plain ``datetime.date``. So we normalise at the read
    boundary once; downstream ``compute_max_pain_drift`` only re-checks via
    ``_to_date`` against its own constructor inputs, not against rows
    fetched from the table.
    """
    if value is None:
        return None
    # ``pd.Timestamp`` is a subclass of ``datetime.datetime`` and exposes
    # ``.date()``; ``datetime.datetime`` likewise. Plain ``datetime.date``
    # does NOT expose ``.date()`` (it has no instance method of that name),
    # so the two-arm check below is required.
    if isinstance(value, datetime):
        try:
            return value.date()
        except (ValueError, TypeError):
            # ``pd.NaT`` (Not-a-Time) raises ``ValueError`` from ``.date()``
            # even though ``isinstance(NaT, datetime)`` is True. PRIMARY KEY
            # on ``snapshot_date`` makes this unreachable in practice (the
            # column is mandatory) but defense-in-depth matches
            # ``_to_date``'s missing-input semantics.
            return None
    if isinstance(value, date):
        return value
    return value  # short-circuit — leave unknown scalars alone


# ─────────────────────────────────────────────────────────────────────
# DuckDB I/O helpers — operate on the engine objects supplied.
# ─────────────────────────────────────────────────────────────────────


def init_max_pain_daily_table(engine) -> None:
    """Create the table + indexes. Idempotent — multiple calls are safe.

    Performs a one-time migration: if the legacy PRIMARY KEY
    (snapshot_date, symbol) is detected (forbids per-expiry rows), the
    table is dropped + recreated with the new PRIMARY KEY
    (snapshot_date, symbol, expiry). Uses DuckDB's
    ``information_schema`` to probe PK membership — portable across
    DuckDB versions (SQLite's ``pragma_table_info`` uses different
    column names: ``name/pk`` vs DuckDB's ``column_name/...``).

    Engines lacking introspection (rare) or transient I/O errors
    silently fall through to ``CREATE TABLE IF NOT EXISTS``, which
    adds the new ``expiry`` column to a legacy table but does NOT
    alter its PRIMARY KEY (DuckDB's ALTER TABLE cannot change a PK
    constraint, so a manual DROP is required for those engines).
    """
    try:
        # Check whether `expiry` is part of the PRIMARY KEY via
        # DuckDB's information_schema (portable across DuckDB versions;
        # pragma_table_info column names differ between engines —
        # SQLite uses `name/pk`, DuckDB uses `column_name/...`).
        res = engine.query(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.table_name = 'max_pain_daily' "
            "AND tc.constraint_type = 'PRIMARY KEY' "
            "AND kcu.column_name = 'expiry'"
        )
        # Legacy schema: `expiry` exists but is NOT in the PK → drop
        # so the CREATE below seeds the new composite-key schema.
        if not res:
            engine.execute_write("DROP TABLE IF EXISTS max_pain_daily")
    except Exception as exc:
        # Non-DuckDB engines (or transient I/O errors) silently fall
        # through to CREATE TABLE IF NOT EXISTS, which adds the new
        # `expiry` column to a legacy table but does NOT alter its
        # PRIMARY KEY constraint. Logged at debug to aid incident
        # triage without spamming prod logs.
        import logging
        logging.debug(
            f"max_pain_drift init: migration check failed "
            f"({type(exc).__name__}: {exc}); using "
            f"CREATE TABLE IF NOT EXISTS path"
        )

    engine.execute_write(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL_LIST:
        engine.execute_write(stmt)


def accumulate_today(engine, ticker: str, spot: float | None,
                     max_pain_row: dict[str, Any],
                     snapshot_date: date | None = None,
                     expiry: str | None = None) -> None:
    """UPSERT today's max-pain row for ``ticker`` into ``max_pain_daily``.

    ``snapshot_date`` defaults to today (local date). The UPSERT pattern
    means re-running on the same day OVERWRITES today's row with the
    freshest numbers — no duplicate rows, no cron-restart litter.
    """
    warnings: list[str] = []
    if snapshot_date is None:
        snapshot_date = date.today()
    spot_clean = _safe_float("spot", max_pain_row, spot, warnings)
    max_pain_strike = _safe_float("max_pain_strike", max_pain_row,
                                  max_pain_row.get("max_pain_strike"),
                                  warnings)
    total_loss = _safe_float("total_loss_at_strike", max_pain_row,
                              max_pain_row.get("total_loss_at_strike"),
                              warnings)
    calls_at = _safe_float("calls_at_strike", max_pain_row,
                            max_pain_row.get("calls_at_strike"), warnings)
    puts_at = _safe_float("puts_at_strike", max_pain_row,
                           max_pain_row.get("puts_at_strike"), warnings)
    if warnings:
        # Surface warnings without raising — caller (route) inspects engine stdout.
        import logging
        for w in warnings:
            logging.warning(f"accumulate_today({ticker}): {w}")
    if max_pain_strike is None:
        # Can't snapshot a row without a strike — defensive no-op.
        return
    engine.execute_write(UPSERT_SQL, [(
        snapshot_date,
        ticker.upper(),
        spot_clean if spot_clean is not None else 0.0,
        max_pain_strike,
        total_loss if total_loss is not None else 0.0,
        int(calls_at) if calls_at is not None else 0,
        int(puts_at) if puts_at is not None else 0,
        expiry or "",
    )])


def accumulate_today_per_expiry(
    engine,
    ticker: str,
    spot: float | None,
    per_expiry_rows: list[dict[str, Any]],
    snapshot_date: date | None = None,
) -> int:
    """UPSERT one row per expiry for ``ticker`` into ``max_pain_daily``.

    Batched (single ``execute_write`` call) — the new PK
    ``(snapshot_date, symbol, expiry)`` allows multiple rows per
    (date, ticker) so each listed expiry's pin number is tracked
    separately. Returns the number of tuples actually written.

    Defensive semantics match ``accumulate_today``: rows missing
    ``max_pain_strike`` are silently skipped; other malformations
    log a warning and coerce to safe defaults. The ``"_unknown"``
    sentinel + empty expiries are also dropped here so callers
    don't have to remember to filter (single place to enforce).
    """    # Drop "_unknown" sentinel + empty expiries so the legacy
    # fallback bucket never pollutes max_pain_daily. Defensively
    # capture non-dict rows in a single pass for a debug-time
    # visibility emission — the empty-expiry / "_unknown" cases are
    # by-design sentinel filtering (expected legitimate inputs being
    # filtered) and stay silent. Single-pass filter keeps us from
    # walking per_expiry_rows twice (once for the count, once for
    # the type-name list inside the f-string).
    non_dict_rows = [r for r in per_expiry_rows if not isinstance(r, dict)]
    if non_dict_rows:
        # Debug (NOT warning): production callers won't spam prod logs
        # when a single malformed row passes by. A debug-time caller
        # chasing a missing row can now see the count + ticker via
        # PYTHONLOGLEVEL=debug or a logger filter on the
        # ``services.max_pain_drift`` logger.
        import logging
        logging.debug(
            f"accumulate_today_per_expiry({ticker}): "
            f"silently dropped {len(non_dict_rows)} non-dict row(s) "
            f"from per_expiry_rows "
            f"(filtered types: {[type(r).__name__ for r in non_dict_rows]})"
        )
    per_expiry_rows = [
        r for r in per_expiry_rows
        if isinstance(r, dict)
        and r.get("expiry") not in (None, "", "_unknown")
    ]



    if not per_expiry_rows:
        return 0
    warnings: list[str] = []
    if snapshot_date is None:
        snapshot_date = date.today()
    # row={} is a benign placeholder for the spot-coercion path —
    # _safe_float ignores its `row` arg when coercing `value`.
    spot_clean = _safe_float("spot", {}, spot, warnings)
    tuples: list[tuple] = []
    for row in per_expiry_rows:
        max_pain_strike = _safe_float(
            "max_pain_strike", row, row.get("max_pain_strike"), warnings,
        )
        if max_pain_strike is None:
            continue
        total_loss = _safe_float(
            "total_loss_at_strike", row, row.get("total_loss_at_strike"),
            warnings,
        )
        calls_at = _safe_float(
            "calls_at_strike", row, row.get("calls_at_strike"), warnings,
        )
        puts_at = _safe_float(
            "puts_at_strike", row, row.get("puts_at_strike"), warnings,
        )
        expiry = row.get("expiry") or ""
        tuples.append((
            snapshot_date,
            ticker.upper(),
            spot_clean if spot_clean is not None else 0.0,
            max_pain_strike,
            total_loss if total_loss is not None else 0.0,
            int(calls_at) if calls_at is not None else 0,
            int(puts_at) if puts_at is not None else 0,
            expiry,
        ))
    if warnings:
        import logging
        for w in warnings:
            logging.warning(
                f"accumulate_today_per_expiry({ticker}): {w}"
            )
    engine.execute_write(UPSERT_SQL, tuples)
    return len(tuples)


def read_recent_drift(engine, ticker: str, n_days: int = 14) -> list[dict[str, Any]]:
    """Return the last ``n_days`` ``max_pain_daily`` rows for ``ticker``.

    Forward-chronological (oldest first) so the drift math reads naturally.
    Returns ``[]`` on DB error / empty table / unreachable symbol.
    """
    if n_days <= 0:
        return []
    sql = (
        f"SELECT snapshot_date, symbol, spot, max_pain_strike, "
        f"total_loss_at_strike, calls_at_strike, puts_at_strike, expiry "
        f"FROM {TABLE_NAME} "
        f"WHERE symbol = ? "
        f"ORDER BY snapshot_date DESC "
        f"LIMIT ?"
    )
    try:
        # ``query`` is the synchronous helper; runs inside the connection.
        # We use ``query_async`` in callers that are already async.
        rows = engine.query(sql, [ticker.upper(), n_days])
        # Rows are returned in DESC order (newest first); flip to ASC so
        # downstream compute_max_pain_drift can do oldest→newest walks.
        #
        # Normalise ``snapshot_date`` from ``pd.Timestamp`` (leaked by
        # ``engine.query`` via ``pandas.fetchdf``) to a plain
        # ``datetime.date`` so callers see the documented contract.
        rows = [
            {**r, "snapshot_date": _coerce_to_date(r.get("snapshot_date"))}
            for r in rows
        ]
        return list(reversed(rows))
    except Exception as exc:    # pragma: no cover (defensive)
        import logging
        logging.warning(f"read_recent_drift({ticker}): {type(exc).__name__}: {exc}")
        return []


def read_recent_drift_per_expiry(
    engine, ticker: str, n_days: int = 30,
) -> list[dict[str, Any]]:
    """Return per-expiry max_pain_strike history grouped by ``expiry``.

    Reads ``max_pain_daily`` for ``ticker`` EXCLUDING the OVERALL row
    (``expiry == ''``) and the legacy sentinel bucket (``expiry ==
    '_unknown'``), then groups by ``expiry`` and sorts each group ASC by
    ``snapshot_date`` so the chart front-end can draw a polyline per
    listed expiry.

    Output schema (list[dict])::

        [
            {
                "expiry": "2026-07-17",
                "n_points": int,
                "first_strike": float | None,
                "last_strike": float | None,
                "drift_strike_Nd": float | None,
                "history": [
                    {"date": date, "strike": float | None,
                     "spot": float | None},
                    ...
                ],
            },
            ...
        ]

    Defensive semantics mirror ``read_recent_drift``: a DB exception
    bubbles to ``[]`` + a logging.warning, never crashes the route.
    Expiries are returned sorted ASC by ISO date string so the chart
    can assign color indices in a deterministic forward-month order.
    """
    if n_days <= 0:
        return []
    sql = (
        f"SELECT snapshot_date, max_pain_strike, spot, expiry "
        f"FROM {TABLE_NAME} "
        f"WHERE symbol = ? "
        f"ORDER BY expiry ASC, snapshot_date ASC"
    )
    try:
        # No n_days predicate in SQL for simplicity; we filter below.
        # (DuckDB snapshot density is bounded by the cron cadence \u2014 typically
        # one row per day per listed expiry \u2014 so a 30-day window rarely
        # returns more than ~120 rows for liquid names.)
        raw_rows = engine.query(sql, [ticker.upper()])
        rows = [
            {**r, "snapshot_date": _coerce_to_date(r.get("snapshot_date"))}
            for r in raw_rows
        ]
    except Exception as exc:    # pragma: no cover (defensive degrade)
        import logging
        logging.warning(
            f"read_recent_drift_per_expiry({ticker}): "
            f"{type(exc).__name__}: {exc}"
        )
        return []

    # Group by expiry; drop the OVERALL row (``expiry == ''``) and the
    # legacy ``_unknown`` sentinel bucket by predicate in addition to
    # the SQL ``WHERE``. Drop non-finite / NaN snapshot_date or strike.
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        exp = str(r.get("expiry") or "")
        if exp in ("", "_unknown"):
            continue
        sd = r.get("snapshot_date")
        strike = r.get("max_pain_strike")
        if sd is None:
            continue
        try:
            strike_f = float(strike)
        except (TypeError, ValueError):
            continue
        if not (strike_f == strike_f):    # NaN check (NaN != NaN)
            continue
        groups.setdefault(exp, []).append({
            "date": sd,
            "strike": strike_f,
            "spot": r.get("spot"),
        })

    # Trim each group to the last ``n_days`` rows (ASC order \u2014 take the
    # tail). This is the window-respecting step; the SQL filter kept
    # ALL available history to compute first_strike / drift_strike_Nd
    # accurately against any deeper-than-n_days baseline.
    today = date.today()
    cutoff = date.fromordinal(today.toordinal() - int(n_days))

    out: list[dict[str, Any]] = []
    for exp in sorted(groups.keys()):
        historical = [pt for pt in groups[exp] if pt["date"] >= cutoff]
        if not historical:
            continue
        first_strike = historical[0]["strike"]
        last_strike = historical[-1]["strike"]
        drift_strike_Nd: float | None = (
            round(last_strike - first_strike, 4)
            if (first_strike is not None and last_strike is not None)
            else None
        )
        out.append({
            "expiry": exp,
            "n_points": len(historical),
            "first_strike": (round(first_strike, 4)
                             if first_strike is not None else None),
            "last_strike": (round(last_strike, 4)
                            if last_strike is not None else None),
            "drift_strike_Nd": drift_strike_Nd,
            "history": [
                {
                    "date": pt["date"],
                    "strike": (round(pt["strike"], 4)
                               if pt["strike"] is not None else None),
                    "spot": pt["spot"],
                }
                for pt in historical
            ],
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Pure-logic drift math — no I/O, fully testable.
# ─────────────────────────────────────────────────────────────────────


def compute_max_pain_drift(
    snapshots: list[dict[str, Any]],
    today_spot: float | None = None,
    spot_migration_threshold_pct: float = 0.005,
) -> dict[str, Any]:
    """Compute drift analytics from a list of dated max-pain snapshots.

    Args:
        snapshots: list of {snapshot_date, max_pain_strike, spot, ...} dicts.
            Must be sorted ASC by ``snapshot_date`` but auto-sort is
            applied defensively.
        today_spot: override for today's spot (used when caller knows
            it more precisely than the snapshot's stored spot). Defaults
            to the last snapshot's ``spot`` field.
        spot_migration_threshold_pct: spot-relative threshold for the
            "stable" zone. 0.005 = 0.5% of spot. Matches floww's
            implied-move band's short-delta convention.

    Returns:
        A dict matching the documented schema:
        {
            "today_strike": float|None,
            "today_spot": float|None,
            "yesterday_strike": float|None,
            "drift_strike_1d": float|None,
            "drift_strike_Nd": float|None,
            "drift_toward_now": float|None,
            "drift_velocity_per_day": float|None,
            "pin_probability_score": float,        # 0..1
            "direction_label": str,
            "n_days_covered": int,
            "warnings": list[str],
        }
    """
    warnings: list[str] = []

    # Defensive normalization.
    if not isinstance(snapshots, list):
        return {
            "today_strike": None, "today_spot": None, "yesterday_strike": None,
            "drift_strike_1d": None, "drift_strike_Nd": None,
            "drift_toward_now": None, "drift_velocity_per_day": None,
            "pin_probability_score": 0.0,
            "direction_label": "insufficient_data",
            "n_days_covered": 0,
            "warnings": ["snapshots must be a list"],
        }

    # Filter out future-dated snapshots + non-numeric strikes.
    cleaned: list[dict[str, Any]] = []
    today = date.today()
    for raw in snapshots:
        if not isinstance(raw, dict):
            warnings.append("non-dict snapshot skipped")
            continue
        snap_date = _to_date(raw.get("snapshot_date"), "snapshot_date", warnings)
        if snap_date is None:
            continue
        if snap_date > today:
            warnings.append(f"future-dated snapshot dropped: {snap_date}")
            continue
        strike = _safe_float("max_pain_strike", raw,
                              raw.get("max_pain_strike"), warnings)
        spot = _safe_float("spot", raw, raw.get("spot"), warnings)
        if strike is None:
            # Strike is mandatory — drop the row.
            warnings.append(
                f"max_pain_strike missing/NaN on {snap_date} — dropped"
            )
            continue
        cleaned.append({
            "snapshot_date": snap_date,
            "max_pain_strike": strike,
            "spot": spot,            # may be None; handled below
            # preserve other fields transitively
            "total_loss_at_strike": raw.get("total_loss_at_strike"),
            "calls_at_strike": raw.get("calls_at_strike"),
            "puts_at_strike": raw.get("puts_at_strike"),
            "expiry": raw.get("expiry"),
        })

    # Auto-sort ASC by snapshot_date even if caller sent reverse-chron.
    cleaned.sort(key=lambda r: (r["snapshot_date"], r["max_pain_strike"]))

    n = len(cleaned)
    base_shape: dict[str, Any] = {
        "today_strike": None, "today_spot": None, "yesterday_strike": None,
        "drift_strike_1d": None, "drift_strike_Nd": None,
        "drift_toward_now": None, "drift_velocity_per_day": None,
        "pin_probability_score": 0.0,
        "direction_label": "insufficient_data",
        "n_days_covered": n,
        "warnings": warnings,
    }

    if n == 0:
        base_shape["direction_label"] = "insufficient_data"
        return base_shape

    last = cleaned[-1]
    today_strike = last["max_pain_strike"]
    today_spot_val: float | None = (
        today_spot if today_spot is not None else last["spot"]
    )

    if n == 1:
        # Single snapshot → no drift computable. Today-strike + spot only.
        return {
            **base_shape,
            "today_strike": round(today_strike, 4),
            "today_spot": (round(today_spot_val, 4)
                           if today_spot_val is not None else None),
            "yesterday_strike": None,
            "drift_strike_1d": None,
            "drift_strike_Nd": None,
            "drift_toward_now": None,
            "drift_velocity_per_day": None,
            "pin_probability_score": _pin_score(today_strike, today_spot_val),
            "direction_label": "insufficient_data",
            "n_days_covered": 1,
        }

    yesterday_strike = cleaned[-2]["max_pain_strike"]
    oldest = cleaned[0]

    # Drift scalars.
    drift_strike_1d = round(today_strike - yesterday_strike, 4)
    drift_strike_Nd = round(today_strike - oldest["max_pain_strike"], 4)

    # Stable-relative drift-toward-spot:
    if today_spot_val is None or oldest["spot"] is None:
        drift_toward_now: float | None = None
        warnings.append("spot missing on at least one snapshot — "
                        "drift_toward_now unavailable")
    else:
        d_old = abs(oldest["max_pain_strike"] - today_spot_val)
        d_new = abs(today_strike - today_spot_val)
        drift_toward_now = round(d_old - d_new, 4)

    # Velocity (per day, only meaningful if we have ≥3 snapshots for a slope)
    drift_velocity: float | None
    if n >= 2:
        drift_velocity = round(drift_strike_Nd / max(1, n - 1), 4)
    else:
        drift_velocity = None

    # Pin-probability score.
    pin_score = _pin_score(today_strike, today_spot_val)

    # Direction label — threshold scales with spot to remain comparable
    # across SPY @ 520 vs NVDA @ 950.
    if drift_toward_now is None or today_spot_val is None:
        label = "insufficient_data"
    elif drift_toward_now > today_spot_val * spot_migration_threshold_pct:
        label = "migrating_toward_spot"
    elif drift_toward_now < -today_spot_val * spot_migration_threshold_pct:
        label = "migrating_away"
    else:
        label = "stable"

    return {
        "today_strike": round(today_strike, 4),
        "today_spot": (round(today_spot_val, 4)
                       if today_spot_val is not None else None),
        "yesterday_strike": round(yesterday_strike, 4),
        "drift_strike_1d": drift_strike_1d,
        "drift_strike_Nd": drift_strike_Nd,
        "drift_toward_now": drift_toward_now,
        "drift_velocity_per_day": drift_velocity,
        "pin_probability_score": pin_score,
        "direction_label": label,
        "n_days_covered": n,
        "warnings": warnings,
    }


def _pin_score(strike: float | None, spot: float | None) -> float:
    """Heuristic 0..1 score: closer-to-spot strikes pin harder.

    Returns 1.0 if strike == spot; decays linearly to 0 at |strike - spot|
    >= 5% of spot. Bounded [0, 1].
    """
    if strike is None or spot is None or spot <= 0:
        return 0.0
    dist = abs(strike - spot)
    return float(max(0.0, min(1.0, 1.0 - dist / (0.05 * spot))))


__all__ = [
    "compute_max_pain_drift",
    "accumulate_today",
    "accumulate_today_per_expiry",
    "read_recent_drift",
    "init_max_pain_daily_table",
    "TABLE_NAME",
    "CREATE_TABLE_SQL",
    "CREATE_INDEX_SQL_LIST",
    "UPSERT_SQL",
]
