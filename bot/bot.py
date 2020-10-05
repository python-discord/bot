import asyncio
import logging
import socket
import warnings
from collections import defaultdict
from typing import Dict, Optional

import aiohttp
import discord
from async_rediscache import RedisSession
from discord.ext import commands
from sentry_sdk import push_scope

from bot import DEBUG_MODE, api, constants
from bot.async_stats import AsyncStatsClient

log = logging.getLogger('bot')
LOCALHOST = "127.0.0.1"


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
        self.api_client = api.APIClient(loop=self.loop)
        self.filter_list_cache = defaultdict(dict)

        self._connector = None
        self._resolver = None
        self._guild_available = asyncio.Event()

        statsd_url = constants.Stats.statsd_host

        if DEBUG_MODE:
            # Since statsd is UDP, there are no errors for sending to a down port.
            # For this reason, setting the statsd host to 127.0.0.1 for development
            # will effectively disable stats.
            statsd_url = LOCALHOST

        try:
            self.stats = AsyncStatsClient(self.loop, statsd_url, 8125, prefix="bot")
        except socket.gaierror as socket_error:
            self.stats = AsyncStatsClient(self.loop, LOCALHOST)
            self.loop.call_later(30, self.retry_statsd_connection, statsd_url)
            log.warning(f"Statsd client failed to instantiate with error:\n{socket_error}")

    def retry_statsd_connection(self, statsd_url: str, retry_after: int = 30, attempt: int = 1) -> None:
        """Callback used to retry a connection to statsd if it should fail."""
        if attempt >= 10:
            log.error("Reached 10 attempts trying to reconnect AsyncStatsClient. Aborting")
            return

        try:
            self.stats = AsyncStatsClient(self.loop, statsd_url, 8125, prefix="bot")
        except socket.gaierror:
            log.warning(f"Statsd client failed to reconnect (Retry attempt: {attempt})")
            # Use a fallback strategy for retrying, up to 10 times.
            self.loop.call_later(retry_after, self.retry_statsd_connection, statsd_url, retry_after * 2, attempt + 1)

    async def cache_filter_list_data(self) -> None:
        """Cache all the data in the FilterList on the site."""
        full_cache = await self.api_client.get('bot/filter-lists')

        for item in full_cache:
            self.insert_item_into_filter_list_cache(item)

    def _recreate(self) -> None:
        """Re-create the connector, aiohttp session, the APIClient and the Redis session."""
        # Use asyncio for DNS resolution instead of threads so threads aren't spammed.
        # Doesn't seem to have any state with regards to being closed, so no need to worry?
        self._resolver = aiohttp.AsyncResolver()

        # Its __del__ does send a warning but it doesn't always show up for some reason.
        if self._connector and not self._connector._closed:
            log.warning(
                "The previous connector was not closed; it will remain open and be overwritten"
            )

        if self.redis_session.closed:
            # If the RedisSession was somehow closed, we try to reconnect it
            # here. Normally, this shouldn't happen.
            self.loop.create_task(self.redis_session.connect())

        # Use AF_INET as its socket family to prevent HTTPS related problems both locally
        # and in production.
        self._connector = aiohttp.TCPConnector(
            resolver=self._resolver,
            family=socket.AF_INET,
        )

        # Client.login() will call HTTPClient.static_login() which will create a session using
        # this connector attribute.
        self.http.connector = self._connector

        # Its __del__ does send a warning but it doesn't always show up for some reason.
        if self.http_session and not self.http_session.closed:
            log.warning(
                "The previous session was not closed; it will remain open and be overwritten"
            )

        self.http_session = aiohttp.ClientSession(connector=self._connector)
        self.api_client.recreate(force=True, connector=self._connector)

        # Build the FilterList cache
        self.loop.create_task(self.cache_filter_list_data())

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
        """
        Clears the internal state of the bot and recreates the connector and sessions.

        Will cause a DeprecationWarning if called outside a coroutine.
        """
        # Because discord.py recreates the HTTPClient session, may as well follow suit and recreate
        # our own stuff here too.
        self._recreate()
        super().clear()

    async def close(self) -> None:
        """Close the Discord connection and the aiohttp session, connector, statsd client, and resolver."""
        await super().close()

        await self.api_client.close()

        if self.http_session:
            await self.http_session.close()

        if self._connector:
            await self._connector.close()

        if self._resolver:
            await self._resolver.close()

        if self.stats and self.stats._transport:
            self.stats._transport.close()

        if self.redis_session:
            await self.redis_session.close()

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
        self._recreate()

        if self.stats:
            await self.stats.create_socket()
        else:
            log.info("self.stats is not defined, skipping create_socket step in login")

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
        if self.stats:
            self.stats.incr(f"errors.event.{event}")
        else:
            log.info(f"self.stats is not defined, skipping errors.event.{event} increment in on_error")

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
