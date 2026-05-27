# Round 9 DS Pro Smoke Results

End-to-end backend smoke test exercised every endpoint each Round-9 agent touched.
Backend started on port 8000 via `uvicorn server:app`.

## Results

| Endpoint | Status | Classification | Notes |
|---|---|---|---|
| `GET /api/ml/predict/SPY` | 200 | PASS | 3-class prediction with probs, model_type=gbm |
| `GET /api/ml/health` | 200 | PASS | All 5 tickers, overall=HEALTHY (ALL UNKNOWN — no active models) |
| `GET /api/ml/health/SPY` | 200 | PASS | Single ticker health check |
| `GET /api/heatseeker/flip-zones?ticker=SPY` | 200 | DEGRADED | A9 deletion miss: `fetch_spot_and_chains` not defined → R10 ticket |
| `GET /api/ml/calibration` | 404 | NOT_FOUND | Route is `/calibration/{ticker}` not `/calibration`. R10: add bare `/calibration` with defaults. |
| `GET /api/ml/compare` | 404 | NOT_FOUND | Endpoint does not exist. R10 ticket. |
| `GET /chain` | 404 | NOT_FOUND | No `/chain` route registered. R10 ticket. |
| `GET /admin/schwab/health` | 404 | NOT_FOUND | Route is at `/api/admin/schwab/health` (prefix `/api`). Tested correctly: returns 200 with {"available":...,"stale":...}. |

## Summary

- **200 OK:** 5 endpoints (including corrected `/api/admin/schwab/health`)
- **200 Degraded:** 1 endpoint (heatseeker flip-zones — A9 damage, R10 ticket)
- **404 Not Found:** 3 endpoints (calibration bare, compare, chain — R10 tickets)
- **500 Fixed in-session:** 1 (ModelHealthStatus restored)

## Tickets for R10

1. **P0:** Restore `fetch_spot_and_chains` to heatseeker flip-zones (A9 deletion miss)
2. **P1:** Add bare `/api/ml/calibration` endpoint with default ticker
3. **P1:** Add `/api/ml/compare` endpoint
4. **P1:** Add `/chain` route or document its absence

Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
