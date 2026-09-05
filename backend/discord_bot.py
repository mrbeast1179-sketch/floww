"""
backend/discord_bot.py — Tidehunter Discord gateway bot (separate process).

Run:  cd backend && .venv/bin/python3 discord_bot.py
Needs: DISCORD_BOT_TOKEN + Alpaca keys in env. Paper venue only.

Commands (! prefix): buy / sell / holdings / orders / approve / alerts / help.
Trading commands (!buy/!sell/!approve) require DISCORD_ALLOWED_USER_IDS
membership; everything else is read-only. discord.py is imported lazily so
the FastAPI backend boots without it installed.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

log = logging.getLogger("discord_bot")


def _commands():
    from discord.ext import commands

    from services import discord_ops as ops

    intents = __import__("discord").Intents.default()
    intents.message_content = True  # enable in Developer Portal too
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    def _deny(ctx) -> bool:
        return ops.is_trading_allowed(getattr(getattr(ctx, "author", None), "id", None))

    def _router():
        from services.order_router import OrderRouter

        return OrderRouter("discord-paper")

    def _engine():
        from services.duckdb_engine import db as duckdb_engine

        return duckdb_engine

    @bot.command(name="help")
    async def help_cmd(ctx):
        await ctx.send(ops.HELP_TEXT)

    @bot.command(name="holdings")
    async def holdings_cmd(ctx):
        try:
            from alpaca_client import AlpacaClient

            client = AlpacaClient()
            if not client.enabled:
                await ctx.send("Alpaca paper keys not configured.")
                return

            pos = await client.get_positions()
            if not pos:
                await ctx.send("No open paper positions.")
                return
            lines = [f"{p.get('symbol')}: {p.get('qty')} @ {p.get('current_price', '?')}"
                     for p in pos[:20]]
            await ctx.send("**Paper holdings**\n" + "\n".join(lines))
        except Exception as e:
            await ctx.send(f"holdings failed: {e}")

    @bot.command(name="orders")
    async def orders_cmd(ctx):
        await ctx.send("Open-order listing lives at GET /api/alpaca/orders — bot shows fills on trade replies.")

    @bot.command(name="alerts")
    async def alerts_cmd(ctx, n: int = 5):
        rows = ops.fetch_recent_alerts(_engine(), limit=n)
        if not rows:
            await ctx.send("No recent alerts.")
            return
        lines = []
        for a in rows:
            lines.append(f"`{a.get('key')}` {a.get('tier')} {a.get('rule')} "
                         f"{a.get('under')} {a.get('bias') or ''} score={a.get('score')}")
        await ctx.send("**Recent alerts** (approve with `!approve <key> [qty]`)\n" + "\n".join(lines))

    async def _trade(ctx, side: str, qty: int, symbol: str, order_type="market", limit_price=0.0):
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        import time

        router = _router()
        res = await router.submit_order({
            "ticker": symbol.upper(), "side": side, "qty": qty,
            "order_type": order_type, "limit_price": limit_price,
            "signal_id": f"discord:{ctx.author.id}:{int(time.time() * 1e6)}",
            "timestamp_us": int(time.time() * 1e6),
        })
        if res.get("status") == "submitted":
            await ctx.send(f"PAPER {side.upper()} {qty} {symbol.upper()} submitted "
                           f"(`{res.get('client_order_id')}`)")
        else:
            await ctx.send(f"Trade rejected: {res.get('reason', res)}")

    @bot.command(name="buy")
    async def buy_cmd(ctx, qty: int = 0, symbol: str = "", *rest):
        if not symbol or qty <= 0:
            await ctx.send("Usage: `!buy <qty> <SYM> [limit <px>]`")
            return
        limit_px = 0.0
        otype = "market"
        if len(rest) >= 2 and rest[0].lower() == "limit":
            try:
                limit_px = float(rest[1])
                otype = "limit"
            except (TypeError, ValueError):
                await ctx.send("Usage: `!buy <qty> <SYM> [limit <px>]`")
                return
        await _trade(ctx, "buy", qty, symbol, otype, limit_px)

    @bot.command(name="sell")
    async def sell_cmd(ctx, qty: int = 0, symbol: str = "", *rest):
        if not symbol or qty <= 0:
            await ctx.send("Usage: `!sell <qty> <SYM>`")
            return
        await _trade(ctx, "sell", qty, symbol)

    @bot.command(name="approve")
    async def approve_cmd(ctx, key: str = "", qty: int = 1):
        if not key:
            await ctx.send("Usage: `!approve <alert-key> [qty]`")
            return
        if not _deny(ctx):
            await ctx.send("Trading commands are allowlisted (DISCORD_ALLOWED_USER_IDS).")
            return
        res = await ops.execute_approve(key, qty, _engine(), _router())
        if res.get("status") == "submitted":
            await ctx.send(f"PAPER trade from `{key}` submitted.")
        else:
            await ctx.send(f"Approve failed: {res.get('reason', res)}")

    @bot.event
    async def on_command_error(ctx, error):
        await ctx.send(f"Command error: {type(error).__name__}. Try `!help`.")

    return bot


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("DISCORD_BOT_TOKEN not set — refusing to start.")
        return 2
    try:
        import discord  # noqa: F401
    except ImportError:
        print("discord.py not installed — run: .venv/bin/pip install 'discord.py>=2.3'")
        return 2
    bot = _commands()
    bot.run(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
