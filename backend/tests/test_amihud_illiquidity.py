"""
backend/tests/test_amihud_illiquidity.py

Regression tests for the Amihud (2002) illiquidity-ratio service used
by Flowseeker Pro. Locks the observable behaviour of
:class:`AmihudIlliquidity` so refactors cannot silently change the
illiquidity estimate or the LIQUID / NORMAL / ILLIQUID label thresholds.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_amihud_illiquidity.py -v

Or directly (no pytest install needed):

    python3 backend/tests/test_amihud_illiquidity.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.amihud_illiquidity import (
    AmihudIlliquidity,
    LABEL_COLORS,
    LABEL_ILLIQUID,
    LABEL_LIQUID,
    LABEL_NORMAL,
)


# ─────────────────────────────────────────────────────────────────────
# Lifecycle / warming
# ─────────────────────────────────────────────────────────────────────

def test_warming_with_fewer_than_window_observations():
    am = AmihudIlliquidity(window=20, history=40)
    # First push seeds _last_spot, second yields the first (r, dv).
    am.push_snapshot(call_vol=100, put_vol=100, spot=100.0)
    am.push_snapshot(call_vol=200, put_vol=100, spot=100.5)
    out = am.compute()
    assert out["is_warming"] is True
    assert out["amihud"] == 0.0
    assert out["abs_return"] == 0.0
    assert out["dollar_volume"] == 0.0
    assert out["label"] == LABEL_NORMAL
    assert out["label_color"] == LABEL_COLORS[LABEL_NORMAL]
    assert out["n_obs"] == 1  # only 1 (r,dv) pair so far; window=20 → warming


def test_first_push_seeds_last_spot_without_appending():
    """First push only seeds ``_last_spot``; no observation is appended."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 100.0)  # seeds spot=100
    assert am.n_obs == 0
    am.push_snapshot(200, 100, 100.5)  # generates (r, dv)
    assert am.n_obs == 1


def test_zero_dollar_volume_observations_are_skipped():
    """If (call_vol + put_vol) == 0, the DV == 0 push is silently dropped."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(0, 0, 100.0)        # seeds spot, no obs (tot==0)
    am.push_snapshot(0, 0, 101.0)        # dv==0 → skipped (no append)
    assert am.n_obs == 0


def test_invalid_spot_skipped():
    """Bad spot (zero / NaN / negative) must not be appended."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 0.0)            # spot <= 0 → skip
    am.push_snapshot(100, 100, -5.0)           # negative spot → skip
    am.push_snapshot(100, 100, float("nan"))   # NaN spot → skip
    am.push_snapshot(100, 100, float("inf"))   # +Inf spot → skip
    assert am.n_obs == 0


# ─────────────────────────────────────────────────────────────────────
# Amihud estimator correctness
# ─────────────────────────────────────────────────────────────────────

def test_zero_return_yields_zero_amihud():
    """Constant spot across pushes → |r| = 0 → amihud = 0 → LIQUID."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 100.0)
    for _ in range(10):
        am.push_snapshot(100, 100, 100.0)  # spot unchanged → r=0
    out = am.compute()
    assert out["is_warming"] is False
    assert out["amihud"] == 0.0
    assert out["abs_return"] == 0.0
    assert out["label"] == LABEL_LIQUID  # 0.0 < 1e-7 per spec


def test_high_impact_low_volume_yields_illiquid():
    """Tiny volume + large return → huge ILLIQ → ILLIQUID."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 100.0)
    # 5 pushes: same small total_vol=1, each spot moves 10% (r=0.0953).
    spots = [111.0, 122.0, 134.0, 147.0, 162.0]
    for sp in spots:
        am.push_snapshot(1, 0, sp)
    out = am.compute()
    assert out["is_warming"] is False
    assert out["amihud"] >= 1e-5
    assert out["label"] == LABEL_ILLIQUID


def test_low_impact_high_volume_yields_liquid():
    """Huge volume + tiny return → tiny ILLIQ → LIQUID."""
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 100.0)
    spots = [100.0001, 100.0002, 100.0003, 100.0004, 100.0005]
    for sp in spots:
        am.push_snapshot(1_000_000, 1_000_000, sp)
    out = am.compute()
    assert out["is_warming"] is False
    assert out["amihud"] < 1e-7
    assert out["label"] == LABEL_LIQUID


# ─────────────────────────────────────────────────────────────────────
# Buffer clamping
# ─────────────────────────────────────────────────────────────────────

def test_history_buffer_clamps_to_maxlen():
    am = AmihudIlliquidity(window=5, history=20)
    am.push_snapshot(100, 100, 100.0)  # seed
    for k in range(200):
        # Tiny spot moves so each push appends; amplitude is small enough
        # that none of the divisions produce illiq > 1e10 and overflow.
        spot = 100.0 + 0.001 * k
        am.push_snapshot(100, 100, spot)
    assert am.n_obs == 20


def test_windowed_mean_uses_last_n_observations_only():
    """The mean only sees the LAST ``window`` (r, dv) pairs."""
    am = AmihudIlliquidity(window=5, history=20)
    # First 15 pushes: high ILLIQ (heavy return, tiny volume).
    am.push_snapshot(100, 100, 100.0)
    for k in range(15):
        spot = 100.0 * (1.10 ** (k + 1))   # 10% per push
        am.push_snapshot(1, 0, spot)         # dv = 1 * spot
    # Last 5 pushes: tiny return, huge volume → very tiny ILLIQ.
    flat_spot = 100.0 * (1.10 ** 15)
    for _ in range(5):
        am.push_snapshot(1_000_000, 1_000_000, flat_spot)
    out = am.compute()
    assert out["is_warming"] is False
    # Window is dominated by the last 5 (low ILLIQ) → LIQUID.
    assert out["label"] == LABEL_LIQUID
    assert out["n_obs"] == 5


# ─────────────────────────────────────────────────────────────────────
# Label thresholds (boundary cases)
# ─────────────────────────────────────────────────────────────────────

def test_label_thresholds_match_specification():
    """3-band boundaries at amihud = 1e-7 and amihud = 1e-5."""
    # amihud ≈ 5e-8 (below 1e-7) → LIQUID
    out = _amihud_with_target(5e-8, window=5, total_vol=1000)
    assert out["label"] == LABEL_LIQUID

    # amihud ≈ 5e-6 (middle of NORMAL) → NORMAL
    out = _amihud_with_target(5e-6, window=5, total_vol=1000)
    assert out["label"] == LABEL_NORMAL

    # amihud ≈ 5e-4 (well above 1e-5) → ILLIQUID
    out = _amihud_with_target(5e-4, window=5, total_vol=1000)
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
        AmihudIlliquidity(window=1, history=20)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for window < 2")
    try:
        AmihudIlliquidity(window=10, history=5)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when history < window")


# ─────────────────────────────────────────────────────────────────────
# Synthetic data helper
# ─────────────────────────────────────────────────────────────────────

def _amihud_with_target(target_illiq: float, window: int = 5, total_vol: float = 1000.0):
    """Push ``window`` observations that yield mean ILLIQ ≈ target_illiq.

    Strategy: each push keeps spot roughly constant so dv is similar
    across pushes, and varies the absolute log-return proportionally
    to the target. This avoids pathological edge cases (r=0, dv=0)
    and produces a mean amihud within a small tolerance of the target.
    """
    am = AmihudIlliquidity(window=window, history=window * 2)
    am.push_snapshot(total_vol, 0.0, 100.0)  # seed
    # We want mean ILLIQ = target_illiq. Each push keeps dv ≈ total_vol*100,
    # so |r_i| ≈ target_illiq * (total_vol * 100) per push.
    dv = total_vol * 100.0
    target_abs_r = target_illiq * dv
    cur = 100.0
    signs = [+1.0, -1.0, +1.0, -1.0, +1.0]  # alternating for variety
    for i in range(window):
        target_spot = cur * math.exp(signs[i] * target_abs_r)
        am.push_snapshot(total_vol, 0.0, target_spot)
        cur = target_spot
    return am.compute()


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
