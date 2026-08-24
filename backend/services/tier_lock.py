"""
backend/services/tier_lock.py

Tier-lock hysteresis — the missing bridge between the conviction engine's
tier stamping (tier_of in flow_alerts.py) and the v1 retuner
(alert_tuner.AlertTuner). Without a lock, a tier's factor-count threshold
yoyos every retune: the engine flips an alert's tier, the feed reads
unstable, and a desk can't anchor a blanket view of "what does GOLD mean".
A real desk sets the threshold and locks it when the data supports it,
not retunes every 24h.

Lock-engage condition (all three):
  - last-3-day measured hit-rate is RISING (strict day-over-day)
  - 7d Wilson lower bound (z=1.645, 90%) >= tier_target - 0  (on the bound side)
  - 30d Wilson lower bound (z=1.645, 90%) >= tier_target

Lock-release condition (all three, deliberately stricter):
  - last-3-day measured hit-rate is FALLING (strict day-over-day)
  - 7d Wilson lower bound (z=1.96, 95%) < tier_target - flat_band
  - 30d Wilson lower bound (z=1.96, 95%) < tier_target - flat_band

Tier targets: GOLD 0.60, SILVER 0.50, BRONZE 0.40 (the empirical hit-rate
floors per tier; below these the engine starts to over-fire).

Pure: takes the alert_quality(7d/30d) aggregates + alert_quality_daily rows,
returns the new lock state. Never raises — a transient Mongo/DuckDB hiccup
must surface as "no lock change" so the retuner runs as today.

Persistence: a DuckDB `tier_locks` table holds the current lock state so
the lock survives backend restarts (locks can be 40+ days old; recomputing
"when did this lock engage" from a 30-day bounded SQL query would be wrong).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Wilson z-scores — lock-engage uses 90% (z=1.645) one-sided, lock-release
# uses 95% (z=1.96) so release is strictly harder than engage. The
# asymmetry is the hysteresis: a tier can drop data fast, but the bound
# has to fall a wider band before the release condition trips.
_Z_ENGAGE = 1.645
_Z_RELEASE = 1.96

# Flat band (5pp) is the deliberate dead-zone between engage and release.
# Without it, single-day sample noise would yo-yo a tier in and out of
# lock at the exact same Wilson threshold — the failure mode that would
# make the lock counterproductive.
_FLAT_BAND = 0.05

# Tier target hit-rates — the floor a tier must clear in both windows
# before we trust it enough to lock. Bracket below the historical "measured"
# hit-rate for GOLD/SILVER/BRONZE overnight.
_TIER_TARGETS = {
    "GOLD": 0.60,
    "SILVER": 0.50,
    "BRONZE": 0.40,
}

# A tier that has fewer than this many days of measured-alert history
# cannot lock (the strict-monotone day-over-day check on a 2-day sample
# is noise, not signal). 3 = the minimal rising-or-falling arithmetic
# (d0>d1>d2 needs three points).
_MIN_DAYS_FOR_LOCK = 3

# Schema init — idempotent CREATE IF NOT EXISTS. Per-contract ADD COLUMN
# IF NOT EXISTS guards the migration path the same way flow_alerts.py
# guards on cw_spread / cluster / wins columns. Safe to call on every
# /alerts/quality read.
_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS tier_locks (
        tier TEXT PRIMARY KEY,
        is_engaged BOOLEAN,
        locked_hit_rate DOUBLE,
        locked_at TIMESTAMP
    )
"""


def init_tier_locks_table(engine) -> None:
    """Idempotent table init. Safe to call on every read path."""
    try:
        engine.execute_write(_TABLE_SQL)
    except Exception as e:
        logger.debug(f"tier_lock table init skipped: {e}")


def wilson_lower_bound(wins: int, n: int, z: float) -> float:
    """Wilson (1927) lower bound — matches convictionUi.js wilsonBounds()
    so the backend and frontend agree on the same small-sample CIs.

    Returns the LO half of {lo, hi}; the upper-bound math would be
    symmetry-equivalent so we keep the helper to ones the lock predicate
    actually consumes.
    """
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, wins / n))
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    spread = z * math.sqrt((p * (1.0 - p)) / n + z2 / (4.0 * n * n))
    return max(0.0, (center - spread) / denom)


def _is_rising(hit_rates: list[float]) -> bool:
    """Strict monotone day-over-day rise: d0 > d1 > d2.
    Repeated equal days disqualify — strict, not >=, by design. The strict
    form prevents a flat-day tier from spuriously satisfying the engage
    predicate when the underlying data is genuinely noise."""
    if len(hit_rates) != _MIN_DAYS_FOR_LOCK:
        return False
    return hit_rates[0] > hit_rates[1] > hit_rates[2]


def _is_falling(hit_rates: list[float]) -> bool:
    """Strict monotone day-over-day fall: d0 < d1 < d2. Mirror of _is_rising
    so the symmetric Z-engage/Z-release guards have parallel inputs."""
    if len(hit_rates) != _MIN_DAYS_FOR_LOCK:
        return False
    return hit_rates[0] < hit_rates[1] < hit_rates[2]


def _last_n_daily_hit_rates(daily_rows: list[dict], tier: str, n: int = _MIN_DAYS_FOR_LOCK) -> list[float]:
    """Last N daily hit_rate values for a tier from alert_quality_daily rows,
    ordered MOST-RECENT first. Missing days are NOT backfilled — a gap in
    data is information (no measured alert = no signal) and the locking
    math should read it as fewer-than-N, which simply disqualifies the
    lock on the length check."""
    out = []
    for r in sorted(daily_rows or [], key=lambda x: str(x.get("date") or ""), reverse=True):
        if str(r.get("tier") or "").upper() != tier.upper():
            continue
        hr = r.get("hit_rate")
        if hr is None:
            continue
        try:
            v = float(hr)
        except (TypeError, ValueError):
            continue
        if math.isnan(v) or math.isinf(v):
            continue
        out.append(v)
        if len(out) >= n:
            break
    return out


def _tier_window_wins(quality_rows: list[dict], tier: str) -> tuple[int, int]:
    """Sum wins and n_measured across all (rule, tier) rows for a tier in
    one quality window. The canonical per-tier aggregator: e.g. a tier
    whose GOLD rule fired 5-of-8 and SILVER rule fired 3-of-5 contributes
    (8 wins, 13 n_measured). This is intentionally coarser than per-rule
    analysis — the lock predicate cares about tier-level stability, not
    per-rule noise.
    """
    wins = 0
    n = 0
    has_int_wins = False
    for r in quality_rows or []:
        if str(r.get("tier") or "").upper() != tier.upper():
            continue
        nm = r.get("n_measured") or 0
        try:
            nm = int(nm)
        except (TypeError, ValueError):
            nm = 0
        n += nm
        w = r.get("wins")
        if w is not None:
            try:
                wins += int(w)
                has_int_wins = True
                continue
            except (TypeError, ValueError):
                pass
        hr = r.get("hit_rate")
        if hr is None:
            continue
        try:
            hr_v = float(hr)
        except (TypeError, ValueError):
            continue
        if math.isnan(hr_v) or math.isinf(hr_v):
            continue
        # Legacy fallback when backend SQL doesn't yet stamp `wins`.
        wins += int(round(hr_v * nm))
    return (wins if has_int_wins else wins, n) if n > 0 else (0, 0)


def evaluate_lock(
    quality_7d: list[dict],
    quality_30d: list[dict],
    daily_rows: list[dict],
    *,
    prev_locked: dict[str, bool] | None = None,
) -> dict[str, bool]:
    """Compute the NEW lock state per tier from current data + previous
    state. Pure function — the I/O layer that calls it persists the
    return value to DuckDB.

    Returns `{GOLD: bool, SILVER: bool, BRONZE: bool}` of is_engaged
    candidate states for THIS evaluation pass. The caller decides whether
    to commit (a state transition or new lock).

    `prev_locked` is optional: in steady state, the tier NOT engaged
    yesterday stays not-engaged today unless the engage predicate
    succeeds, which is the same logic; the parameter exists for
    symmetry with the asymmetry-of-z scores test.
    """
    out: dict[str, bool] = {}
    for tier, target in _TIER_TARGETS.items():
        last_n = _last_n_daily_hit_rates(daily_rows, tier)
        if len(last_n) < _MIN_DAYS_FOR_LOCK:
            out[tier] = False
            continue
        wins_7, n_7 = _tier_window_wins(quality_7d, tier)
        wins_30, n_30 = _tier_window_wins(quality_30d, tier)

        if n_7 <= 0 or n_30 <= 0:
            # No aggregate measurement in either window → release if
            # previously engaged, otherwise stay released. The condition
            # is asymmetric with the explicit fall/fall-with-bands logic:
            # insufficient data CANNOT keep a tier locked; it can only
            # release one (we never auto-engage on underpower).
            out[tier] = False
            continue

        lo_7_engage = wilson_lower_bound(wins_7, n_7, _Z_ENGAGE)
        lo_30_engage = wilson_lower_bound(wins_30, n_30, _Z_ENGAGE)
        lo_7_release = wilson_lower_bound(wins_7, n_7, _Z_RELEASE)
        lo_30_release = wilson_lower_bound(wins_30, n_30, _Z_RELEASE)

        prev_engaged = bool((prev_locked or {}).get(tier, False))

        if prev_engaged:
            # Already engaged: release conditions (falling + weak bands).
            if _is_falling(last_n) and lo_7_release < target - _FLAT_BAND and lo_30_release < target - _FLAT_BAND:
                out[tier] = False
            else:
                # Persist engagement — including the "falling but within
                # flat band" case, which is the hysteresis dead-zone.
                out[tier] = True
        else:
            # Currently released: engage conditions (rising + strong bands).
            if _is_rising(last_n) and lo_7_engage >= target and lo_30_engage >= target:
                out[tier] = True
                # Compute the locked_hit_rate snapshot at engage time —
                # this is the floor the release predicate compares against.
                # The CURRENT 30d Wilson lower bound is the right figure:
                # it reflects the data quality at lock time, not the pool
                # median, so a release sequence can later be reasoned
                # against the same statistical snapshot.
                out[f"_{tier}_locked_rate"] = lo_30_engage  # type: ignore[assignment]
            else:
                out[tier] = False
    return out


def update_locks(
    engine,
    quality_7d: list[dict],
    quality_30d: list[dict],
    daily_rows: list[dict],
) -> dict[str, dict]:
    """End-to-end update — pure eval + DuckDB write. Returns the post-
    commit lock state for the caller to surface in the /alerts/quality
    response.

    Reads `tier_locks` first (current state), evaluates the transition,
    writes any change. Returns the projected JSON-shape dict per tier:

        {"GOLD": {"engaged": bool, "locked_hit_rate": float|None,
                  "locked_at": "YYYY-MM-DDTHH:MM:SS"|None}, ...}
    """
    init_tier_locks_table(engine)
    try:
        prev_rows = engine.query("SELECT tier, is_engaged FROM tier_locks")
    except Exception:
        prev_rows = []
    prev_locked = {str(r["tier"]).upper(): bool(r.get("is_engaged")) for r in prev_rows or []}
    eval_lock = evaluate_lock(quality_7d, quality_30d, daily_rows, prev_locked=prev_locked)
    locked_rates = {str(k).lstrip("_").replace("_locked_rate", ""): v
                    for k, v in eval_lock.items() if str(k).startswith("_")}
    try:
        rows = engine.query("SELECT tier, is_engaged, locked_hit_rate, locked_at FROM tier_locks")
    except Exception:
        rows = []
    committed: dict[str, dict] = {str(r["tier"]).upper(): {
        "engaged": bool(r.get("is_engaged")),
        "locked_hit_rate": r.get("locked_hit_rate"),
        "locked_at": (r["locked_at"].isoformat() if hasattr(r.get("locked_at"), "isoformat")
                      else r.get("locked_at")),
    } for r in rows or []}
    now_ts = datetime.now(_ET)
    for tier, _ in _TIER_TARGETS.items():
        was_engaged = prev_locked.get(tier, False)
        wants_engaged = bool(eval_lock.get(tier, False))
        if was_engaged == wants_engaged:
            continue
        try:
            if wants_engaged:
                engine.execute_write(
                    """INSERT INTO tier_locks (tier, is_engaged, locked_hit_rate, locked_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT (tier) DO UPDATE SET
                           is_engaged = excluded.is_engaged,
                           locked_hit_rate = excluded.locked_hit_rate,
                           locked_at = excluded.locked_at""",
                    [[tier, True, locked_rates.get(tier), now_ts]],
                )
                committed[tier] = {
                    "engaged": True,
                    "locked_hit_rate": locked_rates.get(tier),
                    "locked_at": now_ts.isoformat(timespec="seconds"),
                }
            else:
                engine.execute_write(
                    """UPDATE tier_locks SET is_engaged = FALSE,
                                            locked_hit_rate = NULL,
                                            locked_at = NULL
                       WHERE tier = ?""",
                    [[tier]],
                )
                committed[tier] = {
                    "engaged": False,
                    "locked_hit_rate": None,
                    "locked_at": None,
                }
        except Exception as e:
            logger.debug(f"tier_lock write skipped for {tier}: {e}")
    # Ensure every tier shows up in the projection (default: not engaged).
    for tier, _ in _TIER_TARGETS.items():
        committed.setdefault(tier, {
            "engaged": False,
            "locked_hit_rate": None,
            "locked_at": None,
        })
    return committed


def get_all_locks(engine) -> dict[str, dict]:
    """Read-only accessor for the route handler — ~1ms DuckDB read. Does
    not evaluate transitions; that's update_locks()'s job."""
    init_tier_locks_table(engine)
    try:
        rows = engine.query("SELECT tier, is_engaged, locked_hit_rate, locked_at FROM tier_locks")
    except Exception:
        return {t: {"engaged": False, "locked_hit_rate": None, "locked_at": None}
                for t in _TIER_TARGETS}
    out = {t: {"engaged": False, "locked_hit_rate": None, "locked_at": None}
           for t in _TIER_TARGETS}
    for r in rows or []:
        out[str(r["tier"]).upper()] = {
            "engaged": bool(r.get("is_engaged")),
            "locked_hit_rate": r.get("locked_hit_rate"),
            "locked_at": (r["locked_at"].isoformat() if hasattr(r.get("locked_at"), "isoformat")
                          else r.get("locked_at")),
        }
    return out


def is_locked(engine, tier: str) -> bool:
    """One-tier boolean for the retuner optimize_threshold short-circuit."""
    return bool(get_all_locks(engine).get(str(tier).upper(), {}).get("engaged", False))
