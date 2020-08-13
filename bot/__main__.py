import logging

import discord
import sentry_sdk
from discord.ext.commands import when_mentioned_or
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from bot import constants, patches
from bot.bot import Bot

sentry_logging = LoggingIntegration(
    level=logging.DEBUG,
    event_level=logging.WARNING
)

sentry_sdk.init(
    dsn=constants.Bot.sentry_dsn,
    integrations=[
        sentry_logging,
        AioHttpIntegration(),
        RedisIntegration(),
    ]
)

allowed_roles = [discord.Object(id_) for id_ in constants.MODERATION_ROLES]
bot = Bot(
    command_prefix=when_mentioned_or(constants.Bot.prefix),
    activity=discord.Game(name="Commands: !help"),
    case_insensitive=True,
    max_messages=10_000,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=allowed_roles)
)

# Backend
bot.load_extension("bot.cogs.backend.config_verifier")
bot.load_extension("bot.cogs.backend.error_handler")
bot.load_extension("bot.cogs.backend.logging")
bot.load_extension("bot.cogs.backend.sync")

# Filters
bot.load_extension("bot.cogs.filters.antimalware")
bot.load_extension("bot.cogs.filters.antispam")
bot.load_extension("bot.cogs.filters.filter_lists")
bot.load_extension("bot.cogs.filters.filtering")
bot.load_extension("bot.cogs.filters.security")
bot.load_extension("bot.cogs.filters.token_remover")
bot.load_extension("bot.cogs.filters.webhook_remover")

# Info
bot.load_extension("bot.cogs.info.doc")
bot.load_extension("bot.cogs.info.help")
bot.load_extension("bot.cogs.info.information")
bot.load_extension("bot.cogs.info.python_news")
bot.load_extension("bot.cogs.info.reddit")
bot.load_extension("bot.cogs.info.site")
bot.load_extension("bot.cogs.info.source")
bot.load_extension("bot.cogs.info.stats")
bot.load_extension("bot.cogs.info.tags")
bot.load_extension("bot.cogs.info.wolfram")

# Moderation
bot.load_extension("bot.cogs.moderation.defcon")
bot.load_extension("bot.cogs.moderation.incidents")
bot.load_extension("bot.cogs.moderation.modlog")
bot.load_extension("bot.cogs.moderation.silence")
bot.load_extension("bot.cogs.moderation.slowmode")
bot.load_extension("bot.cogs.moderation.verification")

# Moderation - Infraction
bot.load_extension("bot.cogs.moderation.infraction.infractions")
bot.load_extension("bot.cogs.moderation.infraction.management")
bot.load_extension("bot.cogs.moderation.infraction.superstarify")

# Moderation - Watchchannels
bot.load_extension("bot.cogs.moderation.watchchannels.bigbrother")
bot.load_extension("bot.cogs.moderation.watchchannels.talentpool")

# Utils
bot.load_extension("bot.cogs.utils.bot")
bot.load_extension("bot.cogs.utils.clean")
bot.load_extension("bot.cogs.utils.eval")
bot.load_extension("bot.cogs.utils.extensions")
bot.load_extension("bot.cogs.utils.jams")
bot.load_extension("bot.cogs.utils.reminders")
bot.load_extension("bot.cogs.utils.snekbox")
bot.load_extension("bot.cogs.utils.utils")

# Misc
bot.load_extension("bot.cogs.alias")
bot.load_extension("bot.cogs.dm_relay")
bot.load_extension("bot.cogs.duck_pond")
bot.load_extension("bot.cogs.off_topic_names")

if constants.HelpChannels.enable:
    bot.load_extension("bot.cogs.help_channels")

# Apply `message_edited_at` patch if discord.py did not yet release a bug fix.
if not hasattr(discord.message.Message, '_handle_edited_timestamp'):
    patches.message_edited_at.apply_patch()

bot.run(constants.Bot.token)
