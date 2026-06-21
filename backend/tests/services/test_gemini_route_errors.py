"""
backend/tests/services/test_gemini_route_errors.py

Phase 6 Task 10 / Decision Queue item #2 fix-attendance:

Failing test for the audit-surfaced silent-failure anti-pattern in
``backend/routes/gemini.py``.  Each of the 9 error-body return sites
(L22/L24/L36/L38/L54/L56/L68/L70/L87 per the audit
``docs/superpowers/research/2026-06-20-decoder-endpoint-silent-failure-audit.md``
commit ``ebd5f77``) currently returns a bare dict with the FastAPI
default HTTP 200 -- a monitoring agent checking ``r.status_code`` would
conclude the call succeeded even when the underlying Gemini API was
unavailable.  This is the "HTTP 200 with error body" anti-pattern
called out in audit row #2 (REPRODUCIBLE-HOT-SPOT).

After the fix (this commit's ``backend/routes/gemini.py`` change),
each error-body return becomes a
``JSONResponse(status_code=503, content={"error": ...})`` that
**preserves the existing API contract body shape** (the ``"error"``
key remains) while surfacing the error via a proper 5xx status code.

Per plan section: TDD discipline:
- This file MUST fail on the pre-fix code (returns bare dict).
- This file MUST pass on the post-fix code (returns JSONResponse).

If a future refactor reverts the fix, the ``isinstance(result,
JSONResponse)`` assertions fail immediately and the audit's grade is
restored to REPRODUCIBLE-HOT-SPOT.

CR-polish iterations applied (per post-fix code-reviewer):
1. ``_assert_503_with_error_body``: tightened from presence-only to
   non-empty error string check so a future over-clever ``.strip()``
   regression that lands an empty-string body still fails the test.
2. ``test_gemini_503_on_analyzer_exception``: added path-stability
   substring check that the stubbed RuntimeError reason substring
   ``"stubbed:"`` reaches the response body, catching a future
   refactor that re-raises as a different exception subclass.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Defensive sys.path setup (mirror test_bs_greeks_canonical.py pattern):
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi.responses import JSONResponse  # noqa: E402


def _stub_analyzer(monkeypatch: pytest.MonkeyPatch, *, behavior: str) -> MagicMock:
    """Install a stub for the lazy-imported ``gemini_analyzer`` module so
    each handler's internal ``from gemini_analyzer import ...`` resolves
    to a controlled mock.

    Behavior values:
    - ``"exception"``: analyzer methods raise RuntimeError (covers the
      L24/L38/L56/L70/L87 try-block catch paths).
    - ``"none"``: analyzer methods return None (covers the L22/L36/L54/L68
      "Gemini not available" fallbacks).
    - ``"no_key"``: only the module exists WITHOUT ``GEMINI_API_KEY`` so
      the /status lazy import raises ImportError.
    """
    monkeypatch.delitem(sys.modules, "gemini_analyzer", raising=False)
    mod = MagicMock()
    mod.GEMINI_API_KEY = ""
    analyzer_cls = MagicMock()
    instance = analyzer_cls.return_value

    if behavior == "exception":

        def _raise(*args, **kwargs):  # pragma: no cover - exception path
            raise RuntimeError("stubbed: API key invalid or quota exhausted")

        for name in (
            "analyze_trade",
            "analyze_regime",
            "summarize_day",
            "explain_flow_signal",
        ):
            setattr(instance, name, _raise)
    elif behavior == "none":
        for name in (
            "analyze_trade",
            "analyze_regime",
            "summarize_day",
            "explain_flow_signal",
        ):
            setattr(instance, name, MagicMock(return_value=None))
    elif behavior == "no_key":
        # /status falls into the except clause because the try block does
        # `from gemini_analyzer import GEMINI_API_KEY`.  We omit the
        # constant from the stub entirely so the lazy import raises
        # ImportError, which is caught by the handler's outer
        # `except Exception` and returns the {"error": ...} error path.
        del mod.GEMINI_API_KEY
    else:
        raise ValueError(f"unknown behavior: {behavior}")

    mod.GeminiAnalyzer = analyzer_cls
    monkeypatch.setitem(sys.modules, "gemini_analyzer", mod)
    return mod


def _assert_503_with_error_body(handler_name: str, result) -> None:
    """Common assertion: result must be a JSONResponse(status_code=503)
    whose body carries a non-empty ``"error"`` key (API-contract
    preservation -- see audit section: Hot-spot #2 next-step fix plan).

    Tightened per code-review from presence-only to non-empty-string
    check so a future refactor that accidentally normalises the reason
    to ``""`` (e.g. via over-clever ``.strip()`` or a default-empty
    ``str(e)`` on a subclass) still fails the test.
    """
    assert isinstance(result, JSONResponse), (
        f"{handler_name}: returned {type(result).__name__}, expected JSONResponse. "
        f"Bare dict == HTTP 200 silent-failure anti-pattern "
        f"(audit doc ebd5f77 row #2)."
    )
    assert result.status_code == 503, (
        f"{handler_name}: returned status {result.status_code}, expected 503"
    )
    body = json.loads(result.body)
    assert "error" in body, (
        f"{handler_name}: response body lost its 'error' key -- "
        f"this would break callers that read response.json()['error']."
    )
    assert isinstance(body["error"], str) and body["error"].strip(), (
        f"{handler_name}: response body['error'] is empty or whitespace -- "
        f"the original handler returned a non-empty reason "
        f"(e.g. 'Gemini not available. Check API key and quota.' "
        f"or the underlying exception's str())."
    )


# -------------------------------------------------------------------------
# Test class 1 -- analyzer raises Exception (covers the catch path on all
# 4 endpoints).  Path-stability: the stubbed RuntimeError reason substring
# ("stubbed:") reaches the response body so a future refactor that
# re-raises as a different exception subclass is caught here.
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_fn,args",
    [
        ("analyze_trade", ({"ticker": "SPY"}, None)),
        ("analyze_regime", ({"regime": "active"},)),
        ("summarize_day", ([{"trade_id": 1}],)),
        ("explain_signal", ({"type": "divergence"},)),
    ],
)
async def test_gemini_503_on_analyzer_exception(endpoint_fn, args, monkeypatch):
    """When the analyzer raises, the route returns 503 + error body,
    and the underlying exception's str() (containing the stubbed reason)
    surfaces in the response body via str(e)."""
    _stub_analyzer(monkeypatch, behavior="exception")

    from routes.gemini import (  # noqa: E402
        analyze_regime,
        analyze_trade,
        explain_signal,
        summarize_day,
    )

    fn_map = {
        "analyze_trade": analyze_trade,
        "analyze_regime": analyze_regime,
        "summarize_day": summarize_day,
        "explain_signal": explain_signal,
    }
    fn = fn_map[endpoint_fn]

    result = await fn(*args)
    _assert_503_with_error_body(endpoint_fn, result)

    # Path-stability check on the analyzer-exception path.
    body = json.loads(result.body)
    assert "stubbed" in body["error"], (
        f"{endpoint_fn}: response body['error'] lost the stubbed-reason "
        f"substring; either the exception class changed or str(e) was "
        f"overwritten upstream. body={body['error']!r}"
    )


# -------------------------------------------------------------------------
# Test class 2 -- analyzer returns None (covers the "Gemini not available"
# fallback on the same 4 endpoints).
# -------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint_fn,args",
    [
        ("analyze_trade", ({"ticker": "SPY"}, None)),
        ("analyze_regime", ({"regime": "active"},)),
        ("summarize_day", ([{"trade_id": 1}],)),
        ("explain_signal", ({"type": "divergence"},)),
    ],
)
async def test_gemini_503_on_analyzer_returns_none(endpoint_fn, args, monkeypatch):
    """When the analyzer returns None, the 'Gemini not available' fallback
    returns 503 (not 200)."""
    _stub_analyzer(monkeypatch, behavior="none")

    from routes.gemini import (  # noqa: E402
        analyze_regime,
        analyze_trade,
        explain_signal,
        summarize_day,
    )

    fn_map = {
        "analyze_trade": analyze_trade,
        "analyze_regime": analyze_regime,
        "summarize_day": summarize_day,
        "explain_signal": explain_signal,
    }
    fn = fn_map[endpoint_fn]

    result = await fn(*args)
    _assert_503_with_error_body(endpoint_fn, result)


# -------------------------------------------------------------------------
# Test class 3 -- GET /status fails when GEMINI_API_KEY lookup fails.
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_gemini_status_503_when_api_key_missing(monkeypatch):
    """When ``GEMINI_API_KEY`` cannot be imported, /api/ai/status returns
    503 (not 200).  Reproduces audit-row #2's 9th hit at L87.
    """
    _stub_analyzer(monkeypatch, behavior="no_key")

    from routes.gemini import get_ai_status  # noqa: E402

    result = await get_ai_status()
    _assert_503_with_error_body("get_ai_status", result)
