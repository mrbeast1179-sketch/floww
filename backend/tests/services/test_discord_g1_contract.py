"""G1.4 contract: cooldown table + alias surface pinned against drift."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from discord.ext import commands

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import discord_bot as gateway  # noqa: E402


@pytest_asyncio.fixture
async def live_bot():
    bot = gateway._commands()
    await bot._async_setup_hook()
    bot._connection.user = SimpleNamespace(id=999)
    yield bot
    await bot.close()


def test_cooldown_table_pinned():
    assert gateway._COOLDOWN_S == {"heatmap": 20.0, "vanna": 20.0, "walls": 5.0}


@pytest.mark.asyncio
async def test_alias_surface_pinned(live_bot):
    surface = {}
    for cmd in live_bot.walk_commands():
        surface[cmd.name] = sorted(cmd.aliases)
    assert surface["heatmap"] == ["hm"]
    assert surface["walls"] == ["w"]
    assert surface["vanna"] == ["v"]
    assert surface["holdings"] == ["p", "pos", "positions"]
    assert surface["help"] == ["h"]
    assert surface["alerts"] == ["a"]
    assert surface["journal"] == ["j"]
    assert surface["cancel"] == ["x"]
