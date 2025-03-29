import asyncio

import aiohttp
import discord
from async_rediscache import RedisSession
from discord.ext import commands
from pydis_core import StartupError
from pydis_core.site_api import APIClient
from redis import RedisError

import bot
from bot import constants
from bot.bot import Bot
from bot.log import get_logger, setup_sentry

LOCALHOST = "127.0.0.1"


async def _create_redis_session() -> RedisSession:
    """Create and connect to a redis session."""
    redis_session = RedisSession(
        host=constants.Redis.host,
        port=constants.Redis.port,
        password=constants.Redis.password,
        use_fakeredis=constants.Redis.use_fakeredis,
        global_namespace="bot",
        decode_responses=True,
    )
    try:
        return await redis_session.connect()
    except RedisError as e:
        raise StartupError(e)


async def main() -> None:
    """Entry async method for starting the bot."""
    setup_sentry()

    statsd_url = constants.Stats.statsd_host
    if constants.DEBUG_MODE:
        # Since statsd is UDP, there are no errors for sending to a down port.
        # For this reason, setting the statsd host to 127.0.0.1 for development
        # will effectively disable stats.
        statsd_url = LOCALHOST

    allowed_roles = list({discord.Object(id_) for id_ in constants.MODERATION_ROLES})
    intents = discord.Intents.all()
    intents.presences = False
    intents.dm_typing = False
    intents.dm_reactions = False
    intents.invites = False
    intents.webhooks = False
    intents.integrations = False

    async with aiohttp.ClientSession() as session:
        bot.instance = Bot(
            guild_id=constants.Guild.id,
            http_session=session,
            redis_session=await _create_redis_session(),
            statsd_url=statsd_url,
            command_prefix=commands.when_mentioned_or(constants.Bot.prefix),
            activity=discord.Game(name=f"Commands: {constants.Bot.prefix}help"),
            case_insensitive=True,
            max_messages=10_000,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=allowed_roles),
            intents=intents,
            allowed_roles=list({discord.Object(id_) for id_ in constants.MODERATION_ROLES}),
            api_client=APIClient(
                site_api_url=constants.URLs.site_api,
                site_api_token=constants.Keys.site_api,
            ),
        )
        async with bot.instance as _bot:
            await _bot.start(constants.Bot.token)


try:
    asyncio.run(main())
except StartupError as e:
    message = "Unknown Startup Error Occurred."
    if isinstance(e.exception, aiohttp.ClientConnectorError | aiohttp.ServerDisconnectedError):
        message = "Could not connect to site API. Is it running?"
    elif isinstance(e.exception, OSError):
        message = "Could not connect to Redis. Is it running?"

    # The exception is logged with an empty message so the actual message is visible at the bottom
    log = get_logger("bot")
    log.fatal("", exc_info=e.exception)
    log.fatal(message)

    exit(69)
