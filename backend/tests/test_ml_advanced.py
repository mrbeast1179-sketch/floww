"""Tests for synthetic data generation and advanced ML."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import numpy as np


def test_synthetic_data_generation():
    """Test synthetic data generation."""
    from ml_synthetic import generate_synthetic_snapshots
    
    base = {
        "ticker": "SPY",
        "spot": 450.0,
        "total_gex": -1e9,
        "net_gex": -5e8,
        "king_strike": 450.0,
        "king_gex": -1e8,
        "top_floor": 460.0,
        "top_ceiling": 440.0,
        "regime": "negative",
        "strikes_compact": [{"strike": 450.0, "gex": -1e8}],
    }
    
    snaps = generate_synthetic_snapshots(base, num_snapshots=50)
    
    assert len(snaps) == 50
    assert all(s["ticker"] == "SPY" for s in snaps)
    assert all(s["spot"] > 0 for s in snaps)
    assert all(s["regime"] in ("POSITIVE", "NEGATIVE", "positive", "negative") for s in snaps)
    
    # Check price variation
    spots = [s["spot"] for s in snaps]
    assert len(set(spots)) > 1  # Should have variation
    
    # Check regime changes
    regimes = [s["regime"] for s in snaps]
    assert len(set(regimes)) >= 1  # At least one regime


def test_synthetic_data_with_positive_regime():
    """Test synthetic data with positive regime."""
    from ml_synthetic import generate_synthetic_snapshots
    
    base = {
        "ticker": "SPY",
        "spot": 450.0,
        "total_gex": 1e9,
        "net_gex": 5e8,
        "king_strike": 450.0,
        "king_gex": 1e8,
        "top_floor": 460.0,
        "top_ceiling": 440.0,
        "regime": "POSITIVE",
        "strikes_compact": [{"strike": 450.0, "gex": 1e8}],
    }
    
    snaps = generate_synthetic_snapshots(base, num_snapshots=20)
    assert len(snaps) == 20
    assert all(s["regime"] in ("POSITIVE", "NEGATIVE", "positive", "negative") for s in snaps)


def test_walkforward_splits():
    """Test walk-forward split generation."""
    from ml_advanced import prepare_walkforward_data, extract_rich_features
    
    # Create synthetic snapshots
    snaps = []
    for i in range(100):
        spot = 450 + np.random.normal(0, 5)
        snaps.append({
            "ticker": "SPY",
            "spot": spot,
            "total_gex": -1e9 + np.random.normal(0, 1e7),
            "net_gex": -5e8 + np.random.normal(0, 5e6),
            "king_strike": spot + np.random.normal(0, 2),
            "king_gex": -1e8 + np.random.normal(0, 1e6),
            "top_floor": spot + 10,
            "top_ceiling": spot - 10,
            "regime": "negative" if np.random.random() < 0.7 else "positive",
            "strikes_compact": [{"strike": spot + j, "gex": np.random.normal(0, 1e6)} for j in range(-5, 5)],
        })
    
    splits = prepare_walkforward_data(snaps, train_window=30, test_window=10, step=5)
    
    assert len(splits) > 0
    
    for X_train, y_train, X_test, y_test in splits:
        assert X_train.shape[0] > 0
        assert X_test.shape[0] > 0
        assert X_train.shape[1] == X_test.shape[1]  # Same number of features
        assert len(np.unique(y_train)) >= 1  # At least one class


def test_rich_features():
    """Test rich feature extraction."""
    from ml_advanced import extract_rich_features
    
    snaps = [
        {"spot": 450.0, "total_gex": -1e9, "net_gex": -5e8, "king_strike": 450.0, "king_gex": -1e8, "top_floor": 460.0, "top_ceiling": 440.0, "regime": "negative", "strikes_compact": [{"strike": 450.0, "gex": -1e8}]},
        {"spot": 452.0, "total_gex": -1.1e9, "net_gex": -5.5e8, "king_strike": 452.0, "king_gex": -1.1e8, "top_floor": 462.0, "top_ceiling": 442.0, "regime": "negative", "strikes_compact": [{"strike": 452.0, "gex": -1.1e8}]},
    ]
    
    features = extract_rich_features(snaps, 1)
    
    assert "spot" in features
    assert "net_gex" in features
    assert "regime_positive" in features
    assert "regime_negative" in features
    assert "spot_change_pct" in features
    assert "gex_change_pct" in features
    assert "realized_vol" in features
    assert len(features) >= 15  # Should have many features