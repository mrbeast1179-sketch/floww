"""Integration tests for the institutional alerts routing pipeline.

Three tests. Conviction v2.2 (commit a6fffe8 + Freebuff wire-up 642d225)
hooked `backend/services/flow_desk.py::desk_pass` into
`backend/routes/flowseeker.py::_run_institutional_alerts` between
`fa.eval_institutional(...)` and `fa.dedup_filter(...)`. These tests
pin that wire-up against silent regression.

Pipeline stages under protection:
  eval_institutional → init_flow_alert_tables → desk_pass → dedup_filter

Patches the deferred-import boundaries (`services.flow_alerts.*`,
`services.flow_desk.desk_pass`) and the auxiliary helpers
(`_volume_baselines`, `_prev_contract_oi`, `_cached_regimes`) so the
orchestrator under test runs without real backend servers / Mongo /
DuckDB.
"""
from unittest.mock import AsyncMock, patch

import pytest

from routes import flowseeker as fs


def _make_recorder(call_log, name, return_value):
    """Return a side_effect fn that records `name` on `call_log` and returns
    `return_value`. Replaces the (call_log.append, return_val)[1]
    tuple-trick; reads more clearly for future maintainers.
    """
    def _side_effect(*_a, **_k):
        call_log.append(name)
        return return_value
    return _side_effect


# Reusable shape for fake alert-rows. The route's `update_moves` call
# extracts `r["under"]` immediately before invoking update_moves; keep
# "under" in the fixture so a future test that drops the update_moves
# mock doesn't crash with KeyError.
_ROW_BASE = {
    "ckey": "SPY231215C00400000",
    "occ": "OCCSYM",
    "spot": 405.0,
    "under": "SPY",
}


@pytest.mark.asyncio
async def test_desk_pass_wired_between_eval_and_dedup():
    """eval → init → desk → dedup ordering. Swap any two and the test
    red-flips; this pins the four-stage pipeline shape from the handoff
    contract.
    """
    call_log = []
    rows_in = [{**_ROW_BASE}]
    eval_out = [{"under": "SPY", "ckey": "SPY231215C00400000", "tier": "GOLD"}]
    desk_out = [
        {
            "under": "SPY",
            "ckey": "SPY231215C00400000",
            "tier": "GOLD",
            "why": "campaign: day 3 of positioning",
        }
    ]

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch(
             "services.flow_alerts.eval_institutional",
             side_effect=_make_recorder(call_log, "eval", eval_out),
         ), \
         patch(
             "services.flow_alerts.init_flow_alert_tables",
             side_effect=_make_recorder(call_log, "init", None),
         ), \
         patch(
             "services.flow_desk.desk_pass",
             side_effect=_make_recorder(call_log, "desk", desk_out),
         ), \
         patch(
             "services.flow_alerts.dedup_filter",
             side_effect=_make_recorder(call_log, "dedup", None),
         ), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        await fs._run_institutional_alerts(rows_in)

    assert call_log == ["eval", "init", "desk", "dedup"]


@pytest.mark.asyncio
async def test_empty_input_returns_before_pipeline():
    """Empty normed → early return before any stage fires. Protects against
    a future edit accidentally dropping or re-arranging the
    `if not normed: return` guard at the top of `_run_institutional_alerts`.
    """
    call_log = []

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch(
             "services.flow_alerts.eval_institutional",
             side_effect=_make_recorder(call_log, "eval", []),
         ), \
         patch(
             "services.flow_alerts.init_flow_alert_tables",
             side_effect=_make_recorder(call_log, "init", None),
         ), \
         patch(
             "services.flow_desk.desk_pass",
             side_effect=_make_recorder(call_log, "desk", []),
         ), \
         patch(
             "services.flow_alerts.dedup_filter",
             side_effect=_make_recorder(call_log, "dedup", []),
         ), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        await fs._run_institutional_alerts([])

    # norm_rows([]) returns []; the route's early-return guards BEFORE any
    # of the four pipeline stages fires.
    assert call_log == []


@pytest.mark.asyncio
async def test_desk_pass_raises_does_not_crash_orchestrator():
    """Pin the route's BACKSTOP contract: if desk_pass raises (whether from
    its own internal exception OR from a bug that leaks past flow_desk's
    internal fail-open), the route catches via its outer try/except. The
    alert pipeline never propagates an exception to the caller; no alert
    stage is silently touched after the raise.

    desk_pass's own internal fail-open contract is exercised in the
    14-case `test_flow_desk.py` suite — this test is the ORCHESTRATOR's
    backstop. Asserting `call_log == ["eval", "init"]` proves the route
    caught the exception BEFORE reaching dedup_filter (the except handler
    logs a warning and exits the function, never touching downstream
    stages).
    """
    call_log = []
    rows_in = [{**_ROW_BASE}]
    eval_out = [{"under": "SPY", "ckey": "SPY231215C00400000", "tier": "GOLD"}]

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch(
             "services.flow_alerts.eval_institutional",
             side_effect=_make_recorder(call_log, "eval", eval_out),
         ), \
         patch(
             "services.flow_alerts.init_flow_alert_tables",
             side_effect=_make_recorder(call_log, "init", None),
         ), \
         patch(
             "services.flow_desk.desk_pass",
             side_effect=RuntimeError("desk_pass induced crash for fail-open test"),
         ), \
         patch(
             "services.flow_alerts.dedup_filter",
             side_effect=_make_recorder(call_log, "dedup", []),
         ), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        # If the route doesn't tolerate desk_pass raising, this call
        # raises to pytest. The fact that pytest sees no exception is the
        # primary assertion: the orchestrator survives the crash.
        await fs._run_institutional_alerts(rows_in)

    # eval → init succeeded; desk_pass raised (caught by outer try/except);
    # dedup_filter & persist never fired. This proves the backstop.
    assert call_log == ["eval", "init"]
