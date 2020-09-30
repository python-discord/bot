import asyncio
import logging

import discord
import sentry_sdk
from async_rediscache import RedisSession
from discord.ext.commands import when_mentioned_or
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from bot import constants, patches
from bot.bot import Bot
from bot.utils.extensions import EXTENSIONS

# Set up Sentry.
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

# Create the redis session instance.
redis_session = RedisSession(
    address=(constants.Redis.host, constants.Redis.port),
    password=constants.Redis.password,
    minsize=1,
    maxsize=20,
    use_fakeredis=constants.Redis.use_fakeredis,
    global_namespace="bot",
)

# Connect redis session to ensure it's connected before we try to access Redis
# from somewhere within the bot. We create the event loop in the same way
# discord.py normally does and pass it to the bot's __init__.
loop = asyncio.get_event_loop()
loop.run_until_complete(redis_session.connect())


# Instantiate the bot.
allowed_roles = [discord.Object(id_) for id_ in constants.MODERATION_ROLES]
intents = discord.Intents().all()
intents.presences = False
intents.dm_typing = False
intents.dm_reactions = False
intents.invites = False
intents.webhooks = False
intents.integrations = False
bot = Bot(
    redis_session=redis_session,
    loop=loop,
    command_prefix=when_mentioned_or(constants.Bot.prefix),
    activity=discord.Game(name="Commands: !help"),
    case_insensitive=True,
    max_messages=10_000,
    allowed_mentions=discord.AllowedMentions(everyone=False, roles=allowed_roles),
    intents=intents
)

# Load extensions.
extensions = set(EXTENSIONS)  # Create a mutable copy.
if not constants.HelpChannels.enable:
    extensions.remove("bot.exts.help_channels")

for extension in extensions:
    bot.load_extension(extension)

# Apply `message_edited_at` patch if discord.py did not yet release a bug fix.
if not hasattr(discord.message.Message, '_handle_edited_timestamp'):
    patches.message_edited_at.apply_patch()

bot.run(constants.Bot.token)
