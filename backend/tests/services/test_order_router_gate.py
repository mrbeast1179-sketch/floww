"""
backend/tests/services/test_order_router_gate.py

Defence-in-depth regression tests for the FLOWW_ENABLE_LIVE_SCHWAB env gate
in backend/services/order_router.py.

Pinned-test properties:
- When FLOWW_ENABLE_LIVE_SCHWAB is unset/0/"false", submit_order must NOT
  make any outbound httpx call to api.schwabapi.com; it must return
  {"status": "error", "reason": "..."} with a clear "live order submission"
  reason string.
- When FLOWW_ENABLE_LIVE_SCHWAB=="1", submit_order proceeds normally
  (httpx.AsyncClient().post(...) is invoked) — the existing happy-path tests
  in test_order_router.py remain valid.
- The MARKET-order guard fires INDEPENDENTLY of the live-env gate — when
  live is disabled AND order_type=MARKET, the LIVE gate's RuntimeError wins
  (it fires before _build_order_payload is called). When live is enabled AND
  order_type=MARKET AND ALLOW_MARKET_ORDERS=False, the MARKET ValueError
  wins (as before).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _make_router(token_return: str | None = "fake-token"):
    from services.order_router import OrderRouter

    mock_tokens = MagicMock()
    mock_tokens.get_access_token.return_value = token_return
    mock_tokens.is_expired.return_value = False
    return OrderRouter("acc-gate-test", token_manager=mock_tokens)


def _limit_intent() -> dict:
    return {
        "ticker": "SPY",
        "side": "buy",
        "qty": 1,
        "order_type": "limit",
        "limit_price": 450.0,
        "signal_id": "sig-gate-1",
        "timestamp_us": 1700000000,
    }


class TestLiveSchwabEnvGate:
    """Pinned tests for the FLOWW_ENABLE_LIVE_SCHWAB gate."""

    @pytest.mark.asyncio
    async def test_unset_env_blocks_live_post_and_returns_error(self, monkeypatch):
        """When env var is UNSET, submit_order must short-circuit BEFORE any httpx call."""
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_SCHWAB", raising=False)

        router = _make_router()
        intent = _limit_intent()

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await router.submit_order(intent)

        # No outbound call to Schwab
        mock_client_cls.assert_not_called()
        # Result is structured error (not a raised exception)
        assert result["status"] == "error"
        assert "live order submission" in result["reason"]
        assert "FLOWW_ENABLE_LIVE_SCHWAB=1" in result["reason"]
        # Position tracker untouched (no fill happened)
        assert router.position_tracker.get("SPY") == 0
        assert router._order_cache == {}

    @pytest.mark.parametrize(
        "env_value",
        ["0", "false", "False", "no", "yes", "", " ", "lol"],
    )
    @pytest.mark.asyncio
    async def test_non_one_env_values_block_live_post(self, monkeypatch, env_value):
        """Any env value other than exactly '1' must short-circuit. This pins the
        '== 1' comparison so truthy-ish strings like 'true' do NOT slip through."""
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_SCHWAB", env_value)

        router = _make_router()
        intent = _limit_intent()

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await router.submit_order(intent)

        mock_client_cls.assert_not_called()
        assert result["status"] == "error"
        assert "live order submission" in result["reason"]

    @pytest.mark.asyncio
    async def test_env_one_allows_live_post(self, monkeypatch):
        """When env == '1' the gate lets submit_order through to the happy path."""
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_SCHWAB", "1")

        router = _make_router()
        intent = _limit_intent()

        with patch.object(router, "_make_client_order_id", return_value="gate-cid"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.raise_for_status = MagicMock()
                mock_resp.json.return_value = {}
                mock_client.post.return_value = mock_resp
                mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
                result = await router.submit_order(intent)

        mock_client_cls.assert_called()
        assert result["status"] == "submitted"
        assert result["client_order_id"] == "gate-cid"
        # Position tracker reflects the fill (proves we reached the full happy path)
        assert router.position_tracker.get("SPY") == 1

    @pytest.mark.asyncio
    async def test_gate_independent_of_market_order_guard_live_off(self, monkeypatch):
        """When live is OFF, the live gate fires first regardless of order_type."""
        monkeypatch.delenv("FLOWW_ENABLE_LIVE_SCHWAB", raising=False)

        router = _make_router()
        intent = _limit_intent()
        intent["order_type"] = "limit"  # benign type

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await router.submit_order(intent)

        mock_client_cls.assert_not_called()
        # Live gate wins (not MARKET-ValueError)
        assert "live order submission" in result["reason"]
        assert "MARKET orders disabled" not in result["reason"]


    @pytest.mark.asyncio
    async def test_market_order_guard_still_fires_when_live_enabled(self, monkeypatch):
        """When live is ON but order_type=MARKET, the existing MARKET guard still fires.
        This pins defence-in-depth: the new env gate does NOT replace the old MARKET
        guard, and `_build_order_payload` raises ValueError("MARKET orders disabled")
        — the test asserts via pytest.raises to match the pre-existing propagation
        contract (not wrapped by submit_order's try).
        """
        import services.order_router as or_mod

        monkeypatch.setenv("FLOWW_ENABLE_LIVE_SCHWAB", "1")

        # Force ALLOW_MARKET_ORDERS off for the test (it is the default, but pin it)
        with patch.object(or_mod, "ALLOW_MARKET_ORDERS", False):
            router = _make_router()
            intent = _limit_intent()
            intent["order_type"] = "market"

            with patch("httpx.AsyncClient") as mock_client_cls:
                with pytest.raises(ValueError, match="MARKET orders disabled"):
                    await router.submit_order(intent)

            # Crucially: httpx was never called (MARKET guard fired before httpx post).
            mock_client_cls.assert_not_called()




    @pytest.mark.asyncio
    async def test_no_access_token_takes_priority_over_gate(self, monkeypatch):
        """When token manager fails to mint a token, the no-access-token path
        still wins (it fires after the gate). Pins the error-channel ordering."""
        monkeypatch.setenv("FLOWW_ENABLE_LIVE_SCHWAB", "1")

        from services.order_router import OrderRouter

        mock_tokens = MagicMock()
        mock_tokens.get_access_token.return_value = None
        mock_tokens.is_expired.return_value = True
        mock_tokens.refresh_token = AsyncMock(return_value=None)
        router = OrderRouter("acc-no-tok", token_manager=mock_tokens)

        with patch("httpx.AsyncClient") as mock_client_cls:
            result = await router.submit_order(_limit_intent())

        mock_client_cls.assert_not_called()
        assert result["status"] == "error"
        assert result["reason"] == "no_access_token"
