import functools
import logging
import typing as t
from enum import Enum
from pkgutil import iter_modules

from discord import Colour, Embed
from discord.ext import commands
from discord.ext.commands import Bot, Context, group

from bot.constants import Emojis, MODERATION_ROLES, Roles, URLs
from bot.pagination import LinePaginator
from bot.utils.checks import with_role_check

log = logging.getLogger(__name__)

UNLOAD_BLACKLIST = {"bot.cogs.extensions", "bot.cogs.modlog"}
EXTENSIONS = frozenset(
    ext.name
    for ext in iter_modules(("bot/cogs",), "bot.cogs.")
    if ext.name[-1] != "_"
)


class Action(Enum):
    """Represents an action to perform on an extension."""

    # Need to be partial otherwise they are considered to be function definitions.
    LOAD = functools.partial(Bot.load_extension)
    UNLOAD = functools.partial(Bot.unload_extension)
    RELOAD = functools.partial(Bot.reload_extension)


class Extension(commands.Converter):
    """
    Fully qualify the name of an extension and ensure it exists.

    The * and ** values bypass this when used with the reload command.
    """

    async def convert(self, ctx: Context, argument: str) -> str:
        """Fully qualify the name of an extension and ensure it exists."""
        # Special values to reload all extensions
        if ctx.command.name == "reload" and (argument == "*" or argument == "**"):
            return argument

        argument = argument.lower()

        if "." not in argument:
            argument = f"bot.cogs.{argument}"

        if argument in EXTENSIONS:
            return argument
        else:
            raise commands.BadArgument(f":x: Could not find the extension `{argument}`.")


class Extensions(commands.Cog):
    """Extension management commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(name="extensions", aliases=("ext", "exts", "c", "cogs"), invoke_without_command=True)
    async def extensions_group(self, ctx: Context) -> None:
        """Load, unload, reload, and list loaded extensions."""
        await ctx.invoke(self.bot.get_command("help"), "extensions")

    @extensions_group.command(name="load", aliases=("l",))
    async def load_command(self, ctx: Context, extension: Extension) -> None:
        """Load an extension given its fully qualified or unqualified name."""
        msg, _ = self.manage(extension, Action.LOAD)
        await ctx.send(msg)

    @extensions_group.command(name="unload", aliases=("ul",))
    async def unload_command(self, ctx: Context, extension: Extension) -> None:
        """Unload a currently loaded extension given its fully qualified or unqualified name."""
        if extension in UNLOAD_BLACKLIST:
            msg = f":x: The extension `{extension}` may not be unloaded."
        else:
            msg, _ = self.manage(extension, Action.UNLOAD)

        await ctx.send(msg)

    @extensions_group.command(name="reload", aliases=("r",))
    async def reload_command(self, ctx: Context, *extensions: Extension) -> None:
        """
        Reload extensions given their fully qualified or unqualified names.

        If an extension fails to be reloaded, it will be rolled-back to the prior working state.

        If `*` is given as the name, all currently loaded extensions will be reloaded.
        If `**` is given as the name, all extensions, including unloaded ones, will be reloaded.
        """
        if len(extensions) > 1:
            msg = await self.batch_reload(*extensions)
        else:
            msg, _ = self.manage(extensions[0], Action.RELOAD)

        await ctx.send(msg)

    @extensions_group.command(name="list", aliases=("all",))
    async def list_command(self, ctx: Context) -> None:
        """
        Get a list of all cogs, including their loaded status.

        Gray indicates that the cog is unloaded. Green indicates that the cog is currently loaded.
        """
        embed = Embed()
        lines = []
        cogs = {}

        embed.colour = Colour.blurple()
        embed.set_author(
            name="Python Bot (Cogs)",
            url=URLs.github_bot_repo,
            icon_url=URLs.bot_avatar
        )

        for key, _value in self.cogs.items():
            if "." not in key:
                continue

            if key in self.bot.extensions:
                cogs[key] = True
            else:
                cogs[key] = False

        for key in self.bot.extensions.keys():
            if key not in self.cogs:
                cogs[key] = True

        for cog, loaded in sorted(cogs.items(), key=lambda x: x[0]):
            if cog in self.cogs:
                cog = self.cogs[cog]

            if loaded:
                status = Emojis.status_online
            else:
                status = Emojis.status_offline

            lines.append(f"{status}  {cog}")

        log.debug(f"{ctx.author} requested a list of all cogs. Returning a paginated list.")
        await LinePaginator.paginate(lines, ctx, embed, max_size=300, empty=False)

    async def batch_reload(self, *extensions: str) -> str:
        """
        Reload given extensions and return a message with the results.

        If `*` is given, all currently loaded extensions will be reloaded along with any other
        specified extensions. If `**` is given, all extensions, including unloaded ones, will be
        reloaded.
        """
        failures = {}

        if "**" in extensions:
            to_reload = EXTENSIONS
        elif "*" in extensions:
            to_reload = set(self.bot.extensions.keys()) | set(extensions)
            to_reload.remove("*")
        elif extensions:
            to_reload = extensions
        else:
            to_reload = self.bot.extensions.copy().keys()

        for extension in to_reload:
            _, error = self.manage(extension, Action.RELOAD)
            if error:
                failures[extension] = error

        emoji = ":x:" if failures else ":ok_hand:"
        msg = f"{emoji} {len(to_reload) - len(failures)} / {len(to_reload)} extensions reloaded."

        if failures:
            failures = '\n'.join(f'{ext}\n    {err}' for ext, err in failures.items())
            msg += f'\nFailures:```{failures}```'

        log.debug(f'Reloaded all extensions.')

        return msg

    def manage(self, ext: str, action: Action) -> t.Tuple[str, t.Optional[str]]:
        """Apply an action to an extension and return the status message and any error message."""
        verb = action.name.lower()
        error_msg = None

        try:
            action.value(self.bot, ext)
        except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
            if action is Action.RELOAD:
                # When reloading, just load the extension if it was not loaded.
                return self.manage(ext, Action.LOAD)

            msg = f":x: Extension `{ext}` is already {verb}ed."
            log.debug(msg[4:])
        except Exception as e:
            if hasattr(e, "original"):
                e = e.original

            log.exception(f"Extension '{ext}' failed to {verb}.")

            error_msg = f"{e.__class__.__name__}: {e}"
            msg = f":x: Failed to {verb} extension `{ext}`:\n```{error_msg}```"
        else:
            msg = f":ok_hand: Extension successfully {verb}ed: `{ext}`."
            log.debug(msg[10:])

        return msg, error_msg

    # This cannot be static (must have a __func__ attribute).
    def cog_check(self, ctx: Context) -> bool:
        """Only allow moderators and core developers to invoke the commands in this cog."""
        return with_role_check(ctx, *MODERATION_ROLES, Roles.core_developer)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Handle BadArgument errors locally to prevent the help command from showing."""
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error))
            error.handled = True


def setup(bot: Bot) -> None:
    """Load the Extensions cog."""
    bot.add_cog(Extensions(bot))
    log.info("Cog loaded: Extensions")
