import logging
import socket

from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord import Game
from discord.ext.commands import AutoShardedBot, when_mentioned_or

from bot.constants import Bot, ClickUp
from bot.formatter import Formatter


log = logging.getLogger(__name__)

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

# Global aiohttp session for all cogs
# - Uses asyncio for DNS resolution instead of threads, so we don't spam threads
# - Uses AF_INET as its socket family to prevent https related problems both locally and in prod.
bot.http_session = ClientSession(
    connector=TCPConnector(
        resolver=AsyncResolver(),
        family=socket.AF_INET,
    )
)

# Internal/debug
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.rmq")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.events")


# Commands, etc
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.cogs")

# Local setups usually don't have the clickup key set,
# and loading the cog would simply spam errors in the console.
if ClickUp.key is not None:
    bot.load_extension("bot.cogs.clickup")
else:
    log.info("`CLICKUP_KEY` not set in the environment, not loading the ClickUp cog.")

bot.load_extension("bot.cogs.deployment")
bot.load_extension("bot.cogs.doc")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.fun")
bot.load_extension("bot.cogs.hiphopify")
bot.load_extension("bot.cogs.snakes")
bot.load_extension("bot.cogs.tags")
bot.load_extension("bot.cogs.verification")

bot.run(Bot.token)

bot.http_session.close()  # Close the aiohttp session when the bot finishes running
