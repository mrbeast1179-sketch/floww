# Round 9 Backend Diagnostic

Generated 2026-05-25 by DeepSeek V4 Pro Bulletproof session.
Inventory source: `grep -rhoE '/api/...' frontend/src`
Probe target: http://localhost:8000 (direct uvicorn, not via CRA proxy)

## Endpoint Inventory

5 endpoints found in React source:

- /api/databento
- /api/heatseeker
- /api/live
- /api/ml
- /api/preferences

## Categorization

### 200 OK
(none)

### 404 Not Found
All 5 endpoints returned 404:
- /api/databento → 404
- /api/heatseeker → 404
- /api/live → 404
- /api/ml → 404
- /api/preferences → 404

### 500 Server Error
(none)

### Other
(none)

## Response Format

All endpoints return JSON from uvicorn:
```json
{"error":"Not Found","status_code":404,"path":"/api/[endpoint]"}
```

Headers: `server: uvicorn`, `content-type: application/json`, `x-response-time-ms` present.

## Root Cause Analysis

The backend server (uvicorn on port 8000) is running but has no registered routes for the /api/* prefix. The React app sends requests to localhost:8000 but uvicorn doesn't recognize the /api/* paths.

Possible causes:
1. Routes are registered under a different prefix (e.g., just `/heatseeker` not `/api/heatseeker`)
2. The FastAPI app router was modified and routes were removed
3. The backend main.py doesn't include the route modules

## Recommendations for Round 9

1. Check `backend/main.py` or `backend/app.py` for the FastAPI app definition and verify route registrations
2. If routes exist without `/api` prefix, either add the prefix or update the React proxy config
3. Test each route module directly: `python -c "from backend.routes import heatseeker"` etc.
4. Priority: fix backend route registration before any frontend work
