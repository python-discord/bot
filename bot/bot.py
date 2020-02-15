import logging
import socket
import warnings
from typing import Optional

import aiohttp
from discord.ext import commands

from bot import api

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

        log.addHandler(api.APILoggingHandler(self.api_client))

    def add_cog(self, cog: commands.Cog) -> None:
        """Adds a "cog" to the bot and logs the operation."""
        super().add_cog(cog)
        log.info(f"Cog loaded: {cog.qualified_name}")

    def clear(self) -> None:
        """
        Clears the internal state of the bot and recreates the connector and sessions.

        Will cause a DeprecationWarning if called outside a coroutine.
        """
        # Because discord.py recreates the HTTPClient session, may as well follow suite and recreate
        # our own stuff here too.
        self._recreate()
        super().clear()

    async def close(self) -> None:
        """Close the Discord connection and the aiohttp session, connector, and resolver."""
        await super().close()

        await self.api_client.close()

        if self.http_session:
            await self.http_session.close()

        if self._connector:
            await self._connector.close()

        if self._resolver:
            await self._resolver.close()

    async def login(self, *args, **kwargs) -> None:
        """Re-create the connector and set up sessions before logging into Discord."""
        self._recreate()
        await super().login(*args, **kwargs)

    def _recreate(self) -> None:
        """Re-create the connector, aiohttp session, and the APIClient."""
        # Use asyncio for DNS resolution instead of threads so threads aren't spammed.
        # Use AF_INET as its socket family to prevent HTTPS related problems both locally
        # and in production.
        self._resolver = aiohttp.AsyncResolver()
        self._connector = aiohttp.TCPConnector(
            resolver=self._resolver,
            family=socket.AF_INET,
        )

        # Client.login() will call HTTPClient.static_login() which will create a session using
        # this connector attribute.
        self.http.connector = self._connector

        self.http_session = aiohttp.ClientSession(connector=self._connector)
        self.api_client.recreate(connector=self._connector)
