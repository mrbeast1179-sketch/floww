"""Tests for services/exposure_alerts.py — grid snapshot event evaluator.

Ported from odaialdajani/floww-2 (gsd/010, read-only — their repo untouched):
same behaviors pinned against our adapted evaluator (float/str strike-key
normalization added for our in-process grids).
"""
from services.exposure_alerts import (
    RULE_CHARM_PIN,
    RULE_VEX_WALL,
    evaluate_exposure_events,
    evaluate_ticker,
    events_to_alerts,
)


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
        assert evaluate_exposure_events({}, None) == []
        assert evaluate_exposure_events({"vex_grid": {}, "charm_grid": {}}, None) == []
        assert evaluate_exposure_events(None, None) == []

    def test_float_strike_keys_match_str_keys(self):
        """Our in-process grids may carry float keys; JSON carries str."""
        new = {"vex_grid": {"2026-09-04": {760.0: 1_000_000}}, "charm_grid": {}}
        old = {"vex_grid": {"2026-09-04": {"760": 0.0}}, "charm_grid": {}}
        events = evaluate_exposure_events(new, old, threshold_pct=0.25)
        assert any(e["kind"] == "vex_wall_formed" for e in events)


class TestWriter:
    def test_events_to_c6_alerts(self):
        alerts = events_to_alerts("SPY", 760.0, [
            {"kind": "vex_wall_formed", "strike": 760.0,
             "expiry": "2026-09-04", "magnitude": 2_000_000},
        ])
        assert len(alerts) == 1
        a = alerts[0]
        assert a["rule"] == RULE_VEX_WALL and a["under"] == "SPY"
        assert a["tier"] == "SILVER" and a["side"] == "FLOW"
        assert a["premium"] is None and a["p_method"] == "uncalibrated"
        assert a["ttl_s"] == 4 * 3600 and a["key"].startswith("exposure:")

    def test_charm_rule_mapping(self):
        alerts = events_to_alerts("QQQ", 700.0, [
            {"kind": "charm_pin_shifted", "strike": 705.0,
             "expiry": "2026-09-04", "magnitude": 1_000},
        ])
        assert alerts[0]["rule"] == RULE_CHARM_PIN


class TestEvaluateTicker:
    def test_first_sight_baselines_then_diffs(self):
        import services.exposure_alerts as ea

        ea._LAST_GRIDS.clear()
        try:
            g1 = _grid({"2026-09-04": {"760": 0.0}})
            assert ea.evaluate_ticker("SPY", g1, 760.0) == []
            g2 = _grid({"2026-09-04": {"760": 1_000_000}})
            alerts = ea.evaluate_ticker("SPY", g2, 760.0)
            assert len(alerts) == 1 and alerts[0]["rule"] == RULE_VEX_WALL
            assert alerts[0]["asof"]
            # same grid again -> silence (no repeat spam)
            assert ea.evaluate_ticker("SPY", g2, 760.0) == []
        finally:
            ea._LAST_GRIDS.clear()

    def test_fail_open(self):
        import services.exposure_alerts as ea

        assert ea.evaluate_ticker("", None, 0) == []
        assert ea.evaluate_ticker("SPY", {"bogus": True}, 0) == []
