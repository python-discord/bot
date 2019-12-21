import asyncio
import logging
import socket
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from bot import api
from bot import constants

log = logging.getLogger('bot')


class Bot(commands.Bot):
    """A subclass of `discord.ext.commands.Bot` with an aiohttp session and an API client."""

    def __init__(self, *args, **kwargs):
        # Use asyncio for DNS resolution instead of threads so threads aren't spammed.
        # Use AF_INET as its socket family to prevent HTTPS related problems both locally
        # and in production.
        self.connector = aiohttp.TCPConnector(
            resolver=aiohttp.AsyncResolver(),
            family=socket.AF_INET,
        )

        super().__init__(*args, connector=self.connector, **kwargs)

        self._guild_available = asyncio.Event()

        self.http_session: Optional[aiohttp.ClientSession] = None
        self.api_client = api.APIClient(loop=self.loop, connector=self.connector)

        log.addHandler(api.APILoggingHandler(self.api_client))

    def add_cog(self, cog: commands.Cog) -> None:
        """Adds a "cog" to the bot and logs the operation."""
        super().add_cog(cog)
        log.info(f"Cog loaded: {cog.qualified_name}")

    def clear(self) -> None:
        """Clears the internal state of the bot and resets the API client."""
        super().clear()
        self.api_client.recreate()

    async def close(self) -> None:
        """Close the aiohttp session after closing the Discord connection."""
        await super().close()

        await self.http_session.close()
        await self.api_client.close()

    async def start(self, *args, **kwargs) -> None:
        """Open an aiohttp session before logging in and connecting to Discord."""
        self.http_session = aiohttp.ClientSession(connector=self.connector)

        await super().start(*args, **kwargs)

    async def on_guild_available(self, guild: discord.Guild) -> None:
        """
        Set the internal guild available event when constants.Guild.id becomes available.

        If the cache appears to still be empty (no members, no channels, or no roles), the event
        will not be set.
        """
        if guild.id != constants.Guild.id:
            return

        if not guild.roles or not guild.members or not guild.channels:
            log.warning(
                "Guild available event was dispatched but the cache appears to still be empty!"
            )
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
