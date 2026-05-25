# Round 8 Backend Endpoint Audit (Round 8 Deep Completion)

Generated 2026-05-25T14:30:11Z by DeepSeek V4 Pro.
Backend: lsof -i :8000 confirms Python listening.
React: lsof -i :3000 confirms node listening.

## Inventory of /api/* endpoints called from React

Total: 5

```
/api/databento
/api/heatseeker
/api/live
/api/ml
/api/preferences
```

## Live health probe (via CRA proxy port 3000)

| Endpoint | HTTP | Content-Type |
|---|---|---|
| /api/databento | 200 | text/html; |
| /api/heatseeker | 200 | text/html; |
| /api/live | 200 | text/html; |
| /api/ml | 200 | text/html; |
| /api/preferences | 200 | text/html; |

## Findings

| Outcome | Count |
|---|---|
| 200 application/json (healthy) | 0
0 |
| 200 text/html (proxy passthrough / route missing) | 5 |
| 404 not found | 0
0 |
| 500 server error | 0
0 |

## Recommendations for Round 9

- Endpoints returning text/html via the proxy mean CRA fell through to index.html — either the path is not in any backend route OR the proxy missed it.
- 404s need backend route implementation.
- 500s have backend bugs (check uvicorn logs).
- Round 9 picks up the failing endpoints in priority order (highest-usage first).
