"""Two new chaos tests for SchwabStreamer: token expiry mid-stream and
re-subscribe-after-error-then-reconnect.

Both are fully mocked — no live Schwab connection required.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .test_schwab_streamer_reconnect import _FakeWS, _connect_side_effect


@pytest.fixture
def streamer(mock_token_manager):
    from services.schwab_streamer import SchwabStreamer
    s = SchwabStreamer(token_manager=mock_token_manager)
    return s


@pytest.fixture
def mock_token_manager():
    tm = MagicMock()
    tm.get_access_token.return_value = "fake-access-token-12345"
    tm.is_expired.return_value = False
    tm.refresh_token = AsyncMock(return_value="refresh-token-67890")
    return tm


@pytest.mark.asyncio
async def test_token_expiry_mid_stream_triggers_reauth(
    streamer, mock_token_manager
) -> None:
    """When the token is expired, the reconnect path calls refresh_token
    before the next connect attempt — not just at initial startup.

    Production flow: start() → _connect_and_stream() → _get_valid_token()
    → if expired, refresh_token().  We let _connect_and_stream run for
    real but patch websockets.connect to drop, triggering reconnect.
    """
    mock_token_manager.is_expired.return_value = True
    mock_token_manager.refresh_token = AsyncMock(return_value="new-token-99")
    mock_token_manager.get_access_token.return_value = "stale-token-00"

    connect_count = 0

    async def drop_after_connect(*args: Any, **kwargs: Any) -> None:
        nonlocal connect_count
        connect_count += 1
        if connect_count >= 2:
            streamer._running = False
            return
        raise ConnectionError("drop after first connect")

    streamer._running = True
    streamer.initial_reconnect_delay = 0.01

    with patch(
        "services.schwab_streamer.websockets.connect",
        side_effect=drop_after_connect,
    ):
        await streamer.start()

    assert connect_count == 2, f"Expected 2 attempts, got {connect_count}"
    assert mock_token_manager.refresh_token.called, (
        "refresh_token must be called when token is expired"
    )


@pytest.mark.asyncio
async def test_resubscribe_after_error_then_reconnect(
    streamer, mock_token_manager
) -> None:
    """After an error message is received and the stream ends, the next
    reconnect re-sends all default subscription wire messages."""
    sent_messages: list[dict[str, Any]] = []

    async def mock_send(data: Any) -> None:
        sent_messages.append(data)

    streamer._send = mock_send

    # --- Phase 1: connected, receives one error, stream ends ---
    messages = [
        json.dumps({"error": "RATE_LIMIT_EXCEEDED", "message": "temp"}),
    ]
    side_eff_1 = _connect_side_effect(
        ws=_FakeWS(messages=messages, closed=True)
    )

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_eff_1):
        streamer._running = True
        with contextlib.suppress(Exception):
            await streamer._connect_and_stream()

    # --- Phase 2: fresh reconnect, re-subscribe happens ---
    sent_messages.clear()
    subscribe_calls: list[str] = []

    async def tracking_subscribe() -> None:
        subscribe_calls.append("called")
        await streamer._subscribe_equities(["SPY", "QQQ", "DIA", "IWM"])
        await streamer._subscribe_options("SPY", num_strikes=20)
        await streamer._subscribe_options("QQQ", num_strikes=20)
        await streamer._subscribe_lob_depth("SPY")
        await streamer._subscribe_lob_depth("QQQ")

    streamer._subscribe_default = tracking_subscribe

    side_eff_2 = _connect_side_effect(ws=_FakeWS(messages=[], closed=True))
    with patch("services.schwab_streamer.websockets.connect", side_effect=side_eff_2):
        streamer._running = True
        with contextlib.suppress(Exception):
            await streamer._connect_and_stream()

    assert len(subscribe_calls) == 1, "Should re-subscribe after error-then-reconnect"
    services = [m.get("service") for m in sent_messages]
    assert services.count("LEVELONE_EQUITIES") == 1
    assert services.count("LEVELONE_OPTIONS") == 2
    assert services.count("LEVEL_TWO_OPTIONS") == 2
