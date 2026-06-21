"""
Variance of order-flow Imbalance (VPIN) domain primitives.

Pure-function mathematical kernel for VPIN (Volume-Synchronized Probability
of Informed Trading) and the underlying Bulk Volume Classification (BVC).

References
----------
Easley, D., López de Prado, M.M., & O'Hara, M. (2012).
"Flow Toxicity and Liquidity in a High-frequency World."
Review of Financial Studies, 25(5), 1457-1493.

Functions
---------
``standard_normal_cdf(x)``
    Standard normal CDF via ``math.erf`` (no scipy dependency).
``bulk_volume_classify(price_changes, volumes, sigma=None, dt=1.0)``
    BVC split:   ``V^B = V * Φ(ΔP / (σ √dt))``, ``V^S = V - V^B``.
``volume_imbalance(buy_volumes, sell_volumes)``
    ``|V^B - V^S|`` per bucket.
``compute_vpin(buy_buckets, sell_buckets, total_buckets)``
    ``Σ|V^B - V^S| / ΣV`` over a rolling window of buckets.
``quote_imbalance(bid_size, ask_size)``
    Top-of-book Quote Imbalance: ``(B - A) / (B + A)`` in [-1, 1].
"""

from __future__ import annotations

import math

import numpy as np

# ----------------------------------------------------------------------
# Standard normal CDF  Φ(x) = ½ · (1 + erf(x / √2))
# ----------------------------------------------------------------------

def standard_normal_cdf(x: float | np.ndarray) -> float | np.ndarray:
    """Standard normal CDF: ``Φ(x) = 0.5 · (1 + erf(x / √2))``.

    Dispatches to ``math.erf`` for scalar inputs and to
    ``np.vectorize(math.erf)`` for array inputs — avoids a scipy
    dependency. Returns the same numeric type as the input.

    Parameters
    ----------
    x : float or np.ndarray
        Input value(s).

    Returns
    -------
    float or np.ndarray
        ``Φ(x)`` in [0, 1].
    """
    if isinstance(x, (int, float)):
        return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))
    arr = np.asarray(x, dtype=np.float64)
    return 0.5 * (1.0 + np.vectorize(math.erf)(arr / math.sqrt(2.0)))


# ----------------------------------------------------------------------
# Bulk Volume Classification (BVC)
# ----------------------------------------------------------------------

def bulk_volume_classify(
    price_changes: np.ndarray,
    volumes: np.ndarray,
    sigma: float | None = None,
    dt: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Classify a sequence of trades into buy and sell volume using BVC.

    For each trade ``t``::

        z_t   = ΔP_t / (σ · √dt)
        Φ(z_t) = 0.5 · (1 + erf(z_t / √2))
        V^B_t = V_t · Φ(z_t)
        V^S_t = V_t − V^B_t

    Parameters
    ----------
    price_changes : np.ndarray
        Per-trade price changes ``ΔP``.
    volumes : np.ndarray
        Per-trade volumes (positive).
    sigma : float, optional
        Realized volatility. If ``None``, defaults to ``np.std(price_changes)``
        with a ``mean(|ΔP|)`` fallback when the std is 0/NaN; if that is also 0,
        splits each trade evenly.
    dt : float
        Observation interval for normalization. Must be positive.

    Returns
    -------
    (buy_volumes, sell_volumes) : tuple[np.ndarray, np.ndarray]
        Buyer-initiated and seller-initiated volume per trade.

    Raises
    ------
    ValueError
        If ``dt <= 0`` or shapes mismatch.
    """
    pc = np.asarray(price_changes, dtype=np.float64)
    v = np.asarray(volumes, dtype=np.float64)
    if pc.shape != v.shape:
        raise ValueError("price_changes and volumes must have the same shape")
    if dt <= 0:
        raise ValueError("dt must be positive")

    if sigma is None:
        sigma = float(np.std(pc))

    if sigma <= 0.0 or math.isnan(sigma) or math.isinf(sigma):
        mean_abs = float(np.mean(np.abs(pc)))
        if mean_abs <= 0.0 or math.isnan(mean_abs):
            return v * 0.5, v * 0.5
        sigma = mean_abs

    z = pc / (sigma * math.sqrt(dt))
    phi = np.asarray(standard_normal_cdf(z), dtype=np.float64)
    buy_volumes = v * phi
    sell_volumes = v - buy_volumes
    return buy_volumes, sell_volumes


# ----------------------------------------------------------------------
# Per-bucket imbalance |V^B − V^S|
# ----------------------------------------------------------------------

def volume_imbalance(
    buy_volumes: np.ndarray,
    sell_volumes: np.ndarray,
) -> np.ndarray:
    """Compute per-bucket absolute imbalance ``|V^B − V^S|``.

    Parameters
    ----------
    buy_volumes, sell_volumes : np.ndarray
        Buyer/seller volumes per bucket (same shape).

    Returns
    -------
    np.ndarray
        Element-wise ``|V^B − V^S|``.

    Raises
    ------
    ValueError
        If shapes differ.
    """
    b = np.asarray(buy_volumes, dtype=np.float64)
    s = np.asarray(sell_volumes, dtype=np.float64)
    if b.shape != s.shape:
        raise ValueError("buy_volumes and sell_volumes must have the same shape")
    return np.abs(b - s)


# ----------------------------------------------------------------------
# VPIN scalar   Σ|V^B − V^S| / ΣV
# ----------------------------------------------------------------------

def compute_vpin(
    buy_buckets: np.ndarray | list[float],
    sell_buckets: np.ndarray | list[float],
    total_buckets: np.ndarray | list[float],
) -> float:
    """Compute the VPIN scalar over a rolling window of finalized buckets.

    ``VPIN = Σ |V^B − V^S| / Σ V`` over the n most-recent buckets.

    Parameters
    ----------
    buy_buckets, sell_buckets, total_buckets : array-like of float
        Finalized bucket-level volumes (same length).

    Returns
    -------
    float
        VPIN in [0, 1]. Returns 0.0 when ``Σ V <= 0``.
    """
    b = np.asarray(buy_buckets, dtype=np.float64)
    s = np.asarray(sell_buckets, dtype=np.float64)
    t = np.asarray(total_buckets, dtype=np.float64)
    total_vol = float(np.sum(t))
    if total_vol <= 0.0:
        return 0.0
    return float(np.sum(np.abs(b - s)) / total_vol)


# ----------------------------------------------------------------------
# Quote Imbalance   (B − A) / (B + A)
# ----------------------------------------------------------------------

def quote_imbalance(bid_size: float, ask_size: float) -> float:
    """Top-of-book Quote Imbalance (QI) in [-1, 1].

    ``QI = (B − A) / (B + A)``. Positive values indicate bid-side pressure.
    Returns ``0.0`` when ``bid_size + ask_size <= 0``.

    Parameters
    ----------
    bid_size, ask_size : float
        Total size at the best bid and best ask respectively.

    Returns
    -------
    float
        QI in [-1, 1].
    """
    denom = float(bid_size) + float(ask_size)
    if denom <= 0.0:
        return 0.0
    return (float(bid_size) - float(ask_size)) / denom
