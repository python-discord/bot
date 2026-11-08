import asyncio
import contextlib
from sys import exception

import aiohttp
import discord
from discord.errors import Forbidden
from discord.ext import commands
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
    "please use `@{bot_name} {command}`{slash} to use this bot."
)
DEPRECATED_PREFIX_SLASH = " or the slash command `/{command}`"


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
        self._finished_extensions: set[str] = set()
        self._extensions_finished_loading = asyncio.Event()

    async def load_extension(self, name: str, *args, **kwargs) -> None:
        """Extend D.py's load_extension function to also record sentry performance stats."""
        try:
            with start_transaction(op="cog-load", name=name):
                await super().load_extension(name, *args, **kwargs)
        finally:
            self._finished_extensions.add(name)
            if self.all_extensions and self._finished_extensions.issuperset(self.all_extensions):
                self._extensions_finished_loading.set()

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
        # The base class only waits for the extension loading tasks to be created, not for them to finish. Cogs that
        # do work in `cog_load` (e.g. fetching from the site API) only register their commands once that completes.
        await self._extension_loading_task
        await self._extensions_finished_loading.wait()
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

        if isinstance(origin, discord.Message):
            self._skip_whitespace_after_prefix(ctx, origin)

        if isinstance(origin, discord.Message) and not ctx.valid and ctx.prefix is not None:
            rest = origin.content[len(ctx.prefix):].lstrip()
            eval_command = self.get_command("eval")
            if eval_command is not None and rest.startswith("```"):
                ctx.command = eval_command
                ctx.invoked_with = "eval"
                ctx.view = StringView(f"eval {rest}")
                ctx.view.index = len("eval")

        return ctx

    def _skip_whitespace_after_prefix(self, ctx: Context, message: discord.Message) -> None:
        """
        Find the command again if the prefix is followed by extra whitespace, e.g. `@Python  ping`.

        discord.py only allows for the whitespace that is part of the prefix, so a second space leaves no command name.
        """
        if ctx.command is not None or ctx.prefix is None:
            return

        view = StringView(message.content)
        if not view.skip_string(ctx.prefix):
            return

        view.skip_ws()
        invoker = view.get_word()
        ctx.view = view
        ctx.invoked_with = invoker
        ctx.command = self.all_commands.get(invoker)

    def _get_deprecated_prefix_command(self, message: discord.Message) -> commands.Command | None:
        """Return the command that the message invokes using the old prefix, if it is one."""
        prefix = constants.Bot.prefix
        if message.author.bot or not message.content.startswith(prefix):
            return None

        view = StringView(message.content)
        view.skip_string(prefix)
        # Allow a code block directly after the command name, e.g. `!eval```code```.
        name = view.get_word().split("`")[0]
        command = self.get_command(name) if name else None

        # Descend into subcommands, e.g. `!infraction search user`.
        while isinstance(command, commands.Group):
            view.skip_ws()
            subcommand = command.get_command(view.get_word())
            if subcommand is None:
                break
            command = subcommand

        return command

    @staticmethod
    def _get_slash_command_name(command: commands.Command) -> str | None:
        """Return the name used to invoke the command as a slash command, or None if it isn't one."""
        names = []
        current = command
        while current is not None:
            if getattr(current, "app_command", None) is None:
                return None
            names.append(current.name)
            current = current.parent

        # A slash group can't be invoked, so a group callback is exposed as its fallback subcommand.
        if fallback := getattr(command, "fallback", None):
            names.insert(0, fallback)
        return " ".join(reversed(names))

    def _build_deprecated_prefix_notice(self, command: commands.Command) -> str:
        """Build the message telling users to mention the bot or use slash commands instead of the old prefix."""
        slash_name = self._get_slash_command_name(command)
        return DEPRECATED_PREFIX_NOTICE.format(
            prefix=constants.Bot.prefix,
            bot_name=self.user.display_name,
            command=command.qualified_name,
            slash=DEPRECATED_PREFIX_SLASH.format(command=slash_name) if slash_name else "",
        )

    async def process_commands(self, message: discord.Message) -> None:
        """Reply with a deprecation notice for old prefix invocations, otherwise process commands as normal."""
        if (command := self._get_deprecated_prefix_command(message)) is not None:
            with contextlib.suppress(discord.HTTPException):
                await message.reply(self._build_deprecated_prefix_notice(command), mention_author=False)
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
