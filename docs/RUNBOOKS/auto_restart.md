# Auto-Restart Runbook

**Trigger:** `High Latency` alert fires (p99 latency > 200ms for 5+ minutes)

**Severity:** MEDIUM

**Automated:** Yes — executed by `runbook_executor.py` when `high_latency` alert fires.

## Steps

### 1. Check Resource Usage
```bash
top -l 1 -n 5 | head -20
df -h / | tail -1
```
**What we're looking for:** CPU > 90%, memory > 85%, disk > 90%.

### 2. Check DuckDB Queue Depth
```bash
curl -s http://localhost:8000/api/metrics | grep duckdb_queue_depth
```
**What we're looking for:** Queue depth > 10000 indicates backpressure.

### 3. Check WebSocket Connections
```bash
curl -s http://localhost:8000/api/ws/status
```
**What we're looking for:** 0 active connections means data feed is down.

### 4. Restart Service (Conditional)
**Condition:** Queue depth > 10000 OR WebSocket connections = 0
```bash
docker compose -f /Users/nav/GitHub/floww/docker-compose.yml restart backend
```
**Human override:** Create `/tmp/runbook_kill_switch` to prevent auto-restart.

### 5. Verify Latency Improved
```bash
curl -s -o /dev/null -w '%{time_total}' http://localhost:8000/api/health
```
**Expected:** < 200ms after restart completes (~10s).

## Rollback
If restart makes things worse:
```bash
docker compose -f /Users/nav/GitHub/floww/docker-compose.yml stop backend
docker compose -f /Users/nav/GitHub/floww/docker-compose.yml start backend
```

## Circuit Breaker
After 3 consecutive failures, auto-remediation is disabled. Reset with:
```python
from services.runbook_executor import executor
executor.reset_circuit_breaker("high_latency")
```

## Audit Trail
Every execution is logged with:
- Timestamp
- Steps executed + output
- Success/failure status
- Duration

View history:
```python
executor.get_execution_history()
```
