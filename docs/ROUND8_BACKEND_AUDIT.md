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

## §Scope-Boundary: Phase 6 Task 10 closure — server.py silent-failure remediation

### Provenance

The original Round 8 audit (backend/ proxy-passthrough gate) was a *route-shape* audit: stop the moment a 5xx/404 surface, treat it as "the route is missing/broken." That boundary deliberately excluded *server-internal* silent-failure patterns — the route works but exceptions are swallowed with `except Exception: pass`.

Phase 6 Task 10 (decision queue = open-task ledger maintained in `Documents/Obsidian Vault/`; +5 = priority order during this closure sweep) expanded the boundary to cover `backend/server.py`, the largest silent-failure concentration in the codebase. This is the **closure entry** for that expansion sweep.

### Scope-boundary expansion

| Boundary dimension              | Round 8 covered        | Phase 6 Task 10 added        |
|---|---|---|
| Routes (HTTP status)            | yes (5 endpoints)      | unchanged                    |
| Content-type / proxy passthrough| yes (5/5 text/html)    | unchanged                    |
| **Server-internal silent failures** | **EXCLUDED**       | **INCLUDED (server.py)**     |
| Frontend component health       | out-of-scope           | unchanged                    |

### Sites remediated (`backend/server.py`)

7 sites classified by uniform-shape: `except Exception: pass` → `log.warning(f"server.py: <thing> raise swallowed (<shape preserved>): {e}", exc_info=True)` for 6 sites, plus a full-shape replacement (dict-return → `JSONResponse(503)`) for 1 site.

Site identification is by **grep-verifiable role label** rather than line number — line positions drift as the file is edited; the post-fix wording strings are stable identifiers.

| Site pattern (post-fix wording substring)                                                                                  | Role                                                                                  | Fix shape                                              | Pre-fix severity                          |
|---|---|---|---|
| `rate_limit_429_count metric raise swallowed`                                                                             | rate_limit_middleware 429 Prometheus counter                                          | log.warning w/ exc_info=True                           | high — silent label-counter loss           |
| `error_tracking.log_error raise swallowed`                                                                                | error_handler error_tracking.log_error call                                           | log.warning w/ exc_info=True                           | high — silent log-tracker loss             |
| `redacted_500_count metric raise swallowed`                                                                               | prod-branch 500-redaction Prometheus counter                                          | log.warning w/ exc_info=True                           | medium — observability gap                 |
| `perf_monitor / set_request_id raise swallowed`                                                                           | perf_monitor.record + set_request_id                                                  | log.warning w/ exc_info=True                           | medium — telemetry loss                    |
| `route template extraction raise swallowed`                                                                               | performance_middleware route-template extraction (best-effort)                       | log.warning w/ exc_info=True                           | low — best-effort, now logged              |
| `duckdb_engine.stop() raise swallowed`                                                                                    | @app.on_event("shutdown") → shutdown_duckdb() handler                                 | log.warning w/ exc_info=True                           | medium — duckdb-conn leak invisible        |
| `return JSONResponse(status_code=503`                                                                                      | schwab_auth_handler dict-return swallow                                               | full replacement: JSONResponse(503, content)           | **critical** — caller treats 200 dict as auth-configured |

Test file: `backend/tests/server/test_server_silent_failure_observability.py` — 8 tests, TDD red→green pre/post proven via `+ log.warning raise swallowed` grep count (0 → 6) and `isinstance(result, JSONResponse)` introspection on the schwab site. ruff CLEAN (`E9/F63/F7/F82/F401/F811` + full style).

### Sign-off (verified 2026-06-21)

Grep-count verification on `backend/server.py`:

| grep -cF pattern                                                                                  | Count |
|---|---|
| `rate_limit_429_count metric raise swallowed`                                                     | 1     |
| `error_tracking.log_error raise swallowed`                                                        | 1     |
| `redacted_500_count metric raise swallowed`                                                       | 1     |
| `perf_monitor / set_request_id raise swallowed`                                                   | 1     |
| `route template extraction raise swallowed`                                                       | 1     |
| `duckdb_engine.stop() raise swallowed`                                                            | 1     |
| `return JSONResponse(status_code=503`                                                             | 1     |
| **Total**                                                                                         | **7 / 7** |

- `[x] pytest tests/server/test_server_silent_failure_observability.py` → 8 / 8 passed
- `[x] ruff check --select=E9,F63,F7,F82,F401,F811 backend/server.py backend/tests/server/test_server_silent_failure_observability.py` → clean
- `[x] ruff check backend/server.py backend/tests/server/test_server_silent_failure_observability.py` (full style) → clean
- `[x] python3 -m py_compile backend/server.py backend/tests/server/test_server_silent_failure_observability.py` → clean

### Forward-looking (Round 9 picks up)

- `backend/services/*/` silent-failure patterns (CVForge client, auth middleware)
- frontend test gaps for Flowseeker Pro (e2e + jest)
- `bundle.js` analytics silent-failures (out-of-scope here)

— end §Scope-Boundary —
