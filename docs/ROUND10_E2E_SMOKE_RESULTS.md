# Round 10 E2E Smoke Test Results

**Date:** 2026-05-29
**Backend:** floww @ commit including Phase 2 /api/ml/compare
**Test method:** HTTP smoke test against `localhost:8000` with all Round 10 endpoints.

## Per-Endpoint Table

| Method | Path | Status | Classification |
|--------|------|--------|---------------|
| GET | /api/health | 200 | 2xx OK |
| GET | /api/ml/calibration/SPY | 200 | 2xx OK |
| GET | /api/ml/calibration?ticker=SPY | 200 | 2xx OK |
| GET | /api/ml/compare | 200 | 2xx OK |
| GET | /api/ml/compare?tickers=SPY,QQQ | 200 | 2xx OK |
| GET | /api/ml/health | 200 | 2xx OK |
| GET | /api/ml/health/SPY | 200 | 2xx OK |
| GET | /api/ml/predict/SPY | 200 | 2xx OK |
| GET | /api/ml/predict/QQQ | 404 | 4xx WARN (no trained model) |
| GET | /api/ml/predict/DIA | 404 | 4xx WARN (no trained model) |
| GET | /api/ml/predict/IWM | 404 | 4xx WARN (no trained model) |
| GET | /api/ml/predict/TLT | 404 | 4xx WARN (no trained model) |
| GET | /api/chain?ticker=SPY | 200 | 2xx OK |
| GET | /api/chain?ticker=SPY&dte_max=7 | 200 | 2xx OK |
| GET | /api/heatseeker/flip-zones?ticker=SPY | 200 | 2xx OK |
| GET | /api/heatseeker/node-lifecycle?ticker=SPY | 200 | 2xx OK |
| GET | /api/heatseeker/air-pockets?ticker=SPY | 200 | 2xx OK |
| GET | /api/admin/schwab/health | 503 | 5xx FAIL (auth not configured) |
| GET | /api/admin/trading/status | 503 | 5xx FAIL (auth not configured) |
| GET | /api/performance/stats | 404 | 4xx WARN (route not found) |
| GET | /api/databento/usage | 503 | 5xx FAIL (auth not configured) |

## Summary

- **Total endpoints:** 21
- **2xx (OK):** 13
- **3xx (Redirect):** 0
- **4xx (Expected - missing data, auth, not found):** 5
- **5xx (Bugs):** 3
- **ERR (Connection errors):** 0

## 5xx Root Cause Analysis

| Endpoint | Status | Root Cause | R10 Fix Ticket |
|----------|--------|-----------|----------------|
| /api/admin/schwab/health | 503 | API_SECRET_KEY not set in .env | R10-config: Set API_SECRET_KEY for admin routes |
| /api/admin/trading/status | 503 | Same auth middleware issue | R10-config: Same |
| /api/databento/usage | 503 | Same auth middleware issue | R10-config: Same |

All three 503s are caused by admin auth middleware returning 503 when `API_SECRET_KEY` is not configured. Expected in dev/test.

## 4xx Analysis

| Endpoint | Status | Root Cause |
|----------|--------|-----------|
| /api/ml/predict/QQQ | 404 | No trained model artifact for QQQ |
| /api/ml/predict/DIA | 404 | No trained model artifact for DIA |
| /api/ml/predict/IWM | 404 | No trained model artifact for IWM |
| /api/ml/predict/TLT | 404 | No trained model artifact for TLT |
| /api/performance/stats | 404 | Route not registered |

## Round 10 New Endpoints Verified

- **/api/ml/compare** — 200 OK, returns JSON with SPY/QQQ/DIA/IWM/TLT keys
- **/api/ml/compare?tickers=SPY,QQQ** — 200 OK, filtered results
- **/api/ml/calibration** — 200 OK (both path param and query param variants)
- **/api/ml/health** — 200 OK
