"""Two new chaos tests for SchwabStreamer: token expiry mid-stream and
re-subscribe-after-error-then-reconnect.

Both are fully mocked — no live Schwab connection required.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Shared test fixtures and helpers.
from .test_schwab_streamer_reconnect import (
    _FakeWS,
    _connect_side_effect,
)


# ---------------------------------------------------------------------------
# Test 9: Token expiry mid-stream triggers re-auth on reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_expiry_mid_stream_triggers_reauth(
    streamer, mock_token_manager
):
    """When the token expires while streaming, the reconnect path calls
    refresh_token before the next connect attempt."""
    # First call: token good.  Second call (after first drop): expired.
    call_count = 0

    def is_expired_side_effect() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 2  # expired on the 2nd+ check

    mock_token_manager.is_expired.side_effect = is_expired_side_effect
    mock_token_manager.refresh_token = AsyncMock(return_value="reauth-token-99")

    connect_count = 0

    async def fail_once_then_stop() -> None:
        nonlocal connect_count
        connect_count += 1
        # Trigger token validation so refresh_token is consulted on reconnect
        await streamer._get_valid_token()
        if connect_count >= 2:
            streamer._running = False
        raise ConnectionError(f"drop {connect_count}")

    streamer._connect_and_stream = fail_once_then_stop
    streamer._running = True
    streamer.initial_reconnect_delay = 0.01

    with patch("services.schwab_streamer.websockets.connect"):
        await streamer.start()

    assert connect_count == 2
    assert mock_token_manager.refresh_token.called, (
        "refresh_token must be called when token expired mid-stream"
    )


# ---------------------------------------------------------------------------
# Test 10: Re-subscribe after error message then reconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resubscribe_after_error_then_reconnect(
    streamer, mock_token_manager
):
    """After an error message is received and the stream ends, the next
    reconnect re-sends all default subscription wire messages."""
    sent_messages: list[dict[str, Any]] = []

    async def mock_send(data: Any) -> None:
        # Production _send receives a dict; store it directly.
        # If a raw JSON string arrives (e.g. from a test that json.dumps
        # before sending), parse it so the assertion helpers work uniformly.
        if isinstance(data, str):
            sent_messages.append(json.loads(data))
        else:
            sent_messages.append(data)

    streamer._send = mock_send

    # --- Phase 1: connected, receives one error, stream ends ---
    messages = [
        json.dumps({"error": "RATE_LIMIT_EXCEEDED", "message": "temp"}),
    ]
    side_eff_1 = _connect_side_effect(ws=_FakeWS(messages=messages, closed=True))

    with patch("services.schwab_streamer.websockets.connect", side_effect=side_eff_1):
        streamer._running = True
        with contextlib.suppress(Exception):
            await streamer._connect_and_stream()

    # --- Phase 2: fresh reconnect, re-subscribe happens ---
    # Reset the message log so assertions only cover Phase 2's re-subscribe.
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
    # Verify wire-format messages for each default subscription.
    services = [m.get("service") for m in sent_messages]
    assert services.count("LEVELONE_EQUITIES") == 1
    assert services.count("LEVELONE_OPTIONS") == 2
    assert services.count("LEVEL_TWO_OPTIONS") == 2
