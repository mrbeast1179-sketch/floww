"""Synthetic reference tests for ``services/ml/gex_inference.py``.

Mirrors the anchor pattern from ``scripts/kelly_calibration_report.py``:
hand-pinned arithmetic on a 3-contract synthetic chain. No yfinance,
no scipy.stats cross-check needed — every output is a closed-form
linear aggregate of ``gamma * oi * 100 * spot^2 * 0.01``.

Hand-derived values from the 3-contract synthetic chain (spot=100):

+------+------+------+-----+-------+------+------+
| type |  K   |  γ   | OI  |  Δ    |  IV  | sign |
+------+------+------+-----+-------+------+------+
|  C   | 100  | 0.05 | 10  |  0.50 | 0.25 |  +1  |
|  C   | 110  | 0.03 | 20  |  0.30 | 0.30 |  +1  |
|  P   |  90  | 0.04 | 15  | -0.40 | 0.28 |  -1  |
+------+------+------+-----+-------+------+------+

Per-strike GEX = sign * gamma * oi * 100 * 10000 * 0.01
  → {100: +5000, 110: +6000,  90: -6000}
  → |gex| at those strikes = [6000, 5000, 6000]
  → gamma_flip = strike with min |gex| → 100

Aggregates:
  call_gex (P-only signed): 5000 + 6000  =  11000
  put_gex  (subtracts!):    0 − 6000     =  -6000
  net_gex  (per-strike sum): 5000 + 6000 + (-6000) = 5000
  gamma_flip = 100 (|5000| < |6000|)
  dist_to_flip = (100 − 100)/100 = 0
  gex_n_strikes = 3
  put_call_ratio = 15 / 30 = 0.5
  total_dex = sum(|delta| * oi * 100) = 0.5*10*100 + 0.3*20*100 + 0.4*15*100
            = 500 + 600 + 600 = 1700
  total_vega = sum(iv * oi * 0.01) = 0.25*0.1 + 0.30*0.2 + 0.28*0.15
             = 0.025 + 0.060 + 0.042 = 0.127
  total_vex = net_gex * 0.01 = 50.0
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def synthetic_chain_3() -> dict:
    """3-contract chain with hand-pinnable per-strike arithmetic."""
    return {
        "spot": 100.0,
        "contracts": [
            {"type": "C", "strike": 100, "gamma": 0.05, "oi": 10,
             "delta": 0.50, "iv": 0.25, "volume": 0,
             "bid": 5.0, "ask": 5.2},
            {"type": "C", "strike": 110, "gamma": 0.03, "oi": 20,
             "delta": 0.30, "iv": 0.30, "volume": 0,
             "bid": 1.0, "ask": 1.1},
            {"type": "P", "strike": 90,  "gamma": 0.04, "oi": 15,
             "delta": -0.40, "iv": 0.28, "volume": 0,
             "bid": 1.0, "ask": 1.2},
        ],
    }


class TestGexInferenceFeatures:
    """Hand-pin the per-strike + per-feature arithmetic on a 3-contract chain."""

    def test_call_gex_and_put_gex_are_signed_correctly(
        self, synthetic_chain_3: dict
    ) -> None:
        """``call_gex`` accumulates with sign +1; ``put_gex`` accumulates
        SUBTRACTED (so it ends up negative for a net-long-put flow).
        """
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        # call_gex = 0.05*10*100 (.1 = 100 * 100 * 0.01 = 100) * 100
        #         = 500 + 600 = 11000
        assert feats["call_gex"] == pytest.approx(11000.0, abs=1e-6)
        # net_call_gex = call_gex
        assert feats["net_call_gex"] == pytest.approx(11000.0, abs=1e-6)
        # put_gex = subtracts gex_unit (0 - 6000) = -6000
        assert feats["put_gex"] == pytest.approx(-6000.0, abs=1e-6)
        assert feats["net_put_gex"] == pytest.approx(-6000.0, abs=1e-6)

    def test_net_gex_and_strike_counts(
        self, synthetic_chain_3: dict
    ) -> None:
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        # net_gex = 11000 - 6000 = 5000 (also = sum of gex_by_strike value)
        assert feats["net_gex"] == pytest.approx(5000.0, abs=1e-6)
        assert feats["gex_n_strikes"] == pytest.approx(3.0, abs=1e-6)

    def test_gamma_flip_is_min_abs_gex_strike(
        self, synthetic_chain_3: dict
    ) -> None:
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        # |gex| at strikes 90, 100, 110 → [6000, 5000, 6000]
        # min |gex| = 5000 at strike=100 → gamma_flip = 100
        assert feats["gamma_flip"] == pytest.approx(100.0, abs=1e-6)
        # dist_to_flip = (100 - 100) / 100 = 0
        assert feats["dist_to_flip"] == pytest.approx(0.0, abs=1e-6)

    def test_total_dex_total_vega_total_vex(
        self, synthetic_chain_3: dict
    ) -> None:
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        # total_dex = sum(|delta| * oi * 100)
        # = 0.50*10*100 + 0.30*20*100 + 0.40*15*100
        # = 500 + 600 + 600 = 1700
        assert feats["total_dex"] == pytest.approx(1700.0, abs=1e-6)
        # total_vega = sum(iv * oi * 0.01)
        # = 0.25*10*0.01 + 0.30*20*0.01 + 0.28*15*0.01
        # = 0.025 + 0.060 + 0.042 = 0.127
        assert feats["total_vega"] == pytest.approx(0.127, abs=1e-3)
        # total_vex = net_gex * 0.01 = 50.0
        assert feats["total_vex"] == pytest.approx(50.0, abs=1e-6)

    def test_put_call_ratio_oi_aggregate(
        self, synthetic_chain_3: dict
    ) -> None:
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        # total_call_oi = 10 + 20 = 30, total_put_oi = 15
        # put_call_ratio = 15 / 30 = 0.5
        assert feats["put_call_ratio"] == pytest.approx(0.5, abs=1e-6)

    def test_roc_zscore_placeholders_zero(
        self, synthetic_chain_3: dict
    ) -> None:
        """net_gex_roc_{1,3,5,10}d and net_gex_zscore_60d are zero
        placeholders (no historical series available in this module).
        """
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features(synthetic_chain_3)
        for key in (
            "net_gex_roc_1d", "net_gex_roc_3d",
            "net_gex_roc_5d", "net_gex_roc_10d",
            "net_gex_zscore_60d",
        ):
            assert feats[key] == pytest.approx(0.0, abs=1e-9), (
                f"{key} drifted from placeholder 0.0; "
                "revisit if intentional"
            )

    def test_empty_chain_returns_safe_defaults(self) -> None:
        """Empty contracts list → all-zero / default features.

        Specifically: ``put_call_ratio`` defaults to **1.0** (parity)
        while the rest of the dict defaults to 0.0 per
        ``_empty_gex_features``.
        """
        from services.ml.gex_inference import compute_gex_features
        feats = compute_gex_features({"spot": 100.0, "contracts": []})
        assert feats["net_gex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["call_gex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["put_gex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["gamma_flip"] == pytest.approx(0.0, abs=1e-6)
        assert feats["dist_to_flip"] == pytest.approx(0.0, abs=1e-6)
        assert feats["gex_n_strikes"] == pytest.approx(0.0, abs=1e-6)
        # Parity default — see _empty_gex_features.
        assert feats["put_call_ratio"] == pytest.approx(1.0, abs=1e-6)
        assert feats["total_dex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["total_vega"] == pytest.approx(0.0, abs=1e-6)
        assert feats["total_vex"] == pytest.approx(0.0, abs=1e-6)

    def test_required_features_set_is_exact(self) -> None:
        """``GEX_REQUIRED_FEATURES`` is the canonical infeature schema."""
        from services.ml.gex_inference import GEX_REQUIRED_FEATURES
        expected = frozenset({
            "call_gex", "put_gex", "net_call_gex", "net_put_gex",
            "net_gex", "gamma_flip", "dist_to_flip", "gex_n_strikes",
            "gex_concentration", "total_dex", "total_vega", "total_vex",
            "put_call_ratio", "net_gex_roc_1d", "net_gex_roc_5d",
            "net_gex_zscore_60d",
        })
        # Yoda-safe form: literal-first (``expected`` is bound here, not
        # a constant). Ruff would flag ``GEX_REQUIRED_FEATURES == expected``.
        assert expected == GEX_REQUIRED_FEATURES

    def test_required_features_completeness_tracks_known_gap(
        self, synthetic_chain_3: dict
    ) -> None:
        """``compute_gex_features`` should emit every required feature
        EXCEPT the currently-known schema gap.

        Currently ``gex_concentration`` is in ``GEX_REQUIRED_FEATURES``
        but the implementation does NOT emit it. Pin this gap
        explicitly so a future impl fix that adds the field is
        surfaced (test failure → update ``expected_known_gaps``).
        """
        from services.ml.gex_inference import (
            GEX_REQUIRED_FEATURES,
            compute_gex_features,
        )
        feats = compute_gex_features(synthetic_chain_3)
        missing = GEX_REQUIRED_FEATURES - set(feats.keys())
        expected_known_gaps = frozenset({"gex_concentration"})
        assert missing == expected_known_gaps, (
            f"compute_gex_features missing set drifted. "
            f"Expected missing={expected_known_gaps}; got={missing}. "
            f"If a new required feature is now emitted, drop it from "
            f"expected_known_gaps; if a new gap opened, add it."
        )
