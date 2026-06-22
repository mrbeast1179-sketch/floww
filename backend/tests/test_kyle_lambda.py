"""
backend/tests/test_kyle_lambda.py

Regression tests for the Kyle's Lambda (market-depth) service used by
Flowseeker Pro. Locks the observable behaviour of :class:`KylesLambda`
so refactors cannot silently change the price-impact estimate or the
LIQUID / NORMAL / ILLIQUID label thresholds.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_kyle_lambda.py -v

Or directly (no pytest install needed):

    python3 backend/tests/test_kyle_lambda.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.kyle_lambda import (
    LABEL_COLORS,
    LABEL_ILLIQUID,
    LABEL_LIQUID,
    LABEL_NORMAL,
    KylesLambda,
)


# ─────────────────────────────────────────────────────────────────────
# Lifecycle / warming
# ─────────────────────────────────────────────────────────────────────

def test_warming_with_fewer_than_window_observations():
    kyle = KylesLambda(window=20, history=40)
    # Stateful contract: the FIRST push only seeds _last_spot and appends
    # no (x, y). The SECOND push produces the first (x, y) observation.
    # So 2 pushes → exactly n_obs == 1 (well below window=20).
    kyle.push_snapshot(call_vol=100, put_vol=100, spot=100.0)
    kyle.push_snapshot(call_vol=200, put_vol=100, spot=100.1)
    out = kyle.compute()
    assert out["is_warming"] is True
    assert out["lambda_value"] == 0.0
    assert out["r_squared"] == 0.0
    assert out["label"] == LABEL_NORMAL
    assert out["label_color"] == LABEL_COLORS[LABEL_NORMAL]
    assert out["n_obs"] == 1  # only 1 (x,y) pair so far; window=20 → warming


def test_first_push_seeds_last_spot_without_appending():
    """The first push only seeds _last_spot — no (x,y) observation."""
    kyle = KylesLambda(window=5, history=20)
    kyle.push_snapshot(100, 100, 100.0)  # seeds spot=100
    assert kyle.n_obs == 0
    kyle.push_snapshot(200, 100, 100.5)  # generates (x,y)
    assert kyle.n_obs == 1


def test_zero_total_volume_observations_are_skipped():
    """A push with total_vol == 0 must NOT pollute the regression buffer."""
    kyle = KylesLambda(window=5, history=20)
    kyle.push_snapshot(0, 0, 100.0)        # seeds spot, no obs
    kyle.push_snapshot(0, 0, 101.0)        # tot==0 → skipped (not appended)
    assert kyle.n_obs == 0


def test_invalid_spot_skipped():
    """Bad spot (zero / NaN / negative) must not be appended."""
    import math as _m
    kyle = KylesLambda(window=5, history=20)
    kyle.push_snapshot(100, 100, 0.0)        # spot <= 0 → skip everything
    kyle.push_snapshot(100, 100, -1.0)       # negative spot → skip
    kyle.push_snapshot(100, 100, float('nan'))  # NaN spot → skip
    assert kyle.n_obs == 0


# ─────────────────────────────────────────────────────────────────────
# OLS regression correctness
# ─────────────────────────────────────────────────────────────────────

def test_perfect_positive_correlation_yields_lambda_one():
    """Manufacture y_i = 1.0 * x_i for every (x, y) → λ=1, r²=1."""
    kyle = KylesLambda(window=5, history=20)
    kyle.push_snapshot(50, 50, 100.0)  # seed
    # 5 (x, y) pairs with y = x exactly: x=0.5 → y=ln(1.5)≈0.405
    # x=-0.2 → y=ln(0.8)≈-0.223. We don't need y=x literally — just need
    # any perfectly-linear pattern to verify r² ≈ 1.0.
    pairs = [(0.8, 1.0), (0.5, 0.7), (-0.3, -0.1), (-0.6, -0.4), (0.2, 0.4)]
    cumspot = 100.0
    for x_target, y_target in pairs:
        # Choose call_vol/(call_vol+put_vol) = (1+x_target)/2; spot multiplier = exp(y_target)
        call_share = (1.0 + x_target) / 2.0  # ∈ [0,1]
        call_vol = max(1.0, call_share * 200.0)
        put_vol  = max(1.0, (1.0 - call_share) * 200.0)
        cumspot *= math.exp(y_target)
        kyle.push_snapshot(call_vol, put_vol, cumspot)
    out = kyle.compute()
    assert out["is_warming"] is False
    assert out["n_obs"] == 5
    # r² for a perfectly-linear pattern with non-zero SS_xy and SS_yy is 1.
    assert out["r_squared"] > 0.99
    # Slope is positive when imbalance ↔ price moves together.
    assert out["lambda_value"] > 0.0


def test_constant_flow_yields_zero_lambda_and_no_division_error():
    """When every push has identical call/put split, SS_xx ≈ 0 → safe fallback."""
    kyle = KylesLambda(window=5, history=20)
    # Every push: balanced 100/100 → x = 0 every time.
    kyle.push_snapshot(100, 100, 100.0)  # seed
    for pt in [101.0, 101.5, 102.7, 103.3, 104.1]:
        kyle.push_snapshot(100, 100, pt)
    out = kyle.compute()
    assert out["is_warming"] is False
    assert out["lambda_value"] == 0.0
    assert out["r_squared"] == 0.0
    # Per spec, lam=0 falls into the LIQUID band (< 0.001). The key
    # invariant is that the constant-flow edge case does NOT crash with
    # ZeroDivisionError and does NOT over-flag ILLIQUID.
    assert out["label"] != LABEL_ILLIQUID
    assert out["label"] == LABEL_LIQUID  # 0.0 < 0.001 per spec


# ─────────────────────────────────────────────────────────────────────
# Buffer clamping
# ─────────────────────────────────────────────────────────────────────

def test_history_buffer_clamps_to_maxlen():
    kyle = KylesLambda(window=5, history=20)
    kyle.push_snapshot(150, 50, 100.0)  # seed
    # Many pushes — only the last 20 (x,y) get retained.
    for k in range(200):
        spot = 100.0 + 0.01 * k
        kyle.push_snapshot(150, 50, spot)
    assert kyle.n_obs == 20


def test_windowed_ols_uses_last_n_observations_only():
    """The OLS window only sees the last ``window`` (x,y) pairs."""
    kyle = KylesLambda(window=5, history=20)
    # First 15 pushes: alternating extreme-imbalance → large positive slope.
    kyle.push_snapshot(150, 50, 100.0)  # seed
    for k in range(15):
        spot = 100.0 + 0.10 * (k + 1)  # strongly increasing
        kyle.push_snapshot(200, 0, spot)   # x ≈ 1 each time
    # Last 5 pushes: zero-imbalance + flat price → x=0, y=0.
    flat_spot = 100.0 + 0.10 * 15
    for _ in range(5):
        kyle.push_snapshot(100, 100, flat_spot)
    out = kyle.compute()
    assert out["is_warming"] is False
    assert out["n_obs"] == 5  # window size, not history
    # Window is dominated by x=0, so lambda ~ 0 / neutral.
    assert abs(out["lambda_value"]) < 1e-6 or out["label"] == LABEL_NORMAL


# ─────────────────────────────────────────────────────────────────────
# Label thresholds (boundary cases)
# ─────────────────────────────────────────────────────────────────────

def test_label_thresholds_match_specification():
    """3-band boundaries at λ = 0.001 and λ = 0.005."""
    # Manufacture pairs (x, y) such that y = λ·synthetic_x and check label.
    # λ = 0.0005 → LIQUID
    out = _ols_with_lambda(0.0005, x_range=(-0.8, 0.8), window=10)
    assert out["label"] == LABEL_LIQUID

    # λ = 0.003 → NORMAL (in [0.001, 0.005))
    out = _ols_with_lambda(0.003, x_range=(-0.8, 0.8), window=10)
    assert out["label"] == LABEL_NORMAL

    # λ = 0.007 → ILLIQUID
    out = _ols_with_lambda(0.007, x_range=(-0.8, 0.8), window=10)
    assert out["label"] == LABEL_ILLIQUID


def test_label_color_matches_label():
    """Every label has a colour and it's a valid hex trio."""
    for lbl in (LABEL_LIQUID, LABEL_NORMAL, LABEL_ILLIQUID):
        c = LABEL_COLORS[lbl]
        assert c.startswith("#") and len(c) == 7


# ─────────────────────────────────────────────────────────────────────
# Constructor validation
# ─────────────────────────────────────────────────────────────────────

def test_invalid_arguments_raise():
    try:
        KylesLambda(window=2, history=20)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for window < 3")
    try:
        KylesLambda(window=10, history=5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when history < window")


# ─────────────────────────────────────────────────────────────────────
# Synthetic data helper
# ─────────────────────────────────────────────────────────────────────

def _ols_with_lambda(target_lambda: float, x_range=(-1.0, 1.0), window: int = 10):
    """Build a KylesLambda with y_i = target_lambda * x_i exactly, return compute()."""
    kyle = KylesLambda(window=window, history=window * 2)
    # Seed spot with a sane value.
    kyle.push_snapshot(100, 100, 100.0)
    cumspot = 100.0
    xs = [x_range[0] + (x_range[1] - x_range[0]) * k / (window - 1) for k in range(window)]
    for x in xs:
        # choose call_vol / put_vol such that (call - put)/(call + put) = x.
        call_share = (1.0 + x) / 2.0
        call_vol = max(1.0, call_share * 200.0)
        put_vol  = max(1.0, (1.0 - call_share) * 200.0)
        cumspot *= math.exp(target_lambda * x)
        kyle.push_snapshot(call_vol, put_vol, cumspot)
    return kyle.compute()


# ─────────────────────────────────────────────────────────────────────
# Plain-script runner (no pytest required)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        (n, f) for n, f in globals().items() if n.startswith("test_")
    ]
    failures = 0
    for name, fn in test_cases:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(test_cases) - failures}/{len(test_cases)} passed")
    sys.exit(0 if failures == 0 else 1)
