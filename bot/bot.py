import asyncio
import contextlib
from sys import exception

import aiohttp
import discord
from discord.errors import Forbidden
from discord.ext.commands import Context
from discord.ext.commands.view import StringView
from pydis_core import BotBase
from pydis_core.utils.error_handling import handle_forbidden_from_block
from sentry_sdk import new_scope, start_transaction

from bot import constants, exts
from bot.log import get_logger

log = get_logger("bot")

DEPRECATED_PREFIX_NOTICE = (
    "Using the `{prefix}` prefix is deprecated due to restrictions placed on us by Discord, "
    "please mention {mention} or use slash commands to use this bot"
)


class BotContext(Context):
    """A context whose `send_help` uses the help cog, as the bot has no discord.py help command."""

    async def send_help(self, *args: object) -> None:
        """Send help for the given command, group, or cog, defaulting to the invoked command."""
        help_cog = self.bot.get_cog("Help")
        entity = args[0] if args else self.command
        if help_cog is None or entity is None:
            return

        formatter = type(help_cog.formatter)()
        formatter.context = self
        await formatter.send_help_for(getattr(entity, "qualified_name", str(entity)))


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
                log.info("Attempting site connection: %s/%s", attempts + 1, constants.URLs.connect_max_retries)
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

    async def _sync_app_commands(self) -> None:
        """Sync application commands to the bot's guild only, clearing any previously registered global commands."""
        await self._extension_loading_task
        guild = discord.Object(self.guild_id)
        self.tree.copy_global_to(guild=guild)
        self.tree.clear_commands(guild=None)
        await self.tree.sync(guild=guild)
        # The global tree is now empty, so this removes any stale global commands.
        await self.tree.sync()

    async def get_context(
        self,
        origin: discord.Message | discord.Interaction,
        /,
        *,
        cls: type[Context] = BotContext,
    ) -> Context:
        """
        Get the invocation context, treating a mention followed directly by a code block as an eval command.

        For example `@Python ```py\nprint("hello")\n``` ` is run as if it were `@Python eval ```py ...``` `.
        """
        ctx = await super().get_context(origin, cls=cls)

        if isinstance(origin, discord.Message) and not ctx.valid and ctx.prefix is not None:
            rest = origin.content[len(ctx.prefix):].lstrip()
            eval_command = self.get_command("eval")
            if eval_command is not None and rest.startswith("```"):
                ctx.command = eval_command
                ctx.invoked_with = "eval"
                ctx.view = StringView(f"eval {rest}")
                ctx.view.index = len("eval")

        return ctx

    def _is_deprecated_prefix_invocation(self, message: discord.Message) -> bool:
        """Return whether the message invokes an existing command using the old prefix."""
        prefix = constants.Bot.prefix
        if message.author.bot or not message.content.startswith(prefix):
            return False

        view = StringView(message.content)
        view.skip_string(prefix)
        # Allow a code block directly after the command name, e.g. `!eval```code```.
        name = view.get_word().split("`")[0]
        return bool(name) and self.get_command(name) is not None

    async def process_commands(self, message: discord.Message) -> None:
        """Reply with a deprecation notice for old prefix invocations, otherwise process commands as normal."""
        if self._is_deprecated_prefix_invocation(message):
            notice = DEPRECATED_PREFIX_NOTICE.format(prefix=constants.Bot.prefix, mention=self.user.mention)
            with contextlib.suppress(discord.HTTPException):
                await message.reply(notice, mention_author=False)
            return

        await super().process_commands(message)

    async def on_error(self, event: str, /, *args, **kwargs) -> None:
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

            log.exception("Unhandled exception in %s.", event)
