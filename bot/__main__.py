import logging
import socket

from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord import Game
from discord.ext.commands import Bot, when_mentioned_or

from bot.constants import Bot as BotConfig, ClickUp
from bot.formatter import Formatter
from bot.utils.service_discovery import wait_for_rmq


log = logging.getLogger(__name__)

bot = Bot(
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

log.info("Waiting for RabbitMQ...")
has_rmq = wait_for_rmq()

if has_rmq:
    log.info("RabbitMQ found")
else:
    log.warning("Timed out while waiting for RabbitMQ")

# Internal/debug
bot.load_extension("bot.cogs.logging")
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
bot.load_extension("bot.cogs.utils")

if has_rmq:
    bot.load_extension("bot.cogs.rmq")

bot.run(BotConfig.token)

bot.http_session.close()  # Close the aiohttp session when the bot finishes running
