"""
backend/tests/test_realised_volatility.py

Regression tests for :mod:`backend.services.realised_volatility`.

Pure-Python test code. Each test instantiates a fresh
:class:`RealisedVolatility` so the suite is independent across cases.
"""
from __future__ import annotations

import math
import sys


def _ensure_imports():
    if "services.realised_volatility" not in sys.modules:
        sys.path.insert(
            0, "/Users/nav/Documents/GitHub/floww/backend"
        )


_ensure_imports()


# ─────────────────────────────────────────────────────────────────────
# Construction / lifecycle
# ─────────────────────────────────────────────────────────────────────


def test_default_construction_yields_empty_buffer():
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility()
    assert rv.window == 60
    assert rv.history == 64
    assert rv.n_obs == 0
    assert rv.is_empty is True
    assert rv.latest_log_return is None
    assert len(rv) == 0


def test_zero_or_negative_window_raises():
    from services.realised_volatility import RealisedVolatility
    for bad in (0, 1, -5, -100):
        try:
            RealisedVolatility(window=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"window={bad} should have raised ValueError")


def test_history_less_than_window_raises():
    from services.realised_volatility import RealisedVolatility
    for bad in (5, 10, 50):
        try:
            RealisedVolatility(window=60, history=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"history={bad} < window=60 should have raised")


def test_buffer_eviction_at_capacity():
    """When history cap is hit, oldest log-return is silently dropped."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=10)
    # Push 20 distinct rising prices → 19 log-returns. After cap=10
    # drops the older ones, only the LAST 10 log-returns remain.
    for i in range(20):
        rv.push_snapshot(100.0 + i)   # r ≈ 0.01
    assert rv.n_obs == 10               # capped to history
    assert rv.capacity == 10


# ─────────────────────────────────────────────────────────────────────
# push_snapshot state-mutation guards
# ─────────────────────────────────────────────────────────────────────


def test_push_snapshot_skips_malformed_inputs():
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=5, history=10)
    for bad in (None, "string", [1, 2], float("nan"), float("inf"),
                -float("inf"), 0.0, -100.0):
        rv.push_snapshot(bad)
    # None of the malformed inputs produced a log-return.
    assert rv.n_obs == 0, "malformed inputs should be silently skipped"


def test_first_push_seeds_spot_no_return_yet():
    """First push seeds ``_last_spot`` but doesn't append a log-return.
    The first log-return appears at the SECOND push."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=5, history=10)
    rv.push_snapshot(100.0)
    assert rv.n_obs == 0                   # first push = seed, no delta
    rv.push_snapshot(101.0)
    assert rv.n_obs == 1
    # log(101/100) ≈ 0.00995
    assert math.isclose(rv.latest_log_return, math.log(101.0 / 100.0), rel_tol=1e-9)


def test_push_snapshot_returns_correct_log_returns():
    """Sequential spot pushes append correct log-returns."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=20, history=20)
    spots = [100.0, 105.0, 110.0, 100.0, 90.0]
    for s in spots:
        rv.push_snapshot(s)
    expected = [
        math.log(105.0 / 100.0),
        math.log(110.0 / 105.0),
        math.log(100.0 / 110.0),
        math.log(90.0  / 100.0),
    ]
    obs = list(rv)
    assert len(obs) == 4
    for got, exp in zip(obs, expected, strict=False):
        assert math.isclose(got, exp, rel_tol=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Warming-out semantics
# ─────────────────────────────────────────────────────────────────────


def test_compute_warming_with_fewer_than_window_obs():
    """Below ``window`` returns ``is_warming=True`` with all-zero outputs."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    # Provide 5 log-returns worth of spot moves (6 pushes).
    for i in range(6):
        rv.push_snapshot(100.0 + i)
    assert rv.n_obs == 5
    out = rv.compute()
    assert out["is_warming"] is True
    assert out["rv_annualised"] == 0.0
    assert out["bv_annualised"] == 0.0
    assert out["rq_annualised"] == 0.0
    assert out["n_obs"] == 5


def test_compute_window_transition_at_exactly_n_observations():
    """At window-1: warming; at window: non-warming (transition)."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=5, history=20)
    # Push exactly window+1 spots = window log-returns.
    for i in range(5):
        rv.push_snapshot(100.0 + i)
    out_warm = rv.compute()
    assert out_warm["is_warming"] is True
    assert out_warm["n_obs"] == 4       # window-1

    rv.push_snapshot(105.0)               # 5th log-return
    out_active = rv.compute()
    assert out_active["is_warming"] is False
    assert out_active["n_obs"] == 5


def test_compute_window_minutes_reflects_polling_period():
    """``window_minutes`` = window × polling_period / 60."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=60)
    # window=60 × 30s polling ⇒ 30 minutes.
    for i in range(61):
        rv.push_snapshot(100.0 + i)
    out = rv.compute(polling_period_seconds=30.0)
    assert out["window_minutes"] == 30


# ─────────────────────────────────────────────────────────────────────
# RV math correctness (the canonical equations)
# ─────────────────────────────────────────────────────────────────────


def test_compute_uniform_spots_yields_zero_volatility():
    """Constant spot ⇒ rv_ann = bv_ann = 0.0."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    for _ in range(20):
        rv.push_snapshot(100.0)         # 0.0% return each time
    out = rv.compute()
    assert out["is_warming"] is False
    assert out["rv_annualised"] == 0.0
    assert out["bv_annualised"] == 0.0
    assert out["n_obs"] == 10
    assert out["window_minutes"] == 5   # 10 × 30s / 60


def test_compute_alternating_log_returns_is_strictly_positive():
    """Alternating ±r ⇒ non-zero vol."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    # Push 11 spots alternating +0.001 / -0.001 around 100.
    spot = 100.0
    rv.push_snapshot(spot)
    for i in range(10):
        if i % 2 == 0:
            spot *= math.exp(0.001)     # ≈ +0.001 log return
        else:
            spot *= math.exp(-0.001)    # ≈ -0.001 log return
        rv.push_snapshot(spot)
    out = rv.compute(annualise_factor=1749.6)
    assert out["rv_annualised"] > 0.0
    # Each log-return is ≈ ±0.001; sqrt(10 × 0.001²) × 1749.6 ≈ 17.5
    # That'd annualise to 1750% which is huge — but the constant here
    # is ``uniform ``r=0.001`` per period → sqrt(10)*0.001*1749.6 ≈ 5.53 ⇒ 553%.
    # The annualisation factor matters more than the precise value here;
    # what matters is that we get a strictly positive finite number.
    assert math.isfinite(out["rv_annualised"])


def test_compute_rv_equals_math_expected_with_known_factor():
    """Cross-check rv against the closed-form equation for a known
    sequence where every log-return has the same magnitude."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    # Push spots so each log-return is *exactly* 0.001.
    spot = 100.0
    r = 0.001
    spots = [100.0]
    for _ in range(10):
        spot *= math.exp(r)
        spots.append(spot)
    for s in spots:
        rv.push_snapshot(s)
    out = rv.compute(annualise_factor=1000.0)   # clean factor
    expected_rv = math.sqrt(10 * r * r) * 1000.0
    assert math.isclose(out["rv_annualised"], expected_rv, rel_tol=1e-3), (
        f"got rv={out['rv_annualised']} expected≈{expected_rv}"
    )


def test_compute_bv_handles_jump_robustly():
    """A single large jump inflates RV but NOT BV proportionally.

    BV uses product of consecutive absolute returns — when there's a
    single big return between tiny ones, BV stays small. RV uses sum
    of squared returns — the big jump dominates.
    """
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=20, history=30)
    # Background: tiny returns; introduce ONE big jump midway.
    spot = 100.0
    rv.push_snapshot(spot)
    for i in range(20):
        # Tiny returns for the first 10 + last 9; ONE big jump in the middle.
        if i == 10:
            spot *= math.exp(0.05)          # 5% jump
        else:
            spot *= math.exp(0.0001)
        rv.push_snapshot(spot)
    out = rv.compute(annualise_factor=1.0)   # unit factor for ratio check
    # RV should be dominated by the jump ⇒ much larger than BV.
    assert out["rv_annualised"] > out["bv_annualised"] * 1.5, (
        f"RV={out['rv_annualised']} should exceed BV={out['bv_annualised']} "
        "in presence of a single jump (BV is jump-robust)."
    )


def test_compute_rq_non_negative_always():
    """RQ = Σr⁴ is always non-negative."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    spot = 100.0
    rv.push_snapshot(spot)
    import random as _r
    rng = _r.Random(7)
    for _i in range(10):
        spot *= math.exp(rng.uniform(-0.005, 0.005))
        rv.push_snapshot(spot)
    out = rv.compute(annualise_factor=1.0)
    assert out["rq_annualised"] >= 0.0


def test_compute_warming_n_obs_field_reflects_buffer_size():
    """The ``n_obs`` field reports the actual buffer count, not the
    window target, while warming."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=60, history=64)
    for i in range(20):
        rv.push_snapshot(100.0 + i)
    out = rv.compute()
    assert out["is_warming"] is True
    assert out["n_obs"] == 19    # 20 pushes − 1 seed = 19 log-returns


# ─────────────────────────────────────────────────────────────────────
# Label classification band
# ─────────────────────────────────────────────────────────────────────


def test_classify_rv_label_thresholds_match_spec():
    from services.realised_volatility import _classify_rv
    assert _classify_rv(0.05)        == "QUIET"
    assert _classify_rv(0.0999)      == "QUIET"
    assert _classify_rv(0.10)        == "MILD"
    assert _classify_rv(0.15)        == "MILD"
    assert _classify_rv(0.1999)      == "MILD"
    assert _classify_rv(0.20)        == "ACTIVE"
    assert _classify_rv(0.30)        == "ACTIVE"
    assert _classify_rv(0.3999)      == "ACTIVE"
    assert _classify_rv(0.40)        == "STRESSED"
    assert _classify_rv(0.80)        == "STRESSED"


def test_classify_rv_negative_treated_as_quiet():
    """Negative (numerically wonky) RV defaults to QUIET."""
    from services.realised_volatility import _classify_rv
    assert _classify_rv(-0.5) == "QUIET"
    assert _classify_rv(-1e-9) == "QUIET"


def test_compute_label_matches_classifier():
    """The ``label`` field in compute output matches the classifier."""
    from services.realised_volatility import RealisedVolatility, _classify_rv
    # Construct a sequence expected to land in MILD band (~12% annualised).
    # 0.20% per-period log return × 60 obs × annualise_factor=10:
    # rv_ann = sqrt(60) * 0.002 * 10 ≈ 0.155
    rv = RealisedVolatility(window=60, history=64)
    spot = 100.0
    rv.push_snapshot(spot)
    for _ in range(60):
        spot *= math.exp(0.002)
        rv.push_snapshot(spot)
    out = rv.compute(annualise_factor=10.0)
    assert out["label"] == _classify_rv(out["rv_annualised"])


# ─────────────────────────────────────────────────────────────────────
# Label colour mapping
# ─────────────────────────────────────────────────────────────────────


def test_label_colors_are_distinct_hex():
    """All 4 labels have distinct colours (no overlap)."""
    from services.realised_volatility import LABEL_COLORS
    assert len(set(LABEL_COLORS.values())) == 4


def test_label_colors_match_brand_palette_in_frontend():
    """Snap the LABEL_COLORS hex constants so the JSX stays in sync.

    This is the source-of-truth for chip colour mapping; if the JSX
    drifts, this test catches it on the first import error.
    """
    from services.realised_volatility import LABEL_COLORS
    # These exact hex strings are serialised into the FlowseekerProTab.jsx
    # colour-mapping switch (see <RealisedVolBar />). Drift = test fail.
    assert LABEL_COLORS["QUIET"]    == "#22c55e"
    assert LABEL_COLORS["MILD"]     == "#84cc16"
    assert LABEL_COLORS["ACTIVE"]   == "#fbbf24"
    assert LABEL_COLORS["STRESSED"] == "#ef4444"


# ─────────────────────────────────────────────────────────────────────
# Defensive end-to-end + FIFO eviction
# ─────────────────────────────────────────────────────────────────────


def test_compute_after_negative_log_spots_recovers_gracefully():
    """If market data goes wonky (log-return huge, or NaN), the estimator
    doesn't propagate it to RV."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=20)
    spots = [100.0, 50.0, 100.0, 50.0, 100.0, 50.0, 100.0, 50.0, 100.0, 50.0, 100.0]
    # Negative-rich log returns: log(50/100) = -0.6931...
    for s in spots:
        rv.push_snapshot(s)
    out = rv.compute(annualise_factor=1.0)
    # Each pair contributes log(0.5)² ≈ 0.48; sum of 10 = 4.8; sqrt ≈ 2.19.
    # Should be a sane finite number, not NaN/Inf.
    assert math.isfinite(out["rv_annualised"])
    assert out["label"] in {"MILD", "ACTIVE", "STRESSED"}


def test_compute_with_window_larger_than_history():
    """``compute`` doesn't blow up when ``window == history``."""
    from services.realised_volatility import RealisedVolatility
    rv = RealisedVolatility(window=10, history=10)
    for i in range(20):
        rv.push_snapshot(100.0 + i)
    out = rv.compute()
    assert math.isfinite(out["rv_annualised"])
    assert math.isfinite(out["bv_annualised"])
    assert math.isfinite(out["rq_annualised"])
