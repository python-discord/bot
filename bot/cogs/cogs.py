# coding=utf-8
import os

from discord import ClientException, Colour, Embed
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import (
    ADMIN_ROLE, BOT_AVATAR_URL, DEVOPS_ROLE, GITHUB_URL_BOT,
    GREEN_CHEVRON, MODERATOR_ROLE, OWNER_ROLE, RED_CHEVRON,
    WHITE_CHEVRON
)
from bot.decorators import with_role
from bot.utils import paginate


class Cogs:
    """
    Cog management commands
    """

    def __init__(self, bot: AutoShardedBot):
        self.bot = bot
        self.cogs = {}

        # Load up the cog names
        for filename in os.listdir("bot/cogs"):
            if filename.endswith(".py") and "_" not in filename:
                if os.path.isfile(f"bot/cogs/{filename}"):
                    cog = filename[:-3]

                    self.cogs[cog] = f"bot.cogs.{cog}"

        # Allow reverse lookups by reversing the pairs
        self.cogs.update({v: k for k, v in self.cogs.items()})

    @command(name="cogs.load()", aliases=["cogs.load", "load_cog"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def load_command(self, ctx: Context, cog: str):
        """
        Load up an unloaded cog, given the module containing it

        You can specify the cog name for any cogs that are placed directly within `bot.cogs`, or specify the
        entire module directly.
        """

        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=GITHUB_URL_BOT,
            icon_url=BOT_AVATAR_URL
        )

        if cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            embed.description = f"Unknown cog: {cog}"

        if full_cog not in self.bot.extensions:
            try:
                self.bot.load_extension(full_cog)
            except ClientException:
                embed.description = f"Invalid cog: {cog}\n\nCog does not have a `setup()` function"
            except ImportError:
                embed.description = f"Invalid cog: {cog}\n\nCould not find cog module {full_cog}"
            except Exception as e:
                embed.description = f"Failed to load cog: {cog}\n\n```{e}```"
            else:
                embed.description = f"Cog loaded: {cog}"
                embed.colour = Colour.green()
        else:
            embed.description = f"Cog {cog} is already loaded"

        await ctx.send(embed=embed)

    @command(name="cogs.unload()", aliases=["cogs.unload", "unload_cog"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def unload_command(self, ctx: Context, cog: str):
        """
        Unload an already-loaded cog, given the module containing it

        You can specify the cog name for any cogs that are placed directly within `bot.cogs`, or specify the
        entire module directly.
        """

        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=GITHUB_URL_BOT,
            icon_url=BOT_AVATAR_URL
        )

        if cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            embed.description = f"Unknown cog: {cog}"

        if full_cog == "bot.cogs.cogs":
            embed.description = "You may not unload the cog management cog!"
        elif full_cog in self.bot.extensions:
            try:
                self.bot.unload_extension(full_cog)
            except Exception as e:
                embed.description = f"Failed to unload cog: {cog}\n\n```{e}```"
            else:
                embed.description = f"Cog unloaded: {cog}"
                embed.colour = Colour.green()
        else:
            embed.description = f"Cog {cog} is not loaded"

        await ctx.send(embed=embed)

    @command(name="cogs.reload()", aliases=["cogs.reload", "reload_cog"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def reload_command(self, ctx: Context, cog: str):
        """
        Reload an unloaded cog, given the module containing it

        You can specify the cog name for any cogs that are placed directly within `bot.cogs`, or specify the
        entire module directly.

        If you specify "*" as the cog, every cog currently loaded will be unloaded, and then every cog present in the
        bot/cogs directory will be loaded.
        """

        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url=GITHUB_URL_BOT,
            icon_url=BOT_AVATAR_URL
        )

        if cog == "*":
            full_cog = cog
        elif cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            embed.description = f"Unknown cog: {cog}"

        if full_cog == "bot.cogs.cogs":
            embed.description = "You may not reload the cog management cog!"
        elif full_cog == "*":
            all_cogs = [
                f"bot.cogs.{fn[:-3]}" for fn in os.listdir("bot/cogs")
                if os.path.isfile("bot/cogs/{}".format(fn)) and fn.endswith(".py") and "_" not in fn
            ]

            failed_unloads = {}
            failed_loads = {}

            unloaded = 0
            loaded = 0

            for loaded_cog in self.bot.extensions.copy().keys():
                try:
                    self.bot.unload_extension(loaded_cog)
                except Exception as e:
                    failed_unloads[loaded_cog] = str(e)
                else:
                    unloaded += 1

            for unloaded_cog in all_cogs:
                try:
                    self.bot.load_extension(unloaded_cog)
                except Exception as e:
                    failed_loads[unloaded_cog] = str(e)
                else:
                    loaded += 1

            lines = [
                "**All cogs reloaded**",
                f"**Unloaded**: {unloaded} / **Loaded**: {loaded}"
            ]

            if failed_unloads:
                lines.append("\n**Unload failures**")

                for cog, error in failed_unloads:
                    lines.append(f"`{cog}` {WHITE_CHEVRON} `{error}`")

            if failed_loads:
                lines.append("\n**Load failures**")

                for cog, error in failed_loads:
                    lines.append(f"`{cog}` {WHITE_CHEVRON} `{error}`")

            return await paginate(lines, ctx, embed, empty=False)

        elif full_cog in self.bot.extensions:
            try:
                self.bot.unload_extension(full_cog)
                self.bot.load_extension(full_cog)
            except Exception as e:
                embed.description = f"Failed to reload cog: {cog}\n\n```{e}```"
            else:
                embed.description = f"Cog reload: {cog}"
                embed.colour = Colour.green()
        else:
            embed.description = f"Cog {cog} is not loaded"

        await ctx.send(embed=embed)

    @command(name="cogs.get_all()", aliases=["cogs.get_all", "get_cogs", "get_all_cogs", "cogs", "cogs.list"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def list_command(self, ctx: Context):
        """
        Get a list of all cogs, including their loaded status.

        A red double-chevron indicates that the cog is unloaded. Green indicates that the cog is currently loaded.
        """

        embed = Embed()
        lines = []
        cogs = {}

        embed.colour = Colour.blurple()
        embed.set_author(
            name="Python Bot (Cogs)",
            url=GITHUB_URL_BOT,
            icon_url=BOT_AVATAR_URL
        )

        for key, value in self.cogs.items():
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
                chevron = GREEN_CHEVRON
            else:
                chevron = RED_CHEVRON

            lines.append(f"{chevron}  {cog}")

        await paginate(lines, ctx, embed, max_size=300, empty=False)


def setup(bot):
    bot.add_cog(Cogs(bot))
    print("Cog loaded: Cogs")
