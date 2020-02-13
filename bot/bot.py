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
                "If the bot is started, the connector will be overwritten with an internal one"
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
        """Clears the internal state of the bot and sets the HTTPClient connector to None."""
        self.http.connector = None  # Use the default connector.
        super().clear()

    async def close(self) -> None:
        """Close the Discord connection and the aiohttp session, connector, and resolver."""
        await super().close()

        await self.http_session.close()
        await self.api_client.close()

        if self._connector:
            await self._connector.close()

        if self._resolver:
            await self._resolver.close()

    async def start(self, *args, **kwargs) -> None:
        """Set up aiohttp sessions before logging in and connecting to Discord."""
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

        await super().start(*args, **kwargs)
