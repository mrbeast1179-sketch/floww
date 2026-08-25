"""
backend/services/exposure_alerts.py

Exposure-change alerts from grid snapshots (steal-list extension).
====================================================================

Compares consecutive heatmap grids (from decoder_core compute_gex_grid)
and emits events when VEX walls form/break or charm pin levels form/shift.
Events flow into the existing flow-alerts DuckDB table so they surface in
the conviction feed alongside flow alerts — no frontend changes.

Pure-logic evaluator (no I/O): callers own persistence, matching the
canonical steal-three contract (strike_cone / risk_neutral_density /
strategy_builder).

Public API
----------

``evaluate_exposure_events(new_grid, old_grid=None, threshold=0.25)``
    Returns a list of event dicts:

    {"kind": "vex_wall_formed" | "vex_wall_broken"
           | "charm_pin_formed" | "charm_pin_shifted",
     "strike": float,
     "expiry": str,
     "magnitude": float}

Threshold semantics: an event fires when a cell's |value| crosses ABOVE
threshold * max_abs of its grid between snapshots (strictly greater for
formed; the prior cell must be below). Broken fires when a previously-
above-threshold cell drops below. Charm pins shift when the argmax strike
of charm moves between expiries' snapshots.

Why it matters: VEX walls are vol-suppression levels dealers defend;
charm pins are where delta hedging concentrates as time decays. A wall
forming or breaking usually precedes a regime shift.
"""

from __future__ import annotations


def _cell_above(value: float, threshold: float) -> bool:
    return value is not None and abs(value) >= threshold


def _max_abs(grid_section: dict) -> float:
    """Max |cell value| across all expiries in a {expiry: {strike: value}} map."""
    vals = [
        abs(float(v))
        for row in grid_section.values()
        if isinstance(row, dict)
        for v in row.values()
        if isinstance(v, (int, float))
    ]
    return max(vals, default=0.0)


def evaluate_exposure_events(
    new_grid: dict,
    old_grid: dict | None = None,
    threshold_pct: float = 0.25,
) -> list[dict]:
    """Compare two heatmap grid payloads and emit exposure events.

    Args:
        new_grid: latest grid payload {expiries[], strikes[], grid{},
                   vex_grid{}, charm_grid{}} (decoder_core shape).
        old_grid: previous snapshot's payload, or None (first run -> only
                  "formed" events for already-large cells).
        threshold_pct: fraction of each grid's max-abs that counts as a wall/pin.

    Returns:
        List of event dicts sorted by |magnitude| descending.
    """
    events: list[dict] = []
    if not new_grid:
        return events

    new_vex = new_grid.get("vex_grid") or {}
    new_charm = new_grid.get("charm_grid") or {}
    old_vex = (old_grid or {}).get("vex_grid") or {}
    old_charm = (old_grid or {}).get("charm_grid") or {}

    # --- VEX walls ---
    vex_threshold_new = threshold_pct * _max_abs(new_vex)
    if vex_threshold_new > 0:
        for expiry, row in new_vex.items():
            old_row = old_vex.get(expiry, {}) if old_vex else {}
            thr_old = threshold_pct * _max_abs(old_vex) if old_vex else 0.0
            for strike, val in row.items():
                v = float(val)
                was = float(old_row.get(strike, 0) or 0)
                above_now = _cell_above(v, vex_threshold_new)
                # A zero/degenerate old threshold means we can't judge the
                # prior state — treat as below so first snapshots emit "formed".
                above_before = (
                    _cell_above(was, thr_old) and thr_old > 0
                    if old_row else False
                )
                if above_now and not above_before:
                    events.append({
                        "kind": "vex_wall_formed", "strike": float(strike),
                        "expiry": expiry, "magnitude": abs(v),
                    })
                elif above_before:
                    # Wall existed at old threshold; check whether it's gone now.
                    broken_thr = max(thr_old, vex_threshold_new)
                    if not _cell_above(v, broken_thr):
                        events.append({
                            "kind": "vex_wall_broken", "strike": float(strike),
                            "expiry": expiry, "magnitude": abs(was),
                        })
    # --- Charm pins ---
    charm_threshold_new = threshold_pct * _max_abs(new_charm)
    if charm_threshold_new > 0:
        for expiry, row in new_charm.items():
            old_row = old_charm.get(expiry, {}) if old_charm else {}
            # Pin = argmax |charm| strike for this expiry
            def _pin(row_):
                best_k, best_v = None, 0.0
                for k, v in (row_ or {}).items():
                    fv = abs(float(v)) if isinstance(v, (int, float)) else 0.0
                    if fv > best_v:
                        best_k, best_v = k, fv
                return best_k, best_v
            new_pin, new_val = _pin(row)
            old_pin, old_val = _pin(old_row)
            if new_pin and _cell_above(new_val, charm_threshold_new):
                if old_pin is None:
                    events.append({
                        "kind": "charm_pin_formed", "strike": float(new_pin),
                        "expiry": expiry, "magnitude": new_val,
                    })
                elif str(old_pin) != str(new_pin):
                    events.append({
                        "kind": "charm_pin_shifted",
                        "strike": float(new_pin),
                        "expiry": expiry,
                        "magnitude": new_val,
                    })

    events.sort(key=lambda e: e["magnitude"], reverse=True)
    return events
