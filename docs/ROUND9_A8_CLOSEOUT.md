# A8 Close-out — Schwab Streamer + WebSocket Hardening

## Summary

Audited and hardened the Schwab streamer (`backend/services/schwab_streamer.py`), WebSocket streamer (`backend/services/websocket_streamer.py`), and ingestion pipeline (`backend/services/ingestion_pipeline.py`). Added chaos tests for reconnect logic and queue backpressure. Fixed 6 bugs.

## Bugs Fixed

| # | File | Bug | Severity | Fix |
|---|------|-----|----------|-----|
| 1 | websocket_streamer.py | No `close_all()` method — clients never closed on shutdown | MEDIUM | Added `ConnectionManager.close_all(code=1001)` |
| 2 | schwab_streamer.py | `_message_timestamps` never reset on reconnect, grows unbounded | LOW | Reset `[]` in `_connect_and_stream()` after successful connect |
| 3 | schwab_streamer.py | `reconnect_count_24h` was cumulative, not rolling 24h window | LOW | Added `_reconnect_timestamps` list with 24h pruning |
| 4 | ingestion_pipeline.py | Dropped messages silently counted but never logged | MEDIUM | Added rate-limited warning log (1/10s) when drops occur |
| 5 | duckdb_engine.py | `_init_schema()` never called — tables don't exist on startup | HIGH | Called `_init_schema()` in `__init__` |
| 6 | mock_schwab_feed.py | BS d1 formula used `log(strike/spot)` instead of `log(spot/strike)` | LOW | Fixed argument order |

## Tests Added

- `tests/schwab/test_streamer_reconnect_chaos.py` — 5 tests
  - `test_reconnect_on_connection_closed` — reconnects within N attempts
  - `test_reconnect_gives_up_on_token_failure` — raises on invalid token
  - `test_reconnect_exponential_backoff` — delay doubles, capped at max
  - `test_stop_closes_websocket` — stop() closes underlying WS
  - `test_reconnect_resets_delay_on_success` — delay resets after success

- `tests/services/test_ingestion_backpressure.py` — 4 tests
  - `test_queue_fills_then_drains_without_loss_under_burst` — queue never exceeds max
  - `test_queue_full_drops_oldest` — oldest dropped when full
  - `test_metrics_track_drops` — drop counter accurate
  - `test_pipeline_restart_after_stop` — works after stop+restart cycle

## Test Results

```
tests/schwab/test_streamer_reconnect_chaos.py — 5 passed
tests/services/test_ingestion_backpressure.py — 4 passed
tests/services/test_ingestion_pipeline.py — 19 passed, 1 pre-existing failure
```

Pre-existing failure: `test_chain_greeks_sign_convention` — mock feed produces positive put delta (numba_greeks issue, not related to this round).

## Files Modified

- `backend/services/websocket_streamer.py` — added `close_all()`
- `backend/services/schwab_streamer.py` — reconnect timestamp rolling window, message_timestamps reset
- `backend/services/ingestion_pipeline.py` — drop warning log
- `backend/services/duckdb_engine.py` — `_init_schema()` called in `__init__`
- `backend/services/mock_schwab_feed.py` — BS d1 formula fix
- `backend/tests/schwab/test_streamer_reconnect_chaos.py` (NEW)
- `backend/tests/services/test_ingestion_backpressure.py` (NEW)
- `docs/ROUND9_A8_STREAMER_HEALTH.md` (NEW)

## Health Endpoint

`/api/admin/schwab/health` verified working:
- Returns all 6 required fields
- Requires X-API-Key header (admin auth)
- Response time <50ms (in-memory, no external calls)

## Architecture Notes

- Schwab streamer: well-designed with exponential backoff, token refresh, message parsing
- Ingestion pipeline: bounded queue with drop-oldest backpressure, batch DuckDB writes
- WebSocket streamer: topic-based broadcasts with per-client error isolation
- Mock feed: GBM price dynamics with full Greeks via numba_greeks, good test coverage
