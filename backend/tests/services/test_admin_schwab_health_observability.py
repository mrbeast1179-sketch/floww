"""
backend/tests/services/test_admin_schwab_health_observability.py

Pinned regression tests for Phase 6 Task 10 Decision Queue #4:
routes/admin.py silent-failure remediation.

The audit doc (docs/superpowers/research/2026-06-20-decoder-endpoint-silent-failure-audit.md,
row #5) graded the `GET /admin/schwab/health` endpoint as
SUSPECTED-leaning-DEFENSIBLE based on an INCORRECT "background loop"
assumption. Recon shows the silent excepts are inside an interactive
FastAPI request handler — REPRODUCIBLE.

Fix shape: NOT JSONResponse(503) (that would break graceful-degradation
clients depending on the HTTP-200+partial-data contract) — instead,
preserve HTTP 200 + partial data BUT eliminate the silent swallow by:
  - logging the exception via `logger.error(...)`
  - injecting an `error` key into the response dict so consumers can
    detect degraded state without needing log access

This is an "observability-gap" fix, not a 5xx-escalation fix.

TDD discipline:
- These tests FAIL on the pre-fix code (silent except: pass; no `error`
  key in body; no logger.error emitted).
- These tests PASS after the fix.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

# Ensure backend/ is on sys.path so `import routes.admin` resolves.
BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes.admin import schwab_health  # noqa: E402

# -------------------------------------------------------------------------
# Stubs — used by `monkeypatch.setattr` to inject failure modes into
# `schwab_health`'s lazy-imports.
# -------------------------------------------------------------------------

class _StubStreamer:
    """Stub mimicking `_schwab_streamer.get_health()`."""

    def __init__(self, *, raise_on_get_health: bool = False) -> None:
        self._raise = raise_on_get_health

    def get_health(self) -> dict:
        if self._raise:
            raise RuntimeError("streamer health probe failed: connection timeout")
        return {"connected": True, "messages_per_minute_5min": 12.5}


class _StubTokenManager:
    """Stub mimicking `schwab.SchwabTokenManager()` / `.load()`.

    Parameterized via the CLASS-LEVEL attribute `raise_on_load`.  Tests
    flip this attribute on the class BEFORE injecting it via
    `monkeypatch.setattr(\"schwab.SchwabTokenManager\", _StubTokenManager)`,
    because the production call site does `SchwabTokenManager()` with no
    positional/keyword args — so the stub's __init__ cannot receive the
    flag via kwargs.
    """

    # Class-level flag; tests override BEFORE monkeypatch.setattr().
    raise_on_load: bool = False


    def __init__(self, *args, **kwargs) -> None:
        # No instance attribute set, so `self.raise_on_load` falls back to
        # the class attribute — which tests control.
        pass


    def load(self) -> dict | None:
        if self.raise_on_load:
            raise RuntimeError("token load failed: credential file not found")
        return None  # simulate 'no saved token yet' (token_ttl_seconds defaults to 0)


# -------------------------------------------------------------------------
# Tests — TDD red phase.  These must FAIL on the pre-fix code.
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_schwab_health_when_streamer_raises_includes_error_in_body(
    monkeypatch, caplog
):
    """
    Streamer probe raises → HTTP 200 + partial data (graceful degradation
    preserved) BUT the body MUST include an `error` key carrying the failure
    detail so consumers can detect the degraded state.

    Pre-fix: `except Exception: pass` swallows the exception silently;
    body has no `error` key, no log emitted → test FAILS.
    Post-fix: logger.error(...) + `error` key injected into body → test PASSES.
    """
    import server
    # `_schwab_streamer` does not exist in server.py on disk; the unless-raising
    # False passes the patch through (creates the attribute on the module).
    monkeypatch.setattr(
        server, "_schwab_streamer",
        _StubStreamer(raise_on_get_health=True),
        raising=False,
    )
    # Token load succeeds (returns None → token_ttl_seconds stays 0 default).
    _StubTokenManager.raise_on_load = False
    monkeypatch.setattr("schwab.SchwabTokenManager", _StubTokenManager)

    with caplog.at_level(logging.ERROR, logger="routes.admin"):
        result = await schwab_health()

    # Graceful degradation preserved: HTTP 200 + defaults for missing stream data.
    assert isinstance(result, dict)
    assert result["connected"] is False
    assert result["token_ttl_seconds"] == 0  # token load returned None but TTL=0 by default

    # The observability hook MUST surface the degraded state.
    assert "error" in result, (
        "schwab_health response is missing 'error' key after streamer.exception "
        f"— this is the silent-swallow regression.  Result: {result!r}"
    )
    assert isinstance(result["error"], str) and result["error"].strip(), (
        "schwab_health 'error' key must be a non-empty string describing the "
        f"streamer failure.  Got: {result.get('error')!r}"
    )

    # Logger.error MUST have been called with the streamer exception details.
    streamer_log_records = [r for r in caplog.records if "streamer" in r.message.lower()]
    assert streamer_log_records, (
        "schwab_health should have logged an ERROR when streamer probe raises. "
        f"Got records: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_schwab_health_when_token_load_raises_includes_error_in_body(
    monkeypatch, caplog
):
    """
    Token load raises → HTTP 200 + partial stream data + injects `error`
    key describing the token branch failure.  Stream data is preserved
    because graceful degradation is the design intent.

    Pre-fix: silent swallow; post-fix: log + `error` key in body.
    """
    import server
    monkeypatch.setattr(
        server, "_schwab_streamer",
        _StubStreamer(raise_on_get_health=False),
        raising=False,
    )
    # Token load raises (class-level flag flipped to True BEFORE injection).
    _StubTokenManager.raise_on_load = True
    monkeypatch.setattr("schwab.SchwabTokenManager", _StubTokenManager)

    with caplog.at_level(logging.ERROR, logger="routes.admin"):
        result = await schwab_health()

    # Streamer is healthy so connected=True; token TTL gracefully defaults to 0.
    assert isinstance(result, dict)
    assert result["connected"] is True
    assert result["token_ttl_seconds"] == 0

    # Observability hook: error key present and non-empty.
    assert "error" in result, (
        "schwab_health response is missing 'error' key after token-load.exception "
        f"— silent-swallow regression.  Result: {result!r}"
    )
    assert isinstance(result["error"], str) and result["error"].strip(), (
        "schwab_health 'error' key must be a non-empty string describing the "
        f"token failure.  Got: {result.get('error')!r}"
    )

    # Logger.error MUST have been called with the token exception details.
    token_log_records = [r for r in caplog.records if "token" in r.message.lower()]
    assert token_log_records, (
        "schwab_health should have logged an ERROR when token load raises. "
        f"Got records: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_schwab_health_when_server_lacks_schwab_streamer_attr_includes_error(
    monkeypatch, caplog
):
    """
    PRODUCTION silent-fail case: server.py on disk DOES NOT define
    `_schwab_streamer` (verified by prior recon).  In production this
    means `from server import _schwab_streamer` ALWAYS raises ImportError on
    this branch — caught silently by the pre-fix `except Exception: pass`.
    Post-fix: an `error` key MUST be injected into the response body so
    monitoring agents can detect the missing streamer configuration.

    This test does NOT monkeypatch `server._schwab_streamer` — it relies on
    the actual missing-attribute state (the production reality).  When
    server.py gains `_schwab_streamer`, this test will start failing and
    signal that the original code path has been broken (intentionally or
    not) — which is the correct TDD signal.

    Optional defensive cleanup: the test uses `monkeypatch.delattr` (NOT
    raising=False) so that even if a future deployment defines
    `_schwab_streamer` as a global, the test still exercises the
    missing-attribute path.
    """
    import server
    # If a future deployment defines `_schwab_streamer`, delete it so this
    # test continues to exercise the production missing-attribute case.
    # `raising=False` makes delattr a no-op when the attribute is already
    # absent (the CURRENT production state).
    monkeypatch.delattr(server, "_schwab_streamer", raising=False)
    # Token load succeeds (returns None → token_ttl_seconds stays 0 default).
    _StubTokenManager.raise_on_load = False
    monkeypatch.setattr("schwab.SchwabTokenManager", _StubTokenManager)

    with caplog.at_level(logging.ERROR, logger="routes.admin"):
        result = await schwab_health()

    # Graceful degradation preserved.
    assert isinstance(result, dict)
    assert result["connected"] is False
    assert result["token_ttl_seconds"] == 0

    # Observability: error key present and describes the missing-attr failure.
    assert "error" in result, (
        "schwab_health response is missing 'error' key when "
        "server._schwab_streamer is missing — this IS the production "
        "silent-fail (verified by recon: server.py never defines "
        "_schwab_streamer).  Pre-fix: swallowed silently.  Post-fix: must "
        f"surface the degraded state.  Got: {result!r}"
    )
    assert isinstance(result["error"], str) and result["error"].strip()
    # Logger.error MUST have been called.
    err_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert err_records, (
        "schwab_health should have logged an ERROR when server._schwab_streamer "
        "is absent.  Got records: " + repr([r.message for r in caplog.records])
    )


@pytest.mark.asyncio
async def test_schwab_health_when_no_failure_has_no_error_key(
    monkeypatch, caplog
):
    """
    Happy-path control case: when both streamer probe AND token load
    succeed, the response MUST NOT contain an `error` key (that would
    cause a false-positive degraded-state signal to consumers).

    Pre-fix: granted (no error key when nothing raised).
    Post-fix: preserved (error key only added when an except branch fires).
    """
    import server
    monkeypatch.setattr(
        server, "_schwab_streamer",
        _StubStreamer(raise_on_get_health=False),
        raising=False,
    )
    monkeypatch.setattr("schwab.SchwabTokenManager", _StubTokenManager)

    with caplog.at_level(logging.ERROR, logger="routes.admin"):
        result = await schwab_health()

    assert isinstance(result, dict)
    assert result["connected"] is True
    # Happy path → no `error` key (don't pollute response shape on success).
    assert "error" not in result, (
        "schwab_health should NOT include 'error' key on the happy path. "
        f"Got: {result!r}"
    )
    # No ERROR-level log records on happy path.
    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not error_records, (
        "schwab_health should NOT emit ERROR-level log records on the happy path. "
        f"Got: {[r.message for r in error_records]}"
    )
