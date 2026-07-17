"""
backend/tests/test_hmm_regime.py

Regression tests for the Gaussian HMM regime detector used by Flowseeker Pro.
Locks the observable behaviour of :class:`GaussianHMMRegime` so refactors cannot
silently change regime classification.

Run from repo root:

    cd /Users/nav/Documents/GitHub/floww
    python3 -m pytest backend/tests/test_hmm_regime.py -v

Or directly (no pytest install needed):

    python3 backend/tests/test_hmm_regime.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services.hmm_regime import GaussianHMMRegime

# ─────────────────────────────────────────────────────────────────────
# Lifecycle / observation buffer
# ─────────────────────────────────────────────────────────────────────

def test_warming_state_with_too_few_observations():
    hmm = GaussianHMMRegime()
    hmm.push_observation((0.5, 1.2))
    out = hmm.classify()
    assert out["is_warming"] is True
    assert out["n_obs"] == 1
    assert out["current_state"] == "RANGING"
    assert out["smoothed_path"] == []
    assert out["confidence"] == 0.0
    # Posterior is uniform while warming.
    assert abs(sum(out["posterior"]) - 1.0) < 1e-9


def test_history_buffer_clamps_to_maxlen():
    hmm = GaussianHMMRegime(history=8)
    for k in range(50):
        hmm.push_observation((0.1 * k, 1.0))
    assert len(hmm._obs) == 8


def test_push_observation_invalidates_fit_flag():
    """A new push should make ``classify()`` return ``is_warming=True`` until the
    next ``fit_iter`` runs (otherwise we might serve stale posterior)."""
    hmm = GaussianHMMRegime()
    for k in range(20):
        hmm.push_observation((0.5 + 0.01 * k, 2.0))
    hmm.fit_iter(em_iterations=10)
    assert hmm._fitted is True
    assert hmm.classify()["is_warming"] is False
    hmm.push_observation((0.6, 2.0))
    assert hmm._fitted is False
    assert hmm.classify()["is_warming"] is True


# ─────────────────────────────────────────────────────────────────────
# Fit / classify output schema
# ─────────────────────────────────────────────────────────────────────

def test_posterior_probabilities_sum_to_one():
    hmm = GaussianHMMRegime()
    for k in range(30):
        hmm.push_observation((0.5 + 0.01 * k, 2.0))
    hmm.fit_iter(em_iterations=20)
    out = hmm.classify()
    assert abs(sum(out["posterior"]) - 1.0) < 1e-6
    assert all(0.0 <= p <= 1.0 + 1e-9 for p in out["posterior"])


def test_smoothed_path_returns_one_state_per_observation():
    hmm = GaussianHMMRegime()
    for k in range(15):
        hmm.push_observation((0.3 + 0.02 * k, 1.5))
    hmm.fit_iter(em_iterations=15)
    out = hmm.classify()
    assert len(out["smoothed_path"]) == 15
    for label in out["smoothed_path"]:
        assert label in {"TRENDING_BULL", "RANGING", "TRENDING_BEAR"}


def test_fit_changes_means_from_initialization():
    """Means should move appreciably after fit on data; otherwise EM didn't run."""
    hmm = GaussianHMMRegime()
    init_means = [row[:] for row in hmm.means]
    for k in range(20):
        hmm.push_observation((0.6 + 0.05 * k, 2.0))
    hmm.fit_iter(em_iterations=15)
    per_state_diff = []
    for i in range(hmm.n_states):
        s = sum(abs(hmm.means[i][k] - init_means[i][k])
                for k in range(hmm.n_features))
        per_state_diff.append(s)
    assert max(per_state_diff) > 1e-3, (
        f"means did not change after fit: post={hmm.means} init={init_means}"
    )


# ─────────────────────────────────────────────────────────────────────
# Behaviour: distinct distributions produce distinct labels
# ─────────────────────────────────────────────────────────────────────

def test_classify_different_distributions_yield_distinct_labels():
    """Three clearly-distinct feature concentrations, each on a fresh HMM,
    should yield at least 2 distinct regime labels (we don't pin the exact
    assignment — EM is unsupervised and the relabel is data-driven).

    Per-distribution, the LAST observation is steered into the bucket
    that should win that distribution:
      BULL  → monotonic ASCENDING f0 (last obs → highest-mean state → BULL)
      BEAR  → monotonic DESCENDING f0 (last obs → lowest-mean state → BEAR)
      NEUT  → oscillating around zero (last obs → RANGING or BULL/BEAR)
    """
    hmm = GaussianHMMRegime()
    for k in range(40):
        hmm.push_observation((0.5 + 0.04 * k, 2.5))   # ascending → BULL bucket
    hmm.fit_iter(em_iterations=25)
    bull_label = hmm.classify()["current_state"]
    assert bull_label == "TRENDING_BULL"

    hmm = GaussianHMMRegime()
    for k in range(40):
        hmm.push_observation((-0.5 - 0.04 * k, 0.6))  # descending → BEAR bucket
    hmm.fit_iter(em_iterations=25)
    bear_label = hmm.classify()["current_state"]
    assert bear_label == "TRENDING_BEAR"

    hmm = GaussianHMMRegime()
    for k in range(40):
        hmm.push_observation((0.0 + 0.02 * math.sin(k * 0.5), 1.5))
    hmm.fit_iter(em_iterations=25)
    neutral_label = hmm.classify()["current_state"]

    observed = {bull_label, bear_label, neutral_label}
    assert len(observed) >= 2, (
        f"expected ≥2 distinct labels across BULL/BEAR/NEUTRAL; got {observed}"
    )


def test_concentrated_bull_data_classifies_as_trending_bull():
    """A clear bull-dominated buffer should land ``current_state`` on
    ``TRENDING_BULL`` after fit (high confidence).

    Strictly ascending f0 so the last observation always sits in the
    highest-mean state (which the post-fit relabel maps to TRENDING_BULL).
    Sin-oscillating data is rejected: the last obs can drift into the
    lowest-mean state and mislabel.
    """
    hmm = GaussianHMMRegime()
    for k in range(60):
        hmm.push_observation((0.5 + 0.02 * k, 2.5))
    hmm.fit_iter(em_iterations=30)
    out = hmm.classify()
    assert out["is_warming"] is False
    assert out["current_state"] == "TRENDING_BULL"
    assert out["confidence"] > 0.85


def test_concentrated_bear_data_classifies_as_trending_bear():
    """A clear put-dominated buffer should land on ``TRENDING_BEAR``.

    Strictly descending f0 so the last observation always sits in the
    lowest-mean state (which the post-fit relabel maps to TRENDING_BEAR).
    """
    hmm = GaussianHMMRegime()
    for k in range(60):
        hmm.push_observation((-0.5 - 0.02 * k, 0.6))
    hmm.fit_iter(em_iterations=30)
    out = hmm.classify()
    assert out["is_warming"] is False
    assert out["current_state"] == "TRENDING_BEAR"
    assert out["confidence"] > 0.85


# ─────────────────────────────────────────────────────────────────────
# Plain-script runner (no pytest required)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        (name, fn) for name, fn in globals().items() if name.startswith("test_")
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
