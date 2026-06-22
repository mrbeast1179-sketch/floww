"""
TDD observability-contract test file for backend/server.py silent-failure
remediation (Phase 6 Task 10 audit Scope-Boundary expansion).

Per-site contracts pinned here:

  Site   | Enclosing context               | Pin (post-fix contract)                              | Line
  -------|---------------------------------|-------------------------------------------------------|-----
  L153   | rate_limit_middleware metric    | 429 response preserved + WARNING when metric raises   | 153
  L229   | global_exception_handler log    | 500 response preserved + WARNING when log raises      | 229
  L247   | redacted_500_count (prod branch)| 500 (redacted body) preserved + WARNING when raises   | 247
  L274   | performance_middleware          | response+header preserved + WARNING when perf raises | 274
  L2661  | route template extraction       | WARNING when scope.get raises, default route fallback | 2661
  L3072  | shutdown_duckdb duckdb.stop     | shutdown completes (warns); WARNING logged            | 3072
  L2178  | schwab_auth_handler stub        | JSONResponse(503) with status=error body              | 2178

Fix shape decisions (per Phase 6 audit precedents):
- L153/L229/L247/L274/L2661/L3072 -> DEFENSIBLE per admin.py precedent (commit
  72b00c8). Replace `except Exception: pass` with
  `except Exception as e: log.warning(..., exc_info=True)`, preserving the
  original HTTP response shape.
- L2178 -> REPRODUCIBLE per gemini.py precedent (commit 23baf34). Wrap return
  dict in `JSONResponse(status_code=503, content=...)`.

This file is INTENDED TO fail on pre-fix code (TDD red phase). After applying
the server.py per-site fixes, all 7 tests pass (TDD green).
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# conftest.aclient provides an httpx.AsyncClient wrapped around server.app.


# ────────────── L153 ──────────────────────────────────────────────────────────
# rate_limit_middleware: when rate_limit_429_count.labels(...).inc() raises,
# the 429 response must STILL be returned AND a WARNING must be logged.

@pytest.mark.asyncio
async def test_rate_limit_middleware_metric_fail_still_returns_429_and_logs_warning(aclient, caplog):
    from collections import deque

    from server import RATE_LIMIT, _rate_limits
    _rate_limits.clear()
    # Settle any startup request
    await aclient.get("/api/spot/SPY")
    # Fill the deque so the next mutating-path request hits the limit.
    _rate_limits["127.0.0.1"] = deque([1000.0] * RATE_LIMIT)

    fake_metric = MagicMock()
    fake_metric.labels.return_value.inc.side_effect = RuntimeError("simulated metric backend down")
    with patch("services.observability.rate_limit_429_count", fake_metric, create=True):
        with caplog.at_level(logging.WARNING, logger="heatseeker"):
            r = await aclient.get("/api/portfolio/rebalance")
    assert r.status_code == 429, f"429 expected even when metric raises; got {r.status_code}"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("rate_limit_429_count" in r.getMessage() for r in warnings), (
        f"rate-limit-metric raise MUST log a WARNING. Got: {[r.getMessage() for r in warnings]}"
    )


# ────────────── L229 ──────────────────────────────────────────────────────────
# global_exception_handler: when error_tracking.log_error raises inside the
# exception handler, the 500 response must STILL be returned AND WARNING logged.

@pytest.mark.asyncio
async def test_global_exception_handler_log_error_fail_still_returns_500_and_logs_warning(aclient, caplog):
    fake_log_error = MagicMock(side_effect=RuntimeError("simulated error-tracking backend down"))
    with patch("error_tracking.log_error", fake_log_error, create=True):
        with patch("server.fetch_spot_and_chains_merged",
                   new=MagicMock(side_effect=RuntimeError("boom from route"))):
            with caplog.at_level(logging.WARNING, logger="heatseeker"):
                r = await aclient.get("/api/alerts/check/SPY")
    assert r.status_code == 500
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("error_tracking" in r.getMessage() for r in warnings), (
        f"log_error raise MUST log a WARNING. Got: {[r.getMessage() for r in warnings]}"
    )


# ────────────── L247 ──────────────────────────────────────────────────────────
# global_exception_handler prod branch: when redacted_500_count raises,
# the prod-redacted 500 response must STILL be returned AND WARNING logged.

@pytest.mark.asyncio
async def test_redacted_500_count_fail_in_prod_still_returns_500_and_logs_warning(aclient, monkeypatch, caplog):
    import server
    monkeypatch.setattr(server, "_is_prod", True, raising=False)
    fake_redacted = MagicMock()
    fake_redacted.labels.return_value.inc.side_effect = RuntimeError("simulated redacted metric down")
    with patch("error_tracking.redacted_500_count", fake_redacted, create=True):
        with patch("server.fetch_spot_and_chains_merged",
                   new=MagicMock(side_effect=RuntimeError("boom prod 500"))):
            with caplog.at_level(logging.WARNING, logger="heatseeker"):
                r = await aclient.get("/api/alerts/check/SPY")
    assert r.status_code == 500
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("redacted_500" in r.getMessage() for r in warnings), (
        f"redacted_500_count raise MUST log a WARNING. Got: {[r.getMessage() for r in warnings]}"
    )
    body = r.json()
    # Prod-redacted body MUST NOT leak type/path
    assert "type" not in body and "path" not in body, (
        f"prod-redacted body should not include type/path; got {body}"
    )


# ────────────── L274 ──────────────────────────────────────────────────────────
# performance_middleware: when perf_monitor.record / set_request_id raises,
# the response must STILL be served AND must STILL have X-Response-Time-Ms
# AND WARNING must be logged.

@pytest.mark.asyncio
async def test_performance_middleware_fail_still_serves_response_with_perf_header_and_logs_warning(aclient, caplog):
    fake_perf_record = MagicMock(side_effect=RuntimeError("perf backing store down"))
    fake_set_rid = MagicMock(side_effect=RuntimeError("req-id service down"))
    with patch("error_tracking.perf_monitor", MagicMock(record=fake_perf_record), create=True):
        with patch("error_tracking.set_request_id", fake_set_rid, create=True):
            with caplog.at_level(logging.WARNING, logger="heatseeker"):
                r = await aclient.get("/api/tickers")
    assert r.status_code == 200
    assert any(k.lower() == "x-response-time-ms" for k in r.headers.keys()), (
        f"perf_monitor fault must NOT strip X-Response-Time-Ms; headers={dict(r.headers)}"
    )
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("perf_monitor" in r.getMessage() for r in warnings), (
        f"perf_monitor raise MUST log a WARNING. Got: {[r.getMessage() for r in warnings]}"
    )


# ────────────── L2661 ──────────────────────────────────────────────────────────
# Direct invocation of performance_middleware() with a fake Request whose
# .scope.get raises. This exercises the actual L2664-2668 try block:
#     route = request.url.path
#     try:
#         if request.scope.get("route"):
#             route = request.scope["route"].path
#     except Exception as e:
#         log.warning(...)
# Pre-fix: silently passed, no warning. Post-fix: WARNING is logged.

@pytest.mark.asyncio
async def test_route_extraction_fail_still_serves_response_and_logs_warning(caplog):
    from server import performance_middleware

    fake_req = MagicMock()
    fake_req.url.path = "/api/spot/SPY"
    fake_scope = MagicMock()
    fake_scope.get.side_effect = RuntimeError("simulated scope.get('route') raise")
    fake_scope.__getitem__.side_effect = RuntimeError("simulated scope['route'] raise")
    fake_req.scope = fake_scope

    fake_response = MagicMock()
    fake_response.headers = {}

    async def _call_next(req):
        return fake_response

    with caplog.at_level(logging.WARNING, logger="heatseeker"):
        try:
            await performance_middleware(fake_req, _call_next)
        except Exception:
            # The obs_metrics block downstream of the L2661 try/except may
            # itself raise (P1 entry in body). Out-of-scope for this test.
            pass

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "route template" in r.getMessage() or "scope" in r.getMessage().lower()
        for r in warnings
    ), (
        f"route-template-extraction raise MUST log a WARNING. "
        f"Got: {[r.getMessage() for r in warnings]}"
    )


# ────────────── L3072 ──────────────────────────────────────────────────────────
# shutdown_duckdb: when duckdb_engine.stop() raises, shutdown must NOT crash
# AND a WARNING must be logged. shutdown_duckdb is registered as a FastAPI
# lifecycle hook (@app.on_event("shutdown")) but the function object is still
# a module-level coroutine accessible at server.shutdown_duckdb.

@pytest.mark.asyncio
async def test_duckdb_stop_fail_in_shutdown_logs_warning(caplog):
    import server
    fn = getattr(server, "shutdown_duckdb", None)
    assert fn is not None, (
        "shutdown_duckdb must be a module-level async function in server.py "
        "(decorated with @app.on_event but referenceable via module ns)"
    )

    fake_duck = MagicMock()
    async def _stop_raises():
        raise RuntimeError("simulated duckdb shutdown flush failure")
    fake_duck.stop = _stop_raises

    with patch.object(server, "duckdb_engine", fake_duck):
        with caplog.at_level(logging.WARNING, logger="heatseeker"):
            try:
                await fn()
            except Exception:
                pass

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "duckdb" in r.getMessage().lower() or "shutdown" in r.getMessage().lower()
        for r in warnings
    ), (
        f"duckdb shutdown fault MUST log a WARNING. "
        f"Got: {[r.getMessage() for r in warnings]}"
    )


# ────────────── L2178 ──────────────────────────────────────────────────────────
# schwab_auth_handler stub: returns dict with status=error that defaults to
# HTTP 200. Per gemini.py precedent, route must return JSONResponse(503) so
# monitoring sees 5xx. Direct call (function not bound to a FastAPI route).

@pytest.mark.asyncio
async def test_schwab_auth_handler_unconfigured_returns_503_and_status_error(monkeypatch):
    import json

    from fastapi.responses import JSONResponse

    monkeypatch.delenv("SCHWAB_CLIENT_ID", raising=False)
    import server
    result = await server.schwab_auth_handler(request={})
    assert isinstance(result, JSONResponse), (
        f"post-fix schwab_auth_handler must return JSONResponse for 503 propagation; got {type(result).__name__}"
    )
    assert result.status_code == 503
    body = json.loads(result.body)
    assert body.get("status") == "error"
    assert "not configured" in body.get("message", "")
