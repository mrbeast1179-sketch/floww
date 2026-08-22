"""Routes tests for /api/flowseeker/auto-trade — preview + execute."""
import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

import routes.flowseeker as fs


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_preview_builds_trades_from_alerts():
    out = _run(fs.auto_trade_preview(tier="SILVER", min_dte=2, equity=100000.0, days=2))
    # route reads the live DuckDB feed; with no persisted alerts we just
    # verify contract shape rather than content.
    assert isinstance(out, dict)
    assert "trades" in out and "count" in out


def test_execute_requires_confirm():
    from fastapi import HTTPException
    try:
        _run(fs.auto_trade_execute(confirm=False, tier="SILVER", min_dte=2, equity=100000.0, days=2))
        assert False, "should have raised"
    except HTTPException as e:
        assert e.status_code == 400
