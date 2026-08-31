from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.mark.asyncio
async def test_zero_mid_price_is_not_replaced_by_last() -> None:
    from services.public_api_adapter import fetch_spot_from_public_api

    broker = MagicMock()
    account = MagicMock(account_id="acct")
    broker.get_trading_account.return_value = account
    broker.get_quotes = AsyncMock(
        return_value=[MagicMock(mid_price=0.0, last=12.0)]
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_spot_from_public_api("SPY")

    assert result == 0.0


@pytest.mark.asyncio
async def test_broker_initialization_requires_a_trading_account() -> None:
    from services.public_api_adapter import _get_broker

    with patch.dict(os.environ, {"PUBLIC_API_KEY": "secret"}, clear=True):
        broker = MagicMock()
        broker.auth = AsyncMock(return_value="token")
        broker.get_accounts = AsyncMock(return_value=[])
        broker.get_trading_account.return_value = None

        with patch(
            "services.public_api_adapter.PublicBroker",
            return_value=broker,
        ):
            import services.public_api_adapter as adapter

            adapter.BROKER = None
            result = await _get_broker()

    assert result is broker
    broker.auth.assert_awaited_once()
    broker.get_accounts.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_chain_returns_none_when_chain_fetch_fails() -> None:
    from services.public_api_adapter import fetch_chain_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_option_expirations = AsyncMock(
        return_value=["2026-09-18"]
    )
    broker.get_quotes = AsyncMock(
        return_value=[MagicMock(mid_price=500.0)]
    )
    broker.get_option_chain_parsed = AsyncMock(
        side_effect=RuntimeError("upstream unavailable")
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_chain_from_public_api("SPY")

    assert result is None
