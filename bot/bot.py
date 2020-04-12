import asyncio
import logging
import socket
import warnings
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from bot import DEBUG_MODE, api, constants
from bot.async_stats import AsyncStatsClient

log = logging.getLogger('bot')


class Bot(commands.Bot):
    """A subclass of `discord.ext.commands.Bot` with an aiohttp session and an API client."""

    def __init__(self, *args, **kwargs):
        if "connector" in kwargs:
            warnings.warn(
                "If login() is called (or the bot is started), the connector will be overwritten "
                "with an internal one"
            )

        super().__init__(*args, **kwargs)

        self.http_session: Optional[aiohttp.ClientSession] = None
        self.api_client = api.APIClient(loop=self.loop)

        self._connector = None
        self._resolver = None
        self._guild_available = asyncio.Event()

        statsd_url = constants.Stats.statsd_host

        if DEBUG_MODE:
            # Since statsd is UDP, there are no errors for sending to a down port.
            # For this reason, setting the statsd host to 127.0.0.1 for development
            # will effectively disable stats.
            statsd_url = "127.0.0.1"

        self.stats = AsyncStatsClient(self.loop, statsd_url, 8125, prefix="bot")

    def add_cog(self, cog: commands.Cog) -> None:
        """Adds a "cog" to the bot and logs the operation."""
        super().add_cog(cog)
        log.info(f"Cog loaded: {cog.qualified_name}")

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

        if self.stats._transport:
            await self.stats._transport.close()

    async def login(self, *args, **kwargs) -> None:
        """Re-create the connector and set up sessions before logging into Discord."""
        self._recreate()
        await self.stats.create_socket()
        await super().login(*args, **kwargs)

    def _recreate(self) -> None:
        """Re-create the connector, aiohttp session, and the APIClient."""
        # Use asyncio for DNS resolution instead of threads so threads aren't spammed.
        # Doesn't seem to have any state with regards to being closed, so no need to worry?
        self._resolver = aiohttp.AsyncResolver()

        # Its __del__ does send a warning but it doesn't always show up for some reason.
        if self._connector and not self._connector._closed:
            log.warning(
                "The previous connector was not closed; it will remain open and be overwritten"
            )

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
