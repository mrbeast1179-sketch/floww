"""Agent C (C2): live alerts must consume the cached calibration blob.

/outcomes/refresh fits and caches calibration_latest in Mongo, but
_run_institutional_alerts never loaded it — live alerts fired uncalibrated
forever even after stage-1 was earned. These pin the wire-up:
cached blob → opts["calibration"] → eval_institutional.
"""
from unittest.mock import AsyncMock, patch

import pytest

from routes import flowseeker as fs

_ROW = {"ckey": "SPY231215C00400000", "occ": "OCCSYM", "spot": 405.0, "under": "SPY"}

_STAGE1 = {
    "stage": 1,
    "n": 80,
    "method_note": "empirical decile hit rates (Wilson CI)",
    "model": {"kind": "decile", "table": {"9": {"n": 8, "hits": 6, "p": 0.75, "ci": [0.4, 0.93]}},
              "n": 80, "trained_at": "2026-09-05T00:00:00+00:00"},
}


def _base_patches(**over):
    kw = dict(
        _volume_baselines=AsyncMock(return_value={}),
        _prev_contract_oi=AsyncMock(return_value={}),
        _cached_regimes=[],
    )
    kw.update(over)
    return kw


@pytest.mark.asyncio
async def test_live_path_forwards_cached_calibration_to_eval():
    """Cached stage-1 blob must reach eval as opts['calibration']."""
    seen = {}

    def _eval(*a, **k):
        seen.update(k)
        return []

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch.object(fs, "_load_calibration", AsyncMock(return_value=_STAGE1)), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch("services.flow_alerts.eval_institutional", side_effect=_eval), \
         patch("services.flow_alerts.init_flow_alert_tables"), \
         patch("services.flow_desk.desk_pass", return_value=[]), \
         patch("services.flow_alerts.dedup_filter", return_value=[]), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        await fs._run_institutional_alerts([{**_ROW}])

    assert (seen.get("opts") or {}).get("calibration") == _STAGE1


@pytest.mark.asyncio
async def test_no_cached_blob_means_no_calibration_opt():
    """Fail-open: no blob → eval call shape exactly as before (no opts)."""
    seen = {}

    def _eval(*a, **k):
        seen.update(k)
        return []

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch.object(fs, "_load_calibration", AsyncMock(return_value=None)), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: r), \
         patch("services.flow_alerts.eval_institutional", side_effect=_eval), \
         patch("services.flow_alerts.init_flow_alert_tables"), \
         patch("services.flow_desk.desk_pass", return_value=[]), \
         patch("services.flow_alerts.dedup_filter", return_value=[]), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"):
        await fs._run_institutional_alerts([{**_ROW}])

    assert "opts" not in seen, "no blob must mean byte-identical eval call"


@pytest.mark.asyncio
async def test_load_calibration_fail_open_without_mongo():
    """Mongo down → None (alerts fire uncalibrated, never crash)."""
    with patch("server.db", side_effect=Exception("mongo down")):
        assert await fs._load_calibration() is None
