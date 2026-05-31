"""
Tests for the canonical degraded_response contract.

The degraded_response shape was unified in Phase 1 to satisfy both:
  - The test contract: {status, reason, stale, retry_after, asof}
  - Legacy callers: {degraded, error_type, detail, spot, contracts}

This regression test ensures neither side breaks on a future edit.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.fetch_coordinator import degraded_response  # noqa: E402


class TestDegradedResponseContract:
    """Verify the unified degraded_response shape."""

    def test_has_test_contract_fields(self):
        """Fields required by the test suite (test_fallback_responses.py)."""
        resp = degraded_response("test_error", "Something went wrong")
        assert resp["status"] == "degraded"
        assert resp["reason"] == "test_error"
        assert resp["stale"] is True
        assert isinstance(resp["retry_after"], int)
        assert isinstance(resp["asof"], float)

    def test_has_legacy_fields(self):
        """Fields required by legacy callers (routes/analytics.py)."""
        resp = degraded_response("computation_error", "division by zero")
        assert resp["degraded"] is True
        assert resp["error_type"] == "computation_error"
        assert resp["detail"] == "division by zero"
        assert "spot" in resp
        assert "contracts" in resp

    def test_superset_does_not_regress(self):
        """All keys expected by either side must be present."""
        resp = degraded_response("fetch_error", "timeout", retry_after=30)
        required_keys = {
            "status", "reason", "stale", "retry_after", "asof",   # test contract
            "degraded", "error_type", "detail", "spot", "contracts", "data",  # legacy
        }
        for key in required_keys:
            assert key in resp, f"Missing key: {key}"

    def test_retry_after_defaults_to_15(self):
        """Default retry_after should be 15 seconds."""
        resp = degraded_response("test", "test")
        assert resp["retry_after"] == 15

    def test_retry_after_custom_value(self):
        """Custom retry_after propagates correctly."""
        resp = degraded_response("test", "test", retry_after=60)
        assert resp["retry_after"] == 60

    def test_asof_is_recent(self):
        """asof should be close to current time."""
        before = time.time()
        resp = degraded_response("test", "test")
        after = time.time()
        assert before - 1 <= resp["asof"] <= after + 1

    def test_empty_contracts_and_none_spot(self):
        """Degraded responses should have empty contracts list and None spot."""
        resp = degraded_response("no_data", "No data available")
        assert resp["contracts"] == []
        assert resp["spot"] is None
        assert resp["data"] is None
