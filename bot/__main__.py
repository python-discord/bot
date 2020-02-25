import logging

import discord
import sentry_sdk
from discord.ext.commands import when_mentioned_or
from sentry_sdk.integrations.logging import LoggingIntegration

from bot import patches
from bot.bot import Bot
from bot.constants import Bot as BotConfig

sentry_logging = LoggingIntegration(
    level=logging.DEBUG,
    event_level=logging.WARNING
)

sentry_sdk.init(
    dsn=BotConfig.sentry_dsn,
    integrations=[sentry_logging]
)

bot = Bot(
    command_prefix=when_mentioned_or(BotConfig.prefix),
    activity=discord.Game(name="Commands: !help"),
    case_insensitive=True,
    max_messages=10_000,
)

# Internal/debug
bot.load_extension("bot.cogs.error_handler")
bot.load_extension("bot.cogs.filtering")
bot.load_extension("bot.cogs.logging")
bot.load_extension("bot.cogs.security")
bot.load_extension("bot.cogs.config_verifier")

# Commands, etc
bot.load_extension("bot.cogs.antimalware")
bot.load_extension("bot.cogs.antispam")
bot.load_extension("bot.cogs.bot")
bot.load_extension("bot.cogs.clean")
bot.load_extension("bot.cogs.extensions")
bot.load_extension("bot.cogs.help")

bot.load_extension("bot.cogs.doc")
bot.load_extension("bot.cogs.verification")

# Feature cogs
bot.load_extension("bot.cogs.alias")
bot.load_extension("bot.cogs.defcon")
bot.load_extension("bot.cogs.eval")
bot.load_extension("bot.cogs.duck_pond")
bot.load_extension("bot.cogs.help_channels")
bot.load_extension("bot.cogs.information")
bot.load_extension("bot.cogs.jams")
bot.load_extension("bot.cogs.moderation")
bot.load_extension("bot.cogs.off_topic_names")
bot.load_extension("bot.cogs.reddit")
bot.load_extension("bot.cogs.reminders")
bot.load_extension("bot.cogs.site")
bot.load_extension("bot.cogs.snekbox")
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
