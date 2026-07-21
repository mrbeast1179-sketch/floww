"""Integration test: the route wires desk_pass between init and dedup.

Conviction v2.2 handoff contract: Fable ships `backend/services/flow_desk.py`,
freebuff wires it into `_run_institutional_alerts`. This test protects that
two-line integration from silent regression (wrong arg order, missing call,
duplicate init, etc.) by mocking the route's pipeline boundaries and
asserting the strict call ordering: eval → init → desk_pass → dedup.
"""
from unittest.mock import AsyncMock, patch

import pytest

from routes import flowseeker as fs


@pytest.mark.asyncio
async def test_desk_pass_wired_between_eval_and_dedup():
    """eval_institutional → init_flow_alert_tables → desk_pass → dedup_filter.

    desk_pass's documented contract (in `backend/services/flow_desk.py`) is
    to receive (engine, rows, alerts) with alerts = eval_institutional's
    output. This test does NOT assert specific positional args — the 14-case
    `test_flow_desk.py` suite covers that internally with `--noconftest`.
    It asserts the four-stage ordering so a future route edit that swaps two
    calls (e.g. dedup before desk_pass) flips this test red.
    """
    rows_in = [{"ckey": "SPY231215C00400000", "occ": "OCCSYM", "spot": 405.0}]
    eval_out = [
        {"under": "SPY", "ckey": "SPY231215C00400000", "tier": "GOLD"}
    ]
    desk_out = [
        {
            "under": "SPY",
            "ckey": "SPY231215C00400000",
            "tier": "GOLD",
            "why": "campaign: day 3 of positioning",
        }
    ]

    call_log = []

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch(
             "services.flow_alerts.eval_institutional",
             side_effect=lambda *a, **k: (call_log.append("eval"), eval_out)[1],
         ), \
         patch(
             "services.flow_alerts.init_flow_alert_tables",
             side_effect=lambda *a, **k: call_log.append("init"),
         ), \
         patch(
             "services.flow_desk.desk_pass",
             side_effect=lambda *a, **k: (call_log.append("desk"), desk_out)[1],
         ), \
         patch(
             "services.flow_alerts.dedup_filter",
             side_effect=lambda *a, **k: call_log.append("dedup"),
         ), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        await fs._run_institutional_alerts(rows_in)

    # Strict chronological ordering of the four pipeline stages. A reordering
    # bug (e.g. moving desk_pass AFTER dedup, or init AFTER desk) flips this.
    assert call_log == ["eval", "init", "desk", "dedup"]
