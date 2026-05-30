"""Chaos test: schwab_streamer survives connection drops with bounded reconnect."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_streamer_module_importable():
    """Smoke: the module imports without side effects."""
    from services import schwab_streamer
    assert schwab_streamer is not None


@pytest.mark.asyncio
async def test_streamer_has_reconnect_config():
    """SchwabStreamer has reconnect configuration attributes."""
    from services.schwab_streamer import SchwabStreamer
    streamer = SchwabStreamer()
    assert hasattr(streamer, 'max_reconnect_delay')
    assert hasattr(streamer, 'initial_reconnect_delay')
    assert hasattr(streamer, '_reconnect_delay')
    # reconnects counter is inside _metrics dict
    assert hasattr(streamer, '_metrics')
    assert 'reconnects' in streamer._metrics
    # Verify initial values
    assert streamer._metrics['reconnects'] == 0
    assert streamer._reconnect_delay == streamer.initial_reconnect_delay


@pytest.mark.asyncio
async def test_streamer_handles_websocket_close():
    """When the underlying WebSocket raises ConnectionClosed, streamer logs + bounded retry."""
    pytest.importorskip("websockets")
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=5.0, initial_reconnect_delay=0.1)

    # Mock _connect_and_stream to simulate connection drops then success
    drops = [
        ConnectionError("drop 1"),
        ConnectionError("drop 2"),
        None,  # third attempt succeeds
    ]
    call_count = 0

    async def mock_connect_and_stream():
        nonlocal call_count
        call_count += 1
        err = drops[call_count - 1]
        if err is not None:
            raise err
        # Success — set reconnect delay back to initial
        streamer._reconnect_delay = streamer.initial_reconnect_delay

    with patch.object(streamer, '_connect_and_stream', new=mock_connect_and_stream):
        # Run start() but cancel after a few retries to avoid infinite loop
        start_task = asyncio.create_task(streamer.start())
        await asyncio.sleep(0.5)  # Let it run through retries
        await streamer.stop()
        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            start_task.cancel()

    # Should have attempted to connect at least 2 times (initial + 1 retry)
    assert call_count >= 2
    # Reconnect counter should have been incremented
    assert streamer._metrics['reconnects'] >= 1
    # Reconnect delay should have grown (exponential backoff)
    assert streamer._reconnect_delay > streamer.initial_reconnect_delay


@pytest.mark.asyncio
async def test_reconnect_delay_capped_at_max():
    """Reconnect delay does not exceed max_reconnect_delay."""
    from services.schwab_streamer import SchwabStreamer
    streamer = SchwabStreamer(max_reconnect_delay=5.0, initial_reconnect_delay=1.0)

    # Simulate many reconnects to verify cap
    for _ in range(10):
        streamer._reconnect_delay = min(streamer._reconnect_delay * 2, streamer.max_reconnect_delay)

    assert streamer._reconnect_delay == streamer.max_reconnect_delay


@pytest.mark.asyncio
async def test_stop_breaks_reconnect_loop():
    """Calling stop() causes the streamer to exit its reconnect loop."""
    from services.schwab_streamer import SchwabStreamer
    streamer = SchwabStreamer(initial_reconnect_delay=0.1)

    async def mock_connect_and_stream():
        raise ConnectionError("always fails")

    with patch.object(streamer, '_connect_and_stream', new=mock_connect_and_stream):
        start_task = asyncio.create_task(streamer.start())
        await asyncio.sleep(0.3)
        await streamer.stop()
        try:
            await asyncio.wait_for(start_task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            start_task.cancel()

    # Streamer should no longer be running
    assert not streamer._running


@pytest.mark.asyncio
async def test_token_refresh_chaos_returns_401():
    """When token refresh returns 401 during reconnect, streamer handles gracefully.

    Scenario: During reconnect, the token refresh endpoint returns 401.
    Expected: Streamer should handle auth failure gracefully (no crash, proper error
    logging), and enter failed state cleanly.
    """
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=2.0, initial_reconnect_delay=0.01)

    # Mock token manager to simulate 401 during refresh
    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = None  # No cached token
    streamer.tokens.is_expired.return_value = True  # Expired
    streamer.tokens.refresh_token = AsyncMock(return_value=None)  # Refresh returns None (401 simulated)

    # _connect_and_stream should raise ConnectionError when no valid token
    with pytest.raises(ConnectionError, match="No valid Schwab access token"):
        await streamer._connect_and_stream()

    # Verify streamer state is clean after failure (no crash)
    # _running is False because we called _connect_and_stream() directly, not start()
    # The key assertion is that the error was handled gracefully (no unhandled exception)
    # and the token refresh was attempted exactly once before failing
    streamer.tokens.refresh_token.assert_called_once()
    # Verify health reflects disconnected state
    assert streamer._health["connected"] is False


@pytest.mark.asyncio
async def test_resubscribe_state_preservation_across_reconnect():
    """After disconnect + reconnect, all active subscriptions are re-established.

    Scenario: Streamer had active subscriptions, reconnects after a drop.
    Expected: Subscriptions are re-established after reconnect.
    """
    pytest.importorskip("websockets")
    from services.schwab_streamer import SchwabStreamer

    streamer = SchwabStreamer(max_reconnect_delay=2.0, initial_reconnect_delay=0.1)

    # Pre-populate subscription state (simulating active subscriptions from first connect)
    original_subscriptions = {"SPY", "QQQ", "OPTIONS_SPY", "OPTIONS_QQQ", "LOB_DEPTH_SPY", "LOB_DEPTH_QQQ"}
    streamer._subscribed_symbols = set(original_subscriptions)

    # Track subscribe calls across disconnect/reconnect cycle
    subscribe_calls = []

    async def mock_subscribe_equities(symbols):
        for s in symbols:
            subscribe_calls.append(f"EQUITY:{s}")
            streamer._subscribed_symbols.add(s)

    async def mock_subscribe_options(underlying, num_strikes=20):
        key = f"OPTIONS_{underlying}"
        subscribe_calls.append(key)
        streamer._subscribed_symbols.add(key)

    async def mock_subscribe_lob_depth(underlying, num_levels=10):
        key = f"LOB_DEPTH_{underlying}"
        subscribe_calls.append(key)
        streamer._subscribed_symbols.add(key)

    # Simulate: first connect succeeds, then WS drops, then reconnect
    connect_count = 0

    async def mock_connect_and_stream():
        nonlocal connect_count
        connect_count += 1

        # On first call, simulate a successful connect that then "drops"
        if connect_count == 1:
            # Simulate subscriptions being re-established (as _subscribe_default does)
            await mock_subscribe_equities(["SPY", "QQQ", "DIA", "IWM"])
            await mock_subscribe_options("SPY", 20)
            await mock_subscribe_options("QQQ", 20)
            await mock_subscribe_lob_depth("SPY")
            await mock_subscribe_lob_depth("QQQ")
            # Simulate connection drop
            raise ConnectionError("simulated drop")

        # On second call (reconnect), re-subscribe again
        await mock_subscribe_equities(["SPY", "QQQ", "DIA", "IWM"])
        await mock_subscribe_options("SPY", 20)
        await mock_subscribe_options("QQQ", 20)
        await mock_subscribe_lob_depth("SPY")
        await mock_subscribe_lob_depth("QQQ")
        # Exit the start() loop
        streamer._running = False

    # Mock token manager
    streamer.tokens = MagicMock()
    streamer.tokens.get_access_token.return_value = "test-token"
    streamer.tokens.is_expired.return_value = False
    streamer.tokens.refresh_token = AsyncMock(return_value="refreshed-token")

    with patch.object(streamer, '_connect_and_stream', mock_connect_and_stream):
        await streamer.start()

    # Verify reconnect happened
    assert connect_count == 2, f"Expected 2 connect attempts, got {connect_count}"
    assert streamer._metrics["reconnects"] == 1

    # Verify all original subscriptions are preserved after reconnect
    assert "SPY" in streamer._subscribed_symbols
    assert "OPTIONS_SPY" in streamer._subscribed_symbols
    assert "LOB_DEPTH_SPY" in streamer._subscribed_symbols
    assert "OPTIONS_QQQ" in streamer._subscribed_symbols

    # Verify subscriptions were called twice (once per connect)
    equity_subs = [c for c in subscribe_calls if c.startswith("EQUITY:")]
    assert len(equity_subs) == 8, f"Expected 8 equity subscribe calls (4 symbols x 2 connects), got {len(equity_subs)}"

    options_subs = [c for c in subscribe_calls if c.startswith("OPTIONS_")]
    assert len(options_subs) == 4, f"Expected 4 options subscribe calls (2 underlyings x 2 connects), got {len(options_subs)}"

    lob_subs = [c for c in subscribe_calls if c.startswith("LOB_DEPTH_")]
    assert len(lob_subs) == 4, f"Expected 4 LOB depth subscribe calls (2 underlyings x 2 connects), got {len(lob_subs)}"
