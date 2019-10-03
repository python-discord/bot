import logging
import os
from enum import Enum
from pkgutil import iter_modules

from discord import Colour, Embed
from discord.ext.commands import Bot, Cog, Context, group

from bot.constants import Emojis, MODERATION_ROLES, Roles, URLs
from bot.decorators import with_role
from bot.pagination import LinePaginator

log = logging.getLogger(__name__)

KEEP_LOADED = ["bot.cogs.extensions", "bot.cogs.modlog"]


class Action(Enum):
    """Represents an action to perform on an extension."""

    LOAD = (Bot.load_extension,)
    UNLOAD = (Bot.unload_extension,)
    RELOAD = (Bot.unload_extension, Bot.load_extension)


class Extensions(Cog):
    """Extension management commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

        log.info("Initialising extension names...")
        modules = iter_modules(("bot/cogs", "bot.cogs"))
        self.cogs = set(ext for ext in modules if ext.name[-1] != "_")

    @group(name='extensions', aliases=('c', 'ext', 'exts'), invoke_without_command=True)
    @with_role(*MODERATION_ROLES, Roles.core_developer)
    async def extensions_group(self, ctx: Context) -> None:
        """Load, unload, reload, and list active cogs."""
        await ctx.invoke(self.bot.get_command("help"), "extensions")

    @extensions_group.command(name='load', aliases=('l',))
    @with_role(*MODERATION_ROLES, Roles.core_developer)
    async def load_command(self, ctx: Context, cog: str) -> None:
        """
        Load up an unloaded cog, given the module containing it.

        You can specify the cog name for any cogs that are placed directly within `!cogs`, or specify the
        entire module directly.
        """
        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=URLs.github_bot_repo,
            icon_url=URLs.bot_avatar
        )

        if cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            log.warning(f"{ctx.author} requested we load the '{cog}' cog, but that cog doesn't exist.")
            embed.description = f"Unknown cog: {cog}"

        if full_cog:
            if full_cog not in self.bot.extensions:
                try:
                    self.bot.load_extension(full_cog)
                except ImportError:
                    log.exception(f"{ctx.author} requested we load the '{cog}' cog, "
                                  f"but the cog module {full_cog} could not be found!")
                    embed.description = f"Invalid cog: {cog}\n\nCould not find cog module {full_cog}"
                except Exception as e:
                    log.exception(f"{ctx.author} requested we load the '{cog}' cog, "
                                  "but the loading failed")
                    embed.description = f"Failed to load cog: {cog}\n\n{e.__class__.__name__}: {e}"
                else:
                    log.debug(f"{ctx.author} requested we load the '{cog}' cog. Cog loaded!")
                    embed.description = f"Cog loaded: {cog}"
                    embed.colour = Colour.green()
            else:
                log.warning(f"{ctx.author} requested we load the '{cog}' cog, but the cog was already loaded!")
                embed.description = f"Cog {cog} is already loaded"

        await ctx.send(embed=embed)

    @extensions_group.command(name='unload', aliases=('ul',))
    @with_role(*MODERATION_ROLES, Roles.core_developer)
    async def unload_command(self, ctx: Context, cog: str) -> None:
        """
        Unload an already-loaded cog, given the module containing it.

        You can specify the cog name for any cogs that are placed directly within `!cogs`, or specify the
        entire module directly.
        """
        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=URLs.github_bot_repo,
            icon_url=URLs.bot_avatar
        )

        if cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            log.warning(f"{ctx.author} requested we unload the '{cog}' cog, but that cog doesn't exist.")
            embed.description = f"Unknown cog: {cog}"

        if full_cog:
            if full_cog in KEEP_LOADED:
                log.warning(f"{ctx.author} requested we unload `{full_cog}`, that sneaky pete. We said no.")
                embed.description = f"You may not unload `{full_cog}`!"
            elif full_cog in self.bot.extensions:
                try:
                    self.bot.unload_extension(full_cog)
                except Exception as e:
                    log.exception(f"{ctx.author} requested we unload the '{cog}' cog, "
                                  "but the unloading failed")
                    embed.description = f"Failed to unload cog: {cog}\n\n```{e}```"
                else:
                    log.debug(f"{ctx.author} requested we unload the '{cog}' cog. Cog unloaded!")
                    embed.description = f"Cog unloaded: {cog}"
                    embed.colour = Colour.green()
            else:
                log.warning(f"{ctx.author} requested we unload the '{cog}' cog, but the cog wasn't loaded!")
                embed.description = f"Cog {cog} is not loaded"

        await ctx.send(embed=embed)

    @extensions_group.command(name='reload', aliases=('r',))
    @with_role(*MODERATION_ROLES, Roles.core_developer)
    async def reload_command(self, ctx: Context, cog: str) -> None:
        """
        Reload an unloaded cog, given the module containing it.

        You can specify the cog name for any cogs that are placed directly within `!cogs`, or specify the
        entire module directly.

        If you specify "*" as the cog, every cog currently loaded will be unloaded, and then every cog present in the
        bot/cogs directory will be loaded.
        """
        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=URLs.github_bot_repo,
            icon_url=URLs.bot_avatar
        )

        if cog == "*":
            full_cog = cog
        elif cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            log.warning(f"{ctx.author} requested we reload the '{cog}' cog, but that cog doesn't exist.")
            embed.description = f"Unknown cog: {cog}"

        if full_cog:
            if full_cog == "*":
                all_cogs = [
                    f"bot.cogs.{fn[:-3]}" for fn in os.listdir("bot/cogs")
                    if os.path.isfile(f"bot/cogs/{fn}") and fn.endswith(".py") and "_" not in fn
                ]

                failed_unloads = {}
                failed_loads = {}

                unloaded = 0
                loaded = 0

                for loaded_cog in self.bot.extensions.copy().keys():
                    try:
                        self.bot.unload_extension(loaded_cog)
                    except Exception as e:
                        failed_unloads[loaded_cog] = f"{e.__class__.__name__}: {e}"
                    else:
                        unloaded += 1

                for unloaded_cog in all_cogs:
                    try:
                        self.bot.load_extension(unloaded_cog)
                    except Exception as e:
                        failed_loads[unloaded_cog] = f"{e.__class__.__name__}: {e}"
                    else:
                        loaded += 1

                lines = [
                    "**All cogs reloaded**",
                    f"**Unloaded**: {unloaded} / **Loaded**: {loaded}"
                ]

                if failed_unloads:
                    lines.append("\n**Unload failures**")

                    for cog, error in failed_unloads:
                        lines.append(f"{Emojis.status_dnd} **{cog}:** `{error}`")

                if failed_loads:
                    lines.append("\n**Load failures**")

                    for cog, error in failed_loads.items():
                        lines.append(f"{Emojis.status_dnd} **{cog}:** `{error}`")

                log.debug(f"{ctx.author} requested we reload all cogs. Here are the results: \n"
                          f"{lines}")

                await LinePaginator.paginate(lines, ctx, embed, empty=False)
                return

            elif full_cog in self.bot.extensions:
                try:
                    self.bot.unload_extension(full_cog)
                    self.bot.load_extension(full_cog)
                except Exception as e:
                    log.exception(f"{ctx.author} requested we reload the '{cog}' cog, "
                                  "but the unloading failed")
                    embed.description = f"Failed to reload cog: {cog}\n\n```{e}```"
                else:
                    log.debug(f"{ctx.author} requested we reload the '{cog}' cog. Cog reloaded!")
                    embed.description = f"Cog reload: {cog}"
                    embed.colour = Colour.green()
            else:
                log.warning(f"{ctx.author} requested we reload the '{cog}' cog, but the cog wasn't loaded!")
                embed.description = f"Cog {cog} is not loaded"

        await ctx.send(embed=embed)

    @extensions_group.command(name='list', aliases=('all',))
    @with_role(*MODERATION_ROLES, Roles.core_developer)
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


def setup(bot: Bot) -> None:
    """Load the Extensions cog."""
    bot.add_cog(Extensions(bot))
    log.info("Cog loaded: Extensions")
