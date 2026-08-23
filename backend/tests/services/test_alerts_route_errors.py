"""
backend/tests/services/test_alerts_route_errors.py

Phase 6 Task 10 / Decision Queue item #3 fix-attendance:

Failing test for the audit-surfaced silent-failure anti-pattern in
``backend/routes/alerts.py``.  The two error-body return sites at
L134 (``get_alerts_summary`` except-clause) and L181 (``add_snapshot``
except-clause) currently return a bare dict with the FastAPI default
HTTP 200 - a monitoring agent checking ``r.status_code`` would conclude
the call succeeded even when the underlying alert engine raised.

After the fix (this commit's ``backend/routes/alerts.py`` change),
each error-body return becomes a
``JSONResponse(status_code=503, content={"error": ...})`` that
preserves the existing API contract body shape (the ``"error"`` key
remains in ``/summary``; in ``/snapshot`` the same key) while
surfacing the error via a proper 5xx status code.

Per plan section: TDD discipline:
- This file MUST fail on the pre-fix code (returns bare dict).
- This file MUST pass on the post-fix code (returns JSONResponse).

If a future refactor reverts the fix, the ``isinstance(result,
JSONResponse)`` assertions fail immediately and the audit's grade is
restored to REPRODUCIBLE-HOT-SPOT.
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


def _stub_alert_engine_to_raise(monkeypatch: pytest.MonkeyPatch, *, exc: Exception) -> None:
    """Install a stub for the lazy-imported ``alert_engine`` module so
    ``AlertEngine()`` (called inside ``get_alert_engine()``) raises the
    supplied exception.  This is the surface that ``/summary`` hits when
    the engine init fails."""
    monkeypatch.delitem(sys.modules, "alert_engine", raising=False)
    # routes/alerts memoizes the engine in a module global. If any earlier
    # test already built one, get_alert_engine() short-circuits and never
    # hits our raising stub. Reset it (monkeypatch restores after).
    import routes.alerts as _alerts_mod
    monkeypatch.setattr(_alerts_mod, "_alert_engine", None)
    mod = MagicMock()

    def _raise_engine(*args, **kwargs):
        raise exc

    mod.AlertEngine = _raise_engine
    mod.GEXSnapshot = MagicMock()  # referenced by /snapshot
    monkeypatch.setitem(sys.modules, "alert_engine", mod)


def _stub_gex_snapshot_to_raise(monkeypatch: pytest.MonkeyPatch, *, exc: Exception) -> None:
    """Install a stub for the lazy-imported ``alert_engine`` module so
    ``GEXSnapshot(...)`` (called inside ``/snapshot``) raises the
    supplied exception.  ``AlertEngine`` is left functional (so the
    engine instantiation succeeds) but ``engine.add_snapshot`` and
    ``engine.detect_alerts`` raise on access to be safe."""
    monkeypatch.delitem(sys.modules, "alert_engine", raising=False)
    # routes/alerts memoizes the engine in a module global. If any earlier
    # test already built one, get_alert_engine() short-circuits and never
    # hits our raising stub. Reset it (monkeypatch restores after).
    import routes.alerts as _alerts_mod
    monkeypatch.setattr(_alerts_mod, "_alert_engine", None)
    mod = MagicMock()

    def _raise_gex(*args, **kwargs):
        raise exc

    mod.GEXSnapshot = _raise_gex
    engine_instance = MagicMock()
    engine_instance.add_snapshot.side_effect = exc
    engine_instance.detect_alerts.side_effect = exc
    engine_instance._snapshots = {}
    mod.AlertEngine = MagicMock(return_value=engine_instance)
    monkeypatch.setitem(sys.modules, "alert_engine", mod)


def _assert_503_with_error_body(endpoint_name: str, result) -> None:
    """Common assertion: result must be a JSONResponse(status_code=503)
    whose body carries a non-empty ``"error"`` key (API-contract
    preservation -- see audit section: Hot-spot #3 next-step fix plan).

    Mirrors the gemini.py fix companion helper; intentionally function-
    local rather than imported from test_gemini_route_errors so each
    test file is self-contained for the freezer-pruning pass.
    """
    assert isinstance(result, JSONResponse), (
        f"{endpoint_name}: returned {type(result).__name__}, expected JSONResponse. "
        f"Bare dict == HTTP 200 silent-failure anti-pattern "
        f"(audit doc ebd5f77 row #3, sites L134 + L181)."
    )
    assert result.status_code == 503, (
        f"{endpoint_name}: returned status {result.status_code}, expected 503"
    )
    body = json.loads(result.body)
    assert "error" in body, (
        f"{endpoint_name}: response body lost its 'error' key -- "
        f"this would break callers that read response.json()['error']."
    )
    assert isinstance(body["error"], str) and body["error"].strip(), (
        f"{endpoint_name}: response body['error'] is empty or whitespace -- "
        f"the original handler returned a non-empty str(e) reason."
    )


# -------------------------------------------------------------------------
# Site #1 -- /summary: L134 `return {"error": str(e)}` inside the
# get_alerts_summary function's `except Exception as e:` clause.  Trigger
# via AlertEngine() raising on init.
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_alerts_summary_503_when_engine_init_raises(monkeypatch):
    """When AlertEngine() raises (L134 except-clause path), the
    /api/alerts/summary endpoint returns 503 (not 200)."""
    _stub_alert_engine_to_raise(monkeypatch, exc=RuntimeError("stubbed: AlertEngine init failed"))

    from routes.alerts import get_alerts_summary  # noqa: E402

    result = await get_alerts_summary()
    _assert_503_with_error_body("get_alerts_summary", result)

    # The stubbed RuntimeError reason must reach the body via str(e).
    body = json.loads(result.body)
    assert "stubbed" in body["error"], (
        f"get_alerts_summary: response body['error'] lost the stubbed-reason "
        f"substring; either the exception class changed or str(e) was "
        f"overwritten upstream. body={body['error']!r}"
    )


# -------------------------------------------------------------------------
# Site #2 -- /snapshot: L181 `return {"error": str(e)}` inside the
# add_snapshot function's `except Exception as e:` clause.  Trigger via
# GEXSnapshot(...) raising on init.
# -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_alerts_snapshot_503_when_gex_raises(monkeypatch):
    """When GEXSnapshot(...) raises (L181 except-clause path), the
    /api/alerts/snapshot endpoint returns 503 (not 200)."""
    _stub_gex_snapshot_to_raise(monkeypatch, exc=RuntimeError("stubbed: GEXSnapshot init failed"))

    from routes.alerts import add_snapshot  # noqa: E402

    # Minimal payload -- enough to reach the GEXSnapshot(...) line.
    payload = {
        "ticker": "SPY",
        "spot_price": 580.0,
        "gamma_flip": 575.0,
        "call_wall": 585.0,
        "put_wall": 575.0,
        "max_pain": 580.0,
        "max_gamma_strike": 580.0,
        "total_gex": 1e9,
        "net_gex": 5e8,
        "regime": "positive",
        "gex_by_strike": {},
    }
    result = await add_snapshot(payload)
    _assert_503_with_error_body("add_snapshot", result)

    body = json.loads(result.body)
    assert "stubbed" in body["error"], (
        f"add_snapshot: response body['error'] lost the stubbed-reason "
        f"substring. body={body['error']!r}"
    )
