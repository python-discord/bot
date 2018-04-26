# coding=utf-8
import os

from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord import Game
from discord.ext.commands import AutoShardedBot, when_mentioned_or

from bot.formatter import Formatter

bot = AutoShardedBot(
    command_prefix=when_mentioned_or(
        "self.", "bot."
    ),
    activity=Game(
        name="Help: bot.help()"
    ),
    help_attrs={
        "name": "help()",
        "aliases": ["help"]
    },
    formatter=Formatter(),
    case_insensitive=True
)

# Global aiohttp session for all cogs - uses asyncio for DNS resolution instead of threads, so we don't *spam threads*
bot.http_session = ClientSession(connector=TCPConnector(resolver=AsyncResolver()))

# Internal/debug
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.events")


# Commands, etc
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.cogs")
bot.load_extension("bot.cogs.clickup")
bot.load_extension("bot.cogs.deployment")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.fun")
bot.load_extension("bot.cogs.hiphopify")
# bot.load_extension("bot.cogs.math")
bot.load_extension("bot.cogs.tags")
bot.load_extension("bot.cogs.verification")
bot.load_extension("bot.cogs.website")

bot.run(os.environ.get("BOT_TOKEN"))

bot.http_session.close()  # Close the aiohttp session when the bot finishes running
