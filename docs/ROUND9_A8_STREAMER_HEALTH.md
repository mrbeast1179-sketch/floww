# Schwab Streamer Health Contract

## /api/admin/schwab/health (X-API-Key required)

Returns Schwab streamer health status. All values cached in process memory; does not hit Schwab API.

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `connected` | bool | True if WS is open AND token TTL > 0 |
| `token_ttl_seconds` | int | Seconds until OAuth token expiry (0 if no token) |
| `last_message_at` | ISO timestamp | Most recent inbound message (UTC) |
| `messages_per_minute_5min` | float | Rolling 5-minute message rate |
| `reconnect_count_24h` | int | Number of reconnects in last 24 hours (rolling window) |
| `lob_depth_rows_24h` | int | LOB depth rows persisted in 24h (cumulative, resets on restart) |

### Response Example

```json
{
  "connected": true,
  "token_ttl_seconds": 3540,
  "last_message_at": "2026-05-27T10:15:23.456789+00:00",
  "messages_per_minute_5min": 82.4,
  "reconnect_count_24h": 2,
  "lob_depth_rows_24h": 15234
}
```

## Reconnect Policy

- **Exponential backoff**: delay doubles each attempt (1s → 2s → 4s → ... → 60s cap)
- **Initial delay**: 1.0 second
- **Max delay**: 60.0 seconds
- **Reset on success**: delay resets to initial after successful connection
- **Bounded**: no infinite attempts — reconnects forever but with capped delay
- **Message timestamps**: reset on each successful reconnect (5-min rate window starts fresh)

## Backpressure Policy

- **Queue**: `asyncio.Queue(maxsize=10000)` (bounded)
- **On full**: drops oldest message, then inserts new one
- **Drop tracking**: `_metrics["dropped"]` incremented on each drop
- **Warning log**: rate-limited to 1 per 10 seconds when drops occur
- **Drain rate**: batch flush every 50ms, batch size 100 ticks / 50 chains

## WebSocket Client Management

- **ConnectionManager**: tracks all active WebSocket connections by topic
- **Graceful shutdown**: `close_all(code=1001, reason="Server shutting down")` closes all clients
- **Broadcast**: catches `ConnectionClosed` per-client, disconnects failed clients
- **Topic subscriptions**: per-topic sets, cleaned up on disconnect

## Round 10 Candidates

- Add `manager.close_all()` call to server shutdown lifespan handler
- Add Prometheus metric for `websocket_broadcast_latency_seconds`
- Add `enqueue_lob_depth` to existing backpressure tests
- Consider making `max_reconnect_delay` configurable via env var
- Add test: verify `close_all()` is called during server shutdown
