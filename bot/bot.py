import asyncio
import logging
import socket

import aiohttp
from discord.ext import commands

from bot import api

log = logging.getLogger('bot')


class Bot(commands.Bot):
    """A subclass of `discord.ext.commands.Bot` with an aiohttp session and an API client."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Global aiohttp session for all cogs
        # - Uses asyncio for DNS resolution instead of threads, so we don't spam threads
        # - Uses AF_INET as its socket family to prevent https related problems both locally and in prod.
        self.http_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                resolver=aiohttp.AsyncResolver(),
                family=socket.AF_INET,
            )
        )

        self.api_client = api.APIClient(loop=asyncio.get_event_loop())
        log.addHandler(api.APILoggingHandler(self.api_client))
