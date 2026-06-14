"""
backend/services/uoa.py

Unusual Options Activity (UOA) detection.
Stub — returns empty list until real implementation is wired in.
"""
from typing import Any


def calc_uoa(
    spot: float,
    contracts: list[dict[str, Any]],
    ticker: str,
    min_premium: float = 100_000,
    limit: int = 20,
) -> dict[str, Any]:
    """Detect unusual options activity. Stub returns empty."""
    return {"ticker": ticker, "spot": spot, "unusual": [], "n_scanned": len(contracts)}
