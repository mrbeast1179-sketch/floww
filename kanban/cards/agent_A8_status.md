# A8 Status — Schwab Streamer + WebSocket Hardening

[2026-05-27T10:45:00Z] A8 :: DONE :: All tasks complete :: HEAD=4174e42

## Summary
- 6 bugs fixed across 5 files
- 9 new chaos tests (5 reconnect + 4 backpressure) — all pass
- Health contract documented
- Close-out written

## Bugs Fixed
1. websocket_streamer: added close_all() for graceful shutdown
2. schwab_streamer: _message_timestamps reset on reconnect
3. schwab_streamer: reconnect_count_24h now rolling 24h window
4. ingestion_pipeline: rate-limited drop warning log
5. duckdb_engine: _init_schema() called in __init__ (HIGH — tables never created)
6. mock_schwab_feed: BS d1 formula corrected (spot/strike)

## Tests
- tests/schwab/test_streamer_reconnect_chaos.py — 5 passed
- tests/services/test_ingestion_backpressure.py — 4 passed
- tests/services/test_ingestion_pipeline.py — 19 passed, 1 pre-existing failure

## Docs
- docs/ROUND9_A8_STREAMER_HEALTH.md
- docs/ROUND9_A8_CLOSEOUT.md
