import asyncio
import contextlib
import contextvars
import types
from sys import exception

import aiohttp
from discord.errors import Forbidden
from discord.ext import commands
from pydis_core import BotBase
from pydis_core.utils import scheduling
from pydis_core.utils._extensions import walk_extensions
from pydis_core.utils.error_handling import handle_forbidden_from_block
from sentry_sdk import new_scope, start_transaction

from bot import constants, exts
from bot.log import get_logger

log = get_logger("bot")

_current_extension: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_extension", default=None
)


class StartupError(Exception):
    """Exception class for startup errors."""

    def __init__(self, base: Exception):
        super().__init__()
        self.exception = base


class Bot(BotBase):
    """A subclass of `pydis_core.BotBase` that implements bot-specific functions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Track extension load failures and tasks so we can report them after all attempts have completed
        self.extension_load_failures: dict[str, BaseException] = {}
        self._extension_load_tasks: dict[str, asyncio.Task] = {}


    async def add_cog(self, cog: commands.Cog) -> None:
        """
        Add a cog to the bot with exception handling.

        Override of `BotBase.add_cog` to capture and log any exceptions raised during cog loading,
        including the extension name if available.
        """
        extension = _current_extension.get()

        try:
            await super().add_cog(cog)
            log.info(f"Cog successfully loaded: {cog.qualified_name}")

        except BaseException as e:
            key = extension or f"(unknown)::{cog.qualified_name}"
            self.extension_load_failures[key] = e

            log.exception(
                "FAILED during add_cog (extension=%s, cog=%s)",
                extension,
                cog.qualified_name,
            )
            # Propagate error
            raise

    async def _load_extensions(self, module: types.ModuleType) -> None:

        log.info("Waiting for guild %d to be available before loading extensions.", self.guild_id)
        await self.wait_until_guild_available()

        self.all_extensions = walk_extensions(module)

        async def _load_one(extension: str) -> None:
            token = _current_extension.set(extension)

            try:
                log.info(f"Loading extension: {extension}")
                await self.load_extension(extension)
                log.info(f"Loaded extension: {extension}")

            except BaseException as e:
                self.extension_load_failures[extension] = e
                log.exception("FAILED to load extension: %s", extension)
                raise

            finally:
                _current_extension.reset(token)

        for extension in self.all_extensions:
            task = scheduling.create_task(_load_one(extension))
            self._extension_load_tasks[extension] = task

        # Wait for all load tasks to complete so we can report any failures together
        await asyncio.gather(*self._extension_load_tasks.values(), return_exceptions=True)

        if self.extension_load_failures:
            log.warning(
                "Extension/cog load failures (%d): %s",
                len(self.extension_load_failures),
                ", ".join(sorted(self.extension_load_failures.keys())),
            )

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
