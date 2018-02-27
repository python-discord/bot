# coding=utf-8
import os

from discord import Embed, Message, ClientException, Colour
from discord.ext.commands import AutoShardedBot, Context, command

from bot.constants import MODERATOR_ROLE, ADMIN_ROLE, DEVOPS_ROLE, OWNER_ROLE
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
        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url="https://github.com/discord-python/bot",
            icon_url="https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png"
        )

        if cog in self.cogs:
            full_cog = self.cogs[cog]
        elif "." in cog:
            full_cog = cog
        else:
            full_cog = None
            embed.description = f"Unknown cog: {cog}"

        if full_cog == "bot.cogs.cogs":
            embed.description = "You may not reload the cog management cog!"
        elif full_cog not in self.bot.extensions:
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
        cog = cog.lower()

        embed = Embed()
        embed.colour = Colour.red()

        embed.set_author(
            name="Python Bot (Cogs)",
            url="https://github.com/discord-python/bot",
            icon_url="https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png"
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
        self.bot.load_extension(cog)
        self.bot.unload_extension(cog)

    @command(name="cogs.get_all()", aliases=["cogs.get_all", "get_cogs", "get_all_cogs"])
    @with_role(MODERATOR_ROLE, ADMIN_ROLE, OWNER_ROLE, DEVOPS_ROLE)
    async def list_command(self, ctx: Context):
        embed = Embed()
        lines = []

        embed.colour = Colour.blurple()
        embed.set_author(
            name="Python Bot (Cogs)",
            url="https://github.com/discord-python/bot",
            icon_url="https://raw.githubusercontent.com/discord-python/branding/master/logos/logo_circle.png"
        )

        for key, value in self.cogs.items():
            if "." not in key:
                continue

            if key in self.bot.extensions:
                lines.append(f"\u00BB **`{value}`** (Loaded)")
            else:
                lines.append(f"\u00BB **`{value}`** (Unloaded)")

        for cog_name in self.bot.extensions.keys():
            if cog_name in self.cogs:
                continue

            lines.append(f"\u00BB **`{cog_name}`** (Loaded)")

        await paginate(sorted(lines), ctx, embed, max_size=300, empty=False)


def setup(bot):
    bot.add_cog(Cogs(bot))
    print("Cog loaded: Cogs")
