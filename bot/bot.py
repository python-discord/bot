import asyncio
import contextlib
from sys import exception

import aiohttp
from discord.errors import Forbidden
from pydis_core import BotBase
from pydis_core.utils.error_handling import handle_forbidden_from_block
from sentry_sdk import new_scope, start_transaction

from bot import constants, exts
from bot.log import get_logger

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

    async def load_extension(self, name: str, *args, **kwargs) -> None:
        """Extend D.py's load_extension function to also record sentry performance stats."""
        with start_transaction(op="cog-load", name=name):
            await super().load_extension(name, *args, **kwargs)

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
        await self.load_extensions(exts)

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Log errors raised in event listeners rather than printing them to stderr."""
        e_val = exception()

        if isinstance(e_val, Forbidden):
            message = args[0] if event == "on_message" else args[1] if event == "on_message_edit" else None

            with contextlib.suppress(Forbidden):
                # Attempt to handle the error. This reraises the error if's not due to a block,
                # in which case the error is suppressed and handled normally. Otherwise, it was
                # handled so return.
                await handle_forbidden_from_block(e_val, message)
                return

        self.stats.incr(f"errors.event.{event}")

        with new_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extra("args", args)
            scope.set_extra("kwargs", kwargs)

            log.exception(f"Unhandled exception in {event}.")
