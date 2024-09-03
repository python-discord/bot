import asyncio
import contextlib
from sys import exc_info
import aiohttp
from discord.errors import Forbidden
from pydis_core import BotBase
from pydis_core.utils.error_handling import handle_forbidden_from_block
from sentry_sdk import push_scope, start_transaction
from bot import constants, exts
from bot.log import get_logger

log = get_logger("bot")

class StartupError(Exception):
    """Exception class for startup errors."""
    def __init__(self, base: Exception):
        super().__init__(str(base))
        self.exception = base

class Bot(BotBase):
    """A subclass of `pydis_core.BotBase` that implements bot-specific functions."""

    async def load_extension(self, name: str, *args, **kwargs) -> None:
        """Extend D.py's load_extension function to also record sentry performance stats."""
        with start_transaction(op="cog-load", name=name):
            await super().load_extension(name, *args, **kwargs)

    async def ping_services(self) -> None:
        """A helper to make sure all the services the bot relies on are available on startup."""
        for attempt in range(1, constants.URLs.connect_max_retries + 1):
            try:
                log.info(f"Attempting site connection: {attempt}/{constants.URLs.connect_max_retries}")
                await self.api_client.get("healthcheck")
                return
            except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError):
                if attempt == constants.URLs.connect_max_retries:
                    raise
                await asyncio.sleep(constants.URLs.connect_cooldown)

    async def setup_hook(self) -> None:
        """Default async initialisation method for discord.py."""
        await super().setup_hook()
        await self.load_extensions(exts)

    async def on_error(self, event: str, *args, **kwargs) -> None:
        """Log errors raised in event listeners rather than printing them to stderr."""
        _, error, _ = exc_info()
        if isinstance(error, Forbidden):
            message = args[0] if event == "on_message" else args[1] if event == "on_message_edit" else None
            with contextlib.suppress(Forbidden):
                await handle_forbidden_from_block(error, message)
                return

        self.stats.incr(f"errors.event.{event}")
        with push_scope() as scope:
            scope.set_tag("event", event)
            scope.set_extras({
                "args": args,
                "kwargs": kwargs
            })
            log.exception(f"Unhandled exception in {event}.")
