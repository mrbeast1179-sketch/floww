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

Phase 6 Task 10 (decision queue +5 new row) expanded the boundary to cover `backend/server.py`, the largest silent-failure concentration in the codebase. This is the **closure entry** for that expansion sweep.

### Scope-boundary expansion

| Boundary dimension              | Round 8 covered        | Phase 6 Task 10 added        |
|---|---|---|
| Routes (HTTP status)            | yes (5 endpoints)      | unchanged                    |
| Content-type / proxy passthrough| yes (5/5 text/html)    | unchanged                    |
| **Server-internal silent failures** | **EXCLUDED**       | **INCLUDED (server.py)**     |
| Frontend component health       | out-of-scope           | unchanged                    |

### Sites remediated (`backend/server.py`)

7 sites classified by uniform-shape: `except Exception: pass` → `log.warning(f"server.py: <thing> raise swallowed (<shape preserved>): {e}", exc_info=True)` for 6 sites, plus a full-shape replacement (dict-return → `JSONResponse(503)`) for 1 site.

| Line | Site                                                       | Fix shape (log.warning w/ exc_info=True or full replacement)                                                                              | Pre-fix severity                            |
|---|---|---|---|
| L153 | rate_limit_middleware 429 metric                          | swallowed except — log `rate_limit_429_count` metric raise                                                                                | high — silent label-counter loss             |
| L229 | error_handler log_error call                               | swallowed except — log `error_tracking.log_error` raise                                                                                   | high — silent log-tracker loss               |
| L247 | prod-branch 500-redaction counter                          | swallowed except — log `redacted_500_count` metric raise                                                                                  | medium — observability gap                   |
| L274 | perf_monitor.record + set_request_id                       | swallowed except — log `perf_monitor` / `set_request_id` raise                                                                              | medium — telemetry loss                      |
| L2661 | performance_middleware route-template extraction         | swallowed except — log route-template extraction raise                                                                                  | low — best-effort, now logged                |
| L3072 | `@app.on_event("shutdown")` → `shutdown_duckdb()`          | swallowed except — log `duckdb_engine.stop()` raise                                                                                       | medium — duckdb-conn leak invisible          |
| **L2178** | schwab_auth_handler dict-return swallow              | dict-return → explicit `return JSONResponse(status_code=503, content={...})` (gemini.py precedent)                                     | **critical** — caller treated 200 dict as auth-configured |

Test file: `backend/tests/server/test_server_silent_failure_observability.py` — 8 tests, TDD red→green pre/post proven via `+ log.warning` grep count (0 → 6) and `isinstance(result, JSONResponse)` introspection on L2178. ruff CLEAN (`E9/F63/F7/F82/F401/F811` + full style).

### Audit-discrepancy reconciliation

The Round 8 raw sweep cited 6 `except Exception: pass` sites; the Phase 6 Task 10 recon walked every `except` clause in `backend/server.py` and identified exactly 6 + 1 dict-return = 7.

- **False positives**: L2629 and L3040 — decorator wrappers without body (no `pass` to swallow).
- **True positives (new discoveries)**: L2661 and L3072 — the original sweep tagged these differently due to prefix-line pattern matching, but they live in the silent-failure zone.

This entry supersedes any prior in-line reference to "6 silent-exception sites" for `backend/server.py` — the correct number is **7**.

### Sign-off

- [x] `backend/server.py` grep post-fix wording: 7/7 hits
- [x] test file pytest: 8/8 passed
- [x] ruff `E9/F63/F7/F82/F401/F811` + full style: clean
- [x] `py_compile` on `backend/server.py` + test file: clean
- [x] pathspec commit (DOC ONLY) on `docs/ROUND8_BACKEND_AUDIT.md`

### Forward-looking (Round 9 picks up)

- `backend/services/*/` silent-failure patterns (CVForge client, auth middleware)
- frontend test gaps for Flowseeker Pro (e2e + jest)
- `bundle.js` analytics silent-failures (out-of-scope here)

— end §Scope-Boundary —
