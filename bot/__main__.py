import logging
import socket

from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord import Game
from discord.ext.commands import Bot, when_mentioned_or

from bot.constants import Bot as BotConfig, DEBUG_MODE
from bot.utils.service_discovery import wait_for_rmq


log = logging.getLogger(__name__)

bot = Bot(
    command_prefix=when_mentioned_or("!"),
    activity=Game(name="Commands: !help"),
    case_insensitive=True,
    max_messages=10_000
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
bot.load_extension("bot.cogs.filtering")
bot.load_extension("bot.cogs.modlog")

# Commands, etc
bot.load_extension("bot.cogs.antispam")
bot.load_extension("bot.cogs.bigbrother")
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.clean")
bot.load_extension("bot.cogs.cogs")

# Only load this in production
if not DEBUG_MODE:
    bot.load_extension("bot.cogs.doc")
    bot.load_extension("bot.cogs.verification")

# Feature cogs
bot.load_extension("bot.cogs.alias")
bot.load_extension("bot.cogs.deployment")
bot.load_extension("bot.cogs.defcon")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.fun")
bot.load_extension("bot.cogs.superstarify")
bot.load_extension("bot.cogs.information")
bot.load_extension("bot.cogs.moderation")
bot.load_extension("bot.cogs.off_topic_names")
bot.load_extension("bot.cogs.reddit")
bot.load_extension("bot.cogs.reminders")
bot.load_extension("bot.cogs.site")
bot.load_extension("bot.cogs.snakes")
bot.load_extension("bot.cogs.snekbox")
bot.load_extension("bot.cogs.tags")
bot.load_extension("bot.cogs.token_remover")
bot.load_extension("bot.cogs.utils")
bot.load_extension("bot.cogs.wolfram")

if has_rmq:
    bot.load_extension("bot.cogs.rmq")

bot.run(BotConfig.token)

bot.http_session.close()  # Close the aiohttp session when the bot finishes running
