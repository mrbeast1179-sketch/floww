"""Tests for services/exposure_alerts.py — grid snapshot event evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.exposure_alerts import evaluate_exposure_events


def _grid(vex_cells: dict[str, dict[str, float]], charm_cells: dict[str, dict[str, float]] | None = None) -> dict:
    expiries = sorted({e for e in vex_cells} | set(charm_cells or {}))
    strikes = sorted({k for row in vex_cells.values() for k in row}
                     | {k for row in (charm_cells or {}).values() for k in row})
    return {
        "expiries": expiries,
        "strikes": strikes,
        "vex_grid": vex_cells,
        "charm_grid": charm_cells or {},
        "grid": {},
        "strike_totals": [],
    }


class TestVexWalls:
    def test_wall_formed_when_crossing_threshold(self):
        # old: cell 0; new: 1_000_000 (max) -> threshold 250k -> formed
        old = _grid({"2026-09-04": {"760": 0.0}})
        new = _grid({"2026-09-04": {"760": 1_000_000}})
        events = evaluate_exposure_events(new, old, threshold_pct=0.25)
        kinds = [e["kind"] for e in events]
        assert "vex_wall_formed" in kinds

    def test_no_event_below_threshold(self):
        old = _grid({"2026-09-04": {"760": 900_000}})
        new = _grid({"2026-09-04": {"760": 1_000_000}})  # max=1M, thr=250k
        # was above thr before too -> no formed event
        events = evaluate_exposure_events(new, old, threshold_pct=0.25)
        assert not [e for e in events if e["kind"] == "vex_wall_formed"]

    def test_wall_broken(self):
        old = _grid({"2026-09-04": {"760": 1_000_000}})
        new = _grid({"2026-09-04": {"760": 100_000}})
        events = evaluate_exposure_events(new, old, threshold_pct=0.25)
        assert any(e["kind"] == "vex_wall_broken" and e["strike"] == 760.0 for e in events)


class TestCharmPins:
    def test_pin_formed_first_snapshot(self):
        new = _grid({"2026-09-04": {}}, charm_cells={"2026-09-04": {"765": 500_000.0}})
        events = evaluate_exposure_events(new, None, threshold_pct=0.25)
        assert any(e["kind"] == "charm_pin_formed" and e["strike"] == 765.0 for e in events)

    def test_pin_shift_detected(self):
        old = _grid({}, charm_cells={"2026-09-04": {"760": 800_000.0, "770": 100.0}})
        new = _grid({}, charm_cells={"2026-09-04": {"760": 50.0, "770": 900_000.0}})
        events = evaluate_exposure_events(new, old, threshold_pct=0.25)
        shifted = [e for e in events if e["kind"] == "charm_pin_shifted"]
        assert shifted and shifted[0]["strike"] == 770.0


class TestEdgeCases:
    def test_identical_grids_zero_events(self):
        g = _grid({"2026-09-04": {"760": 500_000.0}},
                  charm_cells={"2026-09-04": {"765": 300_000.0}})
        assert evaluate_exposure_events(g, g, threshold_pct=0.25) == []

    def test_empty_grids_return_empty(self):
        assert evaluate_exposure_events({}, {}) == []

    def test_sorted_by_magnitude_desc(self):
        new = _grid({"2026-09-04": {"750": 2_000_000, "780": 4_000_000}})
        events = evaluate_exposure_events(new, None, threshold_pct=0.25)
        mags = [e["magnitude"] for e in events]
        assert mags == sorted(mags, reverse=True)
