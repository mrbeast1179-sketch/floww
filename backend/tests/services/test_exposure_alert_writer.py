"""Tests for exposure_alert_writer (GSD #10 O-2 mapping)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.exposure_alert_writer import evaluate_and_convert, events_to_alerts


def test_events_to_alerts_shape():
    events = [
        {"kind": "vex_wall_formed", "strike": 760.0, "expiry": "2026-09-04",
         "magnitude": 1_000_000.0},
        {"kind": "charm_pin_shifted", "strike": 770.0, "expiry": "2026-09-04",
         "magnitude": -500.0},
    ]
    alerts = events_to_alerts("SPY", 7640.0, events,
                              now=datetime(2026, 8, 25, 12, 0))
    assert len(alerts) == 2
    a = alerts[0]
    assert a["under"] == "SPY"
    assert a["tier"] == "GOLD"
    assert a["rule"] == "exposure_vex_wall_formed"
    # dedup key is stable per ticker/kind/expiry/strike
    assert a["key"] == "exposure:vex_wall_formed:SPY:2026-09-04:760"
    assert a["strike"] == 760.0
    assert a["exp"] == "2026-09-04"
    assert isinstance(a["score"], int) and 50 <= a["score"] <= 99
    assert alerts[1]["tier"] == "SILVER"


def test_dedup_key_stable_across_calls():
    e = [{"kind": "vex_wall_broken", "strike": 750.0, "expiry": "2026-08-28",
          "magnitude": 900_000.0}]
    k1 = events_to_alerts("QQQ", 100.0, e)[0]["key"]
    k2 = events_to_alerts("QQQ", 101.5, e)[0]["key"]
    assert k1 == k2


def test_evaluate_and_convert_end_to_end():
    old = {
        "expiries": ["2026-09-04"], "strikes": ["760"],
        "grid": {}, "charm_grid": {},
        "vex_grid": {"2026-09-04": {"760": 0.0}},
    }
    new = {
        "expiries": ["2026-09-04"], "strikes": ["760"],
        "grid": {}, "charm_grid": {},
        "vex_grid": {"2026-09-04": {"760": 4_000_000.0}},
    }
    alerts = evaluate_and_convert(new, old, "IWM", 759.0)
    assert any(a["rule"] == "exposure_vex_wall_formed" for a in alerts)


def test_identical_grids_no_alerts():
    g = {
        "expiries": ["2026-09-04"], "strikes": ["760"], "grid": {},
        "charm_grid": {"2026-09-04": {"765": 300_000.0}},
        "vex_grid": {"2026-09-04": {"760": 500_000.0}},
    }
    assert evaluate_and_convert(g, g, "SPY", 7640.0) == []
