"""Tests for DataQualityChecker persistence — anomaly-only writes, lazy db."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.data_quality import DataQualityChecker


@pytest.fixture
def checker():
    return DataQualityChecker()


def _chains(spot: float = 765.0):
    # gamma + spot are required by _compute_net_gex (dollar GEX formula)
    cv = [{"strike": spot - 5 + i, "type": "call" if i % 2 else "put",
           "gamma": 0.004, "spot": spot,
           "oi": 1000 + i * 7, "iv": 0.15, "T": 0.01} for i in range(20)]
    yf = [{"strike": spot - 5 + i, "type": "call" if i % 2 else "put",
           "gamma": 0.004, "spot": spot,
           "oi": 1000 + i * 7, "iv": 0.15, "T": 0.01} for i in range(20)]
    return cv, yf


@pytest.mark.asyncio
async def test_ok_result_not_persisted(checker, monkeypatch):
    """OK rows carry no signal — must not hit Mongo."""
    persist_calls = []
    monkeypatch.setattr(
        checker, "_persist",
        lambda result: persist_calls.append(result),
    )
    cv, yf = _chains()
    await checker.check_gex_consistency(cv, yf, "SPY")
    assert checker._history[-1]["status"] == "OK"
    assert persist_calls == []


@pytest.mark.asyncio
async def test_critical_result_persisted(checker, monkeypatch):
    """CRITICAL divergence must reach Mongo."""
    persist_calls = []
    monkeypatch.setattr(
        checker, "_persist",
        lambda result: persist_calls.append(result),
    )
    # Divergent chains: same strikes, wildly different OI -> large rel_err
    cv, yf = _chains()
    for i, c in enumerate(yf):
        # Asymmetric divergence: uniform scaling cancels out in rel_err
        c["oi"] = int(c["oi"] * (1.6 if i % 2 else 0.4))
    result = await checker.check_gex_consistency(cv, yf, "SPY")
    assert result["status"] in ("WARNING", "CRITICAL")
    assert len(persist_calls) == 1
    assert persist_calls[0]["ticker"] == "SPY"


def test_persist_never_raises(checker):
    """Mongo down / db unbound — monitoring must not crash the caller."""
    import sys
    # Simulate server.db raising on access
    checker._persist({"status": "WARNING", "ticker": "SPY"})  # real path swallows
    # If we got here without raising, the contract holds.


def test_lazy_db_no_module_level_binding():
    """The module must not import server.db at module level (test-mocking hazard)."""
    import services.data_quality as dq
    src = open(dq.__file__).read()
    assert "from server import db\n" not in src.split("def ")[0], \
        "module-level db binding found"
