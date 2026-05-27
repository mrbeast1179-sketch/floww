# Agent A8 — Schwab Streamer + WebSocket Hardening (target: 3 hours)

**You are Agent A8.** Read `_PREAMBLE.md`. Scope: audit + harden the Schwab streamer (`backend/schwab/*`), `services/websocket_streamer.py`, and `services/ingestion_pipeline.py`. Add chaos tests for reconnect logic. Document the health-metric contract.

Your file ownership: `backend/schwab/*.py`, `backend/services/websocket_streamer.py`, `backend/services/ingestion_pipeline.py`, new test files, `docs/ROUND9_A8_*`.

---

## Mission

| # | Task | Min |
|---|------|-----|
| 1 | Pre-flight + inventory | 20 |
| 2 | Read Schwab streamer + identify failure modes | 30 |
| 3 | Read websocket_streamer + check task lifecycle | 25 |
| 4 | Read ingestion_pipeline + queue backpressure | 20 |
| 5 | Verify /admin/schwab/health endpoint contract | 15 |
| 6 | Chaos test: connection drop + reconnect | 30 |
| 7 | Chaos test: backpressure under message storm | 25 |
| 8 | Fix any real bugs found (TDD) | 20 |
| 9 | Document streamer health contract | 15 |
| 10 | Close-out | 10 |

Total ~210 min (3.5 hr — slightly over budget; trim Tasks 6-7 if running long).

---

## Task 1 — Pre-flight + inventory (20 min)

- [ ] **1.1** `pwd` canonical.
- [ ] **1.2** Inventory files in scope:
  ```bash
  ls backend/schwab/ 2>&1 | head -10
  ls backend/services/websocket_streamer.py backend/services/ingestion_pipeline.py 2>&1
  ```
- [ ] **1.3** Find existing tests:
  ```bash
  ls backend/tests/schwab/ backend/tests/services/test_websocket* backend/tests/services/test_ingestion* 2>&1 | head -10
  ```
- [ ] **1.4** Confirm prior commits that touched these files (so you build on existing pattern, not re-invent):
  ```bash
  git log --oneline backend/schwab/ backend/services/websocket_streamer.py backend/services/ingestion_pipeline.py | head -10
  ```
- [ ] **1.5** First pulse.

---

## Task 2 — Read Schwab streamer + failure modes (30 min)

- [ ] **2.1** Open every `.py` in `backend/schwab/` with `Read`. List the classes/functions.
- [ ] **2.2** Identify:
  - Connection class — does it handle disconnect gracefully?
  - Token refresh — what happens on 401? Exponential backoff?
  - Reconnect logic — bounded retries or infinite loop?
  - Message handlers — do they catch parse errors?
  - State on reconnect — does it re-subscribe to all symbols or lose state?
- [ ] **2.3** Look for `health` method or `get_health()`:
  ```bash
  grep -rn 'def get_health\|def health\|@property' backend/schwab/ 2>&1 | head -10
  ```
- [ ] **2.4** Note bugs in `/tmp/a8_schwab_bugs.txt`.
- [ ] **2.5** Pulse.

---

## Task 3 — Read websocket_streamer + task lifecycle (25 min)

- [ ] **3.1** Open `backend/services/websocket_streamer.py` with `Read`.
- [ ] **3.2** Per the L1 leak audit (line 125-127), this file creates 3 tasks in `start()`:
  ```python
  asyncio.create_task(self._tick_broadcast_loop()),
  asyncio.create_task(self._analytics_broadcast_loop()),
  asyncio.create_task(self._toxicity_broadcast_loop()),
  ```
  These ARE stored in a list (per audit; "already managed, not a leak") — verify:
  ```bash
  grep -nA3 'asyncio.create_task' backend/services/websocket_streamer.py | head -20
  ```
- [ ] **3.3** Check `stop()`:
  - Does it cancel each task?
  - Does it await each cancel?
  - Does it close connected clients with proper close code (1001 = going away)?
- [ ] **3.4** Check the broadcast loops:
  - Are they bounded by `_shutdown_event`?
  - Do they catch ConnectionClosed exceptions per-client?
  - Do they handle the case where the broadcast queue grows unbounded?
- [ ] **3.5** Pulse.

---

## Task 4 — Read ingestion_pipeline + backpressure (20 min)

- [ ] **4.1** `Read` the file.
- [ ] **4.2** Check the queue:
  - Is it `asyncio.Queue` (bounded? unbounded?)
  - What happens when full — drop / block / log?
  - Stats: does it expose queue depth?
- [ ] **4.3** Check the consumer task:
  - Does it loop forever, or honor `_shutdown_event`?
  - Does it batch writes or one-at-a-time?
- [ ] **4.4** Pulse.

---

## Task 5 — Verify /admin/schwab/health endpoint (15 min)

- [ ] **5.1** Start backend:
  ```bash
  lsof -ti :8000 | xargs kill -9 2>/dev/null
  cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_a8.log 2>&1 &
  sleep 4
  ```
- [ ] **5.2** Hit the health endpoint (it requires X-API-Key per H11):
  ```bash
  # First find the API key value
  grep API_SECRET_KEY backend/.env 2>&1 | head -3
  # Then hit with key
  KEY=$(grep '^API_SECRET_KEY' backend/.env | cut -d= -f2)
  curl -s -H "X-API-Key: $KEY" 'http://localhost:8000/admin/schwab/health' | python3 -m json.tool
  ```
- [ ] **5.3** Verify response includes: `connected`, `token_ttl_seconds`, `last_message_at`, `messages_per_minute_5min`, `reconnect_count_24h`, `lob_depth_rows_24h`.
- [ ] **5.4** Pulse.

---

## Task 6 — Chaos test: connection drop + reconnect (30 min)

- [ ] **6.1** Create `backend/tests/schwab/test_streamer_reconnect_chaos.py`:
  ```python
  """Chaos test: streamer survives connection drops with bounded reconnect."""
  import asyncio
  import pytest
  from unittest.mock import AsyncMock, MagicMock, patch
  
  
  @pytest.mark.asyncio
  async def test_reconnect_on_connection_closed():
      """When the underlying socket raises ConnectionClosed, streamer reconnects within N attempts."""
      # If Schwab streamer class doesn't exist or has a different name, use grep to find it.
      try:
          from schwab.streamer import SchwabStreamer
      except ImportError:
          pytest.skip("SchwabStreamer not at expected import path — locate first")
  
      streamer = SchwabStreamer()
      with patch.object(streamer, "_connect", new=AsyncMock()) as mock_connect, \
           patch.object(streamer, "_listen", new=AsyncMock(side_effect=[
               ConnectionError("simulated drop"),
               ConnectionError("simulated drop 2"),
               None,  # third attempt succeeds
           ])):
          await streamer.run_with_retry(max_retries=3)
          assert mock_connect.call_count >= 2, "should have reconnected"
  
  
  @pytest.mark.asyncio
  async def test_reconnect_gives_up_after_max_retries():
      """Bounded retry: after N attempts, raise rather than infinite loop."""
      try:
          from schwab.streamer import SchwabStreamer
      except ImportError:
          pytest.skip("SchwabStreamer import path")
  
      streamer = SchwabStreamer()
      with patch.object(streamer, "_connect", new=AsyncMock()), \
           patch.object(streamer, "_listen", new=AsyncMock(side_effect=ConnectionError("always fails"))):
          with pytest.raises(ConnectionError):
              await streamer.run_with_retry(max_retries=3)
  ```
  **IMPORTANT:** Adjust import path + method names to match actual code. Use `grep -rn 'class Schwab' backend/schwab/` to find. If the methods aren't named `_connect` / `_listen` / `run_with_retry`, adapt the test.
- [ ] **6.2** Run: `cd backend && .venv/bin/python3 -m pytest tests/schwab/test_streamer_reconnect_chaos.py -v 2>&1 | tail -10`.
- [ ] **6.3** If the methods don't exist (i.e., your test skips), the streamer LACKS reconnect logic — note in close-out, add it in Task 8.
- [ ] **6.4** Commit (subject `test(a8): chaos test for reconnect`).
- [ ] **6.5** Pulse.

---

## Task 7 — Chaos test: queue backpressure under message storm (25 min)

- [ ] **7.1** Create `backend/tests/services/test_ingestion_backpressure.py`:
  ```python
  """When the ingestion queue fills, the pipeline must apply backpressure, not crash or hang."""
  import asyncio
  import pytest
  
  
  @pytest.mark.asyncio
  async def test_queue_fills_then_drains_without_loss_under_burst():
      from services.ingestion_pipeline import IngestionPipeline
      from services.duckdb_engine import duckdb_engine
  
      pipeline = IngestionPipeline(
          db=duckdb_engine,
          batch_size=100,
          flush_interval_sec=0.05,
      )
      await pipeline.start()
  
      # Burst 1000 messages
      for i in range(1000):
          await pipeline.enqueue_tick({"symbol": "SPY", "price": 450 + i * 0.01, "ts": i})
  
      # Wait briefly for drain
      await asyncio.sleep(0.5)
      depth_after = pipeline.queue_depth()
      assert depth_after < 100, f"queue did not drain: {depth_after}"
  
      await pipeline.stop()
  
  
  @pytest.mark.asyncio
  async def test_queue_full_drops_oldest_or_signals_caller():
      """If the queue is bounded and full, the behavior must be documented (drop or error)."""
      from services.ingestion_pipeline import IngestionPipeline
      from services.duckdb_engine import duckdb_engine
  
      pipeline = IngestionPipeline(
          db=duckdb_engine,
          batch_size=10,
          flush_interval_sec=10,  # never flushes, so queue stays full
      )
      await pipeline.start()
  
      # Fill way past capacity
      enqueue_results = []
      for i in range(2000):
          try:
              await pipeline.enqueue_tick({"symbol": "SPY", "ts": i})
              enqueue_results.append("ok")
          except (asyncio.QueueFull, RuntimeError) as e:
              enqueue_results.append(f"blocked:{type(e).__name__}")
      
      # If queue is bounded, we should see at least one blocked or dropped enqueue
      # If queue is unbounded, all 2000 succeeded — that's its own contract decision
      ok_count = enqueue_results.count("ok")
      print(f"enqueue results: {ok_count} ok, {len(enqueue_results) - ok_count} blocked/dropped")
      
      await pipeline.stop()
  ```
- [ ] **7.2** Run. Adjust method names (`enqueue_tick`, `queue_depth`) if they don't match real code.
- [ ] **7.3** Commit. Pulse.

---

## Task 8 — Fix any real bugs (20 min)

Based on Tasks 2-7 findings, apply minimal fixes. Examples:
- Add `_shutdown_event.is_set()` check in broadcast loops
- Wrap `await ws.send(...)` in try/except `ConnectionClosed`
- Add `max_retries` to reconnect logic if missing
- Add `client.close(code=1001)` in `stop()` if missing

- [ ] **8.1** Apply each fix with `Edit`. One bug, one commit.
- [ ] **8.2** Verify each with the relevant pytest module.
- [ ] **8.3** Commit + push + gate per fix.

---

## Task 9 — Document streamer health contract (15 min)

Write `docs/ROUND9_A8_STREAMER_HEALTH.md`:
```markdown
# Schwab Streamer Health Contract

## /admin/schwab/health (X-API-Key required)

Returns:
- connected: bool — true if WS is open AND token TTL > 0
- token_ttl_seconds: int — seconds until OAuth token expiry
- last_message_at: ISO timestamp — most recent inbound message
- messages_per_minute_5min: float — rolling 5-min msg rate
- reconnect_count_24h: int — number of reconnects in last 24h
- lob_depth_rows_24h: int — LOB depth rows persisted in 24h

## Reconnect policy

- Exponential backoff with jitter
- Max <N> retries (see schwab/streamer.py:<line>)
- On exhaustion, returns to disconnected state and surfaces in health endpoint

## Backpressure policy

- Queue: <type> (bounded N, unbounded, etc.)
- On full: <behavior>
- Drain rate: <batch_size> every <flush_interval_sec>s

## Round 10 candidates
- <items>
```

- [ ] **9.1** Commit + push + gate.
- [ ] **9.2** Pulse.

---

## Task 10 — Close-out (10 min)

- [ ] **10.1** `docs/ROUND9_A8_CLOSEOUT.md`.
- [ ] **10.2** Commit + push + gate.
- [ ] **10.3** Final pulse.

---

## Halt conditions

1. Schwab streamer module not found at expected path — HALT and report, don't guess.
2. Chaos test requires a real Schwab connection — HALT, the test should mock not connect.
3. A fix in `services/websocket_streamer.py` would race with A1's earlier on_stop changes — verify A1 didn't already wire close logic; STOP if uncertain.
4. Origin gate fails.
5. 15-min pulse gap.
