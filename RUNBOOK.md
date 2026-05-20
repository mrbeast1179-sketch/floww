# RUNBOOK.md — Confluence Decoder Operations

## Starting the System Locally

### Prerequisites
- Python 3.11 venv at `backend/.venv`
- MongoDB Atlas connection string in `.env`
- Databento API key in `.env`
- Node.js ≥ 18 for frontend

### Environment Setup
```bash
cd /Users/nav/Documents/GitHub/floww
cp .env.example .env
# Edit .env with your keys:
#   MONGODB_URI=mongodb+srv://...
#   DATABENTO_API_KEY=...
#   SCHWAB_API_KEY=...
#   SCHWAB_SECRET=...
```

### Start Backend
```bash
cd backend
source .venv/bin/activate
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```
API docs available at http://localhost:8000/docs

### Start Frontend
```bash
cd frontend
npm install   # first time only
npm run start
```
React app available at http://localhost:3000

### Verify Health
```bash
curl http://localhost:8000/api/health
# Expected: {"app":"confluence-decoder","version":"2.0","status":"healthy",...}
```

## Running Tests

### Full Test Suite
```bash
cd backend
source .venv/bin/activate
python -m pytest tests/ -v
```

### Microstructure Math Tests Only
```bash
python -m pytest tests/services/test_microstructure_math.py -v
```

### Specific Test Class
```bash
python -m pytest tests/services/test_microstructure_math.py::TestVpinClassification -v
```

### Frontend Tests
```bash
cd frontend
npm run test
```

## Truth Audit

The truth audit validates that the system's data and models are consistent.

```bash
cd /Users/nav/Documents/GitHub/floww
bash qc/audit/truth_audit.sh
```

Expected output: `ALL CHECKS PASSED` or a list of failures.

### When Truth Audit Goes Red
1. Check `memory/reference_truth_audit.md` for the last known good state
2. Compare current failures against the reference
3. Common causes:
   - MongoDB connection dropped → check `MONGODB_URI` and network
   - Stale data → re-run `scripts/backfill_gex_history.py`
   - Model drift → retrain with `scripts/train_production.py`

## Deployment

### Docker Compose
```bash
docker-compose up -d
```

### Manual Deployment
1. Build frontend: `cd frontend && npm run build`
2. Copy build to backend: `cp -r build ../backend/static/`
3. Start backend: `cd backend && python -m uvicorn server:app --host 0.0.0.0 --port 8000`

## Monitoring

### Logs
- Backend logs: stdout (uvicorn) + `logs/backend.log` if configured
- Structured JSON logs in production mode
- Tail logs: `tail -f logs/backend.log | jq .`

### Metrics
- Prometheus endpoint: `GET /metrics`
- Key metrics:
  - `floww_vpin_current` — current VPIN per ticker
  - `floww_anomaly_score` — reconstruction error
  - `floww_trinity_score` — Trinity Alignment Index
  - `floww_websocket_connections` — active WS connections
  - `floww_api_request_duration_seconds` — API latency histogram

### Health Checks
- `GET /api/health` — overall system health
- `GET /api/health/mongodb` — MongoDB connectivity
- `GET /api/health/duckdb` — DuckDB engine status

## Common Errors + Fixes

### ImportError: cannot import name 'metrics' from 'services.observability'
**Cause:** Missing `metrics` namespace in observability module.
**Fix:** Already fixed in latest commit. Pull latest: `git pull origin main`

### MongoDB SSL Error (errno=54)
**Cause:** Network reset during SSL handshake.
**Fix:** Check firewall/VPN. The system degrades gracefully — DuckDB still works.

### TestClient + Motor Async Event Loop (24 test failures)
**Cause:** Known issue — TestClient creates a new event loop per test but Motor
client is bound to the first loop.
**Fix:** Migrate to `pytest-asyncio` with proper event loop fixtures. Not yet done.

### Frontend Dev Server Hangs
**Cause:** craco/webpack first build can take 3-5 minutes.
**Fix:** Wait for "Compiled successfully" message. If >5 min, kill and retry.

### Dash UI Mount Failed
**Cause:** Dash requires a Flask app; FastAPI uses Starlette.
**Fix:** Non-fatal. The WSGIMiddleware wrapper handles this. Check logs for details.

### Rate Limit Errors in Tests
**Cause:** Rate limiter active in test mode.
**Fix:** Set `TESTING=true` in `.env` to bypass rate limiting.

## Recovery Procedures

### MongoDB Connection Lost
1. System continues in degraded mode (DuckDB only)
2. Check: `curl http://localhost:8000/api/health/mongodb`
3. Restart MongoDB Atlas cluster if needed
4. Reconnect: restart backend process

### DuckDB Corruption
1. Stop backend
2. Remove `data/duckdb/floww.duckdb`
3. Restart backend (recreates empty database)
4. Re-run backfill scripts

### Model Registry Corrupted
1. Check `ml/registry.json` for validity
2. If corrupt, restore from backup: `cp ml/registry.json.bak ml/registry.json`
3. Re-train affected models: `python scripts/train_production.py --ticker SPY`
