import asyncio
import logging
import socket

import discord
from aiohttp import AsyncResolver, ClientSession, TCPConnector
from discord.ext.commands import Bot, when_mentioned_or

from bot import patches
from bot.api import APIClient, APILoggingHandler
from bot.constants import Bot as BotConfig, DEBUG_MODE


log = logging.getLogger('bot')

bot = Bot(
    command_prefix=when_mentioned_or(BotConfig.prefix),
    activity=discord.Game(name="Commands: !help"),
    case_insensitive=True,
    max_messages=10_000,
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
bot.api_client = APIClient(loop=asyncio.get_event_loop())
log.addHandler(APILoggingHandler(bot.api_client))

# Internal/debug
bot.load_extension("bot.cogs.error_handler")
bot.load_extension("bot.cogs.filtering")
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.modlog")
bot.load_extension("bot.cogs.security")

# Commands, etc
bot.load_extension("bot.cogs.antispam")
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.clean")
bot.load_extension("bot.cogs.cogs")
bot.load_extension("bot.cogs.help")

# Only load this in production
if not DEBUG_MODE:
    bot.load_extension("bot.cogs.doc")
    bot.load_extension("bot.cogs.verification")

# Feature cogs
bot.load_extension("bot.cogs.alias")
bot.load_extension("bot.cogs.defcon")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.free")
bot.load_extension("bot.cogs.information")
bot.load_extension("bot.cogs.infractions")
bot.load_extension("bot.cogs.jams")
bot.load_extension("bot.cogs.moderation")
bot.load_extension("bot.cogs.off_topic_names")
bot.load_extension("bot.cogs.reddit")
bot.load_extension("bot.cogs.reminders")
bot.load_extension("bot.cogs.site")
bot.load_extension("bot.cogs.snekbox")
bot.load_extension("bot.cogs.superstarify")
bot.load_extension("bot.cogs.sync")
bot.load_extension("bot.cogs.tags")
bot.load_extension("bot.cogs.token_remover")
bot.load_extension("bot.cogs.utils")
bot.load_extension("bot.cogs.watchchannels")
bot.load_extension("bot.cogs.wolfram")

# Apply `message_edited_at` patch if discord.py did not yet release a bug fix.
if not hasattr(discord.message.Message, '_handle_edited_timestamp'):
    patches.message_edited_at.apply_patch()

bot.run(BotConfig.token)

# This calls a coroutine, so it doesn't do anything at the moment.
# bot.http_session.close()  # Close the aiohttp session when the bot finishes running
