import asyncio
from sys import exc_info
from traceback import format_exception

import aiohttp
from discord.errors import Forbidden
from pydis_core import BotBase
from pydis_core.utils import scheduling
from sentry_sdk import push_scope

from bot import constants, exts
from bot.log import get_logger
from bot.utils.helpers import try_handle_forbidden

log = get_logger("bot")


class StartupError(Exception):
    """Exception class for startup errors."""

    def __init__(self, base: Exception):
        super().__init__()
        self.exception = base


class Bot(BotBase):
    """A subclass of `pydis_core.BotBase` that implements bot-specific functions."""

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

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

    async def setup_hook(self) -> None:
        """Default async initialisation method for discord.py."""
        await super().setup_hook()

        # This is not awaited to avoid a deadlock with any cogs that have
        # wait_until_guild_available in their cog_load method.
        scheduling.create_task(self.load_extensions(exts))

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Log errors raised in event listeners rather than printing them to stderr."""
        e_type, e_val, e_tb = exc_info()

        if e_type is Forbidden:
            event_to_message_indx = {
                "on_message": 0,
                "on_message_edit": 1
            }
            message = None
            if (message_indx_in_args := event_to_message_indx.get(event)) is not None:
                message = args[message_indx_in_args]

            if await try_handle_forbidden(e_val, message):
                # Error was handled so return
                return

        self.stats.incr(f"errors.event.{event}")

        with push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)

            formatted_exc = "\n".join(format_exception(e_type, e_val, e_tb))
            log.exception(f"Unhandled exception in {event}: {formatted_exc}.")
