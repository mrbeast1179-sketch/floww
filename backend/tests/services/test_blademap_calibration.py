"""
backend/tests/services/test_blademap_calibration.py

RED-first: Blademap's calibration loop proves the SCORE predicts the hit.
alert_quality() groups by (rule, tier) — but tier is a 3-bucket count.
The v3 contract adds CONVICTION-BAND calibration: hit-rate bucketed by
conviction (50-59 / 60-74 / 75+), so the desk can see the monotonic
"higher conviction → higher hit-rate" curve that justifies sizing by
conviction. If the curve is flat, conviction is decoration.

Also: read_alert_feed gains min_conviction + sort_by=conviction so the
feed ranks like Blademap (score DESC), not by tier buckets.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import contextlib

from services.duckdb_engine import DuckDBEngine  # noqa: E402
from services.flow_alerts import (  # noqa: E402
    init_flow_alert_tables,
    persist_alerts,
)


@pytest.fixture
def engine():
    eng = DuckDBEngine(":memory:")
    init_flow_alert_tables(eng)
    yield eng
    with contextlib.suppress(Exception):
        eng._conn.close()


def _alert(key="k", under="PLTR", bias="BULLISH", tier="GOLD", rule="SCORE",
           conviction=80, move_pct=None):
    return {
        "key": key,
        "ckey": f"{under}|call|100|2026-09-18",
        "rule": rule, "tier": tier,
        "side": "BUY", "bias": bias,
        "under": under, "type": "call", "strike": 100.0,
        "exp": "2026-09-18", "dte": 10, "score": 90,
        "est_entry": 1.5, "premium": 1e6, "notional": 2e6,
        "vol_oi": 4.0, "sigma": None, "oi_chg_pct": None,
        "under_price": 100.0, "cw_spread": None, "cluster": False,
        "why": "t", "ttl_s": 3600, "asof": "2026-08-22T10:00:00",
        "conviction": conviction,
        "key_levels": {"entry": 100.0, "invalidation": 97.5, "target": 105.5},
        "context": {"market_regime": "NEGATIVE_GAMMA"},
    }


class TestConvictionCalibration:
    def test_quality_rows_carry_conviction_band(self, engine):
        persist_alerts(engine, [
            _alert(conviction=82, move_pct=1.0),
            _alert(conviction=85, move_pct=-0.2),
            _alert(conviction=65, move_pct=-1.0),
        ])
        rows = engine.query("SELECT * FROM flow_alerts_daily")
        assert all(r.get("conviction") is not None for r in rows)

    def test_conviction_calibration_monotonic_curve(self, engine):
        # 75+: both hit. 60-74: one of two hits. 50-59: zero of one.
        from services.flow_alerts import conviction_calibration, update_moves
        persist_alerts(engine, [
            _alert(key="a", under="AAA", conviction=80),
            _alert(key="b", under="BBB", conviction=90),
            _alert(key="c", under="CCC", conviction=65),
            _alert(key="d", under="DDD", conviction=70),
            _alert(key="e", under="EEE", conviction=55),
        ])
        # stamp moves the way the scan loop does (update_moves)
        update_moves(engine, {
            "AAA": 101.0,   # BULLISH +1% → hit
            "BBB": 101.0,   # hit
            "CCC": 101.0,   # hit
            "DDD": 99.0,    # miss
            "EEE": 99.0,    # miss
        })
        bands = conviction_calibration(engine, days=30)
        assert isinstance(bands, list) and len(bands) >= 3
        band_by = {b["band"]: b for b in bands}
        hi = band_by["75+"]
        mid = band_by["60-74"]
        lo = band_by["50-59"]
        assert hi["n_measured"] == 2 and hi["wins"] == 2
        assert mid["n_measured"] == 2 and mid["wins"] == 1
        assert lo["n_measured"] == 1 and lo["wins"] == 0
        # the whole point: higher conviction must hit harder
        assert hi["hit_rate"] > mid["hit_rate"] > lo["hit_rate"]

    def test_unmeasured_alerts_excluded_from_n_measured(self, engine):
        from services.flow_alerts import conviction_calibration
        persist_alerts(engine, [_alert(conviction=80, move_pct=None)])
        bands = conviction_calibration(engine)
        hi = [b for b in bands if b["band"] == "75+"][0]
        assert hi["n"] == 1 and hi["n_measured"] == 0


class TestFeedRanking:
    def test_read_feed_min_conviction_filter(self, engine):
        persist_alerts(engine, [
            _alert(key="lo", under="SPY", conviction=55),
            _alert(key="hi", under="QQQ", conviction=85),
        ])
        from services.flow_alerts import read_alert_feed
        out = read_alert_feed(engine, days=7, min_conviction=75)
        assert [a["under"] for a in out] == ["QQQ"]

    def test_read_feed_sorted_by_conviction_desc(self, engine):
        persist_alerts(engine, [
            _alert(key="mid", under="IWM", conviction=65),
            _alert(key="top", under="QQQ", conviction=92),
            _alert(key="low", under="TLT", conviction=52),
        ])
        from services.flow_alerts import read_alert_feed
        out = read_alert_feed(engine, days=7, sort_by="conviction")
        convs = [a["conviction"] for a in out]
        assert convs == sorted(convs, reverse=True)
