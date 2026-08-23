"""
backend/tests/test_chain_replay.py

Regression tests for :mod:`backend.services.chain_replay`.

Pure test code — no FastAPI / no httpx. Each test instantiates a
fresh :class:`ChainReplay` so the suite is individually independent.
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta


def _ensure_imports():
    """Helper to keep the relative-import dance out of every test."""
    if "services.chain_replay" not in sys.modules:
        sys.path.insert(
            0, "/Users/nav/Documents/GitHub/floww/backend"
        )


_ensure_imports()


# ─────────────────────────────────────────────────────────────────────
# Reference fixtures — the route layer constructs snapshots that look
# like the augmented output of CompositeFlowScore.compute. Hand-build
# a factory that emits one with deterministic ts so window-query tests
# have a stable timeline.
# ─────────────────────────────────────────────────────────────────────


def _snap(ts, composite=42.5, label="WATCH", label_color="#a3a3a3",
          sub=None, components=None, n_obs_min=20, is_warming=False):
    if sub is None:
        sub = {"illiquidity": 0.3, "toxicity": 0.2, "dislocation": 0.4, "direction": 0.5}
    if components is None:
        components = {
            "amihud_norm": 0.3, "kyle_norm": 0.3, "vpin": 0.2,
            "regime": "RANGING", "ofi_aggr": 150.0,
        }
    return {
        "ts": ts.isoformat() if isinstance(ts, datetime) else ts,
        "composite": composite,
        "label": label,
        "label_color": label_color,
        "sub_scores": sub,
        "components": components,
        "n_obs_min": n_obs_min,
        "is_warming": is_warming,
        # The route also adds these; we keep them to assert public
        # sanitize-then-output behaviour.
        "symbol": "SPY",
        "fetched_at": ts.isoformat() if isinstance(ts, datetime) else ts,
    }


# Convenience: anchor the test timeline at a fixed clock.
ANCHOR = datetime(2026, 6, 21, 12, 0, 0)


# ─────────────────────────────────────────────────────────────────────
# Construction / lifecycle
# ─────────────────────────────────────────────────────────────────────


def test_default_construction_yields_empty_buffer():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    assert cr.size == 0
    assert cr.capacity == 240
    assert cr.is_empty is True
    assert cr.latest is None


def test_zero_or_negative_buffer_size_raises():
    from services.chain_replay import ChainReplay
    for bad in (0, -1, -100):
        try:
            ChainReplay(buffer_size=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"buffer_size={bad} should have raised")


def test_buffer_size_respected_at_construction():
    from services.chain_replay import ChainReplay
    cr = ChainReplay(buffer_size=10)
    assert cr.capacity == 10

    for i in range(25):
        cr.push_snapshot(_snap(ANCHOR + timedelta(minutes=i), composite=i,
                               n_obs_min=20, is_warming=False))
    assert cr.size == 10  # capped
    # The last 10 are kept.
    composites = [s["composite"] for s in cr.read_all()]
    assert composites == [15, 16, 17, 18, 19, 20, 21, 22, 23, 24]


# ─────────────────────────────────────────────────────────────────────
# push_snapshot validation
# ─────────────────────────────────────────────────────────────────────


def test_push_snapshot_returns_true_on_valid_non_warming():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    ok = cr.push_snapshot(_snap(ANCHOR, composite=10, label="LOW",
                                label_color="#64748b"))
    assert ok is True
    assert cr.size == 1
    assert cr.latest["composite"] == 10


def test_push_snapshot_skips_warming():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    ok = cr.push_snapshot(_snap(ANCHOR, is_warming=True,
                                composite=0, label="LOW"))
    assert ok is False
    assert cr.size == 0


def test_push_snapshot_skips_non_dict_inputs():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for bad in (None, 42, "string", [1, 2, 3], 1.5):
        ok = cr.push_snapshot(bad)
        assert ok is False, f"should have rejected {bad!r}"
    assert cr.size == 0


def test_push_snapshot_rejects_missing_or_invalid_label():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    assert cr.push_snapshot({"composite": 50}) is False  # no label
    assert cr.push_snapshot({"composite": 50, "label": None}) is False
    assert cr.push_snapshot({"composite": 50, "label": 123}) is False
    assert cr.size == 0


def test_push_snapshot_rejects_non_finite_composite():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    assert cr.push_snapshot({"composite": float("nan"), "label": "LOW"}) is False
    assert cr.push_snapshot({"composite": float("inf"), "label": "LOW"}) is False
    assert cr.push_snapshot({"composite": None, "label": "LOW"}) is False
    assert cr.push_snapshot({"composite": "string", "label": "LOW"}) is False
    assert cr.size == 0


def test_push_snapshot_renames_fetched_at_to_ts():
    """If the route passes a snapshot without ``ts`` but with
    ``fetched_at``, the public payload should still expose ``ts``.
    """
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    ts_str = ANCHOR.isoformat()
    snap_no_ts = _snap(ANCHOR, composite=33)
    snap_no_ts.pop("ts")
    assert "ts" not in snap_no_ts
    cr.push_snapshot(snap_no_ts)
    out = cr.latest
    assert out["ts"] == ts_str


# ─────────────────────────────────────────────────────────────────────
# read_tail / read_window / read_payload
# ─────────────────────────────────────────────────────────────────────


def test_read_tail_handles_zero_or_oversized_n():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    cr.push_snapshot(_snap(ANCHOR, composite=10))
    cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=30), composite=20))
    cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=60), composite=30))
    assert cr.read_tail(last_n=0) == []
    assert len(cr.read_tail(last_n=2)) == 2
    # If last_n > size, return all snapshots.
    assert len(cr.read_tail(last_n=999)) == 3


def test_read_tail_returns_last_n_in_chronological_order():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for i in range(10):
        cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=i * 30),
                               composite=i * 10))
    composites = [s["composite"] for s in cr.read_tail(last_n=4)]
    assert composites == [60, 70, 80, 90]


def test_read_window_filters_by_minutes_back():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for i in range(10):
        cr.push_snapshot(_snap(ANCHOR + timedelta(minutes=i),
                               composite=i * 5))
    # Anchor at ANCHOR + 9 minutes; 5-minute window → keep snaps whose
    # ``dt.timestamp() >= (anchor - 5 min)``. With inclusive comparison
    # and snapshots at i=0..9 minutes, the kept set is i=4..9 (6 items).
    out = cr.read_window(minutes=5, now=ANCHOR + timedelta(minutes=9))
    timestamps = [s["ts"] for s in out]
    assert len(out) == 6
    # Each kept snapshot should be ≥ ANCHOR + 4 minutes.
    for ts in timestamps:
        assert _parse(ts) >= ANCHOR + timedelta(minutes=4)
    # And the earliest kept (i=4) should equal the threshold.
    composite_vals = [s["composite"] for s in out]
    assert composite_vals[0] == 20  # i=4 → composite = 4*5 = 20


def test_read_window_with_empty_buffer_returns_empty_list():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    assert cr.read_window(minutes=60) == []


def test_read_payload_default_tail_n():
    from services.chain_replay import ChainReplay
    cr = ChainReplay(buffer_size=10)
    for i in range(7):
        cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=i),
                               composite=i))
    payload = cr.read_payload()
    assert payload["window_kind"] == "tail"
    assert payload["window_value"] == 64  # DEFAULT_TAIL_N
    assert payload["size"] == 7
    assert payload["capacity"] == 10
    assert payload["is_empty"] is False
    assert payload["latest"]["composite"] == 6
    assert len(payload["snapshots"]) == 7


def test_read_payload_explicit_last_n():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for i in range(8):
        cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=i)))
    payload = cr.read_payload(last_n=3)
    assert payload["window_kind"] == "tail"
    assert payload["window_value"] == 3
    assert len(payload["snapshots"]) == 3


def test_read_payload_explicit_minutes_selects_window_kind():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for i in range(6):
        cr.push_snapshot(_snap(ANCHOR + timedelta(minutes=i)))
    # Use a huge window so all anchored-at snapshots are kept regardless
    # of what ``datetime.now()`` returns on the test box (the anchor is a
    # fixed 2026-06-21 date, so the window must exceed the real elapsed
    # time since then) — we only need to assert that ``window_kind`` /
    # ``window_value`` are wired up correctly so the frontend can read it.
    payload = cr.read_payload(minutes=10_000_000)
    assert payload["window_kind"] == "minutes"
    assert payload["window_value"] == 10_000_000
    assert len(payload["snapshots"]) == 6


# ─────────────────────────────────────────────────────────────────────
# summarise helper
# ─────────────────────────────────────────────────────────────────────


def test_summarise_iterable_handles_empty():
    from services.chain_replay import ChainReplay
    out = ChainReplay.summarise_iterable([])
    assert out == {"count": 0, "min": 0.0, "max": 0.0,
                   "avg": 0.0, "first_label": None, "last_label": None}


def test_summarise_iterable_correct_aggregates():
    from services.chain_replay import ChainReplay
    snaps = [
        _snap(ANCHOR, composite=10, label="LOW"),
        _snap(ANCHOR + timedelta(seconds=30), composite=80, label="HIGH"),
        _snap(ANCHOR + timedelta(seconds=60), composite=50, label="MED"),
    ]
    out = ChainReplay.summarise_iterable(snaps)
    assert out["count"] == 3
    assert out["min"] == 10.0
    assert out["max"] == 80.0
    assert math.isclose(out["avg"], (10 + 80 + 50) / 3, rel_tol=1e-6)
    assert out["first_label"] == "LOW"
    assert out["last_label"] == "MED"


def test_summarise_iterable_tolerates_garbage_composites():
    from services.chain_replay import ChainReplay
    snaps = [
        {"composite": "not a number", "label": "BAD"},
        _snap(ANCHOR, composite=42),
        {"composite": None, "label": "BAD2"},
    ]
    out = ChainReplay.summarise_iterable(snaps)
    # Only the well-formed one contributes.
    assert out["count"] == 1
    assert out["min"] == 42.0
    assert out["max"] == 42.0


# ─────────────────────────────────────────────────────────────────────
# Snapshot coercion - the public payload schema
# ─────────────────────────────────────────────────────────────────────


def test_public_payload_includes_required_keys():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    cr.push_snapshot(_snap(ANCHOR, composite=72, label="MED",
                           label_color="#fbbf24"))
    latest = cr.latest
    for k in ("ts", "composite", "label", "label_color",
              "sub_scores", "components", "n_obs_min", "is_warming"):
        assert k in latest, f"missing key {k!r}"


def test_sub_scores_and_components_are_coerced_to_float_in_range():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    cr.push_snapshot(_snap(
        ANCHOR, sub={"illiquidity": 0.5, "toxicity": 0.6,
                     "dislocation": 0.7, "direction": 0.8},
        components={"amihud_norm": "0.55", "kyle_norm": "0.33",
                    "vpin": 0.42, "regime": "TRENDING_BULL",
                    "ofi_aggr": "999.123"},
    ))
    s = cr.latest
    assert s["sub_scores"]["illiquidity"] == 0.5
    assert s["sub_scores"]["toxicity"] == 0.6
    assert s["sub_scores"]["dislocation"] == 0.7
    assert s["sub_scores"]["direction"] == 0.8
    assert s["components"]["amihud_norm"] == 0.55
    assert s["components"]["kyle_norm"] == 0.33
    assert s["components"]["vpin"] == 0.42
    assert s["components"]["regime"] == "TRENDING_BULL"
    assert s["components"]["ofi_aggr"] == 999.123


def test_sub_scores_negative_inputs_clamped_to_zero():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    cr.push_snapshot(_snap(
        ANCHOR,
        sub={"illiquidity": -0.5, "toxicity": -0.6,
             "dislocation": -0.7, "direction": -0.8},
    ))
    s = cr.latest
    assert s["sub_scores"]["illiquidity"] == 0.0
    assert s["sub_scores"]["toxicity"] == 0.0
    assert s["sub_scores"]["dislocation"] == 0.0
    assert s["sub_scores"]["direction"] == 0.0


# ─────────────────────────────────────────────────────────────────────
# Ticker-swap helpers (clear, latest, len)
# ─────────────────────────────────────────────────────────────────────


def test_clear_empties_buffer_but_keeps_capacity():
    from services.chain_replay import ChainReplay
    cr = ChainReplay(buffer_size=10)
    cr.push_snapshot(_snap(ANCHOR, composite=1))
    cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=30), composite=2))
    cr.clear()
    assert cr.size == 0
    assert cr.capacity == 10
    assert cr.is_empty is True
    assert cr.latest is None


def test_iteration_yields_chronological_order():
    from services.chain_replay import ChainReplay
    cr = ChainReplay()
    for i in range(5):
        cr.push_snapshot(_snap(ANCHOR + timedelta(seconds=i * 30),
                               composite=i))
    composites = [s["composite"] for s in iter(cr)]
    assert composites == [0, 1, 2, 3, 4]


# ─────────────────────────────────────────────────────────────────────
# Internal helper correctness
# ─────────────────────────────────────────────────────────────────────


def _parse(s):
    """Local ISO-8601 parser for tests (mirrors _iso_to_dt but readable)."""
    return datetime.fromisoformat(s)


def test_iso_to_dt_handles_z_suffix_and_microseconds():
    """Sanity: both Z-suffixed and microsecond-bearing inputs parse.

    On Python 3.11+ the FIRST ``fromisoformat`` call succeeds and the
    microseconds are preserved. On Python 3.9/3.10 the first call
    raises (Z + fractional both rejected) and the helper's fallback
    drops the fractional-seconds suffix — microseconds go to 0.
    Either path yields a valid ``datetime`` with the right day/hour.
    """
    from services.chain_replay import _iso_to_dt
    dt = _iso_to_dt("2026-06-21T12:00:00.123456Z")
    assert dt.year == 2026 and dt.month == 6 and dt.day == 21
    assert dt.hour == 12 and dt.minute == 0 and dt.second == 0
    dt2 = _iso_to_dt("2026-06-21T12:00:00")
    assert dt2.microsecond == 0
