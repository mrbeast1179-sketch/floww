"""
backend/tests/services/test_discord_ops.py — webhook gate/format, command
parsing, allowlist, approve flow. No network (httpx/broker/engine mocked).
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _alert(**over):
    base = {
        "key": "score|SPY|call|745|2099-01-08", "ckey": "SPY|call|745|2099-01-08",
        "rule": "SCORE", "tier": "GOLD", "side": "BUY", "bias": "BULLISH",
        "under": "SPY", "type": "call", "strike": 745, "exp": "2099-01-08",
        "dte": 5, "score": 95, "premium": 2000000, "vol_oi": 6.0,
        "conviction": 88, "why": "score 95 — vol 6.0x OI",
        "key_levels": {"entry": 740.0, "invalidation": 721.5, "target": 765.9},
    }
    base.update(over)
    return base


class TestGate:
    def test_gold_score_posts_by_default(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_MIN_TIER", raising=False)
        monkeypatch.delenv("DISCORD_RULES", raising=False)
        assert ops.should_notify(_alert()) is True

    def test_silver_blocked_by_gold_floor(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_MIN_TIER", "GOLD")
        assert ops.should_notify(_alert(tier="SILVER")) is False

    def test_rule_allowlist(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_RULES", "WHALE")
        assert ops.should_notify(_alert(rule="SCORE")) is False
        assert ops.should_notify(_alert(rule="WHALE")) is True


class TestFormat:
    def test_embed_shape(self):
        from services import discord_ops as ops
        payload = ops.format_alert_message(_alert())
        assert payload["embeds"][0]["title"].startswith("GOLD SCORE — SPY")
        fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
        assert fields["Premium"] == "$2.0M"
        assert "Levels" in fields
        assert "!approve score|SPY|call|745|2099-01-08" in payload["embeds"][0]["footer"]["text"]


class TestPost:
    @pytest.mark.asyncio
    async def test_no_webhook_is_silent_noop(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        assert await ops.post_alerts([_alert()]) == 0

    @pytest.mark.asyncio
    async def test_posts_only_gated(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
        monkeypatch.setenv("DISCORD_MIN_TIER", "GOLD")
        resp = MagicMock(status_code=204)
        posted = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None):
                posted.append(json)
                return resp

        with patch("httpx.AsyncClient", return_value=FakeClient()):
            n = await ops.post_alerts([_alert(), _alert(tier="BRONZE")])
        assert n == 1 and len(posted) == 1


class TestParse:
    def test_buy_sell(self):
        from services import discord_ops as ops
        assert ops.parse_command("!buy 10 SPY") == {
            "cmd": "buy", "qty": 10, "symbol": "SPY", "order_type": "market"}
        assert ops.parse_command("!buy 5 qqq limit 700") == {
            "cmd": "buy", "qty": 5, "symbol": "QQQ",
            "order_type": "limit", "limit_price": 700.0}
        assert ops.parse_command("!sell 3 AAPL")["cmd"] == "sell"
        assert ops.parse_command("!buy ten SPY") is None
        assert ops.parse_command("!buy 10") is None

    def test_approve_alerts_help(self):
        from services import discord_ops as ops
        assert ops.parse_command("!approve score|X 5") == {
            "cmd": "approve", "key": "score|X", "qty": 5}
        assert ops.parse_command("!approve score|X") == {"cmd": "approve", "key": "score|X"}
        assert ops.parse_command("!alerts 3") == {"cmd": "alerts", "n": 3}
        assert ops.parse_command("!alerts") == {"cmd": "alerts", "n": 5}
        assert ops.parse_command("!holdings") == {"cmd": "holdings"}
        assert ops.parse_command("hello") is None
        assert ops.parse_command("!unknowncmd x") is None


class TestAllowlist:
    def test_empty_deny_all_trading(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.delenv("DISCORD_ALLOWED_USER_IDS", raising=False)
        assert ops.is_trading_allowed("123") is False
        assert ops.is_trading_allowed(None) is False

    def test_member_allowed(self, monkeypatch):
        from services import discord_ops as ops
        monkeypatch.setenv("DISCORD_ALLOWED_USER_IDS", "123, 456")
        assert ops.is_trading_allowed(123) is True
        assert ops.is_trading_allowed("999") is False


class TestApprove:
    @pytest.mark.asyncio
    async def test_approve_bullish_executes_buy(self):
        from services import discord_ops as ops
        engine = MagicMock()
        router = MagicMock()
        router.submit_order = AsyncMock(return_value={"status": "submitted"})
        with patch.object(ops, "fetch_recent_alerts", return_value=[_alert()]):
            res = await ops.execute_approve(
                "score|SPY|call|745|2099-01-08", 2, engine, router)
        assert res["status"] == "submitted"
        intent = router.submit_order.call_args.args[0]
        assert intent["side"] == "buy" and intent["qty"] == 2
        assert intent["ticker"] == "SPY"

    @pytest.mark.asyncio
    async def test_approve_unknown_key_errors(self):
        from services import discord_ops as ops
        with patch.object(ops, "fetch_recent_alerts", return_value=[]):
            res = await ops.execute_approve("nope", 1, MagicMock(), MagicMock())
        assert res["status"] == "error"

    @pytest.mark.asyncio
    async def test_approve_nondirectional_errors(self):
        from services import discord_ops as ops
        with patch.object(ops, "fetch_recent_alerts",
                          return_value=[_alert(bias=None, side="STRATEGY")]):
            res = await ops.execute_approve("k", 1, MagicMock(), MagicMock())
        assert res["status"] == "error"
