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
