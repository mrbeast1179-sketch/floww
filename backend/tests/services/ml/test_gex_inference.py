"""
Tests for live GEX feature computation during ML inference.
"""
import numpy as np
import pytest

from services.ml.gex_inference import compute_gex_features


class TestComputeGexFeatures:
    """Test GEX feature computation from options chain."""

    def _make_chain(self, spot=500.0, n_calls=6, n_puts=6):
        """Helper to create a synthetic options chain."""
        contracts = []
        for i in range(n_calls):
            contracts.append({
                "type": "C", "strike": spot - 10 + i * 5,
                "gamma": 0.01 + i * 0.002, "oi": 1000 + i * 200,
                "iv": 0.18 + i * 0.005, "delta": 0.6 - i * 0.05,
                "volume": 100, "expiry": "2024-06-21",
            })
        for i in range(n_puts):
            contracts.append({
                "type": "P", "strike": spot - 10 + i * 5,
                "gamma": 0.01 + i * 0.002, "oi": 800 + i * 150,
                "iv": 0.20 + i * 0.005, "delta": -0.4 + i * 0.05,
                "volume": 80, "expiry": "2024-06-21",
            })
        return {"spot": spot, "contracts": contracts, "ticker": "SPY"}

    def test_empty_chain_returns_defaults(self):
        result = compute_gex_features({"spot": 0, "contracts": []})
        assert result["net_gex"] == 0.0
        assert result["call_gex"] == 0.0

    def test_basic_gex_values(self):
        chain = self._make_chain()
        result = compute_gex_features(chain)
        assert result["net_gex"] != 0.0
        assert result["call_gex"] > 0.0
        assert result["put_gex"] < 0.0
        assert 485 < result["gamma_flip"] < 515
        assert abs(result["dist_to_flip"]) < 0.05

    def test_rolling_features_default_zero(self):
        chain = self._make_chain()
        result = compute_gex_features(chain)
        assert result["net_gex_roc_1d"] == 0.0
        assert result["net_gex_zscore_60d"] == 0.0

    def test_total_dex_vega_nonzero(self):
        chain = self._make_chain()
        result = compute_gex_features(chain)
        assert result["total_dex"] > 0.0
        assert result["total_vega"] > 0.0

    def test_put_call_ratio(self):
        chain = self._make_chain()
        result = compute_gex_features(chain)
        assert 0 < result["put_call_ratio"] < 2.0

    def test_iv_proxies_nonzero(self):
        chain = self._make_chain()
        result = compute_gex_features(chain)
        assert result["realized_vol_t1"] > 0.0

    def test_large_negative_gex(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                {"type": "C", "strike": 495, "gamma": 0.005, "oi": 500, "iv": 0.2, "delta": 0.6, "volume": 50},
                {"type": "P", "strike": 495, "gamma": 0.02, "oi": 3000, "iv": 0.25, "delta": -0.4, "volume": 300},
            ],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] < 0.0
