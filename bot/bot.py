import asyncio
import logging
import socket
import warnings
from collections import defaultdict
from contextlib import suppress
from typing import Dict, List, Optional

import aiohttp
import discord
from async_rediscache import RedisSession
from discord.ext import commands
from sentry_sdk import push_scope

from bot import api, constants
from bot.async_stats import AsyncStatsClient

log = logging.getLogger('bot')
LOCALHOST = "127.0.0.1"


class StartupError(Exception):
    """Exception class for startup errors."""

    def __init__(self, base: Exception):
        super().__init__()
        self.exception = base


class Bot(commands.Bot):
    """A subclass of `discord.ext.commands.Bot` with an aiohttp session and an API client."""

    def __init__(self, *args, redis_session: RedisSession, **kwargs):
        if "connector" in kwargs:
            warnings.warn(
                "If login() is called (or the bot is started), the connector will be overwritten "
                "with an internal one"
            )

        super().__init__(*args, **kwargs)

        self.http_session: Optional[aiohttp.ClientSession] = None
        self.redis_session = redis_session
        self.api_client: Optional[api.APIClient] = None
        self.filter_list_cache = defaultdict(dict)

        self._connector = None
        self._resolver = None
        self._statsd_timerhandle: asyncio.TimerHandle = None
        self._guild_available = asyncio.Event()

        statsd_url = constants.Stats.statsd_host

        if constants.DEBUG_MODE:
            # Since statsd is UDP, there are no errors for sending to a down port.
            # For this reason, setting the statsd host to 127.0.0.1 for development
            # will effectively disable stats.
            statsd_url = LOCALHOST

        self.stats = AsyncStatsClient(self.loop, LOCALHOST)
        self._connect_statsd(statsd_url)

    def _connect_statsd(self, statsd_url: str, retry_after: int = 2, attempt: int = 1) -> None:
        """Callback used to retry a connection to statsd if it should fail."""
        if attempt >= 8:
            log.error("Reached 8 attempts trying to reconnect AsyncStatsClient. Aborting")
            return

        try:
            self.stats = AsyncStatsClient(self.loop, statsd_url, 8125, prefix="bot")
        except socket.gaierror:
            log.warning(f"Statsd client failed to connect (Attempt(s): {attempt})")
            # Use a fallback strategy for retrying, up to 8 times.
            self._statsd_timerhandle = self.loop.call_later(
                retry_after,
                self._connect_statsd,
                statsd_url,
                retry_after * 2,
                attempt + 1
            )

        # All tasks that need to block closing until finished
        self.closing_tasks: List[asyncio.Task] = []

    async def cache_filter_list_data(self) -> None:
        """Cache all the data in the FilterList on the site."""
        full_cache = await self.api_client.get('bot/filter-lists')

        for item in full_cache:
            self.insert_item_into_filter_list_cache(item)

    async def ping_services(self) -> None:
        """A helper to make sure all the services the bot relies on are available on startup."""
        # Connect Site/API
        attempts = 0
        while True:
            try:
                log.info(f"Attempting site connection: {attempts + 1}/{constants.URLs.connect_max_retries}")
                await self.api_client.get("healthcheck")
                break

            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError):
                attempts += 1
                if attempts == constants.URLs.connect_max_retries:
                    raise
                await asyncio.sleep(constants.URLs.connect_cooldown)

    @classmethod
    def create(cls) -> "Bot":
        """Create and return an instance of a Bot."""
        loop = asyncio.get_event_loop()
        allowed_roles = [discord.Object(id_) for id_ in constants.MODERATION_ROLES]

        intents = discord.Intents().all()
        intents.presences = False
        intents.dm_typing = False
        intents.dm_reactions = False
        intents.invites = False
        intents.webhooks = False
        intents.integrations = False

        return cls(
            redis_session=_create_redis_session(loop),
            loop=loop,
            command_prefix=commands.when_mentioned_or(constants.Bot.prefix),
            activity=discord.Game(name=f"Commands: {constants.Bot.prefix}help"),
            case_insensitive=True,
            max_messages=10_000,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=allowed_roles),
            intents=intents,
        )

    def load_extensions(self) -> None:
        """Load all enabled extensions."""
        # Must be done here to avoid a circular import.
        from bot.utils.extensions import EXTENSIONS

        extensions = set(EXTENSIONS)  # Create a mutable copy.
        if not constants.HelpChannels.enable:
            extensions.remove("bot.exts.help_channels")

        for extension in extensions:
            self.load_extension(extension)

    def add_cog(self, cog: commands.Cog) -> None:
        """Adds a "cog" to the bot and logs the operation."""
        super().add_cog(cog)
        log.info(f"Cog loaded: {cog.qualified_name}")

    def add_command(self, command: commands.Command) -> None:
        """Add `command` as normal and then add its root aliases to the bot."""
        super().add_command(command)
        self._add_root_aliases(command)

    def remove_command(self, name: str) -> Optional[commands.Command]:
        """
        Remove a command/alias as normal and then remove its root aliases from the bot.

        Individual root aliases cannot be removed by this function.
        To remove them, either remove the entire command or manually edit `bot.all_commands`.
        """
        command = super().remove_command(name)
        if command is None:
            # Even if it's a root alias, there's no way to get the Bot instance to remove the alias.
            return

        self._remove_root_aliases(command)
        return command

    def clear(self) -> None:
        """Not implemented! Re-instantiate the bot instead of attempting to re-use a closed one."""
        raise NotImplementedError("Re-using a Bot object after closing it is not supported.")

    async def close(self) -> None:
        """Close the Discord connection and the aiohttp session, connector, statsd client, and resolver."""
        # Done before super().close() to allow tasks finish before the HTTP session closes.
        for ext in list(self.extensions):
            with suppress(Exception):
                self.unload_extension(ext)

        for cog in list(self.cogs):
            with suppress(Exception):
                self.remove_cog(cog)

        # Wait until all tasks that have to be completed before bot is closing is done
        log.trace("Waiting for tasks before closing.")
        await asyncio.gather(*self.closing_tasks)

        # Now actually do full close of bot
        await super().close()

        if self.api_client:
            await self.api_client.close()

        if self.http_session:
            await self.http_session.close()

        if self._connector:
            await self._connector.close()

        if self._resolver:
            await self._resolver.close()

        if self.stats._transport:
            self.stats._transport.close()

        if self.redis_session:
            await self.redis_session.close()

        if self._statsd_timerhandle:
            self._statsd_timerhandle.cancel()

    def insert_item_into_filter_list_cache(self, item: Dict[str, str]) -> None:
        """Add an item to the bots filter_list_cache."""
        type_ = item["type"]
        allowed = item["allowed"]
        content = item["content"]

        self.filter_list_cache[f"{type_}.{allowed}"][content] = {
            "id": item["id"],
            "comment": item["comment"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    async def login(self, *args, **kwargs) -> None:
        """Re-create the connector and set up sessions before logging into Discord."""
        # Use asyncio for DNS resolution instead of threads so threads aren't spammed.
        self._resolver = aiohttp.AsyncResolver()

        # Use AF_INET as its socket family to prevent HTTPS related problems both locally
        # and in production.
        self._connector = aiohttp.TCPConnector(
            resolver=self._resolver,
            family=socket.AF_INET,
        )

        # Client.login() will call HTTPClient.static_login() which will create a session using
        # this connector attribute.
        self.http.connector = self._connector

        self.http_session = aiohttp.ClientSession(connector=self._connector)
        self.api_client = api.APIClient(connector=self._connector)

        if self.redis_session.closed:
            # If the RedisSession was somehow closed, we try to reconnect it
            # here. Normally, this shouldn't happen.
            await self.redis_session.connect()

        try:
            await self.ping_services()
        except Exception as e:
            raise StartupError(e)

        # Build the FilterList cache
        await self.cache_filter_list_data()

        await self.stats.create_socket()
        await super().login(*args, **kwargs)

    async def on_guild_available(self, guild: discord.Guild) -> None:
        """
        Set the internal guild available event when constants.Guild.id becomes available.

        If the cache appears to still be empty (no members, no channels, or no roles), the event
        will not be set.
        """
        if guild.id != constants.Guild.id:
            return

        if not guild.roles or not guild.members or not guild.channels:
            msg = "Guild available event was dispatched but the cache appears to still be empty!"
            log.warning(msg)

            try:
                webhook = await self.fetch_webhook(constants.Webhooks.dev_log)
            except discord.HTTPException as e:
                log.error(f"Failed to fetch webhook to send empty cache warning: status {e.status}")
            else:
                await webhook.send(f"<@&{constants.Roles.admin}> {msg}")

            return

        self._guild_available.set()

    async def on_guild_unavailable(self, guild: discord.Guild) -> None:
        """Clear the internal guild available event when constants.Guild.id becomes unavailable."""
        if guild.id != constants.Guild.id:
            return

        self._guild_available.clear()

    async def wait_until_guild_available(self) -> None:
        """
        Wait until the constants.Guild.id guild is available (and the cache is ready).

        The on_ready event is inadequate because it only waits 2 seconds for a GUILD_CREATE
        gateway event before giving up and thus not populating the cache for unavailable guilds.
        """
        await self._guild_available.wait()

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Log errors raised in event listeners rather than printing them to stderr."""
        self.stats.incr(f"errors.event.{event}")

        with push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)

            log.exception(f"Unhandled exception in {event}.")

    def _add_root_aliases(self, command: commands.Command) -> None:
        """Recursively add root aliases for `command` and any of its subcommands."""
        if isinstance(command, commands.Group):
            for subcommand in command.commands:
                self._add_root_aliases(subcommand)

        for alias in getattr(command, "root_aliases", ()):
            if alias in self.all_commands:
                raise commands.CommandRegistrationError(alias, alias_conflict=True)

            self.all_commands[alias] = command

    def _remove_root_aliases(self, command: commands.Command) -> None:
        """Recursively remove root aliases for `command` and any of its subcommands."""
        if isinstance(command, commands.Group):
            for subcommand in command.commands:
                self._remove_root_aliases(subcommand)

        for alias in getattr(command, "root_aliases", ()):
            self.all_commands.pop(alias, None)


def _create_redis_session(loop: asyncio.AbstractEventLoop) -> RedisSession:
    """
    Create and connect to a redis session.

    Ensure the connection is established before returning to prevent race conditions.
    `loop` is the event loop on which to connect. The Bot should use this same event loop.
    """
    redis_session = RedisSession(
        address=(constants.Redis.host, constants.Redis.port),
        password=constants.Redis.password,
        minsize=1,
        maxsize=20,
        use_fakeredis=constants.Redis.use_fakeredis,
        global_namespace="bot",
    )
    try:
        loop.run_until_complete(redis_session.connect())
    except OSError as e:
        raise StartupError(e)
    return redis_session
